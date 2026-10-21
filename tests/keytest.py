"""Press Ctrl+Alt+<key> shortcuts against a test window and log what happens.

Usage: python3 tests/keytest.py s BackSpace Return BackSpace
       python3 tests/keytest.py manual   # just log; press real keys yourself
       python3 tests/keytest.py fullscreen s BackSpace   # start fullscreen

Keys are sent through Mutter's RemoteDesktop D-Bus API, only while the test
window has focus.
"""
import sys
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

CTRL, ALT = 0xffe3, 0xffe9
KEYS = {'Return': 0xff0d, 'BackSpace': 0xff08, 'Left': 0xff51, 'Right': 0xff53,
        'Up': 0xff52, 'Down': 0xff54}

STEPS = sys.argv[1:] or ['s', 'BackSpace', 'Return', 'BackSpace']
FULLSCREEN = STEPS[:1] == ['fullscreen']
if FULLSCREEN:
    STEPS = STEPS[1:]

t0 = time.monotonic()


def log(*args):
    print(f'{time.monotonic() - t0:6.2f}s', *args, flush=True)


bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(path, iface, method, args=None, sig=None):
    return bus.call_sync('org.gnome.Mutter.RemoteDesktop', path, iface, method,
                         args, GLib.VariantType(sig) if sig else None, 0, -1, None)


session = None
SESSION_IFACE = 'org.gnome.Mutter.RemoteDesktop.Session'


def press(key):
    keysym = KEYS.get(key) or ord(key)
    seq = [CTRL, ALT, keysym]
    for k in seq:
        call(session, SESSION_IFACE, 'NotifyKeyboardKeysym', GLib.Variant('(ub)', (k, True)))
    for k in reversed(seq):
        call(session, SESSION_IFACE, 'NotifyKeyboardKeysym', GLib.Variant('(ub)', (k, False)))


app = Gtk.Application(application_id='dev.magnetize.KeyTest')


def on_activate(app):
    win = Gtk.ApplicationWindow(application=app, title='Magnetize key test',
                                default_width=600, default_height=400)
    area = Gtk.DrawingArea()
    area.connect('resize', lambda a, w, h: log(f'size {w}x{h}'))
    win.set_child(area)
    win.connect('notify::maximized', lambda w, p: log('maximized =', w.is_maximized()))
    win.connect('notify::fullscreened', lambda w, p: log('fullscreen =', w.is_fullscreen()))
    win.present()
    if FULLSCREEN:
        win.fullscreen()

    if STEPS == ['manual']:
        log('press shortcuts on this window now')
        GLib.timeout_add_seconds(90, app.quit)
        return

    steps = list(STEPS)

    def run():
        global session
        if not win.is_active():
            log('test window not focused, aborting')
            app.quit()
            return False
        if session is None:
            session = call('/org/gnome/Mutter/RemoteDesktop', 'org.gnome.Mutter.RemoteDesktop',
                           'CreateSession', None, '(o)').unpack()[0]
            call(session, SESSION_IFACE, 'Start')
        if not steps:
            call(session, SESSION_IFACE, 'Stop')
            GLib.timeout_add(500, app.quit)
            return False
        key = steps.pop(0)
        log(f'>>> Ctrl+Alt+{key}')
        press(key)
        return True

    GLib.timeout_add(1500, run)


app.connect('activate', on_activate)
app.run([])
