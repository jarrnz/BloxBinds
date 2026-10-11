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

    def validate(self):
        validate_bindings(self.bindings)
        if self.compatibility not in COMPATIBILITIES:
            raise ValueError("Invalid inventory compatibility status.")
        if type(self.protect_text) is not bool:
            raise ValueError("Text protection must be true or false.")
        return self

    def to_dict(self):
        self.validate()
        return {"version": 1, "bindings": list(self.bindings),
                "compatibility": self.compatibility, "protect_text": self.protect_text}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Unsupported settings format/version.")
        values = data.get("bindings")
        if not isinstance(values, list):
            raise ValueError("Settings must contain a list of bindings.")
        parsed = validate_bindings(values)
        return cls(tuple(str(b) if b else "" for b in parsed),
                   data.get("compatibility", "Unknown"), data.get("protect_text", True)).validate()


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
