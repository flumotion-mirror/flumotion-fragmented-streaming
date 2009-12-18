# -*- Mode: Python; test-case-name: flumotion.test.test_httptokenbouncer -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.
# flumotion-bouncers - Flumotion Advanced bouncers

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

from twisted.trial import unittest
from twisted.internet import defer, reactor

from flumotion.common import testsuite
from flumotion.common import log, errors
from flumotion.common.planet import moods
from flumotion.test import comptest

from flumotion.component.muxers.mpegts import mpegts

import setup
setup.setup()


class TestMPEGTS(comptest.CompTestTestCase):

    def setUp(self):
        self.tp = comptest.ComponentTestHelper()
        self.prod = comptest.pipeline_src('videotestsrc ! video/x-raw-yuv,format=(fourcc)UYVY,width=(int)320,height=(int)240,framerate=(fraction)30/1')

    def tearDown(self):
        d = self.tp.stop_flow()
        # add cleanup, otherwise components a.t.m. don't cleanup after
        # themselves too well, remove when fixed                                                                d.addBoth(lambda _: comptest.cleanup_reactor())
        return d

    def testFlow(self):
        properties = {'rewrite-offset': False}
        mt = comptest.ComponentWrapper('mpegts-muxer', mpegts.MPEGTS,
                                       name='tsmuxer', props=properties,
                                       plugs={})

        enc = comptest.pipeline_cnv('flumch264enc')
        self.tp.set_flow([self.prod, enc, mt])

        d = self.tp.start_flow()

        # wait for the disker to go happy
        d.addCallback(lambda _: enc.wait_for_mood(moods.happy))

        # let it run for a few seconds
        d.addCallback(lambda _: comptest.delayed_d(2, _))
        return d
