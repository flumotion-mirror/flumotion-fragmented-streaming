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

from flumotion.component.common.streamer import fragmentedresource as resources
from twisted.internet import defer
from twisted.web import server
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

__version__ = "$Rev: $"

XML_CONTENT_TYPE = "text/xml"
MANIFEST_NAME = 'Manifest'

CLIENT_ACCESS_POLICY_NAME = "clientaccesspolicy.xml"
CLIENT_ACCESS_POLICY = """
<?xml version="1.0" encoding="utf-8"?>
<access-policy>
    <cross-domain-access>
        <policy>
            <allow-from http-request-headers="*">
                <domain uri="*"/>
            </allow-from>
            <grant-to>
                <resource path="/" include-subpaths="true"/>
            </grant-to>
        </policy>
    </cross-domain-access>
</access-policy>
"""


class SmoothStreamingResource(resources.FragmentedResource):

    logCategory = 'smooth-streamer'

    def __init__(self, streamer, store, httpauth, secretKey, sessionTimeout):
        """
        @param streamer: L{SmoothHTTPLiveStreamer}
        """
        self.store = store
        resources.FragmentedResource.__init__(self, streamer, httpauth,
                secretKey, sessionTimeout)

    def _renderClientAccessPolicy(self, res, request, resource):
        self._writeHeaders(request, XML_CONTENT_TYPE)
        if request.method == 'GET':
            request.write(CLIENT_ACCESS_POLICY)
            self.bytesSent += len(CLIENT_ACCESS_POLICY)
            self._logWrite(request)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderManifest(self, res, request, resource):
        self.debug('_render(): asked for manifest %s', resource)
        self._writeHeaders(request, XML_CONTENT_TYPE)
        if request.method == 'GET':
            manifest = self.store.renderManifest()
            request.setHeader('content-length', len(manifest))
            # under 1.1, make sure to Close, we want clientaccesspolicy.xml
            # to be served by http-server, when running with a porter.
            request.setHeader('Connection', 'Close')
            request.write(manifest)
            self.bytesSent += len(manifest)
            self._logWrite(request)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderFragment(self, res, request, resource):
        p = [c for c in resource.split('/') if c]
        if len(p) != 0 and p[0].startswith("QualityLevels("):
            p[0] = p[0][14:-1]
        else:
            raise resources.FragmentNotAvailable("Invalid fragment request")

        if p[1].startswith("FragmentInfo("):
            p[1] = p[1][13:-1]
            kind = "info"
        elif p[1].startswith("Fragments("):
            p[1] = p[1][10:-1]
            kind = "fragment"
        else:
            raise resources.FragmentNotAvailable("Invalid fragment request")

        try:
            bitrate, (type, time) = p[0], p[1].split("=")
            time = int(time)
        except ValueError:
            raise resources.FragmentNotAvailable("Invalid fragment request")

        fragment, mime, code = self.store.getFragment(bitrate, type, time,
                                                      kind)
        self._writeHeaders(request, mime, code)
        if request.method == 'GET' and code == 200:
            request.setHeader('content-length', len(fragment))
            request.write(fragment)
            self.bytesSent += len(fragment)
        self._logWrite(request)
        request.finish()
        return res

    def _renderError(self, res, request, resource):
        request.write(self._errorMessage(request, http.NOT_FOUND))
        request.finish()
        return res

    def _render(self, request):
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
            return self._renderForbidden(request)
        resource = request.path.replace(self.mountPoint, '', 1)

        d = defer.maybeDeferred(self._checkSession, request)
        # Manifest
        if resource == MANIFEST_NAME:
            d.addCallback(self._renderManifest, request, resource)
        elif resource.endswith(CLIENT_ACCESS_POLICY_NAME):
            d.addCallback(self._renderClientAccessPolicy, request, resource)
        else:
            d.addCallback(self._renderFragment, request, resource)

        d.addErrback(self._renderNotFoundResponse, request)
        return server.NOT_DONE_YET

    render_GET = _render
    render_HEAD = _render
