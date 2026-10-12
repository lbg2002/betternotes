# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore XWayland sticky notes alongside their draggable compact handles.

The position is computed from the *current* compact-window geometry, not
from an earlier position stored when the note was collapsed. Coordinates and
screen dimensions are X11 logical/root coordinates; no wmctrl dependency.
"""
import ctypes
import ctypes.util


def restore_position(handle, expanded, monitors):
    """Place expanded top edge near the handle, safely within one monitor.

    Each rectangle is (x, y, width, height). A compact handle near an edge
    remains near that edge. For multi-monitor setups, select the screen
    containing the handle's center, or the closest monitor otherwise.
    """
    hx, hy, hw, hh = handle
    ww, wh = expanded
    cx, cy = hx + hw / 2, hy + hh / 2
    if not monitors:
        return round(cx - ww / 2), round(hy)
    def dist(mon):
        x, y, w, h = mon
        dx = max(x - cx, 0, cx - (x + w))
        dy = max(y - cy, 0, cy - (y + h))
        return dx * dx + dy * dy
    mx, my, mw, mh = min(monitors, key=dist)
    ww, wh = min(ww, mw), min(wh, mh)
    target_x = cx - ww / 2
    target_y = hy
    return (
        round(max(mx, min(target_x, mx + mw - ww))),
        round(max(my, min(target_y, my + mh - wh))),
    )


def looks_wm_centered(window, monitors, target):
    """Recognize an unexpected desktop-center placement, not manual dragging.

    The original target must be visibly away from the monitor center. Allow
    some Y variation for compositor panels and window decorations.
    """
    if window is None or not monitors:
        return False
    x, y, width, height = window
    tx, ty = target
    for mx, my, mw, mh in monitors:
        if not (mx <= tx < mx + mw and my <= ty < my + mh):
            continue
        center_x = mx + (mw - width) / 2
        center_y = my + (mh - height) / 2
        if abs(tx - center_x) < 130 and abs(ty - center_y) < 130:
            return False
        return abs(x - center_x) <= 130 and abs(y - center_y) <= 155
    return False


def get_window_geometry(surface):
    """Return X11 root geometry or None (including native Wayland surfaces)."""
    try:
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(surface, GdkX11.X11Surface):
            return None
        xid = surface.get_xid()
        libname = ctypes.util.find_library('X11')
        if not libname:
            return None
        lib = ctypes.CDLL(libname)
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XGetGeometry.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
        ]
        lib.XGetGeometry.restype = ctypes.c_int
        lib.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
        ]
        lib.XTranslateCoordinates.restype = ctypes.c_int
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = lib.XOpenDisplay(None)
        if not dpy:
            return None
        try:
            root, child = ctypes.c_ulong(), ctypes.c_ulong()
            rx, ry, bx, by = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
            w, h, border, depth = (ctypes.c_uint() for _ in range(4))
            if not lib.XGetGeometry(
                dpy, xid, ctypes.byref(root), ctypes.byref(rx), ctypes.byref(ry),
                ctypes.byref(w), ctypes.byref(h), ctypes.byref(border),
                ctypes.byref(depth),
            ):
                return None
            if not lib.XTranslateCoordinates(
                dpy, xid, lib.XDefaultRootWindow(dpy), 0, 0,
                ctypes.byref(bx), ctypes.byref(by), ctypes.byref(child),
            ):
                return None
            return bx.value, by.value, w.value, h.value
        finally:
            lib.XCloseDisplay(dpy)
    except (ImportError, ValueError, OSError, AttributeError):
        return None


def move_window(surface, x, y):
    """Ask an EWMH window manager to move a mapped X11 toplevel.

    Mutter/XWayland may override plain XMoveWindow after GTK4 remaps a
    window. _NET_MOVERESIZE_WINDOW is a root-client request that the WM
    interprets in desktop coordinates. It remains a request, not a guarantee.
    """
    try:
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(surface, GdkX11.X11Surface):
            return False
        libname = ctypes.util.find_library('X11')
        if not libname:
            return False
        lib = ctypes.CDLL(libname)
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.XInternAtom.restype = ctypes.c_ulong
        lib.XSendEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
            ctypes.c_void_p,
        ]
        lib.XSendEvent.restype = ctypes.c_int
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]

        class XClientMessageEvent(ctypes.Structure):
            _fields_ = [
                ('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                ('format', ctypes.c_int), ('data', ctypes.c_long * 5),
            ]

        class XEvent(ctypes.Union):
            _fields_ = [
                ('xclient', XClientMessageEvent),
                ('pad', ctypes.c_char * 192),
            ]

        dpy = lib.XOpenDisplay(None)
        if not dpy:
            return False
        try:
            root = lib.XDefaultRootWindow(dpy)
            atom = lib.XInternAtom(dpy, b'_NET_MOVERESIZE_WINDOW', False)
            event = XEvent()
            event.xclient.type = 33   # ClientMessage
            event.xclient.send_event = True
            event.xclient.display = dpy
            event.xclient.window = surface.get_xid()
            event.xclient.message_type = atom
            event.xclient.format = 32
            # NorthWestGravity (1); x and y supplied; source=application.
            event.xclient.data[0] = 1 | (1 << 8) | (1 << 9) | (1 << 12)
            event.xclient.data[1] = int(x)
            event.xclient.data[2] = int(y)
            event.xclient.data[3] = 0
            event.xclient.data[4] = 0
            sent = lib.XSendEvent(
                dpy, root, False, (1 << 20) | (1 << 19),
                ctypes.byref(event),
            )
            lib.XFlush(dpy)
            return bool(sent)
        finally:
            lib.XCloseDisplay(dpy)
    except (ImportError, ValueError, OSError, AttributeError):
        return False


def move_window_direct(surface, x, y):
    """Fallback when the WM does not implement the EWMH positioning request."""
    try:
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(surface, GdkX11.X11Surface):
            return False
        name = ctypes.util.find_library('X11')
        if not name:
            return False
        lib = ctypes.CDLL(name)
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                     ctypes.c_int, ctypes.c_int]
        lib.XMoveWindow.restype = ctypes.c_int
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = lib.XOpenDisplay(None)
        if not dpy:
            return False
        try:
            lib.XMoveWindow(dpy, surface.get_xid(), int(x), int(y))
            lib.XFlush(dpy)
            return True
        finally:
            lib.XCloseDisplay(dpy)
    except (ImportError, ValueError, OSError, AttributeError):
        return False
