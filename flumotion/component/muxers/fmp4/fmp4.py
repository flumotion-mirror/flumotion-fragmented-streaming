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

from flumotion.component import feedcomponent
from flumotion.common import gstreamer, messages, documentation
from flumotion.common.i18n import N_, gettexter
from flumotion.component.muxers.fmp4 import packetizer
packetizer.register()

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

        muxer = 'ismlmux name=muxer movie-timescale=10000000 '\
                'trak-timescale=10000000 streamable=1'
        if self.duration:
            return '%s fragment-method=1 fragment-duration=%s' % \
                    (muxer, self.duration)
        return '%s fragment-method=2 dts-method=2 ! flupacketizer' % muxer
