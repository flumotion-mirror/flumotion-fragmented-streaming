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

from zope.interface import implements
from twisted.internet import reactor, error, defer
from flumotion.common.i18n import N_, gettexter
from flumotion.component import feedcomponent
from flumotion.common import interfaces, netutils, errors, messages
from flumotion.component.component import moods

from flumotion.extern.log import log
from flumotion.component.consumers.applestreamer.common import\
    FragmentNotFound, FragmentNotAvailable, PlaylistNotFound, KeyNotFound
from flumotion.component.consumers.applestreamer.applestreamer import\
    FragmentedStreamer
from flumotion.component.consumers.smoothstreamer.resources import\
    SmoothStreamingResource
from flumotion.component.consumers.smoothstreamer import\
    avcc, waveformatex
__all__ = ['HTTPMedium', 'SmoothHTTPLiveStreamer']
__version__ = ""
T_ = gettexter()


class SmoothHTTPLiveStreamer(FragmentedStreamer):

    logCategory = 'smooth-streamer'

    def init(self):
        reactor.debug = True
        self.store = FragmentStore()
        self.debug("Smooth HTTP live streamer initialising")

    def getUrl(self):
        return "http://%s:%d%s/Manifest" % (self.hostname, self.port, self.mountPoint)

    def __repr__(self):
        return '<SmoothHTTPLiveStreamer (%s)>' % self.name

    def get_mime(self):
        return 'text/xml'

    def make_resource(self, httpauth, props):
        return SmoothStreamingResource(self, self.store, httpauth,
                props.get('secret-key', self.DEFAULT_SECRET_KEY),
                props.get('session-timeout', self.DEFAULT_SESSION_TIMEOUT))

    def configure_pipeline(self, pipeline, props):
        appsink = pipeline.get_by_name('appsink')
        appsink.set_property('emit-signals', True)
        appsink.get_pad("sink").add_buffer_probe(self._sinkPadProbe, None)
        appsink.connect("new-preroll", self._new_preroll)
        appsink.connect("new-buffer", self._new_buffer)
        appsink.connect("eos", self._eos)
        self._segmentsCount = 0
        FragmentedStreamer.configure_pipeline(self, pipeline, props)

    def get_pipeline_string(self, properties):
        return "appsink name=appsink sync=false"

    def _processBuffer(self, buffer):
        currOffset = buffer.offset
        self._lastBufferOffset = currOffset
        self._segmentsCount = self._segmentsCount + 1

        # Wait hls-min-window fragments to set the component 'happy'
        if self._segmentsCount == self._minWindow:
            self.info("%d fragments received. Changing mood to 'happy'",
                    self._segmentsCount)
            self.setMood(moods.happy)
            self.ready = True
        f = StringIO(buffer.data)
        al = list(atoms.read_atoms(f))
        ad = atoms.atoms_dict(al)
        if (buffer.flag_is_set (gst.BUFFER_FLAG_IN_CAPS)):
            self.store.setMoov(ad)
        elif iso.select_atoms(ad, ('moof', 0, 1))[0]:
            fragName = self.store.addFragment(ad, al, buffer.offset, buffer.duration)
            self.info('Added fragment "%s", duration=%s offset=%s',
                      fragName, gst.TIME_ARGS(buffer.duration), currOffset)

    ### START OF THREAD-AWARE CODE (called from non-reactor threads)

    def _sinkPadProbe(self, pad, buffer, none):
        reactor.callFromThread(self.updateBytesReceived, len(buffer.data))
        return True

    def _new_preroll(self, appsink):
        self.log("appsink received a preroll buffer")
        buffer = appsink.emit('pull-preroll')

    def _new_buffer(self, appsink):
        self.log("appsink received a new buffer")
        buffer = appsink.emit('pull-buffer')
        reactor.callFromThread(self._processBuffer, buffer)

    def _eos(self, appsink):
        #FIXME: How do we handle this for live?
        self.log('appsink received an eos')

    ### END OF THREAD-AWARE CODE


class AttributesMixin:

    def getAttributes(self):
        return self.__dict__


class Quality(log.Loggable, AttributesMixin):
    def __init__(self, bitrate, lookahead=2, maxfragments=10):
        self.Bitrate = bitrate
        if (lookahead < 1):
            self.warning('Setting miniumum lookahead to 1')
            lookahead = 1
        self._lookahead = lookahead
        self._lookaheads = [] # list of (atomd, atoml, ts, buffer) for lookahead?
        self._fragments = {} # ts -> buffer
        self._maxfragments = maxfragments + lookahead
        self._track_id = None
        self._stream = None

    def setStream(self, stream):
        self._stream = stream

    def setTrackId(self, track_id):
        self._track_id = track_id

    def getTrackId(self):
        return self._track_id

    def getFragments(self):
        return self._fragments.items()

    def addFragment(self, ad, al, timestamp, duration):
        duration = duration * self._stream.TimeScale / 1000000000
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
            extra = [iso.uuid_sscurrent.make (timestamp, duration), iso.uuid_ssnext.make (next)]
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

            # it's a size-limited list..
            if (len(self._fragments) == self._maxfragments):
                m = min(self._fragments.keys())
                self.debug("removing %r" % m)
                del self._fragments[m]

            # & add our buffer to the list of fragments
            self._fragments[timestamp] = [b, info]
            self.debug("added %s, resulting len %d" % (name,
                len(self._fragments)))

        return name

    def getFragment(self, timestamp, kind=None):
        if kind == "info":
            return self._fragments[timestamp][1]

        return self._fragments[timestamp][0]


class Chunk(AttributesMixin):
    def __init__(self, t):
        self.t = t


class Stream(AttributesMixin):

    def __init__(self, type, subtype="", mime=None, timescale=10000000, chunks=0):
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

    def getQuality(self, bitrate, setdefault=True):
        bitrate = int(bitrate)
        if not self._qualities.has_key(bitrate) and setdefault:
            q = Quality(bitrate)
            q.Index = len(self._qualities)
            self._qualities[bitrate] = q
        q = self._qualities[bitrate]
        return q

    def getQualities(self):
        return self._qualities.items()

    def getMime(self):
        return self._mime

    def getFragments(self):
        # some magic to show only the chunks which are available in all qualities
        ts = {} # ts -> list of qualities
        for br, q in self._qualities.items():
            for t, b in q.getFragments():
                ts.setdefault(t, []).append(q)
        chunks = [Chunk(t) for t, q in ts.items() if len(q) == len(self._qualities)]
        chunks.sort(lambda x, y: cmp(x.t, y.t))
        return chunks

    def getAttributes(self):
        return self.__dict__


class FragmentStore(log.Loggable):

    logCategory = 'fragment-store'

    def __init__(self):
        # default values
        self.Duration = 0
        self.LookAheadFragmentCount = 2
        self.DVRWindowLength = 0
        self.IsLive = "TRUE"
        self._streams = {} # type (audio,video,text) -> stream
        self._qualities = {} # track_id -> quality

    def setMoov(self, moovd):
        moov = iso.select_atoms(moovd, ('moov', 1, 1))[0]
        pprint.pprint(moov)
        self.TimeScale = moov.mvhd.timescale
        self._streams = {}
        for t in moov.trak:
            type = t.mdia.minf.stbl.stsd.entries[0]._atom.type
            # we need to handle h264, aac and then vc1, wma
            if type == "avc1":
                self._addH264Track(t)
            if type == "mp4a":
                self._addAACTrack(t)

    def getFragment(self, bitrate, type, time, kind=None):
        stream = self._streams.get(type)
        if not stream:
            self.warning("bad type %s" % type)
            raise FragmentNotFound(time)

        quality = stream.getQuality(bitrate, False)
        if not quality:
            self.warning("bad bitrate %d" % bitrate)
            raise FragmentNotFound(time)
        try:
            return (quality.getFragment(time, kind), stream.getMime())
        except KeyError:
            raise FragmentNotFound(time)

    def addFragment(self, ad, al, timestamp, duration):
        # add fragment in correct track id
        moof = iso.select_atoms(ad, ('moof', 1, 1))[0]
        track_id = moof.traf.tfhd.track_id
        return self._qualities[track_id].addFragment(ad, al, timestamp, duration)

    def getStream(self, type, timescale, subtype=None, mime=None):
        # Fixme what if we have several stream of the same type but different subtypes etc..?
        return self._streams.setdefault(type, Stream(type, subtype, mime, timescale))

    def _addH264Track(self, trak):
        sps, pps, btrt = None, None, None
        avc1 = trak.mdia.minf.stbl.stsd.entries[0]
        for e in avc1.extra:
            if e._atom.type == "avcC":
                sps, pps = avcc.extract_sps_pps(e)
            elif e._atom.type == "btrt":
                btrt = e.avgBitrate
        timescale = trak.mdia.mdhd.timescale
        stream = self.getStream("video", timescale)
        q = stream.getQuality(btrt)
        q.setStream(stream)
        q.setTrackId(trak.tkhd.id)
        q.FourCC = "AVC1"
        q.CodecPrivateData = "00000001" +  base64.b16encode(sps[0]) + "00000001" + base64.b16encode(pps[0])
        q.MaxWidth = avc1.width
        q.MaxHeight = avc1.height
        self._qualities[q.getTrackId()] = q

    def _addAACTrack(self, trak):
        mp4a = trak.mdia.minf.stbl.stsd.entries[0]
        esds = mp4a.extra[0]
        timescale = trak.mdia.mdhd.timescale
        stream = self.getStream("audio", timescale)
        bitrate = esds.avgBitrate
        q = stream.getQuality(bitrate)
        q.setStream(stream)
        q.setTrackId(trak.tkhd.id)
        #self.warning ("AAC type %d" % (bytearray(esds.data[0])[0] >> 3))
        q.FourCC = "AACL"
        q.BitsPerSample = mp4a.samplesize
        q.Channels = mp4a.channelcount
        q.PacketSize = 1 # = blockalign?
        q.SamplingRate = mp4a.sampleratehi
        q.AudioTag = waveformatex.object_type_id_to_wFormatTag(esds.object_type_id)
        q.CodecPrivateData = base64.b16encode(waveformatex.waveformatex(
            waveformatex.object_type_id_to_wFormatTag(esds.object_type_id),
            mp4a.channelcount,
            mp4a.sampleratehi,
            0, # avgbytepersec
            1, # blockalign
            mp4a.samplesize,
            esds.data))
        self._qualities[q.getTrackId()] = q

    def renderManifest(self):

        def make_attributes(dict):
            l = ['%s="%s"' % (e, str(dict[e])) for e in dict if not e.startswith("_")]
            l.sort()
            return string.join(l, " ")

        m = """<?xml version="1.0"?>\n"""
        m += """<SmoothStreamingMedia MajorVersion="2" MinorVersion="0" %s>\n""" % \
            make_attributes(self.__dict__)
        for s in self._streams.values():
            m += """  <StreamIndex %s>\n""" % \
                make_attributes(s.getAttributes())
            for id, q in s.getQualities():
                m += """    <QualityLevel %s />\n""" % make_attributes(q.getAttributes())
            for c in s.getFragments():
                m += """    <c %s />\n""" % make_attributes(c.getAttributes())
            m += """  </StreamIndex>\n"""
        m += """</SmoothStreamingMedia>\n"""
        return m

