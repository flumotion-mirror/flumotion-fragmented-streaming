# -*- Mode: Python; test-case-name: flumotion.test.test_hls_ring -*-
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

from flumotion.component.consumers.applestreamer import hlsring

import setup
setup.setup()


class TestHLSRing(unittest.TestCase):

    MAIN_PLAYLIST = """\
#EXTM3U
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=300000
http://localhost:8000/stream.m3u8
"""

    STREAM_PLAYLIST = """\
#EXTM3U
#EXT-X-ALLOW-CACHE:YES
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:1
#EXTINF:2,Title
http://localhost:8000/mpegts-1.ts
#EXTINF:2,Title
http://localhost:8000/mpegts-2.ts
#EXTINF:2,Title
http://localhost:8000/mpegts-3.ts
#EXTINF:2,Title
http://localhost:8000/mpegts-4.ts
#EXTINF:2,Title
http://localhost:8000/mpegts-5.ts
"""

    def setUp(self):
        self.ring = hlsring.HLSRing('localhost', 'live.m3u8', 'stream.m3u8',
                'title', window=5)

    def testAddFragment(self):
        self.ring.addFragment('', 0, 10)
        self.assertEqual(len(self.ring._fragmentsDict), 1)
        self.assertEqual(len(self.ring._availableFragments), 1)
        self.assert_(self.ring._availableFragments[0] in
                self.ring._fragmentsDict)

    def testGetFragment(self):
        self.ring.addFragment('string', 0, 10)
        fragment = self.ring.getFragment(self.ring._availableFragments[0])
        self.assertEqual(fragment, 'string')

    def testWindowSize(self):
        for i in range(6):
            self.ring.addFragment('fragment-%s' % i, i, 10)
        self.assertEqual(len(self.ring._availableFragments), 5)
        self.assertEqual(len(self.ring._fragmentsDict), 5)
        self.ring.addFragment('fragment-5', 0, 10)
        self.assertEqual(len(self.ring._availableFragments), 5)
        self.assertEqual(len(self.ring._fragmentsDict), 5)
        self.assert_('fragment-0' not in self.ring._fragmentsDict)
        self.assert_('fragment-0' not in self.ring._availableFragments)

    def testDuplicatedSegments(self):
        for i in range(6):
            self.ring.addFragment('fragment', 0, 10)
        self.assertEqual(len(self.ring._availableFragments), 1)
        self.assertEqual(len(self.ring._fragmentsDict), 1)

    def testHostname(self):
        self.ring.setHostname('/localhost:8000')
        self.assertEqual(self.ring._hostname, 'http://localhost:8000/')

    def testMainPlaylist(self):
        self.ring._hostname = 'http://localhost:8000/'
        self.assertEqual(self.ring._renderMainPlaylist(), self.MAIN_PLAYLIST)

    def testStreamPlaylist(self):
        self.ring._hostname = 'http://localhost:8000/'
        self.ring.title = 'Title'
        for i in range(6):
            self.ring.addFragment('', i, 2)
        self.assertEqual(self.ring._renderStreamPlaylist(),
                self.STREAM_PLAYLIST)

if __name__ == '__main__':
    unittest.main()
