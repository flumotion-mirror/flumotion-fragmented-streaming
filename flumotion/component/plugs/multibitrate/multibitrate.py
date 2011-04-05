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

from twisted.web.resource import Resource
from twisted.web.static import Data

from flumotion.common import log
from flumotion.common.errors import ComponentStartError
from flumotion.component.misc.httpserver.httpserver import HTTPFileStreamer
from flumotion.component.plugs.base import ComponentPlug

__version__ = "$Rev$"


HEADER = "#EXTM3U"

ENTRY_TEMPLATE = \
"""
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=%(bitrate)d
%(stream-url)s"""

CONTENT_TYPE = "application/vnd.apple.mpegurl"

class PlaylistResource(Resource):
    """I generate the directory used to serve the m3u8 playlist
    It contains::
    - a m3u8 file, usually called main.m3u8.
    """

    def __init__(self, mount_point, properties):
        Resource.__init__(self)

        playlist_name = properties.get('playlist-name', 'main.m3u8')

        self._properties = properties
        self._playlist = self._render_playlist()
        self._playlist_name = playlist_name
        self.putChild(self._playlist_name,
                      self._playlist)

    def _render_playlist(self):
        playlist = [HEADER]

        entries = self._properties.get('playlist-entry', [])

        for entry in entries:
            playlist.append(ENTRY_TEMPLATE % entry)
        return Data("\n".join(playlist), CONTENT_TYPE)


class MultibiratePlaylistPlug(ComponentPlug):
    """I am a component plug for a http-server which plugs in a
    http resource containing a main.m3u8 iphone multibitrate playlsit.
    """

    def start(self, component):
        """
        @type component: L{HTTPFileStreamer}
        """
        if not isinstance(component, HTTPFileStreamer):
            raise ComponentStartError(
                "A MultibitratePlug %s must be plugged into a "
                " HTTPFileStreamer component, not a %s" % (
                self, component.__class__.__name__))
        log.debug('multibitrate', 'Attaching to %r' % (component, ))
        resource = PlaylistResource(component.getMountPoint(),
                                          self.args['properties'])
        component.setRootResource(resource)


def test():
    import sys
    from twisted.internet import reactor
    from twisted.python.log import startLogging
    from twisted.web.server import Site
    startLogging(sys.stderr)

    properties = {
        'playlist-entry': [
                  {'stream-url':
                   'http://example.com/iphone/low/stream.m3u8',
                   'bitrate': 100000},
                  {'stream-url':
                   'http://example.com/iphone/medium/stream.m3u8',
                   'bitrate': 200000},
                  {'stream-url':
                   'http://example.com/iphone/high/stream.m3u8',
                   'bitrate': 400000},
        ]}

    root = PlaylistResource('/', properties)
    site = Site(root)

    reactor.listenTCP(8080, site)
    reactor.run()

if __name__ == "__main__":
    test()
