# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2008,2009 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import gst
import gobject

class KeyframesCounter(gst.Element):
    '''
    I count incoming key frames using the delta unit flag.
    I use the buffer's 'offset' value to store the counter
    '''

    __gproperties__ = {
        'silent' : (bool,
            'silent',
            'Whether to count keyframes or not',
            False,
            gobject.PARAM_READWRITE)
    }

    __gstdetails__ = ('KeyframesCounter', 'Generic',
                      'Key frames counter for flumotion', 'Flumotion Dev Team')

    _sinkpadtemplate = gst.PadTemplate ("sink",
                                         gst.PAD_SINK,
                                         gst.PAD_ALWAYS,
                                         gst.caps_from_string("video/mpegts"))
    
    _srcpadtemplate = gst.PadTemplate ("src",
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
       
        self._silent = False
        self._keyframesCount = 0
       
    def do_get_property(self, property):
        if property.name == "silent":
            return self._silent
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
       if property.name == "silent":
            self._silent = bool(value)
       else:
            raise AttributeError, 'unknown property %s' % property.name

    def chainfunc(self, pad, buffer):
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT) \
                and not self._silent: 
            buffer.offset = self._keyframesCount
            self._keyframesCount += 1

        return self.srcpad.push(buffer) 

gobject.type_register(KeyframesCounter)

