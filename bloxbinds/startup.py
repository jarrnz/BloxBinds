"""Visible, reversible per-user Run registration; never enables remapping."""
import subprocess
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BloxBinds"


def startup_command():
    if getattr(sys, "frozen", False):
        paths = [Path(sys.executable)]
    else:
        paths = [Path(sys.executable).with_name("pythonw.exe"), Path(__file__).resolve().parents[1] / "main.py"]
    if any(not path.is_file() for path in paths):
        raise OSError("Startup executable is missing. Extract the ZIP to a permanent folder first.")
    return subprocess.list2cmdline([str(path) for path in paths] + ["--startup"])


class Startup:
    def __init__(self, registry=None, command_factory=startup_command):
        if registry is None:
            import winreg
            registry = winreg
        self.registry = registry
        self.command_factory = command_factory

    def read(self):
        r = self.registry
        try:
            with r.OpenKey(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_READ) as key:
                value, kind = r.QueryValueEx(key, VALUE_NAME)
                return value if kind == r.REG_SZ else None
        except FileNotFoundError:
            return None

    def set(self, enabled):
        r = self.registry
        if enabled:
            command = self.command_factory()
            with r.CreateKeyEx(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_SET_VALUE) as key:
                r.SetValueEx(key, VALUE_NAME, 0, r.REG_SZ, command)
        else:
            try:
                with r.OpenKey(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_SET_VALUE) as key:
                    r.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass

    def repair(self, enabled):
        if enabled and self.read() != self.command_factory():
            self.set(True)
            return "Windows startup path repaired for this location. Disable startup before moving/deleting the app."
        return None
