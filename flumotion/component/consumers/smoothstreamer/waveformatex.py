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

import struct

# this come from mp4split & gstreamer

MP4_MPEG4Audio = 0x40
MP4_MPEG2AudioMain = 0x66
MP4_MPEG2AudioLowComplexity = 0x67
MP4_MPEG2AudioScaleableSamplingRate = 0x68
MP4_MPEG2AudioPart3 = 0x69
MP4_MPEG1Audio = 0x6b

WAVE_FORMAT_AAC = 0xa106
WAVE_FORMAT_MPEG_ADTS_AAC = 0x1600
WAVE_FORMAT_RAW_AAC1 = 0x00ff
WAVE_FORMAT_MP3 = 0x0055


def object_type_id_to_wFormatTag(object_type_id):
    switch = {
        MP4_MPEG4Audio: WAVE_FORMAT_RAW_AAC1,
        MP4_MPEG2AudioMain: WAVE_FORMAT_RAW_AAC1,
        MP4_MPEG2AudioLowComplexity: WAVE_FORMAT_RAW_AAC1,
        MP4_MPEG2AudioScaleableSamplingRate: WAVE_FORMAT_RAW_AAC1,
        MP4_MPEG2AudioPart3: WAVE_FORMAT_MP3,
        MP4_MPEG1Audio: WAVE_FORMAT_MP3}
    return switch.get(object_type_id)


def waveformatex(wFormatTag, nChannels, nSamplesPerSec,
                 nAvgBytesPerSec, nBlockAlign, wBitsPerSample,
                 cbData):
    return struct.pack("<HHLLHHH",
                       wFormatTag, nChannels, nSamplesPerSec,
                       nAvgBytesPerSec, nBlockAlign, wBitsPerSample,
                       len(cbData)) + cbData
