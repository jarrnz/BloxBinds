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
    def test_inventory_button_preserves_manual_pause_after_backquote(self):
        from bloxbinds.win32 import Focus
        self.app.engine.enable(True)
        self.app.engine.process("f10", True, focused=True)
        self.app.engine.process("f10", False)
        self.app.engine.process("backquote", True, focused=True)
        self.app.engine.process("backquote", False)
        self.app.api.focus.return_value = Focus(12, 34, True, False)
        self.app._mode_pending = True
        with patch.object(self.app.quickmove, "activate") as activate:
            self.app._poll()
        activate.assert_not_called()
        self.service.mouse_api.assert_not_called()
        self.assertTrue(self.app.engine.text_paused)
        self.assertFalse(self.app.quickmove.active)

    def test_record_conflict_cancel_and_replace(self):
        from bloxbinds.keys import parse_binding
        self.app.bindings[0].set("q")
        old = self.app.bindings[1].get()
        with patch("bloxbinds.app.messagebox.askyesno", return_value=False):
            self.app.set_recorded_binding(1, parse_binding("q"))
        self.assertEqual(self.app.bindings[1].get(), old)
        with patch("bloxbinds.app.messagebox.askyesno", return_value=True):
            self.app.set_recorded_binding(1, parse_binding("q"))
        self.assertEqual(self.app.bindings[0].get(), "")
        self.assertEqual(self.app.bindings[1].get(), "q")

    def test_clear_slot_and_record_cancel_preserve_other_bindings(self):
        self.app.engine.enable(True)
        self.app.clear_slot(0)
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.app.bindings[0].get(), "")
        self.assertEqual(self.app.bindings[1].get(), "2")
        self.app.record(1)
        self.service.events.put(("record", None))
        self.app._poll()
        self.assertEqual(self.app.bindings[1].get(), "2")

    def test_detection_disabled_skips_background_scan_but_keeps_focus_gate(self):
        from bloxbinds.win32 import Focus
        self.app.automatic.set(False)
        self.app.save()
        self.app.api.detected.reset_mock()
        self.app.toggle_enabled()
        self.app.api.focus.return_value = Focus(12, 34, True)
        self.app._poll()
        self.assertEqual(self.app.activity.get(), "Active — Roblox Focused")
        self.app.api.focus.return_value = Focus(56, 78, False)
        self.app._poll()
        self.assertEqual(self.app.activity.get(), "Waiting for Roblox")
        self.app.api.detected.assert_not_called()
        self.assertFalse(self.app.engine.allowed(self.app.engine.generation, False))

    def test_tray_window_and_engine_share_manual_chat_error_status(self):
        from bloxbinds.win32 import Focus
        self.app.tray = Mock()
        self.app.engine.enable(True)
        self.app.api.focus.return_value = Focus(12, 34, True)
        for key, expected in (("f10", "Manually Paused"), ("enter", "Manually Paused"),
                              ("f10", "Active — Roblox Focused"), ("slash", "Chat Paused")):
            self.app.engine.process(key, True, focused=True)
            self.app.engine.process(key, False)
            self.app._poll()
            self.assertEqual(self.app.activity.get(), expected)
            self.app.tray.set_status.assert_called_with(expected)
        self.app.engine.fail("rejected")
        self.app._poll()
        self.assertEqual(self.app.activity.get(), "Error / Recovery Needed")

    def test_dead_input_service_cannot_be_reported_active(self):
        self.service.healthy.return_value = False
        self.app.toggle_enabled()
        self.app._poll()
        self.assertFalse(self.app.engine.enabled)
        self.assertEqual(self.app.activity.get(), "Error / Recovery Needed")
        self.assertIn("restart", self.app.notice.get())

    def test_inventory_unsupported_leaves_hotbar_available(self):
        self.app.quickmove.set_compatibility("Unsupported");self.app.toggle_enabled()
        self.assertTrue(self.app.engine.enabled);self.assertFalse(self.app.quickmove.active)

    def test_optional_preferences_preserve_live_engine_and_unsaved_bindings(self):
        self.app.engine.enable(True)
        self.app.engine.manual_paused=True;self.app.engine.chat_paused=True
        self.app.bindings[0].set("q")
        self.app.set_preference("sound_feedback",True)
        self.assertTrue(self.app.engine.enabled)
        self.assertTrue(self.app.engine.manual_paused);self.assertTrue(self.app.engine.chat_paused)
        self.assertEqual(self.app.bindings[0].get(),"q")
        self.assertEqual(self.app.engine.settings.bindings[0],"1")
        self.app.sounds.enabled=False  # This automated test never plays audio.
        self.app.save()
        self.assertTrue(self.app.engine.settings.sound_feedback)
        self.assertEqual(self.app.engine.settings.bindings[0],"q")

    def test_options_dialog_is_single_and_update_results_use_validated_page(self):
        from bloxbinds.updates import UpdateResult
        self.app.open_options();dialog=self.app._features_dialog
        self.app.open_options();self.assertIs(self.app._features_dialog,dialog)
        self.assertEqual(str(self.app._download_button.cget("state")),"disabled")
        url="https://github.com/jarrnz/BloxBinds/releases/tag/v1.4.0"
        self.service.events.put(("update",UpdateResult("Update available",url)))
        self.app._poll()
        self.assertIn("Last checked",self.app.update_status.get())
        with patch("webbrowser.open") as browser:
            self.app.open_download();browser.assert_called_once_with(url)
            self.app._update_url="https://other.example/";self.app.open_download()
            self.assertEqual(browser.call_count,1)

    def test_startup_failure_and_settings_failure_preserve_option(self):
        self.app.startup=Mock()
        self.app.startup.set.side_effect=OSError("registration failed")
        with patch("bloxbinds.app.messagebox.showerror"):
            self.assertFalse(self.app.set_preference("launch_with_windows",True))
        self.assertFalse(self.app.engine.settings.launch_with_windows)
        self.app.startup.set.side_effect=None;self.app.startup.reset_mock()
        with patch("bloxbinds.app.save_settings",side_effect=OSError("write failed")),patch("bloxbinds.app.messagebox.showerror"):
            self.assertFalse(self.app.set_preference("launch_with_windows",True))
        self.assertEqual([call.args[0] for call in self.app.startup.set.call_args_list],[True,False])
        self.assertFalse(self.app.engine.settings.launch_with_windows)

    def test_import_confirmation_and_atomic_failure_preserve_live_state(self):
        from bloxbinds.backup import export_settings
        from bloxbinds.settings import Settings
        path=Path(self.temp.name)/"portable.json"
        export_settings(path,Settings(("q","mouse4","mouse5","4","5","6","7","8","9")))
        self.app.engine.enable(True)
        before=self.app.engine.settings
        with patch("bloxbinds.app.filedialog.askopenfilename",return_value=str(path)),patch("bloxbinds.app.messagebox.askyesno",return_value=False):
            self.app.import_backup()
        self.assertTrue(self.app.engine.enabled);self.assertEqual(self.app.engine.settings,before)
        with patch("bloxbinds.app.filedialog.askopenfilename",return_value=str(path)),patch("bloxbinds.app.messagebox.askyesno",return_value=True),patch("bloxbinds.app.save_settings",side_effect=OSError("write failed")),patch("bloxbinds.app.messagebox.showerror"):
            self.app.import_backup()
        self.assertTrue(self.app.engine.enabled);self.assertEqual(self.app.engine.settings,before)
        self.assertFalse(self.app.path.exists())

    def test_valid_import_applies_ui_engine_disk_and_starts_off(self):
        from bloxbinds.backup import export_settings
        from bloxbinds.settings import Settings, load_settings
        path=Path(self.temp.name)/"portable.json"
        desired=Settings(("q","shift+mouse4","mouse5","4","5","6","7","8","9"),automatic_detection=False)
        export_settings(path,desired);self.app.engine.enable(True)
        self.app.quickmove.shortcut=""  # A disabled inventory shortcut must accept blank slots too.
        with patch("bloxbinds.app.filedialog.askopenfilename",return_value=str(path)),patch("bloxbinds.app.messagebox.askyesno",return_value=True):
            self.app.import_backup()
        self.assertEqual(self.app.engine.settings,desired);self.assertEqual(load_settings(self.app.path),(desired,None))
        self.assertEqual(self.app.bindings[1].get(),"shift+mouse4")
        self.assertFalse(self.app.engine.enabled);self.assertFalse(self.app.quickmove.enabled)
        self.assertFalse(self.app.automatic.get())

    def test_cancelled_and_invalid_import_never_replace_settings(self):
        before=self.app.engine.settings;self.app.engine.enable(True)
        with patch("bloxbinds.app.filedialog.askopenfilename",return_value=""):
            self.app.import_backup()
        path=Path(self.temp.name)/"invalid.json";path.write_text('{"path":"not-followed"}',encoding="utf-8")
        with patch("bloxbinds.app.filedialog.askopenfilename",return_value=str(path)),patch("bloxbinds.app.messagebox.showerror") as warning,patch("bloxbinds.app.messagebox.askyesno") as confirm:
            self.app.import_backup();warning.assert_called_once();confirm.assert_not_called()
        self.assertEqual(self.app.engine.settings,before);self.assertTrue(self.app.engine.enabled)

    def test_indicator_tray_reopens_one_window_and_tracks_pause_focus(self):
        from bloxbinds.win32 import Focus
        indicator=Mock();self.app._indicator_factory=Mock(return_value=indicator)
        self.app.tray=Mock();self.app.engine.enable(True)
        self.service.events.put(("tray","indicator"));self.app._poll()
        self.service.events.put(("tray","indicator"));self.app._poll()
        self.app._indicator_factory.assert_called_once()
        for paused in (False,True):
            self.app.engine.manual_paused=paused
            for focus in (Focus(12,34,True),Focus(56,78,False),Focus(),Focus(12,34,True)):
                self.app.api.focus.return_value=focus;self.app._poll()
                expected="Manually Paused" if paused else "Active — Roblox Focused" if focus.roblox else "Waiting for Roblox"
                self.assertEqual(self.app.activity.get(),expected)
                indicator.set_status.assert_called_with(expected);self.app.tray.set_status.assert_called_with(expected)
        self.app.set_preference("indicator",False);indicator.hide.assert_called()
        self.app.close();indicator.close.assert_called_once()

    def test_indicator_failure_does_not_disable_remapping(self):
        self.app.engine.enable(True);self.app.indicator=Mock()
        self.app.indicator.set_status.side_effect=OSError("display unavailable")
        self.app._poll();self.assertTrue(self.app.engine.enabled);self.assertIsNone(self.app.indicator)

    def test_sound_only_on_explicit_enable_and_f10_events(self):
        self.app.sounds=Mock()
        self.app.toggle_enabled();self.app.sounds.play.assert_called_once_with("enabled")
        self.app._poll();self.app._poll();self.assertEqual(self.app.sounds.play.call_count,1)
        self.service.events.put(("sound","paused"));self.app._poll()
        self.app.sounds.play.assert_called_with("paused")
        self.service.events.put(("sound","resumed"));self.app._poll()
        self.app.sounds.play.assert_called_with("resumed")
        self.app.close();self.app.sounds.close.assert_called_once()

    def test_auto_check_is_disabled_by_default_and_once_on_opt_in(self):
        self.assertFalse(self.app.engine.settings.auto_updates);self.assertIsNone(self.app.updates.thread)
        with patch.object(self.app.updates,"automatic",return_value=False) as automatic:
            self.app.set_preference("auto_updates",True)
            automatic.assert_called_once_with(True)
        self.app._poll();self.assertIsNone(self.app.updates.thread)

    def test_reset_confirmation_cancel_and_preserve_optional_preferences(self):
        self.app.set_preference("indicator_topmost",False)
        self.app.bindings[0].set("q");self.app.engine.enable(True)
        with patch("bloxbinds.app.messagebox.askyesno",return_value=False):self.app.confirm_reset()
        self.assertEqual(self.app.bindings[0].get(),"q");self.assertTrue(self.app.engine.enabled)
        with patch("bloxbinds.app.messagebox.askyesno",return_value=True):self.app.confirm_reset()
        self.assertEqual(self.app.bindings[0].get(),"1");self.assertFalse(self.app.engine.enabled)
        self.assertFalse(self.app.engine.settings.indicator_topmost)

    def test_export_cannot_overwrite_live_local_settings(self):
        self.app.save();before=self.app.path.read_bytes()
        with patch("bloxbinds.app.filedialog.asksaveasfilename",return_value=str(self.app.path)),patch("bloxbinds.app.messagebox.showerror") as error:
            self.app.export_backup();error.assert_called_once()
        self.assertEqual(self.app.path.read_bytes(),before)
