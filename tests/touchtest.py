"""Drag a test window by its title bar with a simulated finger, and log its size.

Usage: python3 tests/touchtest.py [--mouse] [left|right|top|top-left|bottom ...]

Add :ms to hold at a target before lifting, e.g. top:1500 (default 400).

Each target drags the (maximized) test window from the middle of its title
bar to that spot on the screen, then lifts. Touches go through Mutter's
RemoteDesktop D-Bus API, tied to a screencast of the first monitor, which is
what absolute input needs.
"""
import sys
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

MOUSE = '--mouse' in sys.argv
TARGETS = [a for a in sys.argv[1:] if a != '--mouse'] or ['left', 'right', 'top-left']
BTN_LEFT = 0x110

t0 = time.monotonic()


def log(*args):
    print(f'{time.monotonic() - t0:6.2f}s', *args, flush=True)


bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(name, path, iface, method, args=None, sig=None):
    return bus.call_sync(name, path, iface, method, args,
                         GLib.VariantType(sig) if sig else None, 0, -1, None)


def first_monitor():
    """(connector, logical x, y, width, height, scale) of the first logical monitor."""
    state = call('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                 'org.gnome.Mutter.DisplayConfig', 'GetCurrentState').unpack()
    _serial, monitors, logical, _props = state
    x, y, scale, _transform, _primary, mons, _p = logical[0]
    connector = mons[0][0]
    for (info, modes, _props2) in monitors:
        if info[0] == connector:
            mode = next(m for m in modes if m[6].get('is-current'))
            width, height = mode[1], mode[2]
            return connector, x, y, round(width / scale), round(height / scale), scale
    raise RuntimeError('no monitor')


RD, SC = 'org.gnome.Mutter.RemoteDesktop', 'org.gnome.Mutter.ScreenCast'
connector, MX, MY, MW, MH, SCALE = first_monitor()
rd_session = call(RD, '/org/gnome/Mutter/RemoteDesktop', RD, 'CreateSession', None, '(o)').unpack()[0]
session_id = call(RD, rd_session, 'org.freedesktop.DBus.Properties', 'Get',
                  GLib.Variant('(ss)', (RD + '.Session', 'SessionId'))).unpack()[0]
sc_session = call(SC, '/org/gnome/Mutter/ScreenCast', SC, 'CreateSession',
                  GLib.Variant('(a{sv})', ({'remote-desktop-session-id': GLib.Variant('s', session_id)},)),
                  '(o)').unpack()[0]
stream = call(SC, sc_session, SC + '.Session', 'RecordMonitor',
              GLib.Variant('(sa{sv})', (connector, {})), '(o)').unpack()[0]

def pointer(method, *args):
    session_iface = RD + '.Session'
    if method == 'Up':
        call(RD, rd_session, session_iface, 'NotifyPointerButton', GLib.Variant('(ib)', (BTN_LEFT, False)))
        return
    _slot, x, y = args
    call(RD, rd_session, session_iface, 'NotifyPointerMotionAbsolute',
         GLib.Variant('(sdd)', (stream, (x - MX) * SCALE, (y - MY) * SCALE)))
    if method == 'Down':
        call(RD, rd_session, session_iface, 'NotifyPointerButton', GLib.Variant('(ib)', (BTN_LEFT, True)))


def touch(method, *args):
    if MOUSE:
        return pointer(method, *args)
    params = {'Down': '(sudd)', 'Motion': '(sudd)', 'Up': '(u)'}[method]
    if method == 'Up':
        values = args
    else:
        slot, x, y = args
        # Mutter reads stream coordinates in physical pixels.
        values = (stream, slot, (x - MX) * SCALE, (y - MY) * SCALE)
    if method == 'Up':
        call(RD, rd_session, RD + '.Session', 'NotifyTouchUp', GLib.Variant(params, values))
    else:
        call(RD, rd_session, RD + '.Session', 'NotifyTouch' + method, GLib.Variant(params, values))


def spot(name):
    edge = 4
    return {
        'left': (MX + edge, MY + MH / 2),
        'right': (MX + MW - edge, MY + MH / 2),
        'top': (MX + MW / 2, MY + edge),
        'bottom': (MX + MW / 2, MY + MH - edge),
        'top-left': (MX + edge, MY + edge),
        'top-right': (MX + MW - edge, MY + edge),
    }[name]


app = Gtk.Application(application_id='dev.magnetize.TouchTest')


def on_activate(app):
    win = Gtk.ApplicationWindow(application=app, title='Magnetize touch test',
                                default_width=600, default_height=400)
    area = Gtk.DrawingArea()
    area.connect('resize', lambda a, w, h: log(f'size {w}x{h}'))
    win.set_child(area)
    win.connect('notify::maximized', lambda w, p: log('maximized =', w.is_maximized()))
    win.present()

    targets = list(TARGETS)

    def drag_next():
        if not win.is_active():
            log('test window not focused, aborting')
            app.quit()
            return False
        if not targets:
            call(RD, rd_session, RD + '.Session', 'Stop')
            GLib.timeout_add(1000, app.quit)
            return False
        target, _, hold = targets.pop(0).partition(':')
        hold = int(hold or 400)
        win.maximize()

        def go():
            # Maximized, the title bar's middle sits just under the top bar.
            start = (MX + MW / 2, MY + 32 + 22)
            end = spot(target)
            log(f'>>> {"mouse" if MOUSE else "touch"} drag title bar -> {target} {tuple(round(v) for v in end)}')
            touch('Down', 0, *start)
            # Step on timers, not sleep(): GTK has to see the touches to start
            # the window move.
            steps = iter(range(1, 31))

            def move():
                i = next(steps, None)
                if i is None:
                    # Hold still a moment, like a person would, then lift.
                    GLib.timeout_add(hold, lift)
                    return False
                f = i / 30
                touch('Motion', 0, start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)
                return True

            def lift():
                touch('Up', 0)
                GLib.timeout_add(1500, drag_next)
                return False
            GLib.timeout_add(150, lambda: GLib.timeout_add(20, move) and False)
            return False
        GLib.timeout_add(800, go)
        return False

    def start():
        call(RD, rd_session, RD + '.Session', 'Start')
        if MOUSE:
            # The first pointer event after starting gets lost; spend it here.
            call(RD, rd_session, RD + '.Session', 'NotifyPointerMotionAbsolute',
                 GLib.Variant('(sdd)', (stream, MW / 2 * SCALE, MH / 2 * SCALE)))
        GLib.timeout_add(700, drag_next)
        return False
    GLib.timeout_add(800, start)


app.connect('activate', on_activate)
app.run([])
