# -*- Mode: Python; test-case-name: flumotion.test.test_http -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.GPL" in the source distribution for more information.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import time
import base64
import hmac
from datetime import datetime, timedelta

from twisted.internet import defer
from twisted.web import server, resource

try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

from flumotion.configure import configure
from flumotion.common import log, uuid
from flumotion.component.consumers.httpfragstreamer.common import\
    FragmentNotFound, PlaylistNotFound, KeyNotFound


__version__ = "$Rev: $"

HTTP_NAME = 'FlumotionHTTPFragmentedServer'
HTTP_VERSION = configure.version
HTTP_SERVER = '%s/%s' % (HTTP_NAME, HTTP_VERSION)

M3U8_CONTENT_TYPE = 'application/vnd.apple.mpegurl'
PLAYLIST_EXTENSION = '.m3u8'
SESSION_TIMEOUT = 10
COOKIE_NAME = 'flumotion-session'
SECRET='2Ed4sB/s#D%&"DGs36y5'
NOT_VALID = 0
VALID= 1
RENEW_AUTH = 2

ERROR_TEMPLATE = """<!doctype html public "-//IETF//DTD HTML 2.0//EN">
<html>
<head>
  <title>%(code)d %(error)s</title>
</head>
<body>
<h2>%(code)d %(error)s</h2>
</body>
</html>
"""

### the Twisted resource that handles the base URL


class HTTPLiveStreamingResource(resource.Resource, log.Loggable):

    # IResource interface variable; True means it will not chain requests
    # further down the path to other resource providers through
    # getChildWithDefault
    isLeaf = True

    def __init__(self, streamer, httpauth):
        """
        @param streamer: L{HTTPFragmentStreamer}
        """
        self.streamer = streamer
        self.httpauth = httpauth
        self.setMountPoint(streamer.mountPoint)
        self.ring = streamer.getRing()

        self.maxclients = self.getMaxAllowedClients(-1)
        self.maxbandwidth = -1 # not limited by default

        # If set, a URL to redirect a user to when the limits above are reached
        self._redirectOnFull = None

        self.bytesSent = 0
        self.bytesReceived = 0
        self.logFilters = None

        socket = 'flumotion.component.plugs.request.RequestLoggerPlug'
        self.loggers = streamer.plugs.get(socket, [])

        socket = \
            'flumotion.component.plugs.requestmodifier.RequestModifierPlug'
        self.modifiers = streamer.plugs.get(socket, [])

        resource.Resource.__init__(self)

    def setMountPoint(self, mountPoint):
        if not mountPoint.startswith('/'):
            mountPoint = '/' + mountPoint
        if not mountPoint.endswith('/'):
            mountPoint = mountPoint + '/'
        self.mountPoint = mountPoint

    def setRoot(self, path):
        self.putChild(path, self)

    def setLogFilter(self, logfilter):
        self.logfilter = logfilter

    def rotateLogs(self):
        """
        Close the logfile, then reopen using the previous logfilename
        """
        for logger in self.loggers:
            self.debug('rotating logger %r' % logger)
            logger.rotate()

    def logWrite(self, request):

        headers = request.getAllHeaders()
        if self.httpauth:
            username = self.httpauth.bouncerName
        else:
            username = '-'

        args = {'ip': request.getClientIP(),
                'time': time.gmtime(),
                'method': request.method,
                'uri': request.uri,
                'username': username, # FIXME: put the httpauth name
                'get-parameters': request.args,
                'clientproto': request.clientproto,
                'response': request.code,
                'bytes-sent': 0, #TODO
                'referer': headers.get('referer', None),
                'user-agent': headers.get('user-agent', None),
                'time-connected': 0, #TODO
                'session-id': request.session.uid}

        l = []
        for logger in self.loggers:
            l.append(defer.maybeDeferred(
                logger.event, 'http_request_completed', args))

        return defer.DeferredList(l)

    def setUserLimit(self, limit):
        self.info('setting maxclients to %d' % limit)
        self.maxclients = self.getMaxAllowedClients(limit)
        # Log what we actually managed to set it to.
        self.info('set maxclients to %d' % self.maxclients)

    def setBandwidthLimit(self, limit):
        self.maxbandwidth = limit
        self.info("set maxbandwidth to %d", self.maxbandwidth)

    def setRedirectionOnLimits(self, url):
        self._redirectOnFull = url

    def getMaxAllowedClients(self, maxclients):
        """
        maximum number of allowed clients based on soft limit for number of
        open file descriptors and fd reservation. Increases soft limit to
        hard limit if possible.
        """
        #FIXME
        return maxclients

    def reachedServerLimits(self):
        if self.maxclients >= 0 and len(self._sessions) >= self.maxclients:
            return True
        elif self.maxbandwidth >= 0:
            # Reject if adding one more client would take us over the limit.
            if ((len(self._sessions) + 1) *
                    self.streamer.getCurrentBitrate() >= self.maxbandwidth):
                return True
        return False

    def isReady(self):
        return self.streamer.isReady()

    def _renewAuthentication(self, request, sessionID, authResponse):
        # Delete, if it's present, the 'flumotion-session' cookie
        for cookie in request.cookies:
            if cookie.startswith('%s=%s' % (COOKIE_NAME, cookie)):
                self.log("delete old cookie for session ID=%s" % sessionID)
                request.cookies.remove(cookie)

        if authResponse and authResponse.duration != 0:
            authExpiracy = time.mktime((datetime.utcnow() +
            timedelta(seconds=authResponse.duration)).timetuple())
        else:
            authExpiracy = 0
        # Create a new token with the same Session ID and the renewed
        # authentication's expiration time
        token = self._generateToken(
                sessionID, request.getClientIP(), authExpiracy)
        request.addCookie(COOKIE_NAME,token, path=self.mountPoint)

    def _checkSession(self, request):
        """
        From t.w.s.Request.getSession()
        Associates the request to a session using the 'flumotion-session'
        cookie and updates the session's timeout.
        If the authentication has expired, re-authenticates the session and
        updates the cookie with the new authentication's expiracy time.
        If the cookie is not valid (bad IP or bad signature) or the session
        has expired, it creates a new session.
        """
        if not request.session:
            cookie = request.getCookie(COOKIE_NAME)
            if cookie:
                # The request has a flumotion cookie
                cookieState = self._cookieIsValid(cookie,
                        request.getClientIP())
                sessionID = base64.b64decode(cookie).split(':')[0]
                if cookieState != NOT_VALID:
                    # The cookie is valid: retrieve or create a session
                    try:
                        # The session exists in this streamer
                        request.session = request.site.getSession(sessionID)
                    except KeyError:
                        # The session doesn't exist
                        # FIXME: We might want to be able to use the same
                        # session in several streamer. Create a new session
                        # here using the same sessionID
                        pass
                    if cookieState == RENEW_AUTH:
                        # The authentication as expired, renew it
                        self.debug('renewing authentication')
                        d = self.httpauth.startAuthentication(request)
                        d.addCallback(lambda res:
                            self._renewAuthentication(request, sessionID, res))
                        return d

            # if it still hasn't been set, fix it up.
            if not request.session:
                self.debug('asked for authentication')
                d = self.httpauth.startAuthentication(request)
                d.addCallback(lambda res:
                    self._createSession(request, authResponse=res))
                return d

        request.session.touch()

    def _createSession(self, request, authResponse=None):
        """
        From t.w.s.Site.makeSession()
        Generates a new Session instance and store it for future reference
        """
        sessionID = uuid.uuid1().hex
        if authResponse and authResponse.duration is not 0:
            authExpiracy = time.mktime((datetime.utcnow() +
            timedelta(seconds=authResponse.duration)).timetuple())
        else:
            authExpiracy = 0

        token = self._generateToken(
                sessionID, request.getClientIP(), authExpiracy)

        request.session = request.site.sessions[sessionID] =\
                request.site.sessionFactory(request.site, sessionID)
        request.session.startCheckingExpiration(SESSION_TIMEOUT)
        request.session.sessionTimeout= SESSION_TIMEOUT
        request.session.notifyOnExpire(lambda:
                self._delClient(sessionID))
        request.addCookie(COOKIE_NAME, token, path=self.mountPoint)

        self._addClient()
        self.log('adding new client with session id: "%s"' % request.session.uid)

    def _generateToken(self, sessionID, clientIP, authExpiracy):
        """
        Generate a cryptografic token:
        PAYLOAD=SESSION_ID||:||CLIENT_IP||:||AUTH_EXPIRACY
        SIG=HMAC(SECRET,PAYLOAD)
        TOKEN=BASE64(PAYLOAD||:||SIG)
        """
        payload = ':'.join([sessionID, clientIP, str(authExpiracy)])
        sig = hmac.new(SECRET, payload).hexdigest()
        return base64.b64encode(':'.join([payload,sig]))

    def _cookieIsValid(self, cookie, clientIP):
        """
        Checks whether the cookie is valid against clientIP, the
        authentication expiracy date and the signature.
        Returns the state of the cookie among 3 states:
        VALID: the cookie is valid (client IP, expiracy and signature are OK)
        RENEW_AUTH: the cookie is valid but the authentication has expired
        NOT_VALID: the cookie is not valid
        """
        token = base64.b64decode(cookie)
        try:
            payload, sig = token.rsplit(':',1)
            sessionID, sessionIP, authExpiracy =\
                    payload.split(':')
        except:
            self.debug("cookie is not valid. reason: malformed cookie")
            return NOT_VALID

        self.log("cheking cookie authentication: "
                "client_ip=%s auth_expiracy:%s" % (sessionIP, authExpiracy))
        # Check signature
        if hmac.new(SECRET,payload).hexdigest() != sig:
            self.debug("cookie is not valid. reason: invalid signature")
            return NOT_VALID
        # Check client IP
        if sessionIP != clientIP:
            self.debug("cookie is not valid. reason: bad client IP")
        # Check authentication expiracy
        if int(authExpiracy) != 0 and int(authExpiracy) < \
                time.mktime(datetime.utcnow().timetuple()):
            self.debug("cookie is not valid. reason: authentication expired")
            return RENEW_AUTH
        self.log("cookie is valid")
        return VALID

    def _addClient(self):
        self.streamer.clientAdded()

    def _delClient(self, uid):
        self.log("session %s expired" % uid)
        self.streamer.clientRemoved()

    def _errorMessage(self, request, error_code):
        request.setHeader('content-type', 'html')
        request.setHeader('server', HTTP_VERSION)
        request.setResponseCode(error_code)

        return ERROR_TEMPLATE % {'code': error_code,
                                 'error': http.RESPONSES[error_code]}

    def _handleNotReady(self, request):
        self.debug("Not sending data, it's not ready")
        return self._errorMessage(request, http.SERVICE_UNAVAILABLE)

    def _handleServerFull(self, request):
        if self._redirectOnFull:
            self.debug("Redirecting client, client limit %d reached",
                self.maxclients)
            error_code = http.FOUND
            request.setHeader('location', self._redirectOnFull)
        else:
            self.debug('Refusing clients, client limit %d reached' %
                self.maxclients)
            error_code = http.SERVICE_UNAVAILABLE
        return self._errorMessage(request, error_code)

    def _renderNotFoundResponse(self, request, error):
        notFoundErrors = [FragmentNotFound, PlaylistNotFound,
                KeyNotFound, PlaylistNotFound]
        if error not in notFoundErrors:
            self.warning("a request ended-up with the following\
                    exception: %s" % error)
        request.write(self._errorMessage(request, http.NOT_FOUND))
        request.finish()
        return ''

    def _renderKey(self, res, request):
        self._writeHeaders(request, 'binary/octect-stream')
        request.setHeader('Pragma', 'no-cache')

        if request.method == 'GET':
            key = self.ring.getEncryptionKey(request.args['key'][0])
            request.write(key)
            self.bytesSent += len(key)
            self.logWrite(request)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderPlaylist(self, res, request, resource):
        self.debug('_render(): asked for playlist %s' % resource)
        self._writeHeaders(request, M3U8_CONTENT_TYPE)
        if request.method == 'GET':
            playlist = self.ring.renderPlaylist(resource)
            request.write(playlist)
            self.bytesSent += len(playlist)
            self.logWrite(request)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderFragment(self, res, request, resource):
        self.debug('_render(): asked for fragment %s' % resource)
        self._writeHeaders(request, 'video/mpeg')
        if request.method == 'GET':
            data = self.ring.getFragment(resource)
            request.write(data)
            self.bytesSent += len(data)
            self.logWrite(request)
        if request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _writeHeaders(self, request, content):
        """
        Write out the HTTP headers for the incoming HTTP request.
        """

        request.setResponseCode(200)
        request.setHeader('Server', HTTP_SERVER)
        request.setHeader('Date', http.datetimeToString())
        request.setHeader('Connection', 'close')
        request.setHeader('Cache-Control', 'no-cache')
        request.setHeader('Cache-Control', 'private')
        request.setHeader('Content-type', content)

        # Call request modifiers
        for modifier in self.modifiers:
            modifier.modify(request)

        # Mimic Twisted as close as possible
        headers = []
        for name, value in request.headers.items():
            headers.append('%s: %s\r\n' % (name.capitalize(), value))
        for cookie in request.cookies:
            headers.append('%s: %s\r\n' % ("Set-Cookie", cookie))

    def _render(self, request):
        self.info('Incoming client connection from %s' % (
            request.getClientIP()))
        self.debug('_render(): request %s' % (request))

        if not self.isReady():
            return self._handleNotReady(request)
        if self.reachedServerLimits():
            return self._handleServerFull(request)

        # A GET request will be like 'mountpoint+resource':
        # 'GET /iphone/fragment-0.ts' or 'GET /fragment-0.ts'
        # The mountpoint is surrounded by '/' in setMountPoint()
        # so we can safely look for the mountpoint and extract the
        # resource name
        if not request.path.startswith(self.mountPoint):
            return self._renderNotFoundResponse(request)
        resource = request.path.replace(self.mountPoint, '', 1)

        d = defer.maybeDeferred(self._checkSession, request)

        # Playlists
        if resource.endswith(PLAYLIST_EXTENSION):
            d.addCallback(self._renderPlaylist, request, resource)
        # Keys
        elif resource == 'key' and 'key' in request.args:
            d.addCallback(self._renderKey, request)
        # Fragments
        else:
            d.addCallback(self._renderFragment, request, resource)

        #d.addErrback(lambda x, request:
        #        self._renderNotFoundResponse(request, x), request)
        return server.NOT_DONE_YET

    def getBytesSent(self):
        return self.bytesSent

    def getBytesReceived(self):
        return self.bytesReceived

    render_GET = _render
    render_HEAD = _render
