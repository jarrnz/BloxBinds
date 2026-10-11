"""Validated, atomic JSON settings. Loading never enables remapping."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .keys import validate_bindings

COMPATIBILITIES = ("Unknown", "Verified by me", "Unsupported")


@dataclass(frozen=True)
class Settings:
    bindings: tuple[str, ...] = tuple(str(i) for i in range(1, 10))
    compatibility: str = "Unknown"
    protect_text: bool = True
    automatic_detection: bool = True
    auto_updates: bool = False
    launch_with_windows: bool = False
    indicator: bool = False
    indicator_topmost: bool = True
    indicator_position: tuple[int, int] | None = None
    sound_feedback: bool = False

    def validate(self):
        validate_bindings(self.bindings)
        if self.compatibility not in COMPATIBILITIES:
            raise ValueError("Invalid inventory compatibility status.")
        if type(self.protect_text) is not bool:
            raise ValueError("Text protection must be true or false.")
        if type(self.automatic_detection) is not bool:
            raise ValueError("Automatic Roblox Detection must be true or false.")
        for name in ("auto_updates", "launch_with_windows", "indicator", "indicator_topmost", "sound_feedback"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false.")
        if self.indicator_position is not None and (
                not isinstance(self.indicator_position, tuple) or len(self.indicator_position) != 2 or
                any(type(n) is not int or abs(n) > 100000 for n in self.indicator_position)):
            raise ValueError("Invalid status indicator position.")
        return self

    def to_dict(self):
        self.validate()
        return {"version": 1, "bindings": list(self.bindings),
                "compatibility": self.compatibility, "protect_text": self.protect_text,
                "automatic_detection": self.automatic_detection,
                **{name: getattr(self, name) for name in ("auto_updates", "launch_with_windows", "indicator",
                    "indicator_topmost", "sound_feedback")},
                "indicator_position": list(self.indicator_position) if self.indicator_position else None}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Unsupported settings format/version.")
        values = data.get("bindings")
        if not isinstance(values, list):
            raise ValueError("Settings must contain a list of bindings.")
        parsed = validate_bindings(values)
        position = data.get("indicator_position")
        if position is not None and not isinstance(position, list):
            raise ValueError("Invalid status indicator position.")
        return cls(tuple(str(b) if b else "" for b in parsed),
                   data.get("compatibility", "Unknown"), data.get("protect_text", True),
                   data.get("automatic_detection", True),
                   data.get("auto_updates", False), data.get("launch_with_windows", False),
                   data.get("indicator", False), data.get("indicator_topmost", True),
                   tuple(position) if position is not None else None, data.get("sound_feedback", False)).validate()


def settings_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BloxBinds" / "settings.json"


def load_settings(path: Path) -> tuple[Settings, str | None]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return Settings.from_dict(json.load(stream)), None
    except FileNotFoundError:
        return Settings(), None
    except (OSError, ValueError, TypeError) as error:
        return Settings(), f"Could not load settings; defaults are in use. {error}"


def save_settings(path: Path, settings: Settings) -> None:
    save_json(path, settings.to_dict())


def save_json(path: Path, data: dict) -> None:
    """Atomically persist validated application data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                prefix="settings-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
