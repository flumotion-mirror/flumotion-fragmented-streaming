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
    logCategory = 'smooth-muxer'

    DEFAULT_FRAGMENT_DURATION = 5000
    _lastSyncPoint = 0L

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
        self.duration = props.get('fragment-duration',
                                  self.DEFAULT_FRAGMENT_DURATION)

        muxer = 'ismlmux name=muxer fragment-duration=%d ' \
            'movie-timescale=10000000 trak-timescale=10000000 streamable=1' % \
            self.duration
        return muxer

    def _pad_added_cb(self, element, pad):
        # The audio stream doesn't not need synchronization
        if 'audio' in pad.get_caps()[0].get_name():
            self.info("Audio pad added")
            return
        id = pad.add_buffer_probe(self._sinkPadProbe)
        self._pad_info[pad] = (False, 0L, 0L, 0L, id)
        self.info("Added pad probe for video pad %s", pad.get_name())

    def configure_pipeline(self, pipeline, properties):
        feedcomponent.MuxerComponent.configure_pipeline(self, pipeline,
                                                        properties)
        element = pipeline.get_by_name('muxer')
        # pad -> (synced, sync_ts, prev_ts, prev_dur, probe_id)
        self._pad_info = {}
        element.connect('pad-added', self._pad_added_cb)

    def _set_desync_flag(self, ts):
        for pad in self._pad_info:
            synced, sync_ts, prev_ts, prev_dur, probe_id = self._pad_info[pad]
            if ts > sync_ts:
                self.info("Setting desync flag in pad %s (old sync was %s)",
                          pad.get_name(), gst.TIME_ARGS(sync_ts))
                self._pad_info[pad] = (False, sync_ts,
                                       prev_ts, prev_dur, probe_id)

    def _other_pads_synced(self, new_sync, comp_pad):
        for pad in self._pad_info:
            if pad == comp_pad:
                continue
            synced, sync, pts, pdts, p_id = self._pad_info[pad]
            if new_sync > sync:
                self.info("Setting desync flag in pad %s (old sync was %s)",
                          pad.get_name(), gst.TIME_ARGS(sync))
                self._pad_info[pad] = False, sync, pts, pdts, p_id
            if new_sync < sync:
                return False
        return True

    def _sinkPadProbe(self, pad, buffer):
        ts = buffer.timestamp
        duration = buffer.duration
        synced, sync_ts, pts, pdur, id = self._pad_info[pad]

        if ts == gst.CLOCK_TIME_NONE or duration == gst.CLOCK_TIME_NONE:
            m = messages.Warning(T_(N_(
                "Can't sync on keyframes, the input source does not write the"
                " timestamp.")))
            self.addMessage(m)
            pad.remove_buffer_probe(id)
            return True

        if (pts + pdur) != ts and pts != 0L:
            self.warning("Discontinuity in muxer input buffer at pad %s: "
                         "marked as desync (%r != %r)" %
                         (pad.get_name(), gst.TIME_ARGS(pts),
                          gst.TIME_ARGS(ts)))
            self._set_desync_flag(ts)
            synced = False

        # don't check fragment sync immediately, as pts is invalid
        elif not synced:
            frag_duration = self.duration * gst.MSECOND
            # detect beginning of fragment, if looping over frag_duration
            _ts = pts % frag_duration
            _tsd = ts % frag_duration
            self.info("trying to sync pad %s %r %r" % (pad.get_name(),
                      gst.TIME_ARGS(_ts), gst.TIME_ARGS(_tsd)))
            if _ts > _tsd:
                sync_ts = ts
                self.debug("updated sync point for pad %s: %s", pad.get_name(),
                        gst.TIME_ARGS(ts))
                if self._other_pads_synced(ts, pad):
                    self.info("Syncing muxer input for pad %s at %r",
                              pad.get_name(), gst.TIME_ARGS(ts))
                    synced = True

        self._pad_info[pad] = (synced, sync_ts, ts, duration, id)
        return synced
