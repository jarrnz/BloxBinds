"""Windows metadata, low-level hooks and SendInput; no Roblox memory access."""

import ctypes as C
import os
import queue
import sys
import threading
import time
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import PureWindowsPath

from .keys import Binding, MODIFIER_VKS, VK_NAMES
from .quickmove import QuickMove

ULONG_PTR = C.c_size_t
LRESULT = C.c_ssize_t
HOOKPROC = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)(LRESULT, C.c_int, W.WPARAM, W.LPARAM)
ENUMPROC = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)(W.BOOL, W.HWND, W.LPARAM)
CLIENT_NAMES = {"robloxplayerbeta.exe", "robloxplayer.exe"}
INPUT_TAG = 0x424C4F58
WM_QUIT = 0x0012


class KBDLLHOOKSTRUCT(C.Structure):
    _fields_ = [("vkCode", W.DWORD), ("scanCode", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MSLLHOOKSTRUCT(C.Structure):
    _fields_ = [("pt", W.POINT), ("mouseData", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class INPUTUNION(C.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", W.DWORD), ("data", INPUTUNION)]


class GUITHREADINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("hwndActive", W.HWND),
                ("hwndFocus", W.HWND), ("hwndCapture", W.HWND), ("hwndMenuOwner", W.HWND),
                ("hwndMoveSize", W.HWND), ("hwndCaret", W.HWND), ("rcCaret", W.RECT)]


@dataclass(frozen=True)
class Focus:
    hwnd: int = 0
    pid: int = 0
    roblox: bool = False
    text_control: bool = False


class WindowsAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise OSError("BloxBinds requires Windows 10 or 11.")
        self.user = C.WinDLL("user32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self._declare(self.user, "GetForegroundWindow", [], W.HWND)
        self._declare(self.user, "GetWindowThreadProcessId", [W.HWND, C.POINTER(W.DWORD)], W.DWORD)
        self._declare(self.user, "GetGUIThreadInfo", [W.DWORD, C.POINTER(GUITHREADINFO)], W.BOOL)
        self._declare(self.user, "GetClassNameW", [W.HWND, W.LPWSTR, C.c_int], C.c_int)
        self._declare(self.user, "IsWindowVisible", [W.HWND], W.BOOL)
        self._declare(self.user, "EnumWindows", [ENUMPROC, W.LPARAM], W.BOOL)
        self._declare(self.user, "GetAsyncKeyState", [C.c_int], W.SHORT)
        self._declare(self.user, "SetWindowsHookExW", [C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD], W.HANDLE)
        self._declare(self.user, "UnhookWindowsHookEx", [W.HANDLE], W.BOOL)
        self._declare(self.user, "CallNextHookEx", [W.HANDLE, C.c_int, W.WPARAM, W.LPARAM], LRESULT)
        self._declare(self.user, "GetMessageW", [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT], C.c_int)
        self._declare(self.user, "PeekMessageW", [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT], W.BOOL)
        self._declare(self.user, "TranslateMessage", [C.POINTER(W.MSG)], W.BOOL)
        self._declare(self.user, "DispatchMessageW", [C.POINTER(W.MSG)], LRESULT)
        self._declare(self.user, "PostThreadMessageW", [W.DWORD, W.UINT, W.WPARAM, W.LPARAM], W.BOOL)
        self._declare(self.user, "SendInput", [W.UINT, C.POINTER(INPUT), C.c_int], W.UINT)
        self._declare(self.user, "MapVirtualKeyW", [W.UINT, W.UINT], W.UINT)
        self._declare(self.kernel, "GetModuleHandleW", [W.LPCWSTR], W.HMODULE)
        self._declare(self.kernel, "GetCurrentThreadId", [], W.DWORD)
        self._declare(self.kernel, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
        self._declare(self.kernel, "CloseHandle", [W.HANDLE], W.BOOL)
        self._declare(self.kernel, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)
        self._declare(self.kernel, "CreateMutexW", [W.LPVOID, W.BOOL, W.LPCWSTR], W.HANDLE)
        self._cache: dict[int, tuple[float, bool]] = {}
        self._cache_lock = threading.Lock()

    @staticmethod
    def _declare(dll, name, args, result):
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result

    def is_client(self, pid: int) -> bool:
        if not pid:
            return False
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(pid)
            if cached and now - cached[0] < 1:
                return cached[1]
        # QUERY_LIMITED_INFORMATION is used only to ask for the executable path.
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        found = False
        if handle:
            try:
                size = W.DWORD(32768)
                path = C.create_unicode_buffer(size.value)
                if self.kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(size)):
                    found = PureWindowsPath(path.value).name.lower() in CLIENT_NAMES
            finally:
                self.kernel.CloseHandle(handle)
        with self._cache_lock:
            if len(self._cache) > 128:
                self._cache.clear()
            self._cache[pid] = now, found
        return found

    def focus(self) -> Focus:
        hwnd = self.user.GetForegroundWindow()
        if not hwnd:
            return Focus()
        pid = W.DWORD()
        tid = self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        text = False
        gui = GUITHREADINFO(cbSize=C.sizeof(GUITHREADINFO))
        if self.user.GetGUIThreadInfo(tid, C.byref(gui)) and gui.hwndFocus:
            name = C.create_unicode_buffer(256)
            self.user.GetClassNameW(gui.hwndFocus, name, len(name))
            text = "edit" in name.value.lower() or bool(gui.hwndCaret)
        return Focus(int(hwnd), pid.value, self.is_client(pid.value), text)

    def detected(self) -> bool:
        found = False

        @ENUMPROC
        def visit(hwnd, _):
            nonlocal found
            if self.user.IsWindowVisible(hwnd):
                pid = W.DWORD()
                self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
                if self.is_client(pid.value):
                    found = True
                    return False
            return True

        self.user.EnumWindows(visit, 0)
        return found

    def tap_slot(self, slot: int, modifiers: tuple[int, ...]):
        """One atomic keyboard batch; held Ctrl/Shift are restored afterwards."""
        events = []

        def add(vk, up=False, scan=False):
            flags = (0x0002 if up else 0) | (0x0008 if scan else 0)
            events.append(INPUT(type=1, ki=KEYBDINPUT(
                0 if scan else vk, self.user.MapVirtualKeyW(vk, 0) if scan else 0,
                flags, 0, INPUT_TAG)))

        for modifier in modifiers:
            add(modifier, up=True)
        add(48 + slot, scan=True)
        add(48 + slot, up=True, scan=True)
        for modifier in reversed(modifiers):
            add(modifier)
        batch = (INPUT * len(events))(*events)
        sent = self.user.SendInput(len(batch), batch, C.sizeof(INPUT))
        if sent != len(batch):
            # Best-effort balancing if Windows accepted only part of the batch.
            cleanup = [INPUT(type=1, ki=KEYBDINPUT(0, self.user.MapVirtualKeyW(48 + slot, 0),
                                                  0x000A, 0, INPUT_TAG))]
            cleanup.extend(INPUT(type=1, ki=KEYBDINPUT(vk, 0, 0, 0, INPUT_TAG)) for vk in modifiers)
            array = (INPUT * len(cleanup))(*cleanup)
            self.user.SendInput(len(array), array, C.sizeof(INPUT))
            raise OSError("Windows rejected simulated input. Remapping has been disabled.")


class SingleInstance:
    def __init__(self, api: WindowsAPI):
        self.api = api
        C.set_last_error(0)
        self.handle = api.kernel.CreateMutexW(None, False, "Local\\BloxBinds-1")
        if not self.handle:
            raise C.WinError(C.get_last_error())
        if C.get_last_error() == 183:
            self.close()
            raise OSError("BloxBinds is already running. Open its existing window.")

    def close(self):
        if self.handle:
            self.api.kernel.CloseHandle(self.handle)
            self.handle = None


class InputService:
    def __init__(self, engine, api=None):
        self.engine = engine
        self.api = api or WindowsAPI()
        self.events = queue.SimpleQueue()
        self._output = queue.Queue(maxsize=32)
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._worker = None
        self._thread_id = 0
        self._startup_error = None
        self._modifiers: set[int] = set()
        self._recording = False
        self._last_focus = (0, 0)
        self.quickmove = QuickMove()
        self._mouse_api = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Input service can only be started once.")
        self._worker = threading.Thread(target=self._send_loop, name="BloxBinds-output", daemon=True)
        self._thread = threading.Thread(target=self._hook_loop, name="BloxBinds-hooks", daemon=True)
        self._worker.start()
        self._thread.start()
        if not self._ready.wait(3):
            self.stop()
            raise OSError("Windows input hooks did not start in time.")
        if self._startup_error:
            self.stop()
            raise OSError(self._startup_error)

    def record(self, active: bool):
        self._recording = active

    def mouse_api(self):
        if self._mouse_api is None:
            from .mouse import MouseAPI
            self._mouse_api = MouseAPI(self.api)
        return self._mouse_api

    def _inventory_shortcut(self, key, down, modifiers, focus):
        from .keys import parse_binding
        shortcut = parse_binding(self.quickmove.shortcut)
        if shortcut in self.engine.mapping:
            return False
        if not (down and focus.roblox and shortcut and Binding(key, modifiers) == shortcut and not self._recording):
            return False
        with self.engine.lock:
            repeated = key in self.engine.held
            self.engine.held.add(key)
            self.engine.suppressed.add(key)
        if repeated:
            return True
        try:
            if self.quickmove.active:
                self.quickmove.cancel()
            else:
                if not self.engine.enabled or focus.text_control or (self.engine.text_paused and self.engine.pause_key != "backquote"):
                    raise ValueError("Resume remapping and close all text entry before Inventory Mode.")
                geometry, _ = self.mouse_api().snapshot(focus)
                self.quickmove.activate(geometry)
                # The explicit mode toggle asserts the backpack is open, not that chat is closed automatically.
                with self.engine.lock:
                    self.engine.text_paused = False
                    self.engine.pause_key = None
                    self.engine.generation += 1
            self.events.put(("quickmove", self.quickmove.status()))
        except (OSError, ValueError) as error:
            self.quickmove.cancel()
            self.events.put(("quickmove", str(error)))
        return True

    def _capture_click(self, down):
        if not down:
            consumed = getattr(self, "_calibration_click", False)
            self._calibration_click = False
            return consumed
        focus = self.api.focus()
        if not self.quickmove.calibrating or not focus.roblox:
            return False
        self._calibration_click = True
        try:
            if focus.text_control:
                raise ValueError("Close text entry before calibration.")
            geometry, cursor = self.mouse_api().snapshot(focus)
            message, profile = self.quickmove.capture(geometry, cursor)
            self.events.put(("quickmove", message))
            if profile:
                self.events.put(("calibrated", (profile, geometry)))
        except (OSError, ValueError) as error:
            self.events.put(("quickmove", str(error)))
        return True

    def _dispatch(self, key, down):
        focus = self.api.focus()
        token = (focus.hwnd, focus.pid)
        if token != self._last_focus:
            self.engine.focus_lost()
            self.quickmove.cancel()
            self._last_focus = token
        modifiers = frozenset(MODIFIER_VKS[vk] for vk in self._modifiers)
        if focus.text_control or (down and key in {"enter", "slash", "backquote", "escape", "f10", "f12"}):
            self.quickmove.cancel()
        if self._inventory_shortcut(key, down, modifiers, focus):
            return True
        inventory_at_start = self.quickmove.active
        move = None
        if self.quickmove.busy and down:
            self.quickmove.cancel()
        if (down and key not in self.engine.held and not self._recording and self.quickmove.active and
                not focus.text_control and self.engine.allowed(self.engine.generation, focus.roblox)):
            slot = self.engine.mapping.get(Binding(key, modifiers))
            if slot:
                try:
                    geometry, cursor = self.mouse_api().snapshot(focus)
                    move = self.quickmove.take(slot, geometry, cursor, self.engine.generation)
                except (OSError, ValueError) as error:
                    self.quickmove.cancel()
                    self.events.put(("quickmove", str(error)))
        inventory = inventory_at_start
        # In Inventory Mode, unsafe slot actions are consumed without a gameplay fallback.
        decision = self.engine.process(key, down, modifiers, focused=focus.roblox,
                                       native_text=focus.text_control, quick_move=inventory or move is not None)
        if move and decision.slot is None:
            self.quickmove.complete(move)
        if key == "f12" and down and {"ctrl", "alt"}.issubset(modifiers):
            self._recording = False
            self.events.put(("emergency", None))
        if self._recording and down and focus.pid == os.getpid():
            if key == "escape":
                self.events.put(("record", None))
            else:
                value = "+".join([m for m in ("ctrl", "shift", "alt", "win") if m in modifiers] + [key])
                self.events.put(("record", value))
            self._recording = False
            # Recording in our own settings window must not type into entries.
            with self.engine.lock:
                self.engine.suppressed.add(key)
            return True
        if decision.slot and (not inventory or move is not None):
            try:
                self._output.put_nowait((decision.slot, decision.generation, token, move))
            except queue.Full:
                self.quickmove.cancel()
                self.engine.enable(False)
                self.events.put(("error", "Input queue filled; remapping disabled."))
        return decision.suppress

    def _hook_loop(self):
        keyboard_hook = mouse_hook = None
        try:
            self._thread_id = self.api.kernel.GetCurrentThreadId()
            message = W.MSG()
            self.api.user.PeekMessageW(C.byref(message), None, 0, 0, 0)
            # Seed keys held before startup. Synthetic events never update these.
            self._modifiers = {vk for vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)
                               if self.api.user.GetAsyncKeyState(vk) & 0x8000}

            @HOOKPROC
            def keyboard(code, wp, lp):
                try:
                    if code >= 0 and wp in (0x100, 0x101, 0x104, 0x105):
                        event = C.cast(lp, C.POINTER(KBDLLHOOKSTRUCT)).contents
                        if not (event.flags & 0x10 or event.dwExtraInfo == INPUT_TAG):
                            down = wp in (0x100, 0x104)
                            if event.vkCode in MODIFIER_VKS:
                                if down:
                                    if self.quickmove.busy:
                                        self.quickmove.cancel()
                                    self._modifiers.add(event.vkCode)
                                else:
                                    self._modifiers.discard(event.vkCode)
                            elif (key := VK_NAMES.get(event.vkCode)) and self._dispatch(key, down):
                                return 1
                except Exception as error:
                    self.engine.enable(False)
                    self.events.put(("error", f"Keyboard hook error: {error}"))
                return self.api.user.CallNextHookEx(None, code, wp, lp)

            @HOOKPROC
            def mouse(code, wp, lp):
                try:
                    if code >= 0:
                        event = C.cast(lp, C.POINTER(MSLLHOOKSTRUCT)).contents
                        if not (event.flags & 1 or event.dwExtraInfo == INPUT_TAG):
                            if wp in (0x201, 0x202) and self._capture_click(wp == 0x201):
                                return 1
                            if wp in (0x201, 0x204, 0x207, 0x20A, 0x20E) or (wp == 0x200 and self.quickmove.busy):
                                self.quickmove.cancel()
                            button = (event.mouseData >> 16) & 0xFFFF
                            if wp in (0x20B, 0x20C) and button in (1, 2):
                                if self._dispatch(f"mouse{button + 3}", wp == 0x20B):
                                    return 1
                except Exception as error:
                    self.engine.enable(False)
                    self.events.put(("error", f"Mouse hook error: {error}"))
                return self.api.user.CallNextHookEx(None, code, wp, lp)

            # References live for the complete message loop.
            module = self.api.kernel.GetModuleHandleW(None)
            keyboard_hook = self.api.user.SetWindowsHookExW(13, keyboard, module, 0)
            mouse_hook = self.api.user.SetWindowsHookExW(14, mouse, module, 0)
            if not keyboard_hook or not mouse_hook:
                raise C.WinError(C.get_last_error())
            self._ready.set()
            while not self._stop.is_set():
                result = self.api.user.GetMessageW(C.byref(message), None, 0, 0)
                if result == -1:
                    raise C.WinError(C.get_last_error())
                if result == 0:
                    break
                self.api.user.TranslateMessage(C.byref(message))
                self.api.user.DispatchMessageW(C.byref(message))
        except Exception as error:
            self._startup_error = str(error)
            self.engine.enable(False)
            self.events.put(("error", f"Input hooks unavailable: {error}"))
        finally:
            for hook in (keyboard_hook, mouse_hook):
                if hook:
                    self.api.user.UnhookWindowsHookEx(hook)
            self._ready.set()

    def _send_loop(self):
        while not self._stop.is_set():
            try:
                job = self._output.get(timeout=0.25)
            except queue.Empty:
                continue
            if job is None:
                break
            slot, generation, token, move = job
            try:
                if move is not None:
                    mouse = self.mouse_api()
                    def allowed():
                        focus = self.api.focus()
                        return (not self._stop.is_set() and self.quickmove.valid(move) and
                                not focus.text_control and token == (focus.hwnd, focus.pid) and
                                self.engine.allowed(generation, focus.roblox, focus.text_control) and
                                mouse.geometry(focus) == move.geometry and
                                mouse.belongs(focus.hwnd, move.source) and mouse.belongs(focus.hwnd, move.target))
                    try:
                        attempted = mouse.drag(move, allowed)
                        self.events.put(("quickmove", "Drag submitted; Roblox result unverified. Target reserved until empty-slot refresh."
                                         if attempted else "Drag refused/cancelled. Check empty-slot appearance and refresh targets."))
                    finally:
                        self.quickmove.complete(move)
                    continue
                # Never hold the engine lock over SendInput: Windows can call
                # hooks synchronously while input is inserted into the queue.
                modifiers = tuple(vk for vk in (0xA0, 0xA1, 0xA2, 0xA3)
                                  if self.api.user.GetAsyncKeyState(vk) & 0x8000)
                if any(self.api.user.GetAsyncKeyState(vk) & 0x8000 for vk in (0x12, 0x5B, 0x5C)):
                    continue
                focus = self.api.focus()
                if token != (focus.hwnd, focus.pid) or not self.engine.allowed(
                        generation, focus.roblox, focus.text_control):
                    continue
                self.api.tap_slot(slot, modifiers)
            except Exception as error:
                self.engine.enable(False)
                self.events.put(("error", str(error)))

    def stop(self):
        self.engine.close()
        self.quickmove.cancel()
        self._recording = False
        self._stop.set()
        try:
            self._output.put_nowait(None)
        except queue.Full:
            pass
        if self._thread_id:
            self.api.user.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        for thread in (self._thread, self._worker):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=3)
                if thread.is_alive():
                    raise RuntimeError(f"{thread.name} did not shut down cleanly.")
