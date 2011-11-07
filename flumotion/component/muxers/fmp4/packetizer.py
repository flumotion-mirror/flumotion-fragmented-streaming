# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007,2008,2009 Fluendo, S.L.
# Copyright (C) 2010,2011 Flumotion Services, S.A.
# All rights reserved.
#
# This file may be distributed and/or modified under the terms of
# the GNU Lesser General Public License version 2.1 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.LGPL" in the source distribution for more information.
#
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

    def _reset_fragment(self, last_event_ts=gst.CLOCK_TIME_NONE):
        self._fragment = []
        self._first_ts = gst.CLOCK_TIME_NONE
        self._last_event_ts = last_event_ts

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

        if self._last_event_ts == gst.CLOCK_TIME_NONE or \
            len(self._fragment) == 0:
            self._reset_fragment(s['timestamp'])
            return True

        index = s['count']
        if self._last_index > index:
            self.warning("Received GstForceKeyunit event with backward "
                         "timestamps")
            self._last_index = index
            self._reset_fragment(s['timestamp'])
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
            buf.duration = s['timestamp'] - self._last_event_ts
        buf.set_caps(self._caps)

        self._reset_fragment(s['timestamp'])
        return self.srcpad.push(buf)


def register():
    gobject.type_register(Packetizer)
    gst.element_register(Packetizer, 'flupacketizer', gst.RANK_MARGINAL)
