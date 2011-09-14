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
        self.add_pad(self.sinkpad)

        self.srcpad = gst.Pad(self._srcpadtemplate, "src")
        self.add_pad(self.srcpad)
        self._reset_fragment()

    def _reset_fragment(self):
        self._fragment = []
        self._in_caps = False
        self._first_ts = gst.CLOCK_TIME_NONE

    def chainfunc(self, pad, buf):
        if buf.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            self._in_caps = True
            return gst.FLOW_OK

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

        # Create the new fragment and send it downstream
        data  = ''.join([b.data for b in self._fragment])
        buf = gst.Buffer(data)
        buf.timestamp = self._first_ts
        if buf.timestamp != gst.CLOCK_TIME_NONE:
            buf.duration = s['timestamp'] - buf.timestamp
        if self._in_caps:
            buf.flag_set(gst.BUFFER_FLAG_IN_CAPS)
        self._reset_fragment()
        return self.srcpad.push(buf)

def register():
    gobject.type_register(Packetizer)
    gst.element_register(Packetizer, 'flupacketizer', gst.RANK_MARGINAL)
