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

import gst

from cStringIO import StringIO as cStringIO
from StringIO import StringIO
from mp4seek import iso, atoms

from flumotion.common import messages
from flumotion.common.i18n import N_, gettexter
from flumotion.component import feedcomponent

__all__ = ['FMP4Aggregator']
__version__ = "$Rev$"
T_ = gettexter()


class FMP4Aggregator(feedcomponent.ParseLaunchComponent):
    '''
    I aggregate/remux several fmp4 streams into a single stream.

    The component allows using a muxer per stream instead a single muxer for
    all the streams, which blocks if one of the streams is late or not working,
    beeing able to feed a streamer with single feed instead of n feeds.

    The component uses n appsink elements, one per input stream and 1 appsrc
    element to push the recombined stream downstream. Once all sinks are
    prelloled, every sink is given a track id and a new moov is build with
    the n tracks. For new incomming fragment, the moof is rewritten changing
    the track id, which would be 1 for all them otherwise.
    '''
    logCategory = 'fmp4-aggregator'

    _moov = None
    _streamheaders = None
    _outputcaps = None
    _sinks = {} # sink -> {got_headers: bool , queue: [], id: int}

    def get_pipeline_string(self, properties):
        # Similar to the MultiInputParseLaunch component but whithout the need
        # of using queues
        eaters = self.config.get('eater', {})
        sources = self.config.get('source', [])
        if eaters == {} and sources != []:
            # for upgrade without manager restart
            feeds = []
            for feed in sources:
                if not ':' in feed:
                    feed = '%s:default' % feed
                feeds.append(feed)
            eaters = {'default': [(x, 'default') for x in feeds]}

        pipeline = ''
        for e in eaters:
            for feed, alias in eaters[e]:
                pipeline += ' @ eater:%s @ !  appsink '\
                            'name=sink_%s emit-signals=true sync=false '\
                            % (alias, alias)
        pipeline += ' appsrc is-live=true name=output '
        return pipeline

    def configure_pipeline(self, pipeline, properties):
        eaters = self.config.get('eater', {})
        self.n_preroll_eaters = len(eaters)
        for e in eaters:
            for feed, alias in eaters[e]:
                sink = self.pipeline.get_by_name('sink_%s' % alias)
                sink.connect("new-buffer", self._new_buffer)
                sink.connect("new-preroll", self._new_preroll)
                tid = len(self._sinks) + 1
                self._sinks[sink] = {'got_headers': False, 'queue': [],
                                     'id': tid}
        self._appsrc = pipeline.get_by_name('output')

    def _all_sinks_prerolled(self):
        return False not in map(lambda s: s['got_headers'],
                                self._sinks.values())

    def _update_caps(self, caps):
        # Rewrite the moov in the streamheaders buffer
        raw_headers = cStringIO()
        iso.write_atoms([self._moov], raw_headers)
        self._streamheaders = gst.Buffer(raw_headers.getvalue())
        self._streamheaders.flag_set(gst.BUFFER_FLAG_IN_CAPS)
        s = caps[0].copy()
        s.set_value('streamheader', (self._streamheaders, ))
        self._outputcaps = gst.Caps(s)
        self._streamheaders.set_caps(self._outputcaps)

    def _parse_headers(self, buf, tid):
        # Parse buffer and get the moov atom
        f = cStringIO(buf.data)
        al = list(atoms.read_atoms(f))
        ad = atoms.atoms_dict(al)
        try:
            moov = iso.select_atoms(ad, ('moov', 1, 1))[0]
        except Exception:
            self.error("Could not parse moov")
            m = messages.Error(T_(N_(
                "First buffer cannot be parsed as a moov. "\
                "The required mp4seek version is 1.0-6")))
            self.addMessage(m)
            return False

        # Modify the track id and update the streamheaders buffer
        trak = moov.trak[0]
        trak.tkhd.id = tid
        if self._moov is None:
            self._moov = moov
        else:
            self._moov.trak.append(trak)
        self._update_caps(buf.caps)
        return True

    def _update_trak_id(self, buf, tid):
        f = StringIO(buf.data)
        al = list(atoms.read_atoms(f))
        ad = atoms.atoms_dict(al)
        a = iso.select_atoms(ad, ('moof', 1, 1))[0].traf.tfhd._atom
        f.seek(a.offset + a.head_size_ext())
        iso.write_ulong(f, tid)
        # FIXME: how can we write this directly in the buffer?
        data = f.getvalue()
        f.close()
        outputbuf = gst.Buffer(data)
        outputbuf.duration = buf.duration
        outputbuf.timestamp = buf.timestamp
        outputbuf.caps = self._outputcaps
        return outputbuf

    def _push_buffer(self, buf):
        buf.set_caps(self._outputcaps)
        self._appsrc.emit('push-buffer', buf)
        self.debug("Forwarding buffer ts:%s duration:%s",
                   gst.TIME_ARGS(buf.timestamp), gst.TIME_ARGS(buf.duration))

    def _new_preroll(self, appsink):
        self.debug("new preroll buffer")
        buf = appsink.emit('pull-preroll')
        appsinkd = self._sinks[appsink]
        # parse the moov
        if buf.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            appsinkd['got_headers'] = self._parse_headers(buf, appsinkd['id'])
        if self._all_sinks_prerolled():
            self.info("Pushing moov downstream")
            self._push_buffer(self._streamheaders)

    def _new_buffer(self, appsink):
        self.debug("new buffer")
        buf = appsink.emit('pull-buffer')

        # discard moov, already parsed in preroll
        if buf.flag_is_set(gst.BUFFER_FLAG_IN_CAPS):
            return True

        # and finally send the current buffer downstream
        outputbuf = self._update_trak_id(buf, self._sinks[appsink]['id'])
        self._push_buffer(outputbuf)
