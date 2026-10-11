"""Local Windows integration probe; sends a number only to its own Tk window."""

import os
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bloxbinds.engine import Engine
from bloxbinds.settings import Settings
from bloxbinds.win32 import InputService, WindowsAPI


def main():
    class ObservedEngine(Engine):
        calls = 0
        def process(self, key, *args, **kwargs):
            if key == "1":
                self.calls += 1
            return super().process(key, *args, **kwargs)

    root = tk.Tk()
    root.title("BloxBinds local input test")
    root.geometry("380x100")
    tk.Label(root, text="Testing simulated input in this window only…").pack()
    entry = tk.Entry(root)
    entry.pack()
    api = WindowsAPI()
    engine = ObservedEngine(Settings())
    service = InputService(engine, api)
    failed = []
    skipped = []

    def cleanup():
        service.stop()
        root.destroy()

    def check():
        try:
            assert entry.get() == "1", f"Tk received {entry.get()!r} instead of '1'"
            assert engine.calls == 0, "A synthetic event reached the mapping state machine"
            assert not engine.enabled
            assert service._output.empty()
        except Exception as error:
            failed.append(str(error))
        finally:
            cleanup()

    def send():
        # The real foreground check prevents sending input to any other app.
        if api.focus().pid != os.getpid():
            skipped.append("Test window could not obtain focus; no input was sent")
            cleanup()
            return
        try:
            api.tap_slot(1, ())
            root.after(100, check)
        except Exception as error:
            failed.append(str(error))
            cleanup()

    try:
        service.start()
        root.update()
        root.focus_force()
        entry.focus_set()
        root.after(300, send)
        root.mainloop()
    finally:
        service.stop()
    if failed:
        print("Native input test failed: " + "; ".join(failed))
        return 1
    if skipped:
        print("Native input test skipped: " + "; ".join(skipped))
        return 2
    print("Native input test passed: SendInput reached our Tk entry; hooks ignored synthetic events; clean shutdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
