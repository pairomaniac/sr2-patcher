#!/usr/bin/env python3
"""Read the frames.log the frametrace patch writes.

    python3 tools/frames.py GAMEDIR/logs/frames.log [N] [SECONDS]

Prints the frame rate, how the intervals between drawn frames spread,
how many frames the game caught up with extra simulation steps, the N
worst intervals (default 10) with when they happened, the gate's flags
and the split of the frame, a timeline in slices of SECONDS (default 10),
and for every pause the worst interval in the five seconds before it -
pause right after a stutter and the pause marks the spot.

The log is one header, "budget <ticks> qpc <0|1>", then one line a frame,
"<entry> <blit> <exit> <steps> <flags>": the counter at the frame gate's
entry (after the game's own work on the frame), after the borderless
present's blit and at the gate's exit (after the catch-up and the spin),
the steps, and the flags the gate reads as bits - 1 running, 2 paused,
4 debug DLL, 8 catch-up allowed. The ticks per 1/60 s and whether the
counter is QueryPerformanceCounter (its low 32 bits) or timeGetTime (ms)
are in the header. Each interval is split into work (the previous exit
to this entry: step and draw), blit (to the blit's return) and rest (to
the exit: catch-up and spin). A stamp that is not inside its frame - the
present was skipped - is left out of the split.
"""
import sys

BUCKETS = ((0, 15, 'under 15 ms'), (15, 18, '15-18 ms  (one refresh)'), (18, 25, '18-25 ms'),
           (25, 40, '25-40 ms  (two)'), (40, 60, '40-60 ms  (three)'), (60, None, 'over 60 ms'))


def read(path):
    with open(path) as fh:
        head = fh.readline().split()
        if len(head) != 4 or head[0] != 'budget' or head[2] != 'qpc':
            raise SystemExit('%s: not a frames.log' % path)
        budget, qpc = int(head[1]), int(head[3])
        if budget <= 0:
            raise SystemExit('%s: a budget of %d ticks' % (path, budget))
        frames, bad = [], 0
        for line in fh:
            try:
                parts = [int(p) for p in line.split()]
            except ValueError:
                parts = []
            if len(parts) == 5:
                frames.append(tuple(parts))
            else:
                bad += 1
    if bad:
        print('%s: %d line%s not readable, skipped' % (path, bad, '' if bad == 1 else 's'))
    return frames, 1000.0 / (budget * 60) if qpc else 1.0, qpc


def describe(flags):
    """The gate's flags as words: what would have stopped a catch-up."""
    words = []
    if not flags & 1:
        words.append('not running')
    if flags & 2:
        words.append('paused')
    if flags & 4:
        words.append('debug DLL')
    if not flags & 8:
        words.append('first tick of a scene')
    return ', '.join(words) if words else 'racing'


def split(ms, work, blit):
    if blit is None:
        return '(work %.1f, rest %.1f)' % (work, ms - work)
    return '(work %.1f, blit %.1f, rest %.1f)' % (work, blit, ms - work - blit)


def main(argv):
    if len(argv) not in (2, 3, 4):
        print(__doc__.strip())
        return 2
    frames, ms_per_tick, qpc = read(argv[1])
    worst_n = int(argv[2]) if len(argv) >= 3 else 10
    slice_s = float(argv[3]) if len(argv) == 4 else 10.0
    if len(frames) < 2:
        raise SystemExit('%s: fewer than two frames' % argv[1])

    def span(a, b):
        return ((b - a) & 0xffffffff) * ms_per_tick
    intervals = []                      # (ms, steps, at, flags, work, blit)
    at = 0.0
    for (_e0, _b0, t0, _s0, _f0), (e1, b1, t1, s1, f1) in zip(frames, frames[1:]):
        ms = span(t0, t1)
        blit = span(e1, b1) if b1 and span(t0, e1) <= span(t0, b1) <= ms else None
        intervals.append((ms, s1, at, f1, span(t0, e1), blit))
        at += ms
    total = at
    if not total:
        raise SystemExit('no time passed between the frames logged')
    print('%d frames over %.1f s: %.2f fps, counter %s' % (
        len(frames), total / 1000, len(intervals) * 1000 / total, 'QueryPerformanceCounter' if qpc else 'timeGetTime'))
    print()
    for lo, hi, label in BUCKETS:
        n = sum(1 for i in intervals if i[0] >= lo and (hi is None or i[0] < hi))
        print('  %-24s %6d  %5.1f%%' % (label, n, 100.0 * n / len(intervals)))
    racing = [i[0] for i in intervals if i[3] & 1 and not i[3] & 2 and 15 <= i[0] < 18]
    if racing:
        pace = sum(racing) / len(racing)
        print('  racing pace %.4f ms, %.3f Hz: %s' % (
            pace, 1000 / pace, 'the spin at 60.000' if abs(pace - 1000 / 60) < 0.003 else 'the display'))
    caught = sum(1 for i in intervals if i[1] > 1)
    print()
    print('caught up with extra steps: %d frames (%.2f%%)' % (caught, 100.0 * caught / len(intervals)))
    print()
    print('worst intervals:')
    for ms, steps, when, flags, work, blit in sorted(intervals, reverse=True)[:worst_n]:
        print('  %7.1f ms  %d step%s  at %6.1f s  %s  %s' % (
            ms, steps, '' if steps == 1 else 's', when / 1000, describe(flags), split(ms, work, blit)))
    print()
    print('timeline, %g s slices:  frames  catch-ups  2-refresh  loading   worst racing' % slice_s)
    start = 0.0
    while start < total:
        end = start + slice_s * 1000
        part = [i for i in intervals if start <= i[2] < end]
        if part:
            racing = [i for i in part if i[3] & 1 and not i[3] & 2]
            worst = max(racing, key=lambda i: i[0]) if racing else None
            print('  %5.0f-%4.0f s  %6d  %8d  %9d  %7d   %s' % (
                start / 1000, end / 1000, len(part), sum(1 for i in part if i[1] > 1),
                sum(1 for i in part if 25 <= i[0] < 40), sum(1 for i in part if not i[3] & 1),
                '%.1f ms, %d step%s  %s' % (worst[0], worst[1], '' if worst[1] == 1 else 's',
                                             split(worst[0], worst[4], worst[5])) if worst else '-'))
        start = end
    pauses = [cur[2] for prev, cur in zip(intervals, intervals[1:]) if cur[3] & 2 and not prev[3] & 2]
    if pauses:
        print()
        print('pauses, and the worst interval in the 5 s before each:')
        for when in pauses:
            before = [i for i in intervals if when - 5000 <= i[2] < when and i[3] & 1]
            if before:
                ms, steps, at = max(before, key=lambda i: i[0])[:3]
                print('  paused at %6.1f s:  %7.1f ms, %d step%s at %6.1f s, %d frames over 18 ms' % (
                    when / 1000, ms, steps, '' if steps == 1 else 's', at / 1000,
                    sum(1 for i in before if i[0] >= 18)))
            else:
                print('  paused at %6.1f s:  nothing before it' % (when / 1000))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
