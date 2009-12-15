# -*- Mode: Python; test-case-name: flumotion.test.test_http -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.GPL" in the source distribution for more information.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import time
import gst

from twisted.internet import defer
from twisted.web import server, resource

try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

from flumotion.configure import configure
from flumotion.common import log


__version__ = "$Rev: $"

HTTP_NAME = 'FlumotionHTTPFragmentedServer'
HTTP_VERSION = configure.version
HTTP_SERVER = '%s/%s' % (HTTP_NAME, HTTP_VERSION)

M3U8_CONTENT_TYPE = 'application/vnd.apple.mpegurl'
PLAYLIST_EXTENSION = '.m3u8'

### the Twisted resource that handles the base URL

class HTTPLiveStreamingResource(resource.Resource, log.Loggable):

    # IResource interface variable; True means it will not chain requests
    # further down the path to other resource providers through
    # getChildWithDefault
    isLeaf = True

    def __init__(self, streamer, httpauth):
        """
        @param streamer: L{HTTPFragmentStreamer}
        """
        self.streamer = streamer
        self.httpauth = httpauth
        self.setMountPoint(streamer.mountPoint)
        self.ring = streamer.getRing()

        self.maxclients = self.getMaxAllowedClients(-1)
        self.maxbandwidth = -1 # not limited by default

        # If set, a URL to redirect a user to when the limits above are reached
        self._redirectOnFull = None

        self.bytesSent = 0
        self.bytesReceived = 0
        self.logFilters = None

        socket = 'flumotion.component.plugs.request.RequestLoggerPlug'
        self.loggers = streamer.plugs.get(socket, [])

        socket = \
            'flumotion.component.plugs.requestmodifier.RequestModifierPlug'
        self.modifiers = streamer.plugs.get(socket, [])

        resource.Resource.__init__(self)

    def setMountPoint(self, mountPoint):
        if not mountPoint.startswith('/'):
            mountPoint = '/' + mountPoint
        if not mountPoint.endswith('/'):
            mountPoint = mountPoint + '/'
        self.mountPoint = mountPoint
    
    def setRoot(self, path):
        self.putChild(path, self)

    def setLogFilter(self, logfilter):
        self.logfilter = logfilter

    def rotateLogs(self):
        """
        Close the logfile, then reopen using the previous logfilename
        """
        for logger in self.loggers:
            self.debug('rotating logger %r' % logger)
            logger.rotate()
    
    def logWrite(self, fd, ip, request, stats):

        headers = request.getAllHeaders()

        if stats:
            bytes_sent = stats[0]
            time_connected = int(stats[3] / gst.SECOND)
        else:
            bytes_sent = -1
            time_connected = -1

        args = {'ip': ip,
                'time': time.gmtime(),
                'method': request.method,
                'uri': request.uri,
                'username': '-', # FIXME: put the httpauth name
                'get-parameters': request.args,
                'clientproto': request.clientproto,
                'response': request.code,
                'bytes-sent': bytes_sent,
                'referer': headers.get('referer', None),
                'user-agent': headers.get('user-agent', None),
                'time-connected': time_connected}

        l = []
        for logger in self.loggers:
            l.append(defer.maybeDeferred(
                logger.event, 'http_session_completed', args))

        return defer.DeferredList(l)

    def setUserLimit(self, limit):
        self.info('setting maxclients to %d' % limit)
        self.maxclients = self.getMaxAllowedClients(limit)
        # Log what we actually managed to set it to.
        self.info('set maxclients to %d' % self.maxclients)

    def setBandwidthLimit(self, limit):
        self.maxbandwidth = limit
        self.info("set maxbandwidth to %d", self.maxbandwidth)

    def setRedirectionOnLimits(self, url):
        self._redirectOnFull = url

    def getMaxAllowedClients(self, maxclients):
        """
        maximum number of allowed clients based on soft limit for number of
        open file descriptors and fd reservation. Increases soft limit to
        hard limit if possible.
        """
        #FIXME
        pass

    def _isReady(self):
        return self.streamer.isReady()
    
    def _renderNotFoundResponse(self, request):
        self._writeHeaders(request,'text/html')
        request.setResponseCode(404)
        request.write('Resource Not Found or Access Denied')
        request.finish()
        return ''

    def _handleNotReady(self, request):
        self.debug('Not sending data, it\'s not ready')
        # FIXME: Close connection or call back later? 
        return server.NOT_DONE_YET

    def _renderKey(self, res, request):
        self._writeHeaders(request, 'binary/octect-stream')
        request.setHeader('Pragma', 'no-cache')

        if request.method == 'GET':
            key = self.ring.getEncryptionKey(request.args['key'][0])
            self.bytesReceived += len(key) 
            request.write(key)
            self.bytesSent += len(key)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderPlaylist(self, res, request, resource):
        self.debug('_render(): asked for playlist %s' % resource)
        self._writeHeaders(request, M3U8_CONTENT_TYPE)
        if request.method == 'GET':
            playlist = self.ring.renderPlaylist(resource)
            self.bytesReceived += len(playlist) 
            request.write(playlist)
            self.bytesSent += len(playlist)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderFragment(self, res, request, resource):
        self.debug('_render(): asked for fragment %s' % resource)
        self._writeHeaders(request, 'video/mpeg')
        if request.method == 'GET':
            data = self.ring.getFragment(resource)
            self.bytesReceived += len(data)
            request.write(data)
            self.bytesSent += len(data)
            request.finish()
        if request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _writeHeaders(self, request, content):  
        """
        Write out the HTTP headers for the incoming HTTP request.
        """
        
        request.setResponseCode(200)
        request.setHeader('Server', HTTP_SERVER)
        request.setHeader('Date', http.datetimeToString())
        request.setHeader('Connection', 'close')
        request.setHeader('Cache-Control', 'cache')
        request.setHeader('Cache-Control', 'private')
        request.setHeader('Content-type', content)

        # Call request modifiers
        for modifier in self.modifiers:
            modifier.modify(request)

        # Mimic Twisted as close as possible
        headers = []
        for name, value in request.headers.items():
            headers.append('%s: %s\r\n' % (name.capitalize(), value))
        for cookie in request.cookies:
            headers.append('%s: %s\r\n' % ("Set-Cookie", cookie))


    def _render(self, request):
        self.info('Incoming client connection from %s' % (
            request.getClientIP()))
        self.debug('_render(): request %s' % (request))

        if not self._isReady():
            return self._handleNotReady(request)
        
        # A GET request will be like mountpoint+resource:
        # 'GET /iphone/fragment-0.ts' or 'GET /fragment-0.ts'
        # The mountpoint is surrounded by '/' in setMountPoint()
        # so we can safely look for the mountpoint and extract the
        # resource name
        if not request.path.startswith(self.mountPoint):
            return self._renderNotFoundResponse(request)
        resource = request.path.replace(self.mountPoint,'',1)

        self.debug('_render(): asked for (possible) authentication')
        d = self.httpauth.startAuthentication(request)
              
        # Playlists
        if resource.endswith(PLAYLIST_EXTENSION):
            d.addCallback(self._renderPlaylist, request, resource)
        # Keys
        elif resource == 'key' and 'key' in request.args:
            d.addCallback(self._renderKey, request)
        # Fragments
        else:
            d.addCallback(self._renderFragment, request, resource)

        d.addErrback(lambda x, request: self._renderNotFoundResponse(request), request)
        return server.NOT_DONE_YET

    def getBytesSent(self):
        return self.bytesSent

    def getBytesReceived(self):
        return self.bytesReceived

    render_GET = _render
    render_HEAD = _render
