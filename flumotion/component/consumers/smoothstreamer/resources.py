# -*- Mode: Python -*-
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

from flumotion.component.consumers.applestreamer.common import \
    FragmentNotFound, FragmentNotAvailable, PlaylistNotFound, KeyNotFound
from flumotion.component.consumers.applestreamer.resources import \
    FragmentedResource
from twisted.internet import reactor, error, defer
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

class SmoothStreamingResource(FragmentedResource):

    logCategory = 'smooth-streamer'

    def __init__(self, streamer, store, httpauth, secretKey, sessionTimeout):
        """
        @param streamer: L{SmoothHTTPLiveStreamer}
        """
        self.setMountPoint(streamer.mountPoint)
        self.store = store
        FragmentedResource.__init__(self, streamer, httpauth, secretKey,
            sessionTimeout)

    def _renderClientAccessPolicy(self, res, request, resource):
        self._writeHeaders(request, XML_CONTENT_TYPE)
        if request.method == 'GET':
            request.write(CLIENT_ACCESS_POLICY)
            self.bytesSent += len(CLIENT_ACCESS_POLICY)
            self.logWrite(request)
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
            self.logWrite(request)
        elif request.method == 'HEAD':
            self.debug('handling HEAD request')
        request.finish()
        return res

    def _renderFragment(self, res, request, resource):
        p = [c for c in resource.split('/') if c]
        if len(p) != 0 and p[0].startswith("QualityLevels("):
            p[0] = p[0][14:-1]
        else:
            raise FragmentNotAvailable("Invalid fragment request")

        if p[1].startswith("FragmentInfo("):
            p[1] = p[1][13:-1]
            kind = "info"
        elif p[1].startswith("Fragments("):
            p[1] = p[1][10:-1]
            kind = "fragment"
        else:
            raise FragmentNotAvailable("Invalid fragment request")

        bitrate, (type, time) = p[0], p[1].split("=")
        fragment, mime, code = self.store.getFragment(bitrate, type, int(time), kind)
        self._writeHeaders(request, mime, code)
        if request.method == 'GET' and code == 200:
            request.setHeader('content-length', len(fragment))
            request.write(fragment)
            self.bytesSent += len(fragment)
        self.logWrite(request)
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
        if resource.endswith(MANIFEST_NAME):
            d.addCallback(self._renderManifest, request, resource)
        elif resource.endswith(CLIENT_ACCESS_POLICY_NAME):
            d.addCallback(self._renderClientAccessPolicy, request, resource)
        else:
            d.addCallback(self._renderFragment, request, resource)

        d.addErrback(self._renderNotFoundResponse, request)
        return server.NOT_DONE_YET

    render_GET = _render
    render_HEAD = _render
