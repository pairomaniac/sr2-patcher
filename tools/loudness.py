#!/usr/bin/env python3
"""The loudness of the game's music, to set the mix's offsets from.

    python3 tools/loudness.py GAMEDIR

Reads every 16-bit PCM .wav under GAMEDIR/music (the CD rips) and
GAMEDIR/BINDATA/BGM (the streamed music; the cp_*.wav there are the car
profiles' narration and are left out) and prints each file's RMS in
dBFS and each folder's mean. The two folders play through two sliders,
and at equal settings the streamed music sits STREAM_DB above the
effects' curve and the CD music CD_DB above it (asm/mix.inc). For the
two to be equally loud at equal settings:

    CD_DB - STREAM_DB = RMS(BGM) - RMS(music)

which the last line prints. RMS is not loudness - it ignores the ear's
weighting and any dynamics - but the two sources are the same kind of
material, so the difference is close enough to start from; the effects
are short sounds and stay a matter of taste.
"""
import array
import math
import os
import sys
import wave

STRIDE = 16                             # every 16th frame: plenty for an RMS


def rms_db(path):
    """RMS of a PCM .wav in dBFS, or None if it is not 16-bit PCM."""
    try:
        with wave.open(path, 'rb') as wav:
            if wav.getsampwidth() != 2:
                return None
            channels = wav.getnchannels()
            frames = wav.getnframes()
            data = wav.readframes(frames)
    except (wave.Error, EOFError):
        return None
    samples = array.array('h')
    samples.frombytes(data[:len(data) // 2 * 2])
    picked = samples[::STRIDE * channels]
    if not picked:
        return None
    total = 0
    for s in picked:
        total += s * s
    mean = total / len(picked)
    if mean == 0:
        return -math.inf
    return 10 * math.log10(mean / (32768.0 * 32768.0))


def folder(path):
    out = []
    if not os.path.isdir(path):
        return out
    for name in sorted(os.listdir(path)):
        if name.lower().endswith('.wav') and not name.lower().startswith('cp_'):
            db = rms_db(os.path.join(path, name))
            if db is not None and db > -math.inf:
                out.append((name, db))
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    game = argv[1]
    means = {}
    for label, sub in (('music', 'music'), ('BGM', os.path.join('BINDATA', 'BGM'))):
        files = folder(os.path.join(game, sub))
        if not files:
            print('%s: no 16-bit PCM .wav files under %s' % (label, os.path.join(game, sub)))
            continue
        for name, db in files:
            print('  %-24s %6.1f dBFS' % (name, db))
        means[label] = sum(db for _n, db in files) / len(files)
        print('%s: %d files, mean %.1f dBFS' % (label, len(files), means[label]))
    if 'music' in means and 'BGM' in means:
        print('CD_DB - STREAM_DB = %+d (hundredths of a dB) for equal loudness at equal sliders'
              % round((means['BGM'] - means['music']) * 100))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
