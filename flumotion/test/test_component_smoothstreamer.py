# -*- Mode: Python; test-case-name: flumotion.test.test_resource -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2009,2010 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.
# flumotion-fragmented-streaming - Flumotion Advanced  fragmented streaming

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import setup
setup.setup()

from twisted.trial import unittest
try:
    from twisted.web import client
except ImportError:
    from twisted.protocols import client

from flumotion.common import log, testsuite, netutils, gstreamer
from flumotion.common.planet import moods
from flumotion.test import comptest

from flumotion.component.consumers.smoothstreamer.smoothstreamer \
    import SmoothHTTPLiveStreamer

attr = testsuite.attr

CONFIG = {
    'feed': [],
    'name': 'smooth-streamer',
    'parent': 'default',
    'eater': {'default': [('muxer-video:default', 'default')]},
    'source': ['muxer-video:default'],
    'avatarId': '/default/smooth-streamer',
    'clock-master': None,
    'plugs': {
        'flumotion.component.plugs.streamdata.StreamDataProviderPlug': [],
        'flumotion.component.plugs.request.RequestLoggerPlug': [],
    },
    'type': 'http-smoothstreamer',
}


class SmoothStreamerTestCase(comptest.CompTestTestCase, log.Loggable):

    properties = {}
    config = CONFIG

    def setUp(self):
        config = self.getConfig()
        config['properties'] = self.properties.copy()
        self.component = SmoothHTTPLiveStreamer(config)

    def tearDown(self):
        return self.component.stop()

    def getConfig(self):
        # test classes can override this to change/extend config
        return self.config.copy()

# test based on test_component_httpstreamer.py
# (FIXME: write base test class for all http-streamer)


class TestSmoothStreamerNoPlug(SmoothStreamerTestCase):

    def testGetUrlIsManifest(self):
        self.failUnless(self.component.getUrl().endswith("Manifest"))


class TestSmoothStreamerDataPlug(SmoothStreamerTestCase):

    def getConfig(self):
        config = CONFIG.copy()
        sType = 'flumotion.component.plugs.streamdata.StreamDataProviderPlug'
        pType = 'streamdataprovider-example'
        config['plugs'] = {sType: [
            {
                'entries': {
                    'default': {
                        'module-name': 'flumotion.component.plugs.streamdata',
                        'function-name': 'StreamDataProviderExamplePlug',
                    }
                }
            },
        ]}
        return config

    def testGetStreamData(self):
        streamData = self.component.getStreamData()
        self.assertEquals(streamData['protocol'], 'HTTP')
        self.assertEquals(streamData['description'], 'Flumotion Stream')
        self.failUnless(streamData['url'].startswith('http://'))
    # plug is started before component can do getUrl
    testGetStreamData.skip = 'See #1137'


class TestSmoothStreamer(comptest.CompTestTestCase, log.Loggable):

    slow = True # and ugly...

    def setUp(self):
        if not gstreamer.element_factory_exists('keyunitscheduler'):
            from flumotion.component.effects.kuscheduler \
                    import kuscheduler
            kuscheduler.register()
        self.tp = comptest.ComponentTestHelper()
        prod = ('videotestsrc is-live=1 ! ' \
                'video/x-raw-yuv,width=(int)320,height=(int)240, '\
                    'framerate=(fraction)30/1 ! ' \
                'keyunitsscheduler interval = 1000000000 !' \
                'flumch264enc ! ismlmux ' \
                'trak-timescale=10000000 movie-timescale=10000000')
        self.s = \
            'flumotion.component.consumers.smoothstreamer.'\
            'SmoothHTTPLiveStreamer'

        self.prod = comptest.pipeline_src(prod)

    def tearDown(self):
        d = comptest.delayed_d(1, None)
        d.addCallback(comptest.cleanup_reactor)
        return d

    def _getFreePort(self):
        while True:
            port = netutils.tryPort()
            if port is not None:
                break

        return port

    def _initComp(self):
        self.compWrapper =\
           comptest.ComponentWrapper('http-smoothstreamer',
                                     SmoothHTTPLiveStreamer,
                                     name='smooth-streamer',
                                     props={'mount-point': 'mytest',
                                            'port': self._getFreePort()})
        self.tp.set_flow([self.prod, self.compWrapper])


        d = self.tp.start_flow()
        d.addCallback(lambda _:
             self.__setattr__('comp', self.compWrapper.comp))
        # wait for the converter to go happy
        d.addCallback(lambda _: self.compWrapper.wait_for_mood(moods.happy))
        return d

    def getURL(self, path):
        # path should start with /
        return 'http://localhost:%d%s' % (self.compWrapper.comp.port, path)

    def testManifestAndFragment(self):
        d = self._initComp()

        d.addCallback(lambda _: comptest.delayed_d(2.0, _))

        def check_manifest(r):
            from xml.dom.minidom import parseString
            media = parseString(r)
            c = media.getElementsByTagName("SmoothStreamingMedia")[0]\
                      .getElementsByTagName("StreamIndex")[0]\
                      .getElementsByTagName("c")
            # in 2 seconds after being happy we should really have at
            # least 2 fragments (1 second of encoded data more)
            self.failIf(len(c) < 2)
            # return last known timestamp
            return int(c[-1].getAttribute("t"))

        d.addCallback(lambda _: \
                client.getPage(self.getURL('/mytest/Manifest')))
        d.addCallback(check_manifest)

        def check_fragment(f):
            # make sure we get at least 1k of encoded video fragment..
            self.failIf(len(f) < 1000)
            # and that we got a moof
            self.assertEqual(f[4:8], "moof")

        url = '/mytest/QualityLevels(400000)/Fragments(video=%d)'
        d.addCallback(lambda t: client.getPage(
            self.getURL(url % t)))
        d.addCallback(check_fragment)

        # and finally stop the flow
        # d.addCallback(lambda _: self.tp.stop_flow())

        return d

if __name__ == '__main__':
    unittest.main()
