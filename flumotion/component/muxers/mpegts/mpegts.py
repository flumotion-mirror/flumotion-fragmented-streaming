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

import sys

import gst

from flumotion.component import feedcomponent
from flumotion.common.i18n import gettexter

T_ = gettexter()


class MPEGTS(feedcomponent.MuxerComponent):
    '''
    Muxes incomming streams in MpegTS format.

    The MpegTS format packetize the output stream in buffers of 188 bytes,
    sending a high number of small buffers for video streams with a big
    bitrate.
    The queues in multifdsink are configured with a limit of 500 buffers,
    which is quickly reached in this particular case.
    To avoid this issue, we group the output buffers by timestamp, pushing only
    buffer downstream per video/audio frame.
    '''
    checkTimestamp = True

    def get_muxer_string(self, properties):
        muxer = 'mpegtsmux name=muxer pat-interval=%d pmt-interval=%d !'\
                'identity name=id silent=true' % (sys.maxint, sys.maxint)
        return muxer

    def configure_pipeline(self, pipeline, properties):
        if properties.get('audio-only', False):
            self.dropAudioKuEvents = False
        feedcomponent.MuxerComponent.configure_pipeline(self,
            pipeline, properties)
        self.muxer = pipeline.get_by_name("muxer")
        self.muxer.get_pad("src").add_data_probe(self._src_data_probe)
        self._id_pad = pipeline.get_by_name("id").get_pad("src")
        self._buffers_queue = []
        self._last_ts = 0

    def _flush_queue(self):
        if len(self._buffers_queue) == 0:
            return gst.FLOW_OK
        data = ''.join([b.data for b in self._buffers_queue])
        buf = gst.Buffer(data)
        buf.set_caps(self._buffers_queue[0].caps)
        buf.timestamp = self._last_ts
        self._buffers_queue = []
        return self._id_pad.push(buf)

    def _src_data_probe(self, pad, data):
        if type(data) == gst.Buffer:
            ts = data.timestamp
            if ts != gst.CLOCK_TIME_NONE and ts > self._last_ts:
                self._flush_queue()
                self._last_ts = ts
            self._buffers_queue.append(data)
            return False
        if type(data) == gst.Event:
            if data.get_structure().get_name() == 'GstForceKeyUnit':
                self._flush_queue()
            return True
