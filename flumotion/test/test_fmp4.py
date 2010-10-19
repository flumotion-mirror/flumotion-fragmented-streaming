# -*- Mode: Python; test-case-name: flumotion.test.test_fmp4 -*-
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

from twisted.trial import unittest
from twisted.internet import defer, reactor

import gst

from flumotion.component import feedcomponent
from flumotion.common import testsuite
from flumotion.common import log, errors
from flumotion.common.planet import moods
from flumotion.test import comptest

from flumotion.component.muxers.fmp4 import fmp4

import setup
setup.setup()


class FMP4Tester(feedcomponent.ParseLaunchComponent):

    logCategory = 'fmp4-tester'

    def get_pipeline_string(self, properties):
        return "appsink name=appsink"

    def configure_pipeline(self, pipeline, props):
        self._nextOffset = 0

        appsink = pipeline.get_by_name('appsink')
        appsink.set_property('emit-signals', True)
        appsink.connect("new-preroll", self.new_preroll)
        appsink.connect("new-buffer", self.new_buffer)
        appsink.connect("eos", self.eos)

    def _processBuffer(self, buffer):
        if buffer.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            return
        if buffer.flag_is_set(gst.BUFFER_FLAG_DELTA_UNIT):
            return
        if buffer.duration == gst.CLOCK_TIME_NONE:
            return
        self.log("New mp4 fragment, duration=%s offset=%s ts=%s flags=%d" %
                (gst.TIME_ARGS(buffer.duration), buffer.offset,
                 gst.TIME_ARGS(buffer.timestamp), buffer.flags))
        
        # FIXME first buffer is slightly longer.. perhaps because of is-live or sync issue
        self.test.failUnlessApproximates(buffer.duration, 500000000, 66666666)
    ### START OF THREAD-AWARE CODE (called from non-reactor threads)

    def new_preroll(self, appsink):
        buffer = appsink.emit('pull-preroll')

    def new_buffer(self, appsink):
        buffer = appsink.emit('pull-buffer')
        reactor.callFromThread(self._processBuffer, buffer)

    def eos(self, appsink):
        self.debug('received eos')

    ### END OF THREAD-AWARE CODE


class TestFMP4(comptest.CompTestTestCase):

    def setUp(self):
        self.tp = comptest.ComponentTestHelper()
        self.prod = comptest.pipeline_src('videotestsrc is-live=1 ! '
             'video/x-raw-yuv,format=(fourcc)UYVY,'
             'width=(int)320,height=(int)240,framerate=(fraction)30/1')

    def tearDown(self):
        d = self.tp.stop_flow()
        # add cleanup, otherwise components a.t.m. don't cleanup after
        # themselves too well, remove when fixed
        d.addBoth(lambda _: comptest.cleanup_reactor())
        return d

    def testFlow(self):
        enc = comptest.pipeline_cnv(
                'flumch264enc max-keyframe-distance=15 min-keyframe-distance=15')

        properties = {'fragment-duration': 500}
        mux = comptest.ComponentWrapper('fmp4-muxer', fmp4.FMP4,
                                       name='muxer', props=properties,
                                       plugs={})
        tester = comptest.ComponentWrapper('fmp4-tester', FMP4Tester,
                                       name='tester', props=properties,
                                       plugs={})

        self.tp.set_flow([self.prod, enc, mux, tester])

        d = self.tp.start_flow()
        tester.comp.test = self

        # wait for the muxer to go happy
        d.addCallback(lambda _: mux.wait_for_mood(moods.happy))

        # let it run for a few seconds
        d.addCallback(lambda _: comptest.delayed_d(3, _))
        return d
