# -*- Mode: Python; test-case-name: flumotion.test.test_ts_segmenter -*-
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

import gst
import gobject


class MpegTSSegmenter(gst.Element):
    '''
    I segment an mpegts stream into segments delimited by key frames
    '''

    _DEFAULT_KEYFRAMES = 2

    __gproperties__ = {
        'keyframes-per-segment': (int,
            'keyframes per seconds',
            'The segment duration in keyframes',
            1, 250, _DEFAULT_KEYFRAMES,
            gobject.PARAM_READWRITE)}

    __gstdetails__ = ('MpegTSSegmenter', 'Codec/Demuxer',
                      'MpegTS keyframe segmenter for flumotion',
                      'Flumotion Dev Team')

    _sinkpadtemplate = gst.PadTemplate("sink",
                                         gst.PAD_SINK,
                                         gst.PAD_ALWAYS,
                                         gst.caps_from_string("video/mpegts"))

    _srcpadtemplate = gst.PadTemplate("src",
                                         gst.PAD_SRC,
                                         gst.PAD_ALWAYS,
                                         gst.caps_from_string("video/mpegts"))

    def __init__(self):
        gst.Element.__init__(self)

        self.sinkpad = gst.Pad(self._sinkpadtemplate, "sink")
        self.sinkpad.set_chain_function(self.chainfunc)
        self.add_pad(self.sinkpad)

        self.srcpad = gst.Pad(self._srcpadtemplate, "src")
        self.add_pad(self.srcpad)

        self._keyframesPerSegment = self._DEFAULT_KEYFRAMES
        self._fullReset()

    def _fullReset(self):
        self._syncKeyframe = False
        self._send_new_segment = True
        self._reset()

    def _reset(self):
        self._count = 0
        self._fragmentTimestamp = gst.CLOCK_TIME_NONE
        self._buffer = []

    def do_get_property(self, property):
        if property.name == "keyframes-per-segment":
            return self._keyframesPerSegment
        else:
            raise AttributeError('unknown property %s' % property.name)

    def do_set_property(self, property, value):
        if property.name == "keyframes-per-segment":
            self._keyframesPerSegment = int(value)
        else:
            raise AttributeError('unknown property %s' % property.name)

    def _addBuffer(self, buffer):
        if len(self._buffer) == 0:
            # Write PAT and PMT at the beginning of each fragment
            s = buffer.get_caps()[0]
            if s.has_field('streamheader'):
                for h in s['streamheader']:
                    self._buffer.append(h.data)

        if self._fragmentTimestamp == gst.CLOCK_TIME_NONE:
            self._fragmentTimestamp = buffer.timestamp

        self._buffer.append(buffer.data)

    def _segment(self, duration):
        outbuf = gst.Buffer(''.join(self._buffer))
        outbuf.set_caps(self.sinkpad.get_caps())
        outbuf.offset = self._count-self._keyframesPerSegment
        outbuf.duration = duration
        outbuf.timestamp = self._fragmentTimestamp
        if self._send_new_segment:
            e = gst.event_new_new_segment(False, 1.0, gst.FORMAT_TIME,
                self._fragmentTimestamp, -1, 0)
            self.send_event(e)
            self._send_new_segment = False
        ret = self.srcpad.push(outbuf)
        self.log('Pushed buffer with length:%d, ts: %d'
            % (len(outbuf), outbuf.timestamp))
        self._reset()
        return ret

    def chainfunc(self, pad, buffer):
        if buffer.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            return gst.FLOW_OK

        ret = gst.FLOW_OK
        # Discard first buffers until we have a valid sync keyframe
        if not self._syncKeyframe:
            if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
                if buffer.offset == gst.BUFFER_OFFSET_NONE:
                    self.warning("Key frames are not counted using the buffer\
                            offset value. Elements depending on this value\
                            like playlists will not be in sync")
                    self._syncKeyframe = True
                    self._addBuffer(buffer)
                elif buffer.offset % self._keyframesPerSegment == 0:
                    self.debug('Found sync keyframe: start segmenting')
                    self._syncKeyframe = True
                    self._addBuffer(buffer)
            return gst.FLOW_OK

        # Detect keyframes
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            # We have a keyframe
            if buffer.offset != gst.BUFFER_OFFSET_NONE:
                # Check for discontinuities, like a muxer restart.
                if self._count != 0 and buffer.offset != self._count + 1:
                    self.warning("Found a discontinuity in the buffers offset."
                                 "freeing fragment and resetting counters")
                    self._fullReset()
                    return gst.FLOW_OK
                else:
                    self._count = buffer.offset
            else:
                self._count = self._count + 1
            if (self._count % self._keyframesPerSegment) == 0 and\
                    self._count != 0:
                # Segment if we have enough keyframes
                duration = buffer.timestamp - self._fragmentTimestamp
                self.debug('%d keyframes detected, segmenting duration %d' %
                    (self._keyframesPerSegment, duration))
                ret = self._segment(duration)
                self._fragmentTimestamp = gst.CLOCK_TIME_NONE
            else:
                # Wait for more keyframes
                self.log('%d keyframes detected, waiting for %d more' %
                        (self._count % self._keyframesPerSegment,
                        self._keyframesPerSegment -
                        self._count % self._keyframesPerSegment))

        self._addBuffer(buffer)
        return gst.FLOW_OK

gst.element_register(MpegTSSegmenter,  "flumpegtssegmenter",
    gst.RANK_MARGINAL)
