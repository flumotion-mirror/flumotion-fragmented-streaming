# -*- Mode: Python; test-case-name: flumotion.muxers.mpegts.mpegts -*-
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

from flumotion.component import feedcomponent
from flumotion.common import gstreamer, messages, documentation
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()


class FMP4(feedcomponent.MuxerComponent):
    checkTimestamp = True
    dropAudioKuEvents = False
    logCategory = 'smooth-muxer'

    def do_check(self):
        exists = gstreamer.element_factory_exists('ismlmux')
        if not exists:
            m = messages.Error(T_(N_(
                        "%s is missing. Make sure your %s "
                        "installation is complete."),
                        'ismlmux', 'ismlmux'))
            documentation.messageAddGStreamerInstall(m)
            self.debug(m)
            self.addMessage(m)
            return

        v = gstreamer.get_plugin_version('isomp4')
        if v < (0, 10, 23, 0):
            m = messages.Warning(
                T_(N_("Versions up to and including %s of the '%s' "
                      "GStreamer plug-in are not suitable for "
                      "smooth streaming.\n"),
                      '0.10.23', 'isomp4'))
            self.addMessage(m)

    def get_muxer_string(self, props):
        self.duration = props.get('fragment-duration', None)

        muxer = 'ismlmux name=muxer dts-method=0' 
        if self.duration:
            return '%s fragment-method=1 duration=%' % (muxer, self.duration)
        return '%s fragment-method=2' % muxer
