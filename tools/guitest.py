#!/usr/bin/env python3
"""The window, driven headlessly.

Every check here is one a person would otherwise find by clicking: a
button that stayed lit with nothing to act on, a heading that never
opened its card, a description that raised on the way to the screen.
None of them raise on their own - the widgets are all present and the
wrong thing is on screen - so each asserts the property rather than the
absence of an exception.

Needs a display. Under CI that is xvfb; locally, run it inside

    xvfb-run -a -s "-screen 0 1600x1400x24" python3 tools/guitest.py

With no display it skips rather than fails, so a checkout on a headless
box without xvfb still gets a clean run - but it says so as a `note:`
line, which is what check.py surfaces. Under CI (CI=true) the same skip
is a failure: the runner is meant to have xvfb and tkinter, and a green
run that tested no window at all should not look like one that did.

No copy of the game is needed. What the window does to real files is
selftest.py's and cabtest.py's.
"""
import os
import sys
import tempfile

# Every pair of palette colours that carries meaning, and the contrast
# WCAG asks of it: 4.5 for text, 3 for a border or a tick. Checked here
# so a palette cannot be adjusted by eye into something unreadable.
PAIRS = [
    ('text', 'card', 'body text on a card', 4.5),
    ('text', 'field', 'typed text in a box', 4.5),
    ('text', 'head', 'a heading on its band', 4.5),
    ('dim', 'card', 'a hint on a card', 4.5),
    ('dim', 'field', 'the log', 4.5),
    ('dim', 'head', 'the status line', 4.5),
    ('red', 'head', 'a refusal in the status line', 4.5),
    ('red', 'card', 'a refusal, a bubble title', 4.5),
    ('go', 'card', 'a link, a prompt, READY', 4.5),
    ('amber', 'card', 'a key, a warning', 4.5),
    ('card', 'go', 'Apply patches', 4.5),
    ('card', 'go_hi', 'Apply hovered', 4.5),
    ('card', 'go_lo', 'Apply pressed', 4.5),
    ('field', 'go', 'the tick in its box', 3.0),
    ('line', 'card', 'a border on a card', 3.0),
    # A box on a card is told apart by its own fill, checked below, so
    # its border only has to close the shape and is not asked for 3.
    ('line', 'field', 'a border round a box', 1.6),
    ('field', 'card', 'a box against the card holding it', 1.25),
    # The three surfaces, each far enough from the next to be seen as a
    # surface of its own rather than as a smudge on the one behind it.
    ('card', 'head', 'a card against its own band', 1.25),
    ('head', 'ink', 'a band against the window', 1.25),
    ('card', 'ink', 'a card against the window', 1.25),
    ('frame', 'ink', 'the rule under the logo', 3.0),
    ('head', 'trough', 'the scrollbar against its trough', 3.0),
    # The hairline is decorative - a card is already told from the
    # window by the paper itself - so it is only asked to be visible
    # against the green it is drawn on.
    ('amber', 'head', 'a step number', 4.5),
    # The banner's two greens, which are only a tone apart on purpose:
    # the stripe on the cut is what makes it a stripe. Far enough apart
    # to be two tones, all the same.
    ('sweep', 'ink', 'the banner\'s lighter green', 1.15),
]


def luminance(colour):
    parts = [int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    parts = [p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4
             for p in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def contrast(a, b):
    high, low = max(luminance(a), luminance(b)), min(luminance(a),
                                                     luminance(b))
    return (high + 0.05) / (low + 0.05)


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILED = []


def check(label, condition, detail=''):
    print('%-4s %s%s' % ('ok' if condition else 'FAIL', label,
                         '' if condition else '   <- %s' % (detail,)))
    if not condition:
        FAILED.append(label)


def build_window(patcher, tk):
    """Open the window without entering its loop, and hand back the root."""
    state = {}
    original = tk.Misc.mainloop

    def stop(self, n=0):
        state['root'] = self
        raise SystemExit(0)

    tk.Misc.mainloop = stop
    try:
        patcher.run_tk()
    except SystemExit:
        pass
    finally:
        tk.Misc.mainloop = original
    return state['root']


def walk(widget, out=None):
    out = [] if out is None else out
    out.append(widget)
    for child in widget.winfo_children():
        walk(child, out)
    return out


def text_of(widget):
    try:
        return str(widget.cget('text'))
    except Exception:                                       # anything: the check is that the window survives it
        return ''


def main():
    # The palette first: it needs no display, so it is checked even where
    # the rest of this skips.
    from uctest import patcher
    for a, b, what, want in PAIRS:
        got = contrast(patcher.PALETTE[a], patcher.PALETTE[b])
        check('%s reads (%s on %s)' % (what, a, b), got >= want,
              '%.2f:1, wants %.1f' % (got, want))

    # A skip is reported as one locally (77, what tools/check.py reads as
    # a skip) and is a failure in CI, where the runner is meant to have
    # both and a green run that tested no window is wrong.
    skip = 1 if os.environ.get('CI') == 'true' else 77
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print('note: no tkinter, so the window was not tested')
        return skip
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        print('note: no display (%s), so the window was not tested - run it '
              'under xvfb-run' % exc)
        return 1 if FAILED else skip

    root = build_window(patcher, tk)
    raised = []

    def callback_failed(exc, val, tb):  # Tk swallows these and prints them; count them instead
        raised.append('%s: %s' % (exc.__name__, val))
    root.report_callback_exception = callback_failed
    root.overrideredirect(True)        # no window manager under xvfb
    root.geometry('+0+0')
    root.update()
    everything = walk(root)
    app = root.app

    buttons = {}
    for w in everything:
        if isinstance(w, ttk.Button):
            buttons.setdefault(text_of(w), []).append(w)
    heads = {text_of(w): w for w in everything
             if isinstance(w, ttk.Label)
             and text_of(w) in ('GAME FOLDER', 'INSTALL', 'PATCHES',
                                'ADD-ONS', 'DIAGNOSTICS', 'LOG', 'ABOUT')}

    def pump(ms=0):
        root.update_idletasks()
        root.update()
        if ms:
            end = root.tk.call('clock', 'milliseconds') + ms
            while root.tk.call('clock', 'milliseconds') < end:
                root.update()

    def enabled(name):
        return 'disabled' not in buttons[name][0].state()

    def is_open(label):
        # label -> the band -> the card, whose last child is the body
        # the heading shows and hides.
        card = heads[label].master.master
        return bool(card.winfo_children()[-1].winfo_manager())

    # ---- nothing to act on, nothing offered --------------------------
    check('every card the window needs is there',
          len(heads) == 7, sorted(heads))
    check('the folder is asked for once, not twice',
          len([w for w in everything
               if isinstance(w, ttk.Entry)
               and not isinstance(w, ttk.Combobox)]) == 3,
          'one folder and two discs')
    check('no button is lit with nothing selected',
          not any(enabled(name) for name in
                  ('Install game', 'Rip soundtrack', 'Apply patches',
                   'Restore original')))
    check('the numbered cards start open and the rest closed',
          all(is_open(n) for n in ('GAME FOLDER', 'INSTALL', 'PATCHES',
                                   'ADD-ONS'))
          and not any(is_open(n) for n in ('DIAGNOSTICS', 'LOG', 'ABOUT')))

    def tall_enough():
        # Either it shows what it should, or it is as tall as it is
        # allowed to be: on a screen too short for the window's own
        # floor, the second is the best there is.
        return (app.canvas.winfo_height() >= min(app.inner.winfo_reqheight(),
                                                 app.cap)
                or root.winfo_height() >= root.maxsize()[1] - 2)

    for _ in range(50):                  # _settle_height runs on an idle
        pump(20)
        if tall_enough():
            break
    check('the window opens showing all it is allowed to',
          tall_enough(),
          '%d of %d, cap %d, window %d of %d' % (
              app.canvas.winfo_height(), app.inner.winfo_reqheight(),
              app.cap, root.winfo_height(), root.maxsize()[1]))

    # The five numbered cards are the patcher; the three below them are
    # reference. The line bound has to leave room for the last of the
    # five, or the window opens looking like it is missing a card. The
    # screen is not part of this: a short one is checked above.
    last = [w for w in walk(root)
            if isinstance(w, ttk.Label) and text_of(w) == 'ADD-ONS']
    foot = (last[0].winfo_rooty() + last[0].winfo_height()
            - app.inner.winfo_rooty()) if last else 0
    allowed = patcher.LINE_CAP * app.row
    # In one column every card is stacked and nothing short of the whole
    # content would reach the fifth, so this is asked of the two-column
    # layout, which is what a screen the window fits on gets.
    check('the opening height leaves room for the last numbered card',
          bool(last) and (app.columns < 2 or allowed >= foot),
          '%d lines is %d, the card ends at %d'
          % (patcher.LINE_CAP, allowed, foot))

    # ---- a path that is not there is refused, and says so -------------
    missing = os.path.join(tempfile.gettempdir(), 'sr2-guitest-no-such.cue')
    app.disc_var.set(missing)
    for _ in range(100):                     # the source is read on a timer
        pump(20)
        if app.disc_note.cget('text') != patcher.INSTALL_PICK:
            break
    check('a source that is not there is refused',
          not enabled('Install game')
          and app.disc_note.cget('text') == patcher.INSTALL_NO_PATH,
          app.disc_note.cget('text'))
    # a file that is not a disc is read off the window's thread, then refused
    junk = os.path.join(tempfile.gettempdir(), 'sr2-guitest-junk.cue')
    with open(junk, 'w') as fh:
        fh.write('not a cue sheet\n')
    app.disc_var.set(junk)
    reading = False
    for _ in range(100):
        pump(20)
        reading |= app.disc_note.cget('text') == patcher.INSTALL_READING
        if app.disc_note.cget('text') not in (patcher.INSTALL_NO_PATH, patcher.INSTALL_READING):
            break
    check('a file that is not a disc is refused',
          not enabled('Install game') and app.disc_note.cget('text') not in (
              patcher.INSTALL_PICK, patcher.INSTALL_NO_PATH, patcher.INSTALL_READING),
          app.disc_note.cget('text'))
    check('and was read off the window\'s thread', reading)
    os.remove(junk)
    app.disc_var.set('')
    pump(400)

    # ---- an empty folder is where an install goes, not a refusal -----
    empty = tempfile.mkdtemp(prefix='sr2-guitest-')
    app.game_var.set(empty)
    for _ in range(100):
        pump(20)
        if app._status_text != patcher.NO_GAME:
            break
    check('an empty folder is not refused, it is where a game goes',
          app._status_text == patcher.NO_GAME_YET
          and not enabled('Apply patches'),
          app._status_text)

    # ---- a folder holding something else is ---------------------------
    with open(os.path.join(empty, patcher.EXE), 'wb') as fh:
        fh.write(b'not the game')
    app.game_var.set(empty + os.sep)        # a write the trace will see
    reading = False
    for _ in range(100):
        pump(20)
        reading |= app._status_text == patcher.GAME_READING
        if app._status_text.startswith('CANNOT PATCH'):
            break
    check('a folder holding something else is refused',
          not enabled('Apply patches')
          and app._status_text.startswith('CANNOT PATCH'),
          app._status_text)
    check('and was read off the window\'s thread', reading)
    check('and the refusal says what to do about it',
          bool(app.game_help.cget('text')))
    check('writing to the log opens the log',
          is_open('LOG'))
    os.remove(os.path.join(empty, patcher.EXE))
    os.rmdir(empty)

    # ---- the boxes and the keys they stand for ------------------------
    check('every diagnostic starts off',
          not any(var.get() for var in app.diagnostics.values()))
    check('the window applies every patch',
          patcher.group_keys(()) == patcher.PATCH_KEYS)
    check('and a minus on the command line leaves one out with what needs it',
          set(patcher.parse_keys(['-widescreen', '-xinput'])) == set(patcher.PATCH_KEYS)
          - {'widescreen', 'widescreen2d', 'widescreen3d', 'resolution', 'xinput', 'devices'})

    # ---- every description can be shown ------------------------------
    bubbles = []

    def find(widget):
        for child in widget.winfo_children():
            find(child)
        if text_of(widget) == '\u24d8':
            bubbles.append(widget)
    find(root)
    check('every patch and diagnostic has a description button',
          len(bubbles) >= len(patcher.FEATURES) + len(patcher.DIAGNOSTIC),
          '%d buttons' % len(bubbles))
    shown = 0
    for btn in bubbles:
        try:
            btn.event_generate('<Button-1>')
            pump()
            shown += 1
        except tk.TclError as exc:
            check('description %d opens' % shown, False, str(exc))
            break
    check('every description opens and closes', shown == len(bubbles))
    root.event_generate('<Escape>')
    pump()
    check('no callback raised on the way', not raised, '; '.join(raised))

    # ---- the tables the window reads from ----------------------------
    check('every patch is in exactly one feature row',
          sorted(k for _g, _l, _t, keys in patcher.FEATURES for k in keys)
          == sorted(patcher.PATCH_KEYS))
    check('every feature row is displayed',
          set(patcher.ESSENTIAL) == set(patcher.BY_GROUP))
    check('every diagnostic has a label',
          set(patcher.DIAGNOSTIC_INFO) == set(patcher.DIAGNOSTIC))

    root.destroy()
    if FAILED:
        print('guitest: %d failed - %s' % (len(FAILED), ', '.join(FAILED)))
        return 1
    print('guitest OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
