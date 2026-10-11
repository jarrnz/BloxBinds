"""One optional, non-activating Tk status window; reuses the main status poll."""
import ctypes as C
from ctypes import wintypes as W
import tkinter as tk

MONITORPROC = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)


class MonitorInfo(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]


def visible_position(position, size, monitors):
    """Clamp to an actual monitor work area, including negative coordinates/gaps."""
    x, y = position or (monitors[0][0] + 20, monitors[0][1] + 20)
    width, height = size
    def distance(rect):
        left, top, right, bottom = rect
        return max(left-x, 0, x-right)**2 + max(top-y, 0, y-bottom)**2
    left, top, right, bottom = min(monitors, key=distance)
    return max(left, min(x, right-width)), max(top, min(y, bottom-height))


class IndicatorAPI:
    def __init__(self):
        self.user = C.WinDLL("user32", use_last_error=True)
        from .win32 import WindowsAPI
        declarations = [("GetAncestor", [W.HWND, W.UINT], W.HWND),
                        ("GetWindowLongPtrW", [W.HWND, C.c_int], C.c_ssize_t),
                        ("SetWindowLongPtrW", [W.HWND, C.c_int, C.c_ssize_t], C.c_ssize_t),
                        ("SetWindowPos", [W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL),
                        ("ShowWindow", [W.HWND,C.c_int],W.BOOL),
                        ("EnumDisplayMonitors", [W.HDC,C.POINTER(W.RECT),MONITORPROC,W.LPARAM],W.BOOL),
                        ("GetMonitorInfoW", [W.HANDLE,C.POINTER(MonitorInfo)],W.BOOL)]
        for name, args, result in declarations:
            WindowsAPI._declare(self.user, name, args, result)

    def monitors(self):
        result = []
        @MONITORPROC
        def visit(handle, dc, rect, data):
            info = MonitorInfo(cbSize=C.sizeof(MonitorInfo))
            if self.user.GetMonitorInfoW(handle, C.byref(info)):
                result.append((info.work.left,info.work.top,info.work.right,info.work.bottom))
            return True
        if not self.user.EnumDisplayMonitors(None, None, visit, 0) or not result:
            raise OSError("Could not locate a visible monitor for the status indicator.")
        return result

    def prepare(self, widget):
        hwnd = self.user.GetAncestor(widget.winfo_id(), 2)
        if not hwnd:
            raise OSError("Could not create status indicator window.")
        C.set_last_error(0)
        style = self.user.GetWindowLongPtrW(hwnd, -20)
        self.user.SetWindowLongPtrW(hwnd, -20, style | 0x08000000 | 0x80)
        if C.get_last_error():
            raise C.WinError(C.get_last_error())
        return hwnd

    def position(self, hwnd, position, size, topmost, show=False):
        # SWP_NOACTIVATE | SWP_FRAMECHANGED; no SetForegroundWindow/focus calls.
        if not self.user.SetWindowPos(hwnd, W.HWND(-1 if topmost else -2), *position, *size, 0x10 | 0x20):
            raise OSError("Could not position status indicator.")
        if show:
            self.user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


class Indicator:
    SIZE = (280, 62)

    def __init__(self, root, on_hide, on_position, api=None):
        self.root, self.on_hide, self.on_position = root, on_hide, on_position
        self.api = api or IndicatorAPI()
        self.window = None
        self.hwnd = None
        self.visible = False
        self.position = None
        self.topmost = True
        self.status = None
        self._drag_origin = None

    def show(self, status, position=None, topmost=True):
        self.topmost = topmost
        self.position = visible_position(position or self.position, self.SIZE, self.api.monitors())
        if self.window is None:
            window = self.window = tk.Toplevel(self.root, takefocus=False)
            window.withdraw()
            window.overrideredirect(True)
            window.configure(bg="#172d3d")
            window.geometry(f"{self.SIZE[0]}x{self.SIZE[1]}{self.position[0]:+d}{self.position[1]:+d}")
            title = tk.Label(window, text="BloxBinds · drag to move", bg="#172d3d", fg="#cedce5", font=("Segoe UI",9))
            title.pack(anchor="w", padx=9, pady=(5,0))
            self.label = tk.Label(window, bg="#172d3d", fg="white", font=("Segoe UI",10), anchor="w")
            self.label.pack(anchor="w", padx=9)
            close = tk.Label(window, text="×", bg="#172d3d", fg="white", cursor="hand2", font=("Segoe UI",12))
            close.place(relx=1, x=-8, y=1, anchor="ne")
            close.bind("<Button-1>", lambda _: self.on_hide())
            for widget in (window,title,self.label):
                widget.bind("<Button-1>", self._begin_drag)
                widget.bind("<B1-Motion>", self._drag)
                widget.bind("<ButtonRelease-1>", self._end_drag)
            window.update_idletasks()
            self.hwnd = self.api.prepare(window)
        self.set_status(status)
        self.api.position(self.hwnd,self.position,self.SIZE,self.topmost,show=True)
        self.visible = True

    def set_status(self, status):
        if self.window is not None and self.status != status:
            self.status = status
            display = "Active" if status == "Active — Roblox Focused" else status
            self.label.configure(text="● " + display)

    def _begin_drag(self, event):
        self._drag_origin = (event.x_root,event.y_root,*self.position)

    def _drag(self, event):
        if self._drag_origin:
            x,y,px,py = self._drag_origin
            self.position = (px+event.x_root-x,py+event.y_root-y)
            self.api.position(self.hwnd,self.position,self.SIZE,self.topmost)

    def _end_drag(self, _):
        self._drag_origin = None
        self.recover_position()
        self.on_position(self.position)

    def recover_position(self):
        if self.visible:
            position = visible_position(self.position,self.SIZE,self.api.monitors())
            if position != self.position:
                self.position = position
                self.api.position(self.hwnd,position,self.SIZE,self.topmost)
                self.on_position(position)

    def hide(self):
        if self.window:
            self.window.withdraw()
            self.api.user.ShowWindow(self.hwnd, 0)
        self.visible = False

    def close(self):
        if self.window:
            self.window.destroy()
        self.window = self.hwnd = None
        self.visible = False
