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

import gst
import gobject


class Packetizer(gst.Element):

    __gstdetails__ = ('Packetizer', 'Converter',
                      'Creates fragments delimited by GstForceKeyUnit events',
                      'Flumotion Dev Team')

    _sinkpadtemplate = gst.PadTemplate("sink",
                                         gst.PAD_SINK,
                                         gst.PAD_ALWAYS,
                                         gst.caps_new_any())

    _srcpadtemplate = gst.PadTemplate("src",
                                         gst.PAD_SRC,
                                         gst.PAD_ALWAYS,
                                         gst.caps_new_any())

    def __init__(self):
        gst.Element.__init__(self)
        self.sinkpad = gst.Pad(self._sinkpadtemplate, "sink")
        self.sinkpad.set_chain_function(self.chainfunc)
        self.sinkpad.set_event_function(self.eventfunc)
        self.sinkpad.set_setcaps_function(self.setcaps)
        self.add_pad(self.sinkpad)

        self.srcpad = gst.Pad(self._srcpadtemplate, "src")
        self.add_pad(self.srcpad)

        self._last_index = 0
        self._reset_fragment()
        self._caps = None

    def _reset_fragment(self):
        self._fragment = []
        self._first_ts = gst.CLOCK_TIME_NONE

    def setcaps(self, pad, caps):
        self._caps = caps
        return self.srcpad.set_caps(caps)

    def chainfunc(self, pad, buf):
        if buf.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            return self.srcpad.push(buf)

        if buf.timestamp != gst.CLOCK_TIME_NONE and \
                self._first_ts == gst.CLOCK_TIME_NONE:
            self._first_ts = buf.timestamp
        self._fragment.append(buf)
        return gst.FLOW_OK

    def eventfunc(self, pad, event):
        s = event.get_structure()
        if event.type != gst.EVENT_CUSTOM_DOWNSTREAM or \
                s.get_name() != 'GstForceKeyUnit':
            return pad.event_default(event)

        if len(self._fragment) == 0:
            return True

        index = s['count']
        if self._last_index > index:
            self.warning("Received GstForceKeyunit event with backward "
                         "timestamps")
            self._last_index = index
            self._reset_fragment()
            return True
        self._last_index = index

        # Create the new fragment and send it downstream
        data = ''.join([b.data for b in self._fragment])
        buf = gst.Buffer(data)
        buf.timestamp = self._first_ts
        lb = self._fragment[-1]
        if lb.duration != gst.CLOCK_TIME_NONE:
            buf.duration = lb.timestamp + lb.duration - self._first_ts
        else:
            buf.duration = s['timestamp'] - self._first_ts
        buf.set_caps(self._caps)

        self._reset_fragment()
        return self.srcpad.push(buf)


def register():
    gobject.type_register(Packetizer)
    gst.element_register(Packetizer, 'flupacketizer', gst.RANK_MARGINAL)
