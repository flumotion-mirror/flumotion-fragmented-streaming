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

    def configure_pipeline(self, pipeline, properties):
        if properties.get("audio-only", False):
            self.dropAudioKuEvents = False
        feedcomponent.MuxerComponent.configure_pipeline(self,
            pipeline, properties)
        self.muxer = pipeline.get_by_name("muxer")
        self.muxer.get_pad("src").add_data_probe(self._src_data_probe)

    def _src_data_probe(self, pad, data):
        return True
