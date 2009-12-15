# -*- Mode: Python -*-
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

import gst
import gobject

from flumotion.component import feedcomponent
from flumotion.common import gstreamer, messages
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()


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

class MPEGTS(feedcomponent.MultiInputParseLaunchComponent):
    checkTimestamp = True

    def do_check(self):
        if gstreamer.get_plugin_version('mpegtsmux') <= (0, 10, 15, 0):
            m = messages.Warning(
                T_(N_("Versions up to and including %s of the '%s' "
                      "GStreamer plug-in are not suitable for streaming.\n"),
                   '0.10.15', 'mpegtsmux'))
            m.add(T_(N_("The stream served by the streamer component "
                        "will probably be unplayable.\n")))
            m.add(T_(N_("The issue will be addressed in version %s of '%s'."),
                     '0.10.16', 'gst-plugins-bad'))
            self.addMessage(m)

    def get_muxer_string(self, properties):
        muxer = 'mpegtsmux name=muxer ! flukeyframescounter name=counter'
        gobject.type_register(KeyframesCounter)
        gst.element_register(KeyframesCounter, "flukeyframescounter",
                gst.RANK_MARGINAL)
        return muxer

    def configure_pipeline(self, pipeline, properties):
        counter = pipeline.get_by_name('counter')
        counter.set_property('silent', properties.get('rewrite-offset', False))
