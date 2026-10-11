"""Native Windows keyboard probe: own focused Tk window only; never a Roblox test."""
import ctypes as C
from ctypes import wintypes as W
import os
import sys
import tkinter as tk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bloxbinds.engine import Engine
from bloxbinds.settings import Settings
from bloxbinds.win32 import INPUT, INPUT_TAG, KEYBDINPUT, InputService, WindowsAPI


def main():
    class ObservedEngine(Engine):
        calls = 0
        def process(self, key, *args, **kwargs):
            self.calls += 1
            return super().process(key, *args, **kwargs)

    root = tk.Tk()
    root.title("BloxBinds local input test")
    root.geometry("480x110")
    tk.Label(root, text="Native input test: this window only. Do not type during the test.").pack()
    entry = tk.Entry(root)
    entry.pack()
    api = WindowsAPI()
    engine = ObservedEngine(Settings())
    service = InputService(engine, api)
    failed, skipped, owned = [], [], []
    cases = ((), (0xA2,), (0xA1,), (0xA5,), (0xA2, 0xA0))
    index = 0

    def cleanup():
        if owned:
            api.release_modifiers(tuple(owned))
            owned.clear()
        service.stop()
        root.destroy()

    def focused():
        if api.focus().pid == os.getpid():
            return True
        skipped.append("Test window lost foreground focus; no further digit input sent")
        cleanup()
        return False

    def finish_case():
        nonlocal index
        try:
            if not focused():
                return
            expected = "12345"[:index + 1]
            assert entry.get() == expected, "Tk did not receive the expected unmodified digits"
            assert all(api.user.GetAsyncKeyState(vk) & 0x8000 for vk in owned), "Held modifiers were not restored"
            api.release_modifiers(tuple(owned))
            owned.clear()
            assert engine.calls == 0, "Injected input reached the physical mapping state machine"
            index += 1
            if index == len(cases):
                assert not engine.enabled and service._output.empty()
                root.after(60, final_check)
            else:
                root.after(60, send)
        except Exception as error:
            failed.append(str(error))
            cleanup()

    def final_check():
        try:
            assert not any(api.user.GetAsyncKeyState(vk) & 0x8000 for vk in (0xA0,0xA1,0xA2,0xA3,0xA4,0xA5)), "Modifier remained stuck"
        except Exception as error:
            failed.append(str(error))
        finally:
            cleanup()

    def tap():
        try:
            if focused():
                api.tap_slot(index + 1, tuple(owned))
                root.after(60, finish_case)
        except Exception as error:
            failed.append(str(error))
            cleanup()

    def send():
        try:
            if not focused():
                return
            modifiers = cases[index]
            owned.extend(modifiers)
            if modifiers:
                events = [INPUT(type=1, ki=KEYBDINPUT(vk,0,1 if vk in (0xA3,0xA5) else 0,0,INPUT_TAG)) for vk in modifiers]
                batch = (INPUT * len(events))(*events)
                if api.user.SendInput(len(events),batch,C.sizeof(INPUT)) != len(events):
                    raise OSError("Windows rejected test modifier input")
            root.after(60, tap)
        except Exception as error:
            failed.append(str(error))
            cleanup()

    try:
        service.start()
        root.update()
        api._declare(api.user, "GetAncestor", [W.HWND, W.UINT], W.HWND)
        api._declare(api.user, "SetForegroundWindow", [W.HWND], W.BOOL)
        hwnd = api.user.GetAncestor(root.winfo_id(), 2)
        api.user.SetForegroundWindow(hwnd)
        root.lift()
        root.focus_force()
        entry.focus_set()
        if any(api.user.GetAsyncKeyState(vk) & 0x8000 for vk in (0xA0,0xA1,0xA2,0xA3,0xA4,0xA5,0x5B,0x5C)):
            skipped.append("A modifier was already held; no input sent")
            cleanup()
        else:
            root.after(250, send)
            root.mainloop()
    finally:
        service.stop()
    if failed:
        print("Native input test failed: " + "; ".join(failed))
        return 1
    if skipped:
        print("Native input test skipped: " + "; ".join(skipped))
        return 2
    print("Native input test passed: five unmodified digits with none/Ctrl/right Shift/right Alt/Ctrl+Shift; restored then released modifiers; injected events ignored; clean shutdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
