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
from flumotion.common import gstreamer, messages, documentation
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()


class MPEGTS(feedcomponent.MuxerComponent):
    checkTimestamp = True

    """
    The mpegts-muxer component muxes a video and an audio stream into an
    MPEG-TS stream and copies the keyframes' OFFSET_END, increased by one for
    each keyframe, to the outgoing mpegts buffers for synchronisation purpose.

    At the muxer level,the synchronisation is done increasing the buffer offset
    for each keyframe and writting it to the outgoing MPEG-TS packet marked as
    keyframes. If the video encoder uses the OFFSET_END as a counter for
    keyframes, we use this value, otherwhise we use an internal counter
    increased on each video keyframe.

    If the muxed stream contains video,mpegtsmux will unset the delta unit flag
    for the output MPEG-TS buffers containing a video keyframe and we only need
    to rewrite the offset of these buffers.

    If the muxed stream only contains audio, we need to mark all the audio
    buffers as delta unit and unset this flag for the first audio buffer after
    the video keyframe. NB: this will only works if mpegtsmux also takes in
    count audio stream for detecting non delta unit"""

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

    def configure_pipeline(self, pipeline, properties):
        feedcomponent.MuxerComponent.configure_pipeline(self,
            pipeline, properties)
        self.muxer = pipeline.get_by_name("muxer")
        self.muxer.get_pad("src").add_buffer_probe(self._srcPadProbe)
        self.audio_only = properties.get("audio-only", False)
        self.has_video = False
        self._inOffset = 0L
        self._count = 0L
        self._last_kf_ts = 0L
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

    def _do_sync(self, buffer):
        # Audio buffer
        if 'audio' in buffer.get_caps()[0].get_name():
            # audio buffers are all 'keyframes' and the DELTA_UNIT flag is set
            # for all of them. We need to unset this flag to help the muxer
            # marking keyframes properly
            buffer.flag_set(gst.BUFFER_FLAG_DELTA_UNIT)
            # if we have only audio, the first audio buffer after the keyframe
            # must be marked has a keyframe
            if self.audio_only and self._last_kf_ts != gst.CLOCK_TIME_NONE and\
                buffer.timestamp >= self._last_kf_ts:
                buffer.flag_unset(gst.BUFFER_FLAG_DELTA_UNIT)
                self._last_kf_ts = gst.CLOCK_TIME_NONE
            return True
        # Video buffer
        # if the buffer is a keyframe take the offset an store it for the
        # outgoing MPEG-TS packets.
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            if buffer.offset_end != gst.BUFFER_OFFSET_NONE:
                self._inOffset = buffer.offset_end
            else:
                self._inOffset = self._count
                self._count += 1
            # update the last keyframe's timestamp for audio-only
            # sinchronization
            self._last_kf_ts = buffer.timestamp
        return True

    def buffer_probe_cb(self, a, buffer, depay, eaterAlias):
        # try to link the eater if it is not linked yet
        if eaterAlias not in self.eaters_linked:
            self._link_eater(depay.get_pad("src"), buffer, eaterAlias)
        # process the buffer for the synchronisation mechanism
        return self._do_sync(buffer)

    def _srcPadProbe(self, pad, buffer):
        # set the stored offset if the outgoing buffer is a keyframe
        if not buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            buffer.offset = self._inOffset
        return True
