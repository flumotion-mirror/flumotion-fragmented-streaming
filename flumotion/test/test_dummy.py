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

import setup
setup.setup()

class TestDummy(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def testDummy(self):
        self.failUnless(True)
