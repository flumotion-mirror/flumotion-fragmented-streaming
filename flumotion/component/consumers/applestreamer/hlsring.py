# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2008,2009 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

import os
from collections import deque

from Crypto.Cipher import AES

from flumotion.component.consumers.applestreamer import common


class Playlister:
    """
    I write Apple HTTP Live Streaming playlists based on added segments.
    """

    def __init__(self):

        self._hostname = ''
        self.mainPlaylist = ''
        self.streamPlaylist = ''
        self.title = ''
        self.fragmentPrefix = ''
        self.window = 0
        self.keysURI = ''
        #FIXME: Make it a property
        self.allowCache = True
        self._duration = 0
        self._fragments = []
        self._counter = None
        self._done = False

    def setHostname(self, hostname):
        if hostname.startswith('/'):
            hostname = hostname[1:]
        if not hostname.endswith('/'):
            hostname = hostname + '/'
        if not hostname.startswith('http://'):
            hostname = 'http://' + hostname
        self._hostname = hostname

    def setAllowCache(self, allowed):
        self.allowCache = allowed

    def _addPlaylistFragment(self, sequenceNumber, duration, encrypted):
        # FIXME: We supose all the fragments have the same duration
        if self._counter is None:
            # This value MUST remain constant
            self._duration = duration
        self._counter = sequenceNumber + 1
        fragmentName = '%s-%s.ts' % (self.fragmentPrefix, sequenceNumber)
        self._fragments.append((fragmentName, duration, encrypted))
        while len(self._fragments) > self.window:
            del self._fragments[0]
        return fragmentName

    def _renderMainPlaylist(self):
        lines = []

        lines.append("#EXTM3U")
        #The bandwith value is not significant for single bitrate
        lines.append("#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=300000")
        lines.append(self._hostname + self.streamPlaylist)
        lines.append("")

        return "\n".join(lines)

    def _renderStreamPlaylist(self):
        lines = []

        lines.append("#EXTM3U")
        lines.append("#EXT-X-ALLOW-CACHE:%s" %
                (self.allowCache and 'YES' or 'NO'))
        lines.append("#EXT-X-TARGETDURATION:%d" % self._duration)
        lines.append("#EXT-X-MEDIA-SEQUENCE:%d" %
            (self._counter - len(self._fragments)))

        for fragment, duration, encrypted in self._fragments:
            if encrypted:
                lines.append('#EXT-X-KEY:METHOD=AES-128,URI="%skey?key=%s"' %
                        (self.keysURI, fragment))
            lines.append("#EXTINF:%d,%s" % (duration, self.title))
            lines.append(self._hostname + fragment)

        lines.append("")

        return "\n".join(lines)

    def renderPlaylist(self, playlist):
        '''
        Returns a string representation of the requestd playlist or raise
        an Exception if the playlist is not found
        '''
        if playlist == self.mainPlaylist:
            return self._renderMainPlaylist()
        elif playlist == self.streamPlaylist:
            return self._renderStreamPlaylist()
        raise common.PlaylistNotFound()


class HLSRing(Playlister):
    '''
    I hold a ring with the fragments available in the playlist
    and update the playlist according to this.
    '''

    BLOCK_SIZE = 16
    PADDING = '0'

    def __init__(self, hostname, mainPlaylist, streamPlaylist, title,
            fragmentPrefix='mpegts', window=5, keyInterval=0, keysURI=None):
        '''
        @param hostname:        hostname to use in the playlist
        @type  hostname:        str
        @param mainPlaylist:    resource name of the main playlist
        @type  mainPlaylist:    str
        @param streamPlaylists: resource names of the playlists
        @type  streamPlaylist:  str
        @param title:           description of the stream
        @type  title:           str
        @param fragmentPrefix:  fragment name prefix
        @type  fragmentPrefix:  str
        @param window:          maximum number of fragments to buffer
        @type  window:          int
        @param keyInterval:     number of fragments sharing the same encryption
                                key. O if not using encryption
        @type  keyInterval:     int
        @param keysURI          URI used to retrieve the encription keys
        @type  keysURI          str

        '''
        Playlister.__init__(self)
        self.setHostname(hostname)
        self.mainPlaylist = mainPlaylist
        self.streamPlaylist = streamPlaylist
        self.title = title
        self.fragmentPrefix = fragmentPrefix
        self.window = window
        self.keyInterval = keyInterval
        self.keysURI = keysURI or self._hostname
        self._encrypted = (keyInterval != 0)
        self._fragmentsDict = {}
        self._keysDict = {}
        self._secret = ''
        self._availableFragments = deque('')

    def _encryptFragment(self, fragment, secret, IV):
        right_pad = lambda s: s + (self.BLOCK_SIZE -len(s) % self.BLOCK_SIZE)\
                * self.PADDING
        left_pad = lambda s: (self.BLOCK_SIZE -len(s) % self.BLOCK_SIZE)\
                * self.PADDING + s
        EncodeAES = lambda c, s: c.encrypt(right_pad(s))

        a = left_pad(str(IV))
        cipher = AES.new(secret, AES.MODE_CBC, left_pad(str(IV)))
        return EncodeAES(cipher, fragment)

    def addFragment(self, fragment, sequenceNumber, duration):
        '''
        Adds a fragment to the ring and updates the playlist.
        If the ring is full, removes the oldest fragment.

        @param fragment:        mpegts raw fragment
        @type  fragment:        array
        @param sequenceNumber:  sequence number relative to the stream's start
        @type  sequenceNumber:  int
        @param duration:        duration of the the segment in seconds
        @type  duration:        int
        '''

        # We only care about the name used in the playlist, we let the
        # playlister name it using an appropiate extension
        fragmentName = self._addPlaylistFragment(sequenceNumber, duration,
                self._encrypted)

        # Don't add duplicated fragments
        if fragmentName in self._availableFragments:
            return

        # If the ring is full, delete the oldest segment
        while len(self._fragmentsDict) >= self.window:
            pop = self._availableFragments.popleft()
            del self._fragmentsDict[pop]
            if pop in self._keysDict:
                del self._keysDict[pop]

        self._availableFragments.append(fragmentName)
        if self._encrypted:
            if sequenceNumber % self.keyInterval == 0:
                self._secret = os.urandom(self.BLOCK_SIZE)
            fragment = self._encryptFragment(fragment, self._secret,
                    sequenceNumber)
            self._keysDict[fragmentName] = self._secret
        self._fragmentsDict[fragmentName] = fragment

    def getFragment(self, fragmentName):
        '''
        Returns a fragment of the playlist or raises an Exception
        if the fragment is not found

        @param fragmentName:    name of the fragment to retrieve
        @type  fragmentName:    str

        @return:                an mpegts raw fragment
        @rtype:                 array
        '''

        if fragmentName in self._fragmentsDict:
            return self._fragmentsDict[fragmentName]
        raise common.FragmentNotFound()

    def getEncryptionKey(self, key):
        '''
        Returns an encryption key from the keys dict or raises an
        Exception if the key is not found

        @param key:     name of the key to retrieve
        @type  key:     str

        @return:        the encryption key
        @rtype:         str
        '''

        if key in self._keysDict:
            return self._keysDict[key]
        raise common.KeyNotFound()
