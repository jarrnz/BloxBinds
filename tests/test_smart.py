"""Smart remapping regressions; input boundaries are mocked except noted native tests."""
import ctypes as C
import json
import os
import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bloxbinds.engine import Engine
from bloxbinds.keys import parse_binding, validate_bindings
from bloxbinds.settings import Settings, load_settings, save_settings
from bloxbinds.win32 import Focus, INPUT, InputService, WindowsAPI


class ShortcutTests(unittest.TestCase):
    def test_supported_examples_and_normalization(self):
        for source, expected in (("R", "r"), ("Shift + R", "shift+r"),
                                 ("Ctrl + Q", "ctrl+q"), ("Alt + E", "alt+e"),
                                 ("Shift+Control+R", "ctrl+shift+r"),
                                 ("Shift+Mouse4", "shift+mouse4"),
                                 ("Ctrl+Mouse5", "ctrl+mouse5"),
                                 ("Alt+Middle Mouse", "alt+mouse3"),
                                 ("RightAlt+E", "alt+e"), ("LeftShift+R", "shift+r")):
            with self.subTest(source=source):
                self.assertEqual(str(parse_binding(source)), expected)

    def test_reserved_system_and_application_controls(self):
        for value in ("alt+tab", "shift+alt+tab", "alt+f4", "alt+space", "ctrl+escape",
                      "ctrl+shift+escape", "ctrl+alt+delete", "ctrl+alt+q", "win+r",
                      "f10", "shift+f10", "ctrl+alt+f12", "alt+f12"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_binding(value)

    def test_duplicate_modifier_order_and_mouse_aliases(self):
        for first, second in (("shift+ctrl+r", "ctrl+shift+r"),
                              ("alt+middle mouse", "alt+mouse3")):
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, "slots 1, 2"):
                validate_bindings([first, second, "3", "4", "5", "6", "7", "8", "9"])

    def test_plain_and_modified_keys_are_distinct(self):
        self.assertEqual(len(validate_bindings(["r", "shift+r", "ctrl+r", "alt+r",
                          "ctrl+shift+r", "shift+alt+r", "mouse3", "mouse4", "mouse5"])), 9)


class MigrationTests(unittest.TestCase):
    def test_legacy_configuration_preserved_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            data = {"version": 1, "bindings": ["q", "mouse4", "mouse5", "4", "5", "6", "7", "8", "9"],
                    "protect_text": False, "compatibility": "Unsupported"}
            path.write_text(json.dumps(data), encoding="utf-8")
            before = path.read_bytes()
            loaded, warning = load_settings(path)
            self.assertIsNone(warning)
            self.assertEqual(loaded.bindings, tuple(data["bindings"]))
            self.assertFalse(loaded.protect_text)
            self.assertEqual(loaded.compatibility, "Unsupported")
            self.assertTrue(loaded.automatic_detection)
            self.assertEqual(path.read_bytes(), before)

    def test_detection_preference_and_new_combinations_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(("alt+e", "mouse3", "shift+mouse4", "ctrl+mouse5", "5", "6", "7", "8", "9"),
                                automatic_detection=False)
            save_settings(path, settings)
            self.assertEqual(load_settings(path), (settings, None))
            self.assertFalse(Engine(load_settings(path)[0]).enabled)

    def test_duplicate_saved_configuration_warns_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            data = Settings().to_dict()
            data['bindings'][:2] = ["alt+mouse3", "Alt+Middle Mouse"]
            path.write_text(json.dumps(data), encoding="utf-8")
            before = path.read_bytes()
            settings, warning = load_settings(path)
            self.assertFalse(Engine(settings).enabled)
            self.assertIn("slots 1, 2", warning)
            self.assertEqual(path.read_bytes(), before)

    def test_detection_setting_requires_boolean(self):
        for value in (None, 0, "false"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings.from_dict({**Settings().to_dict(), "automatic_detection": value})


class SmartEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(Settings(("r", "shift+r", "ctrl+r", "alt+r", "ctrl+shift+r",
                                      "shift+alt+r", "mouse3", "mouse4", "mouse5")))
        self.engine.enable(True)

    def stroke(self, key, mods=frozenset(), **options):
        result = self.engine.process(key, True, mods, focused=True, **options)
        self.engine.process(key, False)
        return result

    def test_all_nine_slots_and_exact_precedence(self):
        for slot, mods in enumerate((set(), {"shift"}, {"ctrl"}, {"alt"}, {"ctrl", "shift"}, {"shift", "alt"}), 1):
            self.assertEqual(self.stroke("r", mods).slot, slot)
        for slot, key in enumerate(("mouse3", "mouse4", "mouse5"), 7):
            self.assertEqual(self.stroke(key).slot, slot)
        self.assertIsNone(self.stroke("r", {"ctrl", "alt"}).slot)

    def test_manual_and_chat_reasons_remain_independent(self):
        self.stroke("f10")
        self.stroke("enter")
        self.assertTrue(self.engine.manual_paused)
        self.assertTrue(self.engine.chat_paused)
        self.assertEqual(self.engine.status(focused=True), "Manually Paused")
        self.stroke("backquote")
        self.engine.focus_lost()
        self.assertIsNone(self.stroke("r").slot)
        self.stroke("f10")
        self.assertFalse(self.engine.text_paused)
        self.assertEqual(self.stroke("r").slot, 1)

    def test_chat_status_and_backquote_preserved(self):
        self.stroke("slash")
        self.stroke("backquote")
        self.assertFalse(self.engine.manual_paused)
        self.assertEqual(self.engine.status(focused=True), "Chat Paused")
        self.assertIsNone(self.stroke("mouse3").slot)

    def test_status_matches_safety_gates_and_recovery(self):
        self.assertEqual(self.engine.status(), "Waiting for Roblox")
        self.assertEqual(self.engine.status(detected=True), "Roblox Not Focused")
        self.assertEqual(self.engine.status(focused=True, native_text=True), "Text Entry Paused")
        self.assertEqual(self.engine.status(focused=True), "Active — Roblox Focused")
        self.assertEqual(self.engine.status(focused=True, inventory=True), "Inventory Mode / Experimental")
        self.engine.fail("rejected")
        self.assertEqual(self.engine.status(focused=True), "Error / Recovery Needed")
        self.assertIsNone(self.stroke("r").slot)
        self.engine.enable(True)
        self.assertEqual(self.engine.status(focused=True), "Active — Roblox Focused")
        self.engine.enable(False)
        self.assertEqual(self.engine.status(focused=True), "Remapping Disabled")

    def test_mouse_hold_focus_loss_and_repeat_are_balanced(self):
        self.assertEqual(self.engine.process("mouse3", True, focused=True).slot, 7)
        self.engine.focus_lost()
        self.assertTrue(self.engine.process("mouse3", True, focused=False).suppress)
        self.assertIsNone(self.engine.process("mouse3", True, focused=True).slot)
        self.assertTrue(self.engine.process("mouse3", False, focused=False).suppress)
        self.assertEqual(self.stroke("mouse3").slot, 7)


class PhysicalHookPathTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(Settings(("r", "shift+r", "ctrl+r", "alt+r", "ctrl+shift+r",
                                      "alt+mouse3", "mouse3", "mouse4", "mouse5")))
        self.engine.enable(True)
        self.api = Mock()
        self.api.focus.return_value = Focus(12, 34, True, False)
        self.api.user.GetAsyncKeyState.return_value = 0
        self.service = InputService(self.engine, self.api)

    def drain(self):
        self.service._output.put(None)
        self.service._send_loop()

    def test_left_and_right_modifiers_normalize_and_release_separately(self):
        for vk, slot in ((0xA0, 2), (0xA1, 2), (0xA2, 3), (0xA3, 3), (0xA4, 4), (0xA5, 4)):
            with self.subTest(vk=vk):
                self.assertFalse(self.service._keyboard_event(vk, True))
                self.assertTrue(self.service._keyboard_event(0x52, True))
                self.assertEqual(self.service._output.get_nowait()[0], slot)
                self.service._keyboard_event(0x52, False)
                self.service._keyboard_event(vk, False)
                self.assertFalse(self.service._modifiers)
        self.service._keyboard_event(0xA0, True)
        self.service._keyboard_event(0xA1, True)
        self.service._keyboard_event(0xA0, False)
        self.service._keyboard_event(0x52, True)
        self.assertEqual(self.service._output.get_nowait()[0], 2)

    def test_middle_and_side_buttons_distinguish_up_down_and_repeat(self):
        for message, data, slot in ((0x207, 0, 7), (0x20B, 1 << 16, 8), (0x20B, 2 << 16, 9)):
            with self.subTest(slot=slot):
                self.assertTrue(self.service._mouse_event(message, data))
                self.assertTrue(self.service._mouse_event(message, data))
                self.assertEqual(self.service._output.qsize(), 1)
                self.assertEqual(self.service._output.get_nowait()[0], slot)
                self.assertTrue(self.service._mouse_event(message + 1, data))
                self.assertFalse(self.service._mouse_event(message + 1, data))

    def test_alt_middle_mouse_and_unassigned_camera_passthrough(self):
        self.service._keyboard_event(0xA5, True)
        self.assertTrue(self.service._mouse_event(0x207))
        self.assertEqual(self.service._output.get_nowait()[0], 6)
        self.service._mouse_event(0x208)
        self.service._keyboard_event(0xA5, False)
        self.engine.apply(Settings())
        self.engine.enable(True)
        self.assertFalse(self.service._mouse_event(0x207))
        self.assertFalse(self.service._mouse_event(0x208))
        self.assertFalse(self.service._mouse_event(0x200))
        self.assertFalse(self.service._mouse_event(0x20A))

    def test_injected_keyboard_mouse_and_modifiers_do_not_recurse(self):
        self.assertFalse(self.service._keyboard_event(0xA5, True, injected=True))
        self.assertFalse(self.service._keyboard_event(0x52, True, injected=True))
        self.assertFalse(self.service._mouse_event(0x207, injected=True))
        self.assertFalse(self.service._modifiers)
        self.assertFalse(self.engine.held)
        self.assertTrue(self.service._output.empty())

    def test_capture_modifiers_mouse_and_balanced_release(self):
        self.api.focus.return_value = Focus(12, os.getpid(), False, False)
        self.service.record(True)
        self.service._keyboard_event(0xA5, True)
        self.assertTrue(self.service._mouse_event(0x207))
        self.assertEqual(self.service.events.get_nowait(), ("record", "alt+mouse3"))
        self.assertFalse(self.engine.enabled)
        self.assertTrue(self.service._output.empty())
        self.assertTrue(self.service._mouse_event(0x208))
        self.service._keyboard_event(0xA5, False)
        self.assertFalse(self.service._modifiers)

    def test_capture_cancel_and_reserved_shortcut_passthrough(self):
        self.api.focus.return_value = Focus(12, os.getpid(), False, False)
        self.service.record(True)
        self.assertTrue(self.service._keyboard_event(0x1B, True))
        self.assertEqual(self.service.events.get_nowait(), ("record", None))
        self.service._keyboard_event(0x1B, False)
        self.service.record(True)
        self.service._keyboard_event(0xA4, True)
        self.assertFalse(self.service._keyboard_event(0x09, True))
        self.assertEqual(self.service.events.get_nowait(), ("record", "alt+tab"))
        self.assertFalse(self.service._recording)

    def test_capture_loses_focus_without_remapping(self):
        self.service.record(True)
        self.assertFalse(self.service._keyboard_event(0x52, True))
        self.assertEqual(self.service.events.get_nowait(), ("record", None))
        self.assertTrue(self.service._output.empty())

    def test_foreground_close_restart_and_manual_pause(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                self.setUp()
                if paused:
                    self.service._dispatch("f10", True)
                    self.service._dispatch("f10", False)
                for focus in (Focus(55, 66, False), Focus(), Focus(77, 88, True)):
                    self.api.focus.return_value = focus
                    consumed = self.service._mouse_event(0x207)
                    self.service._mouse_event(0x208)
                    self.assertEqual(consumed, focus.roblox and not paused)
                self.drain()
                self.assertEqual(self.api.tap_slot.call_count, 0 if paused else 1)
                self.assertEqual(self.engine.manual_paused, paused)

    def test_modifier_release_during_output_is_repaired(self):
        self.service._modifiers = {0xA5}
        self.api.user.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == 0xA5 else 0
        self.service._dispatch("r", True)
        self.api.tap_slot.side_effect = lambda *args: self.service._modifiers.clear()
        self.drain()
        self.api.tap_slot.assert_called_once_with(4, (0xA5,))
        self.api.release_modifiers.assert_called_once_with((0xA5,))

    def test_held_modifier_is_restored_without_cleanup(self):
        self.service._modifiers = {0xA4}
        self.api.user.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == 0xA4 else 0
        self.service._dispatch("r", True)
        self.drain()
        self.api.tap_slot.assert_called_once_with(4, (0xA4,))
        self.api.release_modifiers.assert_not_called()

    def test_reserved_escape_combination_cancels_capture_without_suppression(self):
        self.api.focus.return_value = Focus(12, os.getpid(), False)
        self.service.record(True)
        self.service._modifiers = {0xA2, 0xA0}
        self.assertFalse(self.service._keyboard_event(0x1B, True))
        self.assertEqual(self.service.events.get_nowait(), ("record", None))

    def test_generic_modifier_events_do_not_release_a_still_held_modifier(self):
        self.service._modifiers = {0x11}
        self.api.user.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == 0xA2 else 0
        self.service._dispatch("r", True)
        self.drain()
        self.api.tap_slot.assert_called_once_with(3, (0xA2,))
        self.api.release_modifiers.assert_not_called()

    def test_global_emergency_during_capture(self):
        self.api.focus.return_value = Focus(12, os.getpid(), False)
        self.service.record(True)
        self.service._keyboard_event(0xA3, True)
        self.service._keyboard_event(0xA5, True)
        self.assertTrue(self.service._keyboard_event(0x7B, True))
        self.assertFalse(self.engine.enabled)
        self.assertFalse(self.service._recording)
        self.assertEqual(self.service.events.get_nowait(), ("emergency", None))


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.api = WindowsAPI.__new__(WindowsAPI)
        self.api.user = Mock()
        self.api.kernel = Mock()
        self.api._cache = {}
        self.api._cache_lock = threading.Lock()
        self.api.kernel.OpenProcess.return_value = 99
        self.image = "RobloxPlayerBeta.exe"
        def image(handle, flags, buffer, size):
            buffer.value = "X:" + chr(92) + "Apps" + chr(92) + self.image
            return 1
        self.api.kernel.QueryFullProcessImageNameW.side_effect = image
        self.api.user.GetForegroundWindow.return_value = 12
        def pid(hwnd, pointer):
            C.cast(pointer, C.POINTER(C.c_ulong)).contents.value = 34
            return 56
        self.api.user.GetWindowThreadProcessId.side_effect = pid
        self.api.user.GetGUIThreadInfo.return_value = False
        self.api.user.IsWindowVisible.return_value = True
        self.api.user.EnumWindows.side_effect = lambda visitor, _: visitor(12, 0)

    def test_player_detected_not_studio_browser_or_unrelated(self):
        for image in ("RobloxPlayerBeta.exe", "ROBLOXPLAYER.EXE", "RobloxStudioBeta.exe", "chrome.exe", "other.exe"):
            with self.subTest(image=image):
                self.image = image
                self.api._cache.clear()
                self.assertEqual(self.api.focus().roblox, "player" in image.lower())
                self.assertEqual(self.api.detected(), "player" in image.lower())

    def test_minimized_visible_client_and_no_foreground_window(self):
        self.api.user.GetForegroundWindow.return_value = 0
        self.assertEqual(self.api.focus(), Focus())
        self.assertTrue(self.api.detected())  # Minimized windows retain WS_VISIBLE.
        self.api.user.IsWindowVisible.return_value = False
        self.assertFalse(self.api.detected())

    def test_close_restart_and_pid_cache_expiry(self):
        with patch('bloxbinds.win32.time.monotonic', side_effect=[0, 0.5, 2, 4]):
            self.assertTrue(self.api.is_client(34))
            self.image = "other.exe"
            self.assertTrue(self.api.is_client(34))  # Existing one-second metadata cache.
            self.assertFalse(self.api.is_client(34))
            self.image = "RobloxPlayerBeta.exe"
            self.assertTrue(self.api.is_client(34))
        self.assertEqual(self.api.kernel.CloseHandle.call_count, 3)

    def test_right_modifier_input_flags_and_partial_batch_cleanup(self):
        events = []
        def send(count, batch, size):
            events.append([(batch[i].ki.wVk, batch[i].ki.dwFlags, batch[i].ki.dwExtraInfo)
                           for i in range(count)])
            return count
        self.api.user = SimpleNamespace(SendInput=send, MapVirtualKeyW=lambda vk, _: 2)
        self.api.tap_slot(1, (0xA3, 0xA5))
        self.assertEqual([e[1] for e in events[0]], [3, 3, 8, 10, 1, 1])
        self.api.release_modifiers((0xA3, 0xA5))
        self.assertEqual([e[1] for e in events[1]], [3, 3])
        self.assertTrue(all(e[2] == 0x424C4F58 for group in events for e in group))
        def partial(count, batch, size):
            send(count, batch, size)
            return 1 if len(events) == 3 else count
        self.api.user.SendInput = partial
        with self.assertRaises(OSError):
            self.api.tap_slot(1, (0xA5,))
        self.assertEqual(events[-1][-1][:2], (0xA5, 1))


class TrayStatusTests(unittest.TestCase):
    def test_status_updates_only_on_change_and_no_second_start(self):
        from bloxbinds.tray import Tray
        api = Mock()
        tray = Tray(api, Mock(), lambda: True)
        tray.hwnd = 12
        tray.available = True
        tray.set_status("Manually Paused")
        tray.set_status("Manually Paused")
        api.user.PostMessageW.assert_called_once_with(12, 0x8002, 0, 0)
        tray.thread = Mock()
        with self.assertRaises(RuntimeError):
            tray.start()


class SmokeArgumentTests(unittest.TestCase):
    def test_isolation_cannot_bypass_normal_single_instance_startup(self):
        import main
        with patch('sys.argv', ['main.py', '--isolated-smoke-test']), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                main.main()
        self.assertEqual(result.exception.code, 2)
