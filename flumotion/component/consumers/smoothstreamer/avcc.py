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
