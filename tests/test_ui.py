import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == "win32", "Windows Tk interface")
class UITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from bloxbinds.app import App
        from bloxbinds.win32 import Focus
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        api = Mock()
        api.focus.return_value = Focus()
        api.detected.return_value = False
        self.service = Mock()
        self.service.events = queue.SimpleQueue()
        self.app = App(self.root, api=api, service_factory=lambda engine, api: self.service,
                       path=Path(self.temp.name) / "settings.json", single_instance=False)
        self.addCleanup(self.app.close)
        self.root.update_idletasks()

    def test_nine_editable_slots_and_start_off(self):
        self.assertEqual(len(self.app.entries), 9)
        self.assertEqual(self.app.bindings[8].get(), "9")
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.app.connection.get(), "Roblox: not detected")

    def test_save_persist_apply_and_enable(self):
        self.app.bindings[0].set("Control+Q")
        self.app.save()
        self.assertTrue(self.app.path.is_file())
        self.assertEqual(self.app.engine.settings.bindings[0], "ctrl+q")
        self.assertIn("Saved", self.app.notice.get())
        self.app.toggle_enabled()
        self.assertTrue(self.app.engine.enabled)

    def test_duplicate_warning_does_not_replace_settings(self):
        self.app.bindings[0].set("2")
        with patch("bloxbinds.app.messagebox.showerror") as warning:
            self.app.save()
        warning.assert_called_once()
        self.assertIn("Duplicate", self.app.notice.get())
        self.assertFalse(self.app.path.exists())
        self.assertEqual(self.app.engine.settings.bindings[0], "1")

    def test_unsaved_edits_cannot_be_enabled(self):
        self.app.bindings[0].set("q")
        self.app.toggle_enabled()
        self.assertFalse(self.app.engine.enabled)
        self.assertIn("Save & apply", self.app.notice.get())

    def test_unsupported_immediately_disables(self):
        self.app.toggle_enabled()
        self.app.compatibility.set("Unsupported")
        self.app.compatibility_changed()
        self.assertFalse(self.app.engine.enabled)
        self.app.toggle_enabled()
        self.assertFalse(self.app.engine.enabled)

    def test_record_and_reset(self):
        self.app.record(0)
        self.service.events.put(("record", "mouse4"))
        self.app._poll()
        self.assertEqual(self.app.bindings[0].get(), "mouse4")
        self.app.reset()
        self.assertEqual(self.app.bindings[0].get(), "1")
        self.assertFalse(self.app.engine.enabled)

    def test_close_is_idempotent_and_service_is_stopped(self):
        self.app.close()
        self.app.close()
        self.service.stop.assert_called_once()

    def test_quickmove_panel_is_opt_in_and_calibration_disables_hotbar(self):
        self.app.engine.enable(True)
        original = self.app.engine.settings
        self.app.open_quickmove()
        self.assertFalse(self.app.quickmove.enabled)
        self.assertTrue(self.app.engine.enabled)
        self.assertEqual(self.app.engine.settings, original)
        self.app.begin_quick_calibration()
        self.assertTrue(self.app.quickmove.calibrating)
        self.assertFalse(self.app.engine.enabled)

    def test_tray_restore_toggle_exit_cleanup(self):
        self.app.tray=Mock();self.app.root.withdraw();self.service.events.put(("tray","restore"));self.app._poll()
        self.assertEqual(self.app.root.state(),"normal")
        self.service.events.put(("tray","toggle"));self.app._poll();self.assertTrue(self.app.engine.enabled)
        self.service.events.put(("tray","exit"));self.app._poll();self.assertTrue(self.app._closed)
        self.app.tray.stop.assert_called_once();self.service.stop.assert_called_once()
    def test_tray_cleanup_failure_still_destroys_window(self):
        self.app.tray=Mock();self.app.tray.stop.side_effect=RuntimeError("failed")
        with self.assertRaises(RuntimeError):self.app.close()
        self.service.stop.assert_called_once();self.assertTrue(self.app._closed)
    def test_inventory_unsupported_leaves_hotbar_available(self):
        self.app.quickmove.set_compatibility("Unsupported");self.app.toggle_enabled()
        self.assertTrue(self.app.engine.enabled);self.assertFalse(self.app.quickmove.active)
