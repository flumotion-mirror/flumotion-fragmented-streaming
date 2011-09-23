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

import base64
import pprint
import string
from cStringIO import StringIO

import gst
from mp4seek import atoms, iso

from twisted.internet import reactor
from flumotion.common.i18n import N_, gettexter
from flumotion.common import messages
from flumotion.component.component import moods

from flumotion.extern.log import log
from flumotion.component.base import http
from flumotion.component.common.streamer.fragmentedresource import\
    FragmentNotFound
from flumotion.component.common.streamer.fragmentedstreamer import\
    FragmentedStreamer
from flumotion.component.consumers.smoothstreamer.resources import\
    SmoothStreamingResource
from flumotion.component.consumers.smoothstreamer import\
    avcc, waveformatex

__all__ = ['SmoothHTTPLiveStreamer']
__version__ = ""
T_ = gettexter()

DEFAULT_DVR_WINDOW = 20


class SmoothHTTPLiveStreamer(FragmentedStreamer):

    logCategory = 'smooth-streamer'

    def init(self):
        self.store = FragmentStore()
        self.debug("Smooth HTTP live streamer initializing")

    def getUrl(self):
        slash = ""
        if not self.mountPoint.startswith("/"):
            slash = "/"
        return "http://%s:%d%s%sManifest" % (self.hostname, self.port,
                                             slash, self.mountPoint)

    def __repr__(self):
        return '<SmoothHTTPLiveStreamer (%s)>' % self.name

    def get_mime(self):
        return 'text/xml'

    def configure_auth_and_resource(self):
        self.httpauth = http.HTTPAuthentication(self)
        self.resource = SmoothStreamingResource(self, self.store,
                self.httpauth, self.secret_key, self.session_timeout)

    def configure_pipeline(self, pipeline, props):
        FragmentedStreamer.configure_pipeline(self, pipeline, props)
        self.resource.setMountPoint(self.mountPoint)
        self.store.setDVRWindowLength(props.get('dvr-window',
                                                DEFAULT_DVR_WINDOW))

    def get_pipeline_string(self, properties):
        # Similar to the MultiInpuParseLaunch component but whithout the need
        # of using queues
        eaters = self.config.get('eater', {})
        sources = self.config.get('source', [])
        if eaters == {} and sources != []:
            # for upgrade without manager restart
            feeds = []
            for feed in sources:
                if not ':' in feed:
                    feed = '%s:default' % feed
                feeds.append(feed)
            eaters = {'default': [(x, 'default') for x in feeds]}

        pipeline = ''
        for e in eaters:
            for feed, alias in eaters[e]:
                pipeline += ' @ eater:%s @ ! appsink '\
                            'name=sink_%s emit-signals=true sync=false '\
                            % (alias, alias)
        return pipeline

    def _connect_sink_signals(self):
        eaters = self.config.get('eater', {})
        for e in eaters:
            for feed, alias in eaters[e]:
                sink = self.pipeline.get_by_name('sink_%s' % alias)
                sink.get_pad("sink").add_buffer_probe(self._sink_pad_probe,
                                                      None)
                sink.connect('eos', self._eos)
                sink.connect("new-buffer", self._new_buffer)

    def _process_buffer(self, sink, buffer):
        sink_name = sink.get_name()
        currOffset = buffer.offset
        self._lastBufferOffset = currOffset
        self._fragmentsCount = self._fragmentsCount + 1
        f = StringIO(buffer.data)
        al = list(atoms.read_atoms(f))
        ad = atoms.atoms_dict(al)
        if (buffer.flag_is_set(gst.BUFFER_FLAG_IN_CAPS)):
            try:
                self.store.addMoov(sink_name, ad)
            except Exception, e:
                m = messages.Error(T_(N_(
                    "First buffer cannot be parsed as a moov. "\
                    "The required mp4seek version is 1.0-6")))
                sink.set_state(gst.STATE_NULL)
                self.addMessage(m)
                self.error("First buffer cannot be parsed as a moov: %r" % e)
                return
        elif iso.select_atoms(ad, ('moof', 0, 1))[0]:
            fragName = self.store.addFragment(sink_name, ad, al,
                                              buffer.timestamp,
                                              buffer.duration)
            if fragName is None:
                return
            self.info('Added fragment "%s", duration=%s',
                      fragName, gst.TIME_ARGS(buffer.duration))
            if not self._ready and self.store.prerolled():
                self.info("All streams prerolled. Changing mood to 'happy'")
                self.setMood(moods.happy)
                self._ready = True

    ### START OF THREAD-AWARE CODE (called from non-reactor threads)

    def _new_buffer(self, appsink):
        self.log("appsink created a new fragment")
        buf = appsink.emit('pull-buffer')
        reactor.callFromThread(self._process_buffer, appsink, buf)

    ### END OF THREAD-AWARE CODE


class AttributesMixin:

    def getAttributes(self):
        return self.__dict__


class Quality(log.Loggable, AttributesMixin):

    def __init__(self, store, bitrate, lookahead=2):
        self.Bitrate = bitrate
        if (lookahead < 1):
            self.warning('Setting miniumum lookahead to 1')
            lookahead = 1
        self._lookahead = lookahead
        self._lookaheads = [] # list of (atomd, atoml, ts, buffer)
        self._fragments = {} # ts -> [buffer, info_buffer, duration]
        self._track_id = None
        self._stream = None
        self._store = store

    def setStream(self, stream):
        self._stream = stream

    def setTrackId(self, track_id):
        self._track_id = track_id

    def getTrackId(self):
        return self._track_id

    def getFragments(self):
        return self._fragments.items()

    def addFragment(self, ad, al, timestamp, duration):
        timestamp = timestamp * self._stream.TimeScale / gst.SECOND
        duration = duration * self._stream.TimeScale / gst.SECOND
        self._lookaheads.append((ad, al, timestamp, duration))
        name = "fragment id: %d, b: %d, t: %d, d: %d" % \
            (self._track_id, self.Bitrate, timestamp, duration)

        if (len(self._lookaheads) > self._lookahead):
            ad, al, timestamp, duration = self._lookaheads.pop(0)
            moof = iso.select_atoms(ad, ('moof', 1, 1))[0]
            mdat = iso.select_atoms(ad, ('mdat', 1, 1))[0]

            # prepare "next" uuid box
            next = []
            for la in self._lookaheads:
                next.append((la[2], la[3]))
            # add live SS "uuid" boxes
            extra = [iso.uuid_sscurrent.make(timestamp, duration),
                     iso.uuid_ssnext.make(next)]
            moof.traf.uuid.extend(extra)
            # make sure they are also written
            moof.traf.add_extra_children(extra)

            # get the modified buffer back
            outf = StringIO()
            iso.write_atoms([moof, mdat], outf)
            b = outf.getvalue()
            outf = StringIO()
            iso.write_atoms([moof], outf)
            info = outf.getvalue()

            # it's a duration-limited list..
            ts = self._fragments.keys()
            if len(ts) > 0:
                ts.sort()
                window = ts[-1] - ts[0]
                while True:
                    if (window >= self._store.DVRWindowLength):
                        if len(self._fragments) == 0:
                            break
                        m = min(self._fragments.keys())
                        self.debug("removing %r" % m)
                        frag_duration = self._fragments[m][2]
                        del self._fragments[m]
                        window -= frag_duration
                    else:
                        break

            # & add our buffer to the list of fragments
            self.debug("added %r buffer" % timestamp)
            self._fragments[timestamp] = [b, info, duration]
        return name

    def getFragment(self, timestamp, kind=None):
        f = self._fragments.get(timestamp)
        if not f:
            return None

        if kind == "info":
            return f[1]

        return f[0]

    def getFragmentInLookAhead(self, timestamp, kind=None):
        for l in self._lookaheads:
            if l[2] == timestamp:
                return True
        return False

    def prerolled(self):
        ts = self._fragments.keys()
        if len(ts) == 0:
            return False
        ts.sort()
        window = ts[-1] - ts[0]
        return window >= self._store.DVRWindowLength


class Chunk(AttributesMixin):

    def __init__(self, t):
        self.t = t


class Stream(AttributesMixin):

    def __init__(self, store, type, subtype="", mime=None,
                 timescale=10000000, chunks=0):
        self._store = store
        self.Type = type
        if subtype:
            self.SubType = subtype
        else:
            self.SubType = ""
        self.TimeScale = timescale
        self.Chunks = chunks
        self.Url = "QualityLevels({bitrate})/Fragments(%s={start time})" % type
        self._qualities = {} # bitrate -> q
        if mime:
            self._mime = mime
        else:
            self._mime = "video/mp4"

    def getQuality(self, store, bitrate, setdefault=True):
        bitrate = int(bitrate)
        if not bitrate in self._qualities and setdefault:
            q = Quality(store, bitrate)
            q.Index = len(self._qualities)
            self._qualities[bitrate] = q
        q = self._qualities[bitrate]
        return q

    def getQualities(self):
        return self._qualities.items()

    def getMime(self):
        return self._mime

    def getFragments(self):
        # some magic to show the list of available chunks
        ts = []
        # firs, get a list of all ts in all qualities
        for br, q in self._qualities.items():
            for t, b in q.getFragments():
                if t not in ts:
                    ts.append(t)
        # then, sort them and remove the ones that are out of the window
        ts.sort()
        min_ts = ts[-1] - self._store.DVRWindowLength
        return [Chunk(t) for t in ts if ts >= min_ts]

    def getAttributes(self):
        return self.__dict__


class FragmentStore(log.Loggable):

    logCategory = 'fragment-store'

    def __init__(self):
        # default values
        self.Duration = 0
        self.LookAheadFragmentCount = 2
        self.DVRWindowLength = 0 # in TimeScale
        self._dvr_window_length_sec = 0 # in seconds
        self.IsLive = "TRUE"
        self._streams = {} # type (audio,video,text) -> stream
        self._qualities = {} # (sink, track_id) -> quality

    def setDVRWindowLength(self, window_in_sec):
        self._dvr_window_length_sec = window_in_sec

    def addMoov(self, sink, moovd):
        moov = iso.select_atoms(moovd, ('moov', 1, 1))[0]
        pprint.pprint(moov)
        self.TimeScale = moov.mvhd.timescale
        self.DVRWindowLength = self._dvr_window_length_sec * self.TimeScale
        if len(moov.trak) == 0:
            raise Exception("Empty trak list")
        for t in moov.trak:
            type = t.mdia.minf.stbl.stsd.entries[0]._atom.type
            # we need to handle h264, aac and then vc1, wma
            if type == "avc1":
                self._addH264Track(sink, t)
            if type == "mp4a":
                self._addAACTrack(sink, t)

    def getFragment(self, bitrate, type, time, kind=None):
        stream = self._streams.get(type)
        if not stream:
            self.warning("bad type %s" % type)
            raise FragmentNotFound(time)

        quality = stream.getQuality(self, bitrate, False)
        if not quality:
            self.warning("bad bitrate %d" % bitrate)
            raise FragmentNotFound(time)
        f = quality.getFragment(time, kind)
        if f:
            return (f, stream.getMime(), 200)
        elif quality.getFragmentInLookAhead(time, kind):
            return (None, None, 412)
        else:
            raise FragmentNotFound(time)

    def addFragment(self, sink, ad, al, timestamp, duration):
        # add fragment in correct track id
        moof = iso.select_atoms(ad, ('moof', 1, 1))[0]
        track_id = moof.traf.tfhd.track_id
        if (sink, track_id) not in self._qualities:
            self.warning("Trying to add a fragment with an unknown "
                         "track_id=%s" % track_id)
            return None
        q = self._qualities[(sink, track_id)]
        return q.addFragment(ad, al, timestamp, duration)

    def getStream(self, type, timescale, subtype=None, mime=None):
        # Fixme what if we have several stream of the same
        # type but different subtypes etc..?
        return self._streams.setdefault(type, Stream(self, type, subtype,
                                        mime, timescale))

    def prerolled(self):
        for q in self._qualities.values():
            if not q.prerolled():
                return False
        return True

    def _addH264Track(self, sink, trak):
        sps, pps, btrt = None, None, None
        avc1 = trak.mdia.minf.stbl.stsd.entries[0]
        for e in avc1.extra:
            if e._atom.type == "avcC":
                sps, pps = avcc.extract_sps_pps(e)
            elif e._atom.type == "btrt":
                btrt = e.avgBitrate
        if None in [sps, pps]:
            self.warning("avcC atom is missing in the h264 track and we can't "
                         "decode the SPS/PPS")
            return
        timescale = trak.mdia.mdhd.timescale
        stream = self.getStream("video", timescale)
        q = stream.getQuality(self, btrt)
        q.setStream(stream)
        q.setTrackId(trak.tkhd.id)
        q.FourCC = "AVC1"
        q.CodecPrivateData = "00000001" + base64.b16encode(sps[0]) + \
                             "00000001" + base64.b16encode(pps[0])
        q.MaxWidth = avc1.width
        q.MaxHeight = avc1.height
        self._qualities[(sink, q.getTrackId())] = q

    def _addAACTrack(self, sink, trak):
        mp4a = trak.mdia.minf.stbl.stsd.entries[0]
        esds = mp4a.extra[0]
        timescale = trak.mdia.mdhd.timescale
        stream = self.getStream("audio", timescale)
        bitrate = esds.avgBitrate
        q = stream.getQuality(self, bitrate)
        q.setStream(stream)
        q.setTrackId(trak.tkhd.id)
        #self.warning ("AAC type %d" % (bytearray(esds.data[0])[0] >> 3))
        q.FourCC = "AACL"
        q.BitsPerSample = mp4a.samplesize
        q.Channels = mp4a.channelcount
        q.PacketSize = 1 # = blockalign?
        q.SamplingRate = mp4a.sampleratehi
        q.AudioTag = \
                waveformatex.object_type_id_to_wFormatTag(esds.object_type_id)
        q.CodecPrivateData = base64.b16encode(waveformatex.waveformatex(
            waveformatex.object_type_id_to_wFormatTag(esds.object_type_id),
            mp4a.channelcount,
            mp4a.sampleratehi,
            0, # avgbytepersec
            1, # blockalign
            mp4a.samplesize,
            esds.data))
        self._qualities[(sink, q.getTrackId())] = q

    def renderManifest(self):

        def make_attributes(dict):
            l = ['%s="%s"' % (e, str(dict[e])) for e in dict \
                    if not e.startswith("_")]
            l.sort()
            return string.join(l, " ")

        m = """<?xml version="1.0"?>\n"""
        m += '<SmoothStreamingMedia MajorVersion="2" ' \
             'MinorVersion="0" %s>\n' % make_attributes(self.__dict__)
        for s in self._streams.values():
            m += """  <StreamIndex %s>\n""" % \
                make_attributes(s.getAttributes())
            for id, q in s.getQualities():
                m += """    <QualityLevel %s />\n""" % \
                        make_attributes(q.getAttributes())
            for c in s.getFragments():
                m += """    <c %s />\n""" % make_attributes(c.getAttributes())
            m += """  </StreamIndex>\n"""
        m += """</SmoothStreamingMedia>\n"""
        return m
