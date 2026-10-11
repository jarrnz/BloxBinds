"""Normal mouse drag with physical coordinates, strict guards and balanced release."""

import ctypes as C
import time
from contextlib import contextmanager
from ctypes import wintypes as W

from .quickmove import Geometry
from .win32 import INPUT, INPUT_TAG, MOUSEINPUT


class MouseAPI:
    def __init__(self, api):
        self.api = api
        self.user = api.user
        declare = api._declare
        declare(self.user, "GetClientRect", [W.HWND, C.POINTER(W.RECT)], W.BOOL)
        declare(self.user, "ClientToScreen", [W.HWND, C.POINTER(W.POINT)], W.BOOL)
        declare(self.user, "GetCursorPos", [C.POINTER(W.POINT)], W.BOOL)
        declare(self.user, "GetDpiForWindow", [W.HWND], W.UINT)
        declare(self.user, "SetThreadDpiAwarenessContext", [W.HANDLE], W.HANDLE)
        declare(self.user, "WindowFromPoint", [W.POINT], W.HWND)
        declare(self.user, "GetAncestor", [W.HWND, W.UINT], W.HWND)
        declare(self.user, "IsIconic", [W.HWND], W.BOOL)
        declare(self.user, "GetSystemMetrics", [C.c_int], C.c_int)

    @contextmanager
    def physical_coordinates(self):
        old = self.user.SetThreadDpiAwarenessContext(C.c_void_p(-4))
        if not old:
            raise OSError("Physical mouse coordinate context unavailable; no drag permitted.")
        try:
            yield
        finally:
            self.user.SetThreadDpiAwarenessContext(old)

    def geometry(self, focus):
        with self.physical_coordinates():
            rect, origin = W.RECT(), W.POINT()
            if (not focus.roblox or self.user.IsIconic(focus.hwnd) or
                    not self.user.GetClientRect(focus.hwnd, C.byref(rect)) or
                    not self.user.ClientToScreen(focus.hwnd, C.byref(origin))):
                raise OSError("Roblox client geometry is uncertain.")
            dpi = self.user.GetDpiForWindow(focus.hwnd)
            if not dpi or rect.right <= 0 or rect.bottom <= 0:
                raise OSError("Roblox client size/DPI is uncertain.")
            return Geometry(focus.hwnd, focus.pid, origin.x, origin.y, rect.right, rect.bottom, dpi)

    def cursor(self):
        with self.physical_coordinates():
            point = W.POINT()
            if not self.user.GetCursorPos(C.byref(point)):
                raise OSError("Cursor position is uncertain.")
            return point.x, point.y

    def belongs(self, hwnd, point):
        with self.physical_coordinates():
            window = self.user.WindowFromPoint(W.POINT(*point))
            return bool(window and self.user.GetAncestor(window, 2) == hwnd)

    def snapshot(self, focus):
        geometry, cursor = self.geometry(focus), self.cursor()
        if not self.belongs(focus.hwnd, cursor):
            raise OSError("Cursor is outside Roblox or covered by another window.")
        return geometry, cursor

    def fingerprint(self, hwnd, point, radius):
        from .screen import fingerprint
        with self.physical_coordinates():
            for x in (point[0]-radius, point[0]+radius-1):
                for y in (point[1]-radius, point[1]+radius-1):
                    if not self.belongs(hwnd, (x,y)):
                        raise OSError("Target slot is obscured or outside Roblox.")
            return fingerprint(self.api, point, radius)

    def _send(self, point=None, flags=0):
        x = y = 0
        if point is not None:
            left, top, width, height = (self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79))
            if width <= 1 or height <= 1 or not (left <= point[0] < left + width and top <= point[1] < top + height):
                raise OSError("Mouse coordinate is outside the virtual desktop.")
            x = round((point[0] - left) * 65535 / (width - 1))
            y = round((point[1] - top) * 65535 / (height - 1))
            flags |= 0xC001 | 0x2000  # ABSOLUTE | VIRTUALDESK | MOVE | NOCOALESCE
        event = INPUT(type=0, mi=MOUSEINPUT(x, y, 0, flags, 0, INPUT_TAG))
        if self.user.SendInput(1, C.byref(event), C.sizeof(INPUT)) != 1:
            raise OSError("Windows rejected mouse input; quick-move stopped.")

    def drag(self, move, allowed):
        with self.physical_coordinates():
            # Release the configured combination naturally; no synthetic modifier changes.
            deadline = time.monotonic() + 0.6
            while any(self.user.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
                if not allowed() or time.monotonic() >= deadline:
                    return False
                time.sleep(0.01)
            if (not allowed() or max(abs(a - b) for a, b in zip(self.cursor(), move.source)) > 3 or
                    any(self.user.GetAsyncKeyState(vk) & 0x8000 for vk in (1, 2, 4))):
                return False
            # Validate the desktop targets before pressing any mouse button.
            left, top, width, height = (self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79))
            if not all(left <= p[0] < left + width and top <= p[1] < top + height for p in (move.source, move.target)):
                return False
            # Exact visual reference is conservative: any changed/covered/occupied-looking target blocks.
            if self.fingerprint(move.geometry.hwnd, move.target, move.radius) != move.empty_hash:
                return False
            pressed = False
            try:
                if not allowed():
                    return False
                pressed = True  # Attempt release even if SendInput reports failure.
                self._send(flags=0x0002)
                time.sleep(0.03)
                for step in range(1, 7):
                    if not allowed():
                        return False
                    point = tuple(round(a + (b - a) * step / 6) for a, b in zip(move.source, move.target))
                    self._send(point)
                    time.sleep(0.025)
                if not allowed():
                    return False
                return True
            finally:
                if pressed:
                    self._send(flags=0x0004)  # Balance our button-down even after cancellation.
