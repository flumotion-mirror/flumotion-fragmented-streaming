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

from cStringIO import StringIO
from mp4seek import atoms


def extract_sps_pps(avcc_box):
    data = avcc_box.data
    f = StringIO(data)
    f.seek(5, 1)
    nsps = atoms.read_uchar(f) & 0x1f
    sps = []
    while nsps > 0:
        size = atoms.read_ushort(f)
        sps.append(atoms.read_bytes(f, size))
        nsps -= 1
    npps = atoms.read_uchar(f)
    pps = []
    while npps > 0:
        size = atoms.read_ushort(f)
        pps.append(atoms.read_bytes(f, size))
        npps -= 1
    return (sps, pps)
