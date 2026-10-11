import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bloxbinds.engine import Engine
from bloxbinds.keys import duplicate_bindings, parse_binding, validate_bindings
from bloxbinds.settings import Settings, load_settings, save_settings


def configured(**changes):
    values = [str(n) for n in range(1, 10)]
    values[0], values[1], values[2] = "q", "mouse4", "ctrl+shift+e"
    return Settings(tuple(values), **changes)


class BindingTests(unittest.TestCase):
    def test_defaults_and_unbound(self):
        self.assertEqual(len(validate_bindings(Settings().bindings)), 9)
        self.assertIsNone(parse_binding(""))
        self.assertIsNone(parse_binding("Unbound"))

    def test_normalization_and_side_buttons(self):
        self.assertEqual(str(parse_binding(" Shift + Control + Q ")), "ctrl+shift+q")
        self.assertEqual(str(parse_binding("XButton1")), "mouse4")
        self.assertEqual(str(parse_binding("Mouse5")), "mouse5")

    def test_invalid_and_reserved_keys(self):
        for value in ("ctrl", "alt+q", "win+q", "ctrl+ctrl+q", "ctrl++q",
                      "f10", "ctrl+alt+f12", "enter", "escape", "/", "`", "mouse1", "f25"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_binding(value)

    def test_nine_slots_required(self):
        with self.assertRaises(ValueError):
            validate_bindings(["q"])

    def test_duplicates_after_normalization(self):
        bindings = [parse_binding("ctrl+q"), parse_binding("Control+Q"), None]
        self.assertEqual(duplicate_bindings(bindings), {"ctrl+q": [1, 2]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_bindings(["q", "Q", "3", "4", "5", "6", "7", "8", "9"])

    def test_same_key_different_modifiers_is_allowed(self):
        validate_bindings(["q", "ctrl+q", "shift+q", "ctrl+shift+q", "5", "6", "7", "8", "9"])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(configured())
        self.engine.enable(True)

    def press(self, key, **kwargs):
        return self.engine.process(key, True, focused=True, **kwargs)

    def test_starts_off_and_default_keys_pass_through(self):
        engine = Engine(Settings())
        self.assertFalse(engine.enabled)
        engine.enable(True)
        self.assertFalse(engine.process("1", True, focused=True).suppress)

    def test_keyboard_and_side_mouse_mapping(self):
        self.assertEqual(self.press("q").slot, 1)
        self.assertEqual(self.press("mouse4").slot, 2)
        self.assertIsNone(self.press("mouse5").slot)

    def test_exact_modifier_matching(self):
        self.assertIsNone(self.press("e").slot)
        self.engine.process("e", False)
        self.assertIsNone(self.press("e", modifiers={"ctrl"}).slot)
        self.engine.process("e", False)
        self.assertEqual(self.press("e", modifiers={"ctrl", "shift"}).slot, 3)
        self.engine.process("e", False)
        self.assertIsNone(self.press("e", modifiers={"ctrl", "shift", "alt"}).slot)

    def test_repeats_never_generate_additional_taps(self):
        self.assertEqual(self.press("q").slot, 1)
        repeat = self.press("q")
        self.assertTrue(repeat.suppress)
        self.assertIsNone(repeat.slot)
        self.assertTrue(self.engine.process("q", False).suppress)
        self.assertEqual(self.press("q").slot, 1)

    def test_focus_required_and_stale_jobs_invalidated(self):
        self.assertFalse(self.engine.process("q", True).suppress)
        self.engine.process("q", False)
        decision = self.press("q")
        self.assertTrue(self.engine.allowed(decision.generation, True))
        self.assertFalse(self.engine.allowed(decision.generation, False))
        self.engine.focus_lost()
        self.assertFalse(self.engine.allowed(decision.generation, True))
        self.assertTrue(self.engine.process("q", False, focused=False).suppress)

    def test_synthetic_events_are_ignored_and_do_not_change_physical_state(self):
        self.assertFalse(self.press("q", injected=True).suppress)
        self.assertNotIn("q", self.engine.held)
        self.press("q")
        self.assertFalse(self.engine.process("q", False, injected=True).suppress)
        self.assertIn("q", self.engine.suppressed)

    def test_emergency_disable_is_global_and_invalidates_output(self):
        decision = self.press("q")
        stop = self.engine.process("f12", True, {"ctrl", "alt"}, focused=False)
        self.assertTrue(stop.suppress)
        self.assertFalse(self.engine.enabled)
        self.assertFalse(self.engine.allowed(decision.generation, True))
        self.assertTrue(self.engine.process("f12", False).suppress)
        self.assertTrue(self.engine.process("q", False).suppress)

    def test_chat_keys_pause_until_manual_resume(self):
        for key in ("enter", "slash", "backquote"):
            with self.subTest(key=key):
                self.engine = Engine(configured())
                self.engine.enable(True)
                self.assertFalse(self.press(key).suppress)
                self.assertTrue(self.engine.text_paused)
                self.assertFalse(self.press("q").suppress)
                self.engine.process("q", False)
                self.assertTrue(self.press("f10").suppress)
                self.assertFalse(self.engine.text_paused)
                self.assertEqual(self.press("q").slot, 1)

    def test_native_text_controls_and_optional_heuristic(self):
        self.assertFalse(self.press("q", native_text=True).suppress)
        self.engine.apply(configured(protect_text=False))
        self.engine.enable(True)
        self.engine.process("q", False)
        self.assertEqual(self.press("q", native_text=True).slot, 1)
        self.assertFalse(self.press("enter").suppress)
        self.assertFalse(self.engine.text_paused)

    def test_unsupported_cannot_be_enabled(self):
        self.engine.apply(configured(compatibility="Unsupported"))
        self.assertFalse(self.engine.enable(True))
        self.assertFalse(self.press("q").suppress)

    def test_apply_disables_and_close_is_idempotent(self):
        self.engine.apply(configured())
        self.assertFalse(self.engine.enabled)
        self.engine.close()
        self.engine.close()
        self.assertFalse(self.engine.enable(True))
        self.assertFalse(self.press("q").suppress)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sub" / "settings.json"

    def test_round_trip(self):
        settings = configured(compatibility="Unsupported", protect_text=False)
        save_settings(self.path, settings)
        loaded, warning = load_settings(self.path)
        self.assertEqual(loaded, settings)
        self.assertIsNone(warning)
        self.assertNotIn("enabled", json.loads(self.path.read_text()))
        self.assertFalse(Engine(loaded).enabled)

    def test_missing_defaults_and_corruption_warning(self):
        self.assertEqual(load_settings(self.path), (Settings(), None))
        self.path.parent.mkdir()
        self.path.write_text("{ broken json", encoding="utf-8")
        settings, warning = load_settings(self.path)
        self.assertEqual(settings, Settings())
        self.assertIsNotNone(warning)
        self.assertEqual(self.path.read_text(), "{ broken json")

    def test_invalid_types_and_versions(self):
        for data in ({}, {"version": 99}, {"version": True},
                     {"version": 1, "bindings": [None] * 9},
                     {"version": 1, "bindings": ["q"] * 9},
                     {**Settings().to_dict(), "protect_text": "false"},
                     {**Settings().to_dict(), "compatibility": "automatic"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Settings.from_dict(data)

    def test_atomic_failure_preserves_original(self):
        save_settings(self.path, Settings())
        original = self.path.read_bytes()
        with patch("bloxbinds.settings.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                save_settings(self.path, configured())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
