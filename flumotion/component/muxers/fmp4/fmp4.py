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

import sys

import gst
import gobject

from flumotion.component import feedcomponent
from flumotion.component.component import moods
from flumotion.common import gstreamer, messages, documentation
from flumotion.common.i18n import N_, gettexter
from flumotion.component.consumers.applestreamer import mpegtssegmenter

T_ = gettexter()


class FMP4(feedcomponent.MuxerComponent):
    checkTimestamp = True

    DEFAULT_FRAGMENT_DURATION=5000

    def do_check(self):
        exists = gstreamer.element_factory_exists('mp4mux')
        if not exists:
            m = messages.Error(T_(N_(
                        "%s is missing. Make sure your %s "
                        "installation is complete."),
                        'mp4mux', 'mp4mux'))
            documentation.messageAddGStreamerInstall(m)
            self.debug(m)
            self.addMessage(m)
            return

        v = gstreamer.get_plugin_version('qtmux')
        # The mpegtsmuxer does not use the delta unit flag to mark keyframes
        # until gst-plugin-bad-0.10.18. Patched versions in the platform
        # will be numberer using minor=10 to check if the plugin has been
        # patched
        if v <= (0, 10, 19, 0) and v[3] != 11:
            m = messages.Warning(
                T_(N_("Versions up to and including %s of the '%s' "
                      "GStreamer plug-in are not suitable for "
                      "smooth streaming.\n"),
                      '0.10.19', 'qtmux'))
            self.addMessage(m)

    def get_muxer_string(self, props):
        muxer = 'mp4mux name=muxer fragment-duration=%d ' \
            'movie-timescale=10000000 trak-timescale=10000000 streamable=1' % \
            props.get('fragment-duration', self.DEFAULT_FRAGMENT_DURATION)
        return muxer

    def configure_pipeline(self, pipeline, properties):
        feedcomponent.MuxerComponent.configure_pipeline(self, pipeline, properties)
