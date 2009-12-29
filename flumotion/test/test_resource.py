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

import base64

from twisted.trial import unittest
from twisted.web import server
from twisted.web.http import Request, HTTPChannel
from twisted.internet import defer, reactor
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

from flumotion.component.consumers.applestreamer import resources, hlsring
from flumotion.component.base.http import HTTPAuthentication

import setup
setup.setup()

MAIN_PLAYLIST=\
"""#EXTM3U
#EXT-X-ALLOW-CACHE:YES
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10,
http://localhost/mpegts-0.ts
"""

FRAGMENT = 'fragment1'

class FakeStreamer():

    def __init__(self):
        self.clients = 0
        self.currentBitRate = 1000
        self.ready = True
        self.mountPoint = "localhost"
        self.ring = hlsring.HLSRing("localhost", "main.m3u8", "stream.m3u8", "")
        self.ring.addFragment(FRAGMENT, 0, 10)
        self.plugs = {}
        self.httpauth = HTTPAuthentication(self)

    def clientAdded(self):
        self.clients += 1

    def clientremoved(self):
        self.clients -=1

    isReady = lambda s: s.ready
    getClients = lambda s: str(s.clients)
    getCurrentBitrate = lambda s: s.currentBitRate
    getRing = lambda s: s.ring
    getName = lambda s: s.getName


class FakeTransport:

    def __init__(self):
        pass

    def writeSequence(self, seq):
        pass

    def fileno(self):
        return None

    def write(self, data):
        pass

    def read(self, data):
        pass

    def __getatt__(self, attr):
        return ''

class FakeRequest:
    transport = FakeTransport()

    def __init__(self, site, method, path, args={}, onFinish=None):
        self.site = site
        self.method = method
        self.path = path
        self.uri = 'http://'+path
        self.args = args
        self.cookies = {}
        self.session = None
        self.headers = {}
        self.response = http.OK
        self.data = ""
        self.clientproto=''
        self.code=''

        self.onFinish=onFinish

        self.user = "fakeuser"
        self.passwd = "fakepasswd"
        self.ip = "255.255.255.255"

        # fake out request.transport.fileno
        self.fdIncoming = 3

        # copied from test_web.DummyRequest
        self.sitepath = []
        self.prepath = []
        self.postpath = ['']

    def setResponseCode(self, code):
        self.response = code

    def setHeader(self, field, value):
        self.headers[field] = value

    def addCookie(self, cookieName, cookie, path="/"):
        self.cookies[cookieName] = cookie

    def getCookie(self, cookieName):
        return self.cookies.get(cookieName, None)

    def write(self, text):
        self.data = self.data + text

    def finish(self):
        if isinstance(self.onFinish, defer.Deferred):
            self.onFinish.callback(self)

    getUser = lambda s: s.user
    getPassword = lambda s: s.passwd
    getClientIP = lambda s: s.ip
    getAllHeaders = lambda s: s.headers
    getBytesSent = lambda s: ''
    getDuration = lambda s: 0


class TestAppleStreamerSessions(unittest.TestCase):

    def processRequest(self, method, path):
        d = defer.Deferred()
        request = FakeRequest(self.site, method, path, onFinish=d)
        self.resource.render_GET(request)
        return d

    def checkResponse(self, response, expected):
        self.assertEquals(response.data, expected)
        for d in reactor.getDelayedCalls():
            d.cancel()

    def setUp(self):
        self.streamer = FakeStreamer()
        self.resource = resources.HTTPLiveStreamingResource(
                self.streamer, self.streamer.httpauth)
        self.site = server.Site(self.resource)

    def testNotReady(self):
        self.streamer.ready = False
        request = FakeRequest(self.site, "GET", "/test")
        self.resource.render_GET(request)
        self.assertEquals(request.response, http.SERVICE_UNAVAILABLE)

    def testServerFull(self):
        self.resource.reachedServerLimits = lambda : True
        request = FakeRequest(self.site, "GET", "/test")
        self.resource.render_GET(request)
        self.assertEquals(request.response, http.SERVICE_UNAVAILABLE)

    def testForbiddenRequest(self):
        request = FakeRequest(self.site, "GET", "test.m3u8")
        self.resource.render_GET(request)
        expected = resources.ERROR_TEMPLATE % {
                'code' : http.FORBIDDEN,
                'error': http.RESPONSES[http.FORBIDDEN]}
        self.assertEquals(expected, request.data)

    def testPlaylistNotFound(self):
        d = self.processRequest("GET","/localhost/test.m3u8")
        expected = resources.ERROR_TEMPLATE % {
                'code' : http.NOT_FOUND,
                'error': http.RESPONSES[http.NOT_FOUND]}
        d.addCallback(self.checkResponse, expected)
        return d

    def testFragmentNotFound(self):
        d = self.processRequest("GET","/localhost/test.ts")
        expected = resources.ERROR_TEMPLATE % {
                'code' : http.NOT_FOUND,
                'error': http.RESPONSES[http.NOT_FOUND]}
        d.addCallback(self.checkResponse, expected)
        return d

    def testGetMainPlaylist(self):
        d = self.processRequest("GET","/localhost/stream.m3u8")
        d.addCallback(self.checkResponse, MAIN_PLAYLIST)
        return d

    def testGetFragment(self):
        d = self.processRequest("GET","/localhost/mpegts-0.ts")
        d.addCallback(self.checkResponse, FRAGMENT)
        return d

    def testNewSession(self):
        def checkSessionCreated(request):
            cookie = request.getCookie(resources.COOKIE_NAME)
            self.failIf(cookie is None)
            sessionID = base64.b64decode(cookie).split(':')[0]
            session = self.site.sessions.get(sessionID, None)
            self.failIf(session is None)
            for d in reactor.getDelayedCalls():
                d.cancel()

        d = self.processRequest("GET","/localhost/stream.m3u8")
        d.addCallback(checkSessionCreated)
        return d

'''
sessionExpired is never fired
    def testSessionExpired(self):
        def sessionExpired(result):
            self.assert_(True)
            for d in reactor.getDelayedCalls():
                d.cancel()

        def checkSessionExpired(request, d):
            cookie = request.getCookie(resources.COOKIE_NAME)
            self.failIf(cookie is None)
            sessionID = base64.b64decode(cookie).split(':')[0]
            session = self.site.sessions.get(sessionID, None)
            self.failIf(session is None)
            d.addCallback(sessionExpired)
            session.notifyOnExpire(d.callback)

        d = self.processRequest("GET","/localhost/stream.m3u8")
        d1 = defer.Deferred()
        d.addCallback(checkSessionExpired, d1)
        return d1
'''

















if __name__ == '__main__':
    unittest.main()
