"""Strict portable backups: no paths, startup registration, calibration or runtime state."""
import json
from dataclasses import replace
from .settings import Settings, save_json

PORTABLE = {"version", "bindings", "compatibility", "protect_text", "automatic_detection",
            "auto_updates", "indicator", "indicator_topmost", "sound_feedback"}


def export_settings(path, settings):
    data = settings.to_dict()
    data = {key: value for key, value in data.items() if key in PORTABLE}
    data["compatibility"] = "Unknown"  # A different game/session needs its own verification.
    save_json(path, {"schema_version": 1, "settings": data})


def import_settings(path, current):
    if path.stat().st_size > 65536:
        raise ValueError("Settings backup is too large.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {"schema_version", "settings"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported backup format/schema version.")
    values = data["settings"]
    if not isinstance(values, dict) or set(values) - PORTABLE or not {"version", "bindings"}.issubset(values):
        raise ValueError("Missing or unexpected settings fields.")
    settings = Settings.from_dict(values)
    return replace(settings, compatibility="Unknown", launch_with_windows=current.launch_with_windows,
                   indicator_position=current.indicator_position)
