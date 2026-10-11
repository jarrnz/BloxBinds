"""Run from source or as a PyInstaller executable."""

import argparse
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="BloxBinds Windows hotbar keybind manager")
    parser.add_argument("--smoke-test", action="store_true", help="Open briefly, verify hooks/layout, then close; never enable remapping")
    parser.add_argument("--allow-no-tray",action="store_true",help="Smoke test only: permit Windows CI without an interactive shell")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("BloxBinds requires Windows 10 or 11.", file=sys.stderr)
        return 1
    import tkinter as tk
    from tkinter import messagebox
    from bloxbinds.app import App

    root = tk.Tk()
    root.withdraw()
    callback_errors = []
    if args.smoke_test:
        def callback_error(kind, value, traceback):
            callback_errors.append(str(value))
            print(f"Smoke test callback failed: {value}", file=sys.stderr)
            root.quit()
        root.report_callback_exception = callback_error
    workspace = tempfile.TemporaryDirectory(prefix="BloxBinds-smoke-") if args.smoke_test else None
    try:
        app = App(root, path=Path(workspace.name) / "settings.json" if workspace else None)
        root.deiconify()
        if args.smoke_test:
            root.update()
            assert not app.engine.enabled, "Remapping must start OFF"
            assert app.service._thread.is_alive(), "Hook thread exited unexpectedly"
            assert app.service._worker.is_alive(), "Output worker exited unexpectedly"
            if not args.allow_no_tray or app.tray:
                assert app.tray and app.tray.available and app.tray.thread.is_alive(), "Native tray failed to start"
            assert len(app.entries) == 9, "Missing hotbar entries"
            assert all(entry.winfo_viewable() for entry in app.entries), "Hotbar entries are hidden"
            print(f"UI size: {root.winfo_width()}x{root.winfo_height()}; requested: {root.winfo_reqwidth()}x{root.winfo_reqheight()}")
            assert root.winfo_height() >= root.winfo_reqheight(), "Window clips its contents"
            def finish():
                app.close()
                assert not app.service._thread.is_alive(), "Hook thread failed to stop"
                assert not app.service._worker.is_alive(), "Output worker failed to stop"
                if app.tray:
                    assert not app.tray.thread.is_alive(), "Tray thread failed to stop"
            root.after(1500, finish)
        root.mainloop()
        if callback_errors:
            app.close()
            return 1
        if args.smoke_test:
            print("Smoke test passed: nine slots, native hooks, clean shutdown; remapping remained OFF.")
        return 0
    except Exception as error:
        if "app" in locals() and not app._closed:
            app.close()
        if args.smoke_test:
            print(f"Smoke test failed: {error}", file=sys.stderr)
        else:
            messagebox.showerror("BloxBinds could not start", str(error), parent=root)
        try:
            root.destroy()
        except tk.TclError:
            pass
        return 1
    finally:
        if workspace:
            workspace.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
