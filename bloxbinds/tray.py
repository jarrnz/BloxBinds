"""Native Windows tray; all Tk work is queued to the main thread."""
import ctypes as C
import threading
from ctypes import wintypes as W
from .win32 import LRESULT

WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

class WindowClass(C.Structure):
    _fields_ = [("style",W.UINT),("proc",WNDPROC),("class_extra",C.c_int),("window_extra",C.c_int),
                ("instance",W.HINSTANCE),("icon",W.HICON),("cursor",W.HANDLE),("background",W.HBRUSH),
                ("menu",W.LPCWSTR),("name",W.LPCWSTR)]

class IconData(C.Structure):
    _fields_ = [("size",W.DWORD),("hwnd",W.HWND),("uid",W.UINT),("flags",W.UINT),
                ("callback",W.UINT),("icon",W.HICON),("tip",W.WCHAR*128),
                ("state",W.DWORD),("state_mask",W.DWORD),("info",W.WCHAR*256),
                ("version",W.UINT),("title",W.WCHAR*64),("info_flags",W.DWORD),
                ("guid",C.c_ubyte*16),("balloon",W.HICON)]

class Tray:
    def __init__(self, api, events, enabled):
        self.api, self.events, self.enabled = api, events, enabled
        self.thread = None
        self.hwnd = None
        self.ready = threading.Event()
        self.error = None
        self._stopping = threading.Event()
        self.available = False

    def start(self):
        self.thread = threading.Thread(target=self._run,name="BloxBinds-tray",daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            self.stop()
            raise OSError("System tray startup timed out.")
        if self.error:
            self.stop()
            raise OSError(self.error)

    def _run(self):
        user, kernel = self.api.user, self.api.kernel
        shell = C.WinDLL("shell32",use_last_error=True)
        declare = self.api._declare
        declarations = [
            ("RegisterClassW",[C.POINTER(WindowClass)],W.ATOM),
            ("UnregisterClassW",[W.LPCWSTR,W.HINSTANCE],W.BOOL),
            ("CreateWindowExW",[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,W.LPVOID],W.HWND),
            ("DestroyWindow",[W.HWND],W.BOOL),
            ("DefWindowProcW",[W.HWND,W.UINT,W.WPARAM,W.LPARAM],LRESULT),
            ("PostMessageW",[W.HWND,W.UINT,W.WPARAM,W.LPARAM],W.BOOL),
            ("PostQuitMessage",[C.c_int],None),
            ("LoadIconW",[W.HINSTANCE,W.LPCWSTR],W.HICON),
            ("CreatePopupMenu",[],W.HMENU),
            ("AppendMenuW",[W.HMENU,W.UINT,C.c_size_t,W.LPCWSTR],W.BOOL),
            ("TrackPopupMenu",[W.HMENU,W.UINT,C.c_int,C.c_int,C.c_int,W.HWND,C.POINTER(W.RECT)],W.UINT),
            ("DestroyMenu",[W.HMENU],W.BOOL),
            ("GetCursorPos",[C.POINTER(W.POINT)],W.BOOL),
            ("SetForegroundWindow",[W.HWND],W.BOOL),
            ("RegisterWindowMessageW",[W.LPCWSTR],W.UINT)]
        data = None
        registered = False
        module = kernel.GetModuleHandleW(None)
        name = "BloxBindsTrayWindow"
        try:
            for function,args,result in declarations:
                declare(user,function,args,result)
            declare(shell,"Shell_NotifyIconW",[W.DWORD,C.POINTER(IconData)],W.BOOL)
            restart = user.RegisterWindowMessageW("TaskbarCreated")
            def add_icon():
                if not shell.Shell_NotifyIconW(0,C.byref(data)):
                    raise OSError("Windows system tray is unavailable.")
                self.available = True
                shell.Shell_NotifyIconW(4,C.byref(data))  # Version 0, traditional notification events.
            @WNDPROC
            def procedure(hwnd,message,wp,lp):
                try:
                    if restart and message == restart:
                        add_icon()
                    elif message == 0x8001:
                        if lp in (0x203,0x202):
                            self.events.put(("tray","restore"))
                        elif lp == 0x205:
                            menu = user.CreatePopupMenu()
                            try:
                                for command,label in ((1,"Restore BloxBinds"),(2,"Disable keybinds" if self.enabled() else "Enable keybinds"),(3,"Exit")):
                                    user.AppendMenuW(menu,0,command,label)
                                point = W.POINT()
                                if user.GetCursorPos(C.byref(point)):
                                    user.SetForegroundWindow(hwnd)
                                    selected = user.TrackPopupMenu(menu,0x100|0x2,point.x,point.y,0,hwnd,None)
                                    if selected in (1,2,3):
                                        self.events.put(("tray",{1:"restore",2:"toggle",3:"exit"}[selected]))
                                    user.PostMessageW(hwnd,0,0,0)
                            finally:
                                if menu:
                                    user.DestroyMenu(menu)
                    elif message == 0x10:
                        user.PostQuitMessage(0)
                    elif message == 0x16 and wp:
                        self.events.put(("tray","exit"))
                        user.PostQuitMessage(0)
                    else:
                        return user.DefWindowProcW(hwnd,message,wp,lp)
                except Exception:
                    self.available = False
                    self.events.put(("tray","restore"))
                    self.events.put(("error","System tray failed; application window restored."))
                return 0
            wc = WindowClass(proc=procedure,instance=module,name=name)
            if not user.RegisterClassW(C.byref(wc)):
                raise OSError("Tray window registration failed.")
            registered = True
            self.hwnd = user.CreateWindowExW(0,name,"BloxBinds",0,0,0,0,0,None,None,module,None)
            if not self.hwnd:
                raise OSError("Tray window creation failed.")
            icon = user.LoadIconW(None,C.cast(C.c_void_p(32512),W.LPCWSTR))
            data = IconData(size=C.sizeof(IconData),hwnd=self.hwnd,uid=1,flags=7,callback=0x8001,icon=icon,tip="BloxBinds — wirru")
            add_icon()
            self.ready.set()
            message = W.MSG()
            while not self._stopping.is_set():
                result = user.GetMessageW(C.byref(message),None,0,0)
                if result == -1:
                    raise OSError("Tray message loop failed.")
                if not result:
                    break
                user.TranslateMessage(C.byref(message))
                user.DispatchMessageW(C.byref(message))
        except Exception as error:
            self.error = str(error)
            self.events.put(("error",self.error))
            self.events.put(("tray","restore"))
        finally:
            self.available = False
            if data:
                shell.Shell_NotifyIconW(2,C.byref(data))
            if self.hwnd:
                user.DestroyWindow(self.hwnd)
                self.hwnd = None
            if registered:
                user.UnregisterClassW(name,module)
            self.ready.set()

    def stop(self):
        self._stopping.set()
        if self.hwnd:
            self.api.user.PostMessageW(self.hwnd,0x10,0,0)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(3)
            if self.thread.is_alive():
                raise RuntimeError("System tray did not shut down cleanly.")
