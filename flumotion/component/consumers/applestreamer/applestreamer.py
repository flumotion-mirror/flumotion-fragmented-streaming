# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2009,2010 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.
# flumotion-fragmented-streaming - Flumotion Advanced fragmented streaming

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import time

import gst
import gobject

from twisted.cred import credentials
from twisted.internet import reactor, error, defer
from twisted.web import server
from zope.interface import implements

from flumotion.common import interfaces, netutils, errors, messages
from flumotion.common.i18n import N_, gettexter
from flumotion.component import feedcomponent
from flumotion.component.base import http
from flumotion.component.component import moods
from flumotion.component.consumers.httpstreamer.httpstreamer import\
        HTTPMedium, Stats as Statistics
from flumotion.component.consumers.applestreamer import mpegtssegmenter
from flumotion.component.consumers.applestreamer.hlsring import HLSRing
from flumotion.component.consumers.applestreamer.resources import \
        HTTPLiveStreamingResource
from flumotion.component.misc.porter import porterclient
from flumotion.twisted import fdserver

__all__ = ['HTTPMedium', 'AppleHTTPLiveStreamer']
__version__ = ""
T_ = gettexter()
STATS_POLL_INTERVAL = 10
UI_UPDATE_THROTTLE_PERIOD = 2.0


class Stats(Statistics):

    # FIXME: Clean up httpstreamer.Stats and make a generic class

    def __init__(self, sink):
        Statistics.__init__(self, sink)
        self.sink = sink

    def getBytesSent(self):
        return self.sink.getBytesSent()

    def getBytesReceived(self):
        return self.sink.getBytesReceived()


class LoggableRequest(server.Request):

    def __init__(self, channel, queued):
        server.Request.__init__(self, channel, queued)
        now = time.time()
        self._startTime = now
        self._completionTime = now
        self._bytesWritten = 0L

    def write(self, data):
        server.Request.write(self, data)
        size = len(data)
        self._bytesWritten += size

    def requestCompleted(self, fd):
        server.Request.requestCompleted(self, fd)
        if self._completionTime is None:
            self._completionTime = time.time()

    def getDuration(self):
        return (self._completionTime or time.time()) - self._startTime

    def getBytesSent(self):
        return self._bytesWritten


class Site(server.Site):
    requestFactory = LoggableRequest

    def __init__(self, resource):
        server.Site.__init__(self, resource)


class AppleHTTPLiveStreamer(feedcomponent.ParseLaunchComponent, Stats):
    implements(interfaces.IStreamingComponent)

    logCategory = 'apple-streamer'

    componentMediumClass = HTTPMedium

    DEFAULT_FRAGMENT_PREFIX = 'fragment'
    DEFAULT_MAIN_PLAYLIST = 'main.m3u8'
    DEFAULT_STREAM_PLAYLIST = 'stream.m3u8'
    DEFAULT_KEYFRAMES_PER_SEGMENT = 10
    DEFAULT_MIN_WINDOW = 2
    DEFAULT_MAX_WINDOW = 5
    DEFAULT_PORT = 8080

    def init(self):
        reactor.debug = True
        self.debug("Apple HTTP live streamer initialising")

        self.mountPoint = None
        self.description = None
        self.hlsring = None
        self.resource = None

        # Used if we've slaved to a porter.
        self._pbclient = None
        self._porterUsername = None
        self._porterPassword = None
        self._porterPath = None

        self.type = None
        # Or if we're a master, we open our own port here. Also used for URLs
        # in the porter case.
        self.port = None
        # We listen on this interface, if set.
        self.iface = None
        self._tport = None

        self._updateCallLaterId = None
        self._lastUpdate = 0
        self._updateUI_DC = None

        self.ready = False
        self._updateCallLaterId = None
        self._lastUpdate = 0
        self._updateUI_DC = None

        self._lastBufferOffset = None

        for i in ('stream-mime', 'stream-uptime', 'stream-current-bitrate',
                  'stream-bitrate', 'stream-totalbytes', 'clients-current',
                  'clients-max', 'clients-peak', 'clients-peak-time',
                  'clients-average', 'consumption-bitrate',
                  'consumption-bitrate-current',
                  'consumption-totalbytes', 'stream-bitrate-raw',
                  'stream-totalbytes-raw', 'consumption-bitrate-raw',
                  'consumption-totalbytes-raw', 'stream-url'):
            self.uiState.addKey(i, None)

    def getDescription(self):
        return self.description

    def getRing(self):
        return self.hlsring

    def isReady(self):
        return self.ready

    def check_properties(self, props, addMessage):
        if props.get('type', 'master') == 'slave':
            for k in 'socket-path', 'username', 'password':
                if not 'porter-' + k in props:
                    raise errors.ConfigError("slave mode, missing required"
                                             " property 'porter-%s'" % k)

    def __repr__(self):
        return '<AppleHTTPLiveStreamer (%s)>' % self.name

    def getMaxClients(self):
        return self.resource.maxclients

    def get_mime(self):
        return 'video/mpegts'

    def getUrl(self):
        return "http://%s:%d%s" % (self.hostname, self.port, self.mountPoint)

    def getStreamData(self):
        socket = 'flumotion.component.plugs.streamdata.StreamDataProviderPlug'
        if self.plugs[socket]:
            plug = self.plugs[socket][-1]
            return plug.getStreamData()
        else:
            return {'protocol': 'HTTP',
                    'description': self.description,
                    'url': self.getUrl()}

    def getLoadData(self):
        """Return a tuple (deltaadded, deltaremoved, bytes_transferred,
        current_clients, current_load) of our current bandwidth and
        user values.
        The deltas are estimates of how much bitrate is added, removed
        due to client connections, disconnections, per second.
        """
        # We calculate the estimated clients added/removed per second, then
        # multiply by the stream bitrate
        deltaadded, deltaremoved = self.getLoadDeltas()

        bytes_received = self.getBytesReceived()
        uptime = self.getUptime()
        bitrate = bytes_received * 8 / uptime

        bytes_sent = self.getBytesSent()
        clients_connected = self.getClients()
        current_load = bitrate * clients_connected

        return (deltaadded * bitrate, deltaremoved * bitrate, bytes_sent,
            clients_connected, current_load)

    def update_ui_state(self):
        """Update the uiState object.
        Such updates (through this function) are throttled to a maximum rate,
        to avoid saturating admin clients with traffic when many clients are
        connecting/disconnecting.
        """

        def setIfChanged(k, v):
            if self.uiState.get(k) != v:
                self.uiState.set(k, v)

        def update_ui_state_later():
            self._updateUI_Dself.mediumC = None
            self.update_ui_state()

        now = time.time()

        # If we haven't updated too recently, do it immediately.
        if now - self._lastUpdate >= UI_UPDATE_THROTTLE_PERIOD:
            if self._updateUI_DC:
                self._updateUI_DC.cancel()
                self._updateUI_DC = None

            self._lastUpdate = now
            # fixme: have updateState just update what changed itself
            # without the hack above
            self.updateState(setIfChanged)
        elif not self._updateUI_DC:
            # Otherwise, schedule doing this in a few seconds (unless an update
            # was already scheduled)
            self._updateUI_DC = reactor.callLater(UI_UPDATE_THROTTLE_PERIOD,
                                                  update_ui_state_later)

    def updatePorterDetails(self, path, username, password):
        """Provide a new set of porter login information, for when we're
        in slave mode and the porter changes.
        If we're currently connected, this won't disconnect - it'll just change
        the information so that next time we try and connect we'll use the
        new ones
        """
        if self.type == 'slave':
            self._porterUsername = username
            self._porterPassword = password

            creds = credentials.UsernamePassword(self._porterUsername,
                self._porterPassword)

            self._pbclient.startLogin(creds, self._pbclient.medium)

            # If we've changed paths, we must do some extra work.
            if path != self._porterPath:
                self.debug("Changing porter login to use \"%s\"", path)
                self._porterPath = path
                self._pbclient.stopTrying() # Stop trying to connect with the
                                            # old connector.
                self._pbclient.resetDelay()
                reactor.connectWith(
                    fdserver.FDConnector, self._porterPath,
                    self._pbclient, 10, checkPID=False)
        else:
            raise errors.WrongStateError(
                "Can't specify porter details in master mode")

    def softRestart(self):
        """Stops serving fragments, resets the playlist and starts
        waiting for new segments to become happy again
        """
        self.info("Soft restart, resetting playlist and waiting to fill "
                  "the initial fragments window")
        self.ready = False
        self._segmentsCount = 0
        self._lastBufferOffset = None
        self.hlsring.reset()

    def get_pipeline_string(self, properties):
        gobject.type_register(mpegtssegmenter.MpegTSSegmenter)
        gst.element_register(mpegtssegmenter.MpegTSSegmenter,
                "flumpegtssegmenter", gst.RANK_MARGINAL)
        return " flumpegtssegmenter name=segmenter ! appsink name=appsink"

    def configure_pipeline(self, pipeline, props):
        self.keyframesFramesPerSegment = props.get('keyframes-per-fragment',
                self.DEFAULT_KEYFRAMES_PER_SEGMENT)
        element = pipeline.get_by_name('segmenter')
        element.set_property('keyframes-per-segment',
                self.keyframesFramesPerSegment)

        appsink = pipeline.get_by_name('appsink')
        appsink.set_property('emit-signals', True)
        appsink.connect("new-preroll", self.new_preroll)
        appsink.connect("new-buffer", self.new_buffer)
        appsink.connect("eos", self.eos)

        self._segmentsCount = 0

        mountPoint = props.get('mount-point', '')

        hostname = props.get('hostname', None)
        self.iface = hostname
        if not hostname:
            # Don't call this function unless we need to.
            # It's much preferable to just configure it
            hostname = netutils.guess_public_hostname()

        port = props.get('port', self.DEFAULT_PORT)

        self.description = props.get('description', None)
        if self.description is None:
            self.description = "Flumotion Stream"

        self.hlsring = HLSRing(
            '%s:%s%s' % (hostname, port, mountPoint),
            props.get('main-playlist', self.DEFAULT_MAIN_PLAYLIST),
            props.get('stream-playlist', self.DEFAULT_STREAM_PLAYLIST),
            self.description,
            props.get('fragment-prefix', self.DEFAULT_FRAGMENT_PREFIX),
            props.get('max-window', self.DEFAULT_MAX_WINDOW),
            props.get('key-rotation', 0),
            props.get('keys-uri', None))

        self.mountPoint = mountPoint

        # FIXME: tie these together more nicely
        self.httpauth = http.HTTPAuthentication(self)
        self.resource = HTTPLiveStreamingResource(self, self.httpauth)

        Stats.__init__(self, self.resource)
        self._updateCallLaterId = reactor.callLater(10, self._updateStats)

        # FIXME: Stats needs some love: init funtion reset all these values
        # and the assignment needs to be done after initializing Stats
        self.hostname = hostname
        self.mountPoint = mountPoint
        self.port = port

        self._minWindow = props.get('hls-min-window',
                self.DEFAULT_MIN_WINDOW)

        if 'client-limit' in props:
            limit = int(props['client-limit'])
            self.resource.setUserLimit(limit)
            if limit != self.resource.maxclients:
                m = messages.Info(T_(N_(
                    "Your system configuration does not allow the maximum "
                    "client limit to be set to %d clients."),
                    limit))
                m.description = T_(N_(
                    "Learn how to increase the maximum number of clients."))
                m.section = 'chapter-optimization'
                m.anchor = 'section-configuration-system-fd'
                self.addMessage(m)

        if 'bandwidth-limit' in props:
            limit = int(props['bandwidth-limit'])
            if limit < 1000:
                # The wizard used to set this as being in Mbps, oops.
                self.debug("Bandwidth limit set to unreasonably low %d bps, "
                    "assuming this is meant to be Mbps", limit)
                limit *= 1000000
            self.resource.setBandwidthLimit(limit)

        if 'redirect-on-overflow' in props:
            self.resource.setRedirectionOnLimits(
                props['redirect-on-overflow'])

        if 'bouncer' in props:
            self.httpauth.setBouncerName(props['bouncer'])

        if 'issuer-class' in props:
            self.httpauth.setIssuerClass(props['issuer-class'])

        if 'duration' in props:
            self.httpauth.setDefaultDuration(
                float(props['duration']))

        if 'domain' in props:
            self.httpauth.setDomain(props['domain'])

        if 'avatarId' in self.config:
            self.httpauth.setRequesterId(self.config['avatarId'])

        if 'ip-filter' in props:
            logFilter = http.LogFilter()
            for f in props['ip-filter']:
                logFilter.addIPFilter(f)
            self.resource.setLogFilter(logFilter)

        self.type = props.get('type', 'master')
        if self.type == 'slave':
            # already checked for these in do_check
            self._porterPath = props['porter-socket-path']
            self._porterUsername = props['porter-username']
            self._porterPassword = props['porter-password']

    def do_setup(self):
        root = self.resource

        if self.type == 'slave':
            # Streamer is slaved to a porter.

            # We have two things we want to do in parallel:
            #  - ParseLaunchComponent.do_start()
            #  - log in to the porter, then register our mountpoint with
            #    the porter.
            # So, we return a DeferredList with a deferred for each of
            # these tasks. The second one's a bit tricky: we pass a dummy
            # deferred to our PorterClientFactory that gets fired once
            # we've done all of the tasks the first time (it's an
            # automatically-reconnecting client factory, and we only fire
            # this deferred the first time)

            self._porterDeferred = d = defer.Deferred()
            self._pbclient = porterclient.HTTPPorterClientFactory(
                Site(resource=root), [], d, prefixes=[self.mountPoint])

            creds = credentials.UsernamePassword(self._porterUsername,
                self._porterPassword)
            self._pbclient.startLogin(creds, self._pbclient.medium)

            self.debug("Starting porter login at \"%s\"", self._porterPath)
            # This will eventually cause d to fire
            reactor.connectWith(
                fdserver.FDConnector, self._porterPath,
                self._pbclient, 10, checkPID=False)
        else:
            # Streamer is standalone.
            try:
                self.debug('Listening on %d' % self.port)
                iface = self.iface or ""
                self._tport = reactor.listenTCP(
                    self.port, Site(resource=root),
                    interface=iface)
            except error.CannotListenError:
                t = 'Port %d is not available.' % self.port
                self.warning(t)
                m = messages.Error(T_(N_(
                    "Network error: TCP port %d is not available."),
                    self.port))
                self.addMessage(m)
                self.setMood(moods.sad)
                return defer.fail(errors.ComponentSetupHandledError(t))

    def do_pipeline_playing(self):
        # The component must stay 'waiking' until it receives at least
        # the number of segments defined by the min-window property
        pass

    def do_stop(self):
        if self._updateCallLaterId:
            self._updateCallLaterId.cancel()
            self._updateCallLaterId = None

        if self.httpauth:
            self.httpauth.stopKeepAlive()

        if self._tport:
            self._tport.stopListening()

        l = []

        if self.type == 'slave' and self._pbclient:
            l.append(self._pbclient.deregisterPrefix(self.mountPoint))
        return defer.DeferredList(l)

    def _processBuffer(self, buffer):
        currOffset = buffer.offset
        # When a streamer is plugged the buffer offset is not known yet
        if self._lastBufferOffset is not None:
            nextOffset = (self._lastBufferOffset +
                    self.keyframesFramesPerSegment)
            # Check for fragments discontinuities.
            if currOffset != nextOffset:
                self.warning("Fragment discontinuity. Expected buffer offset "
                            "was: %s, incomming buffer offset is: %s",
                            nextOffset, currOffset)
                if currOffset < nextOffset:
                    # Usually means that the muxer was restarted. The counters
                    # and playlist needs a reset.
                    self.softRestart()

        self._lastBufferOffset = currOffset
        self._segmentsCount = self._segmentsCount + 1
        self.log("New fragment, duration=%s offset=%s" %
                (gst.TIME_ARGS(buffer.duration), currOffset))

        # Wait hls-min-window fragments to set the component 'happy'
        if self._segmentsCount == self._minWindow:
            self.log("%d fragments received. Changing mood to 'happy'" %
                    self._segmentsCount)
            self.setMood(moods.happy)
            self.ready = True
        self.hlsring.addFragment(buffer.data,
                currOffset/self.keyframesFramesPerSegment,
                round(float(buffer.duration) / float(gst.SECOND)))
        self.resource.bytesReceived += len(buffer.data)

    ### START OF THREAD-AWARE CODE (called from non-reactor threads)

    def new_preroll(self, appsink):
        self.debug("new preroll buffer")
        buffer = appsink.emit('pull-preroll')

    def new_buffer(self, appsink):
        self.debug("new buffer")
        buffer = appsink.emit('pull-buffer')
        reactor.callFromThread(self._processBuffer, buffer)

    def eos(self, appsink):
        #FIXME: How do we handle this for live?
        self.debug('received eos')

    ### END OF THREAD-AWARE CODE
