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
    """Request compositor/WM position of X11 client; WM may constrain it."""
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
        lib.XMoveWindow.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int
        ]
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
