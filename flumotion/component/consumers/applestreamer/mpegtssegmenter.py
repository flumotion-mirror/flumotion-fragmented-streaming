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
        self._lastTimestamp = gst.CLOCK_TIME_NONE
        self._syncKeyframe = False
        self._reset()

    def _reset(self):
        self._segmentDuration = 0L
        self._count = 0
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
        self._buffer.append(buffer.data)

    def _segment(self):
        outbuf = gst.Buffer(''.join(self._buffer))
        outbuf.set_caps(self.sinkpad.get_caps())
        outbuf.offset = self._count-self._keyframesPerSegment
        outbuf.duration = self._segmentDuration
        ret = self.srcpad.push(outbuf)
        self.log('Pushed buffer with lenght:%d' % len(outbuf))
        self._reset()
        return ret

    def chainfunc(self, pad, buffer):
        ret = gst.FLOW_OK

        # Check for discontinuities, like a muxer restart.
        if buffer.offset <= self._count:
            self.warning("Found a discontinuity in the buffers offset."
                         "freeing fragment and resetting counters")
            self._fullReset()

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

        # Update segment duration
        if buffer.duration != gst.CLOCK_TIME_NONE:
            self._segmentDuration += buffer.duration
        else:
            # Buffer has no duration, using timestamp
            if buffer.timestamp != gst.CLOCK_TIME_NONE:
                # First buffer received, setting timestamp reference
                if self._lastTimestamp == gst.CLOCK_TIME_NONE:
                    self._lastTimestamp = buffer.timestamp
                # Update last timestamp and duration
                self._segmentDuration += buffer.timestamp - self._lastTimestamp
                self._lastTimestamp = buffer.timestamp

        # Detect keyframes
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            # We have a keyframe
            if buffer.offset != gst.BUFFER_OFFSET_NONE:
                self._count = buffer.offset
            else:
                self._count = self._count + 1
            if (self._count % self._keyframesPerSegment) == 0 and\
                    self._count != 0:
                # Segment if we have enough keyframes
                self.debug('%d keyframes detected, segmenting' %
                        self._keyframesPerSegment)
                ret = self._segment()
            else:
                # Wait for more keyframes
                self.log('%d keyframes detected, waiting for %d more' %
                        (self._count % self._keyframesPerSegment,
                        self._keyframesPerSegment -
                        self._count % self._keyframesPerSegment))

        self._addBuffer(buffer)
        return gst.FLOW_OK

gobject.type_register(MpegTSSegmenter)
