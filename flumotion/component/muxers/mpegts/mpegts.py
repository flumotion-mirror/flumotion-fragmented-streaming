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
from twisted.internet import reactor

from flumotion.component import feedcomponent
from flumotion.component.component import moods
from flumotion.common import messages
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()


class MPEGTS(feedcomponent.MuxerComponent):
    checkTimestamp = True

    bufqueue = []

    def get_muxer_string(self, properties):
        muxer = 'mpegtsmux name=muxer pat-interval=%d pmt-interval=%d '\
            % (sys.maxint, sys.maxint)
        return muxer

    def do_pipeline_playing(self):
        # The component must stay 'waiking' until it receives at least
        # a video source
        pass

    def configure_pipeline(self, pipeline, properties):
        feedcomponent.MuxerComponent.configure_pipeline(self,
            pipeline, properties)
        self.muxer = pipeline.get_by_name("muxer")
        self.muxer.get_pad("src").add_data_probe(self._src_data_probe)
        self.audio_only = properties.get("audio-only", False)
        self.has_video = False
        self.eaters_linked = []

    def _handle_error(self, message, debug_message=""):
        m = messages.Error(T_(N_(message)), debug=debug_message)
        self.addMessage(m)
        # this is usually called from the streaming thread. Change the
        # state in the main loop.
        reactor.callLater(0, self.pipeline.set_state, gst.STATE_NULL)

    def _link_pad(self, src_pad, sink_element, caps, eaterAlias):
        self.debug("Trying to get compatible pad for pad %r with caps %s",
            src_pad, caps)
        sink_pad = sink_element.get_compatible_pad(src_pad, caps)

        if not sink_pad:
            self._handle_error("The incoming data is not compatible with this"
                "muxer.", "Caps %s not compatible with this muxer." % (
                caps.to_string()))
            return False

        self.debug("Got sink pad %r", sink_pad)
        src_pad.link(sink_pad)
        if src_pad.is_blocked():
            self.is_blocked_cb(src_pad, True)
        else:
            src_pad.set_blocked_async(True, self.is_blocked_cb)
        self.eaters_linked.append(eaterAlias)
        return True

    def _link_eater(self, pad, buffer, eaterAlias):
        caps = buffer.caps
        if not caps:
            return False
        struct_name = caps[0].get_name()
        src_pad = self.get_eater_srcpad(eaterAlias)

        if "video" in struct_name:
            # the muxer requires a video stream for the synchronisation
            # mechanism. if we have one, set the mood to 'happy'.
            if not self.has_video:
                self.has_video = True
                self.setMood(moods.happy)
            else:
                self._handle_error("The muxer only supports one video input")
            # if it's audio only, link the video stream to a 'fakesink'
            if self.audio_only:
                fakesink = gst.element_factory_make("fakesink")
                fakesink.set_state(gst.STATE_PLAYING)
                fakesink.set_property("silent", True)
                self.pipeline.add(fakesink)
                return self._link_pad(src_pad, fakesink, caps, eaterAlias)
            # link the video stream to the muxer
            return self._link_pad(src_pad, self.muxer, caps, eaterAlias)

        if "audio" in struct_name:
            return self._link_pad(src_pad, self.muxer, caps, eaterAlias)

    def buffer_probe_cb(self, a, buffer, depay, eaterAlias):
        # try to link the eater if it is not linked yet
        if eaterAlias not in self.eaters_linked:
            self._link_eater(depay.get_pad("src"), buffer, eaterAlias)
        return True

    def _src_data_probe(self, pad, data):
        return True
