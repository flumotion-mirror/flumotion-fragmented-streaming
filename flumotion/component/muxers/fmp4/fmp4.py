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


import gst

from flumotion.component import feedcomponent
from flumotion.common import gstreamer, messages, documentation
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()


class FMP4(feedcomponent.MuxerComponent):
    checkTimestamp = True

    DEFAULT_FRAGMENT_DURATION=5000

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

        v = gstreamer.get_plugin_version('qtmux')
        if v < (0, 10, 11, 0):
            m = messages.Warning(
                T_(N_("Versions up to and including %s of the '%s' "
                      "GStreamer plug-in are not suitable for "
                      "smooth streaming.\n"),
                      '0.10.11', 'qtmux'))
            self.addMessage(m)

    def get_muxer_string(self, props):
        self.duration = props.get('fragment-duration', self.DEFAULT_FRAGMENT_DURATION)

        muxer = 'ismlmux name=muxer fragment-duration=%d ' \
            'movie-timescale=10000000 trak-timescale=10000000 streamable=1' % \
            self.duration
        return muxer

    def _pad_added_cb(self, element, pad):
        id = pad.add_buffer_probe(self._sinkPadProbe)
        self._pad_info[pad] = (False, gst.CLOCK_TIME_NONE,
            gst.CLOCK_TIME_NONE, id)

    def configure_pipeline(self, pipeline, properties):
        feedcomponent.MuxerComponent.configure_pipeline(self, pipeline, properties)
        element = pipeline.get_by_name('muxer')
        self._pad_info = {} # pad -> (synced, prev_ts, prev_dur, probe_id)
        element.connect('pad-added', self._pad_added_cb)

    def _sinkPadProbe(self, pad, buffer):
        ts = buffer.timestamp
        duration = buffer.duration
        synced, pts, pdur, id = self._pad_info[pad]

        if ts == gst.CLOCK_TIME_NONE or duration == gst.CLOCK_TIME_NONE:
            m = messages.Warning(T_(N_(
                "Can't sync on keyframes, the input source does not write the"
                " timestamp.")))
            self.addMessage(m)
            pad.remove_buffer_probe(id)
            return True

        if pts != gst.BUFFER_OFFSET_NONE:
            if (pts + pdur) != ts:
                # FIXME add pad name in message
                self.warning("Discontinuity in muxer input buffer: "
                             "marked as desync (%r != %r)" %
                             (gst.TIME_ARGS(pts), gst.TIME_ARGS(ts)))
                synced = False

            # don't check fragment sync immediately, as pts is invalid
            elif not synced:
                frag_duration = self.duration * gst.MSECOND
                # detect beginning of fragment, if looping over frag_duration
                _ts = pts % frag_duration
                _tsd = ts % frag_duration
                self.debug("trying to sync %r %r" %
                           (gst.TIME_ARGS(_ts), gst.TIME_ARGS(_tsd)))
                if _ts > _tsd:
                    self.info("Syncing muxer input at %r" % gst.TIME_ARGS(ts))
                    synced = True

        self._pad_info[pad] = (synced, ts, duration, id)

        return synced
