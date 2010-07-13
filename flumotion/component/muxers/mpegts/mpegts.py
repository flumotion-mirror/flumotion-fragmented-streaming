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


class MPEGTS(feedcomponent.MultiInputParseLaunchComponent):
    checkTimestamp = True

    def do_check(self):

        exists = gstreamer.element_factory_exists('mpegtsmux')
        if not exists:
            m = messages.Error(T_(N_(
                        "%s is missing. Make sure your %s "
                        "installation is complete."),
                        'mpegtsmux', 'mpegtsmux'))
            documentation.messageAddGStreamerInstall(m)
            self.debug(m)
            self.addMessage(m)
            return

        v = gstreamer.get_plugin_version('mpegtsmux')
        # The mpegtsmuxer does not use the delta unit flag to mark keyframes
        # until gst-plugin-bad-0.10.18. Patched versions in the platform
        # will be numberer using minor=10 to check if the plugin has been
        # patched
        if v <= (0, 10, 17, 0) and v[3] != 11:
            m = messages.Warning(
                T_(N_("Versions up to and including %s of the '%s' "
                      "GStreamer plug-in are not suitable for "
                      "fragmented streaming.\n"),
                      '0.10.17', 'mpegtsmux'))
            self.addMessage(m)

    def get_muxer_string(self, properties):
        muxer = 'mpegtsmux name=muxer pat-interval=%d pmt-interval=%d '\
            '! flumpegtssegmenter keyframes-per-segment=1'\
            % (sys.maxint, sys.maxint)
        return muxer

    def do_pipeline_playing(self):
        # The component must stay 'waiking' until it receives at least
        # a video source
        pass

    def sink_pad_notify_caps(self, sp, _):
        caps = sp.get_negotiated_caps()
        if caps is None:
            return
        struct_name = caps[0].get_name()
        if not self.has_video and struct_name.startswith("video"):
            self.has_video = True
            self.setMood(moods.happy)
        else:
            sp.remove_buffer_probe(self._padProbeIDs[sp])

    def configure_pipeline(self, pipeline, properties):
        self._padProbeIDs = {}
        muxer = pipeline.get_by_name("muxer")
        self.has_video = False
        for sp in muxer.sink_pads():
            self._padProbeIDs[sp] = sp.add_buffer_probe(self._sinkPadProbe)
            sp.connect_after("notify::caps", self.sink_pad_notify_caps)
        muxer.get_pad("src").add_buffer_probe(self._srcPadProbe)
        self._inOffset = 0L
        self._count = 0L

    def _sinkPadProbe(self, pad, buffer):
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            if buffer.offset_end != gst.BUFFER_OFFSET_NONE:
                self._inOffset = buffer.offset_end
            else:
                self._inOffset = self._count
                self._count += 1
        return True

    def _srcPadProbe(self, pad, buffer):
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            buffer.offset = self._inOffset
        return True




