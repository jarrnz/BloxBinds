"""Optional features use mocked network/registry/audio; native indicator tests never send input."""
import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from bloxbinds.backup import export_settings, import_settings
from bloxbinds.engine import Engine
from bloxbinds.settings import Settings, save_settings, load_settings
from bloxbinds.updates import API_URL, Version, UpdateChecker, check_updates, select_release, valid_release_url, NoRedirects
from bloxbinds.startup import Startup, RUN_KEY, startup_command
from bloxbinds.sound import Sounds
from bloxbinds.indicator import Indicator, IndicatorAPI, visible_position
from bloxbinds.win32 import Focus, InputService, WindowsAPI


def release(tag="v1.4.0", prerelease=False, **values):
    return dict(tag_name=tag, prerelease=prerelease, draft=False,
                html_url="https://github.com/jarrnz/BloxBinds/releases/tag/"+tag,
                published_at="2026-10-11T12:00:00Z", **values)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.current = Version.parse("1.3.0-beta")

    def test_newer_stable_and_date(self):
        result = select_release([release()],self.current)
        self.assertIn("v1.4.0",result.message)
        self.assertIn("2026-10-11",result.message)
        self.assertTrue(valid_release_url(result.url))

    def test_beta_channel_and_stable_channel(self):
        newer = release("v1.4.0-beta.2", True)
        self.assertIsNotNone(select_release([newer],self.current).url)
        self.assertIsNone(select_release([newer],Version.parse("1.3.0")).url)

    def test_same_number_stable_is_newer_than_beta(self):
        self.assertIsNotNone(select_release([release("v1.3.0")],self.current).url)

    def test_github_prerelease_flag_without_tag_suffix(self):
        self.assertIsNone(select_release([release("v1.3.0",True)],self.current).url)
        self.assertIsNotNone(select_release([release("v1.4.0",True)],self.current).url)

    def test_latest_and_older_not_offered(self):
        for tag in ("v1.3.0-beta", "v1.2.0", "v1.3.0-alpha"):
            with self.subTest(tag=tag):
                result=select_release([release(tag,True)],self.current)
                self.assertEqual(result.message,"You're up to date.")
                self.assertIsNone(result.url)

    def test_semantic_order_not_string_order(self):
        self.assertGreater(Version.parse("1.10.0"),Version.parse("1.9.0"))
        self.assertGreater(Version.parse("1.3.0-beta.10"),Version.parse("1.3.0-beta.2"))
        self.assertEqual(Version.parse("v1.3.0+build.1"),Version.parse("1.3.0+other"))
        self.assertGreater(Version.parse("1.3.0-rc"),Version.parse("1.3.0-beta"))

    def test_malformed_versions_and_responses(self):
        for value in ("1.3", "01.3.0", "1.3.0-beta.01", "1.3.0-beta..2",None):
            with self.subTest(value=value), self.assertRaises(ValueError): Version.parse(value)
        self.assertIsNone(select_release([release("not-a-version")],self.current).url)
        with self.assertRaises(ValueError): select_release({},self.current)

    def test_sort_candidates_and_ignore_drafts(self):
        data=[release("v1.10.0"),release("v1.9.0"),{**release("v99.0.0"),"draft":True}]
        self.assertIn("v1.10.0",select_release(data,self.current).message)

    def test_invalid_urls_and_repository(self):
        for url in ("http://github.com/jarrnz/BloxBinds/releases/tag/v9.0.0",
                    "https://github.com.evil.example/jarrnz/BloxBinds/releases/tag/v9.0.0",
                    "https://github.com/other/BloxBinds/releases/tag/v9.0.0",
                    "https://user@github.com/jarrnz/BloxBinds/releases/tag/v9.0.0",
                    "https://github.com/jarrnz/BloxBinds/releases/tag/%2e%2e/other", "https://[bad",
                    "https://github.com:443/jarrnz/BloxBinds/releases/tag/v9.0.0",None):
            with self.subTest(url=url):
                self.assertFalse(valid_release_url(url))
                self.assertIsNone(select_release([{**release(),"html_url":url}],self.current).url)

    def test_network_request_has_no_user_settings_or_credentials(self):
        response=Mock()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.geturl.return_value=API_URL
        response.read.return_value=json.dumps([release()]).encode()
        opener=Mock(return_value=response)
        self.assertIsNotNone(check_updates(self.current,opener).url)
        request=opener.call_args.args[0]
        self.assertEqual(request.full_url,API_URL)
        self.assertIsNone(request.data)
        self.assertEqual(opener.call_args.kwargs,{"timeout":8})
        self.assertNotIn("Authorization",dict(request.header_items()))

    def test_offline_timeout_unavailable_and_rate_limit(self):
        for error, word in ((TimeoutError(),"timed out"),(URLError("offline"),"offline"),
                            (HTTPError(API_URL,404,"missing",{},None),"unavailable"),
                            (HTTPError(API_URL,403,"limit",{},None),"rate limit"),
                            (HTTPError(API_URL,429,"limit",{},None),"rate limit")):
            with self.subTest(error=type(error).__name__):
                result=check_updates(self.current,Mock(side_effect=error))
                self.assertIsNone(result.url);self.assertIn(word,result.message)

    def test_malformed_and_oversized_http_payload(self):
        for raw in (b"{bad",b"{}",b"x"*(2*1024*1024+1)):
            response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.geturl.return_value=API_URL;response.read.return_value=raw
            self.assertIn("invalid",check_updates(self.current,Mock(return_value=response)).message)

    def test_redirects_refused(self):
        with self.assertRaises(URLError):
            NoRedirects().redirect_request(None,None,302,"",{},"https://other.example/")

    def test_auto_disabled_once_per_session_no_automatic_download(self):
        events=queue.SimpleQueue();checker=UpdateChecker(events,self.current)
        with patch("bloxbinds.updates.check_updates",return_value=select_release([release()],self.current)) as check:
            self.assertFalse(checker.automatic(False));check.assert_not_called()
            self.assertTrue(checker.automatic(True));checker.thread.join(2)
            self.assertFalse(checker.automatic(True));check.assert_called_once()
            self.assertEqual(events.get_nowait()[0],"update")
        checker.close();self.assertFalse(checker.check())

    def test_background_request_shutdown_discards_late_event(self):
        started=threading.Event();finish=threading.Event();events=queue.SimpleQueue()
        checker=UpdateChecker(events,self.current)
        def pending(_):
            started.set();finish.wait(2);return select_release([release()],self.current)
        with patch("bloxbinds.updates.check_updates",side_effect=pending):
            checker.check();self.assertTrue(started.wait(1))
            self.assertFalse(checker.check());checker.close();finish.set();checker.thread.join(2)
        self.assertTrue(events.empty())


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.r=Mock();self.r.HKEY_CURRENT_USER="current-user";self.r.REG_SZ=1
        self.key=Mock();self.key.__enter__=Mock(return_value=self.key);self.key.__exit__=Mock(return_value=False)
        self.r.CreateKeyEx.return_value=self.key;self.r.OpenKey.return_value=self.key
        self.startup=Startup(self.r,lambda:'"X:\\Portable Apps\\BloxBinds.exe" --startup')

    def test_enable_current_user_and_path_with_spaces(self):
        self.startup.set(True)
        self.r.CreateKeyEx.assert_called_once_with("current-user",RUN_KEY,0,self.r.KEY_SET_VALUE)
        self.r.SetValueEx.assert_called_once_with(self.key,"BloxBinds",0,1,'"X:\\Portable Apps\\BloxBinds.exe" --startup')

    def test_disable_removes_only_own_value(self):
        self.startup.set(False);self.r.DeleteValue.assert_called_once_with(self.key,"BloxBinds")
        self.r.CreateKeyEx.assert_not_called()

    def test_missing_entry_disables_cleanly(self):
        self.r.OpenKey.side_effect=FileNotFoundError()
        self.startup.set(False);self.assertIsNone(self.startup.read())

    def test_missing_executable_does_not_register(self):
        self.startup.command_factory=Mock(side_effect=OSError("missing executable"))
        with self.assertRaises(OSError):self.startup.set(True)
        self.r.SetValueEx.assert_not_called()

    def test_moved_path_is_repaired_only_when_opted_in(self):
        self.r.QueryValueEx.return_value=('"X:\\Old Folder\\BloxBinds.exe" --startup',1)
        self.assertIsNone(self.startup.repair(False));self.r.SetValueEx.assert_not_called()
        self.assertIn("repaired",self.startup.repair(True));self.r.SetValueEx.assert_called_once()

    def test_current_path_no_repeated_write(self):
        self.r.QueryValueEx.return_value=(self.startup.command_factory(),1)
        self.assertIsNone(self.startup.repair(True));self.r.SetValueEx.assert_not_called()

    def test_frozen_command_quotes_spaces(self):
        with patch("bloxbinds.startup.sys.frozen",True,create=True),patch("bloxbinds.startup.sys.executable",r"X:\Portable Apps\BloxBinds.exe"),patch.object(Path,"is_file",return_value=True):
            self.assertEqual(startup_command(),'"X:\\Portable Apps\\BloxBinds.exe" --startup')
        with patch.object(Path,"is_file",return_value=False),self.assertRaises(OSError):startup_command()

    def test_startup_argument_minimizes_and_normal_launch_restores(self):
        import main
        for startup in (False,True):
            root=Mock();app=Mock();app.tray.available=True
            with patch("sys.argv",["main.py"]+(["--startup"] if startup else [])),patch("tkinter.Tk",return_value=root),patch("bloxbinds.app.App",return_value=app) as constructor:
                self.assertEqual(main.main(),0)
            self.assertEqual(root.deiconify.call_count,0 if startup else 1)
            self.assertTrue(constructor.call_args.kwargs["single_instance"])

    def test_startup_duplicate_instance_has_no_popup(self):
        import main
        with patch("sys.argv",["main.py","--startup"]),patch("tkinter.Tk",return_value=Mock()),patch("bloxbinds.app.App",side_effect=OSError("already running")),patch("tkinter.messagebox.showerror") as popup:
            self.assertEqual(main.main(),1);popup.assert_not_called()

    def test_startup_without_tray_shows_usable_window(self):
        import main
        root=Mock();app=Mock();app.tray=None
        with patch("sys.argv",["main.py","--startup"]),patch("tkinter.Tk",return_value=root),patch("bloxbinds.app.App",return_value=app):
            self.assertEqual(main.main(),0)
        root.deiconify.assert_called_once()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"backup.json"
        self.settings=Settings(("r","shift+r","ctrl+q","alt+e","shift+mouse4","ctrl+mouse5","mouse3","8","9"),
                              automatic_detection=False,sound_feedback=True,indicator=True,launch_with_windows=True,
                              indicator_position=(-400,30))

    def test_export_roundtrip_portable_preferences(self):
        export_settings(self.path,self.settings)
        restored=import_settings(self.path,Settings())
        self.assertEqual(restored.bindings,self.settings.bindings)
        self.assertFalse(restored.automatic_detection);self.assertTrue(restored.sound_feedback)
        self.assertTrue(restored.indicator);self.assertFalse(restored.launch_with_windows)
        self.assertIsNone(restored.indicator_position)

    def test_export_contains_no_paths_secrets_runtime_or_machine_fields(self):
        export_settings(self.path,self.settings)
        data=json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(data),{"schema_version","settings"})
        for value in ("launch_with_windows","indicator_position","paused","enabled","token","path","registry"):
            self.assertNotIn(value,data["settings"])
        self.assertNotIn(":\\",self.path.read_text(encoding="utf-8"))

    def test_local_startup_and_position_preserved_on_import(self):
        export_settings(self.path,Settings())
        imported=import_settings(self.path,self.settings)
        self.assertTrue(imported.launch_with_windows);self.assertEqual(imported.indicator_position,(-400,30))

    def test_invalid_json_and_duplicate_fields(self):
        for text in ("bad JSON",'{"schema_version":1,"schema_version":1,"settings":{}}'):
            self.path.write_text(text,encoding="utf-8")
            with self.assertRaises(ValueError):import_settings(self.path,self.settings)

    def test_unsupported_schema_missing_and_unexpected_fields(self):
        export_settings(self.path,Settings());valid=json.loads(self.path.read_text(encoding="utf-8"))
        for data in ({**valid,"schema_version":2},{**valid,"extra":1},
                     {**valid,"settings":{"version":1}},
                     {**valid,"settings":{**valid["settings"],"path":"do-not-follow"}},
                     {**valid,"settings":{**valid["settings"],"sound_feedback":"yes"}}):
            with self.subTest(data=data):
                self.path.write_text(json.dumps(data),encoding="utf-8")
                with self.assertRaises(ValueError):import_settings(self.path,self.settings)

    def test_invalid_reserved_and_duplicate_bindings(self):
        for bindings in (["unknown"]+[str(i) for i in range(2,10)],
                         ["f10"]+[str(i) for i in range(2,10)],
                         ["shift+ctrl+r","ctrl+shift+r"]+[str(i) for i in range(3,10)]):
            self.path.write_text(json.dumps({"schema_version":1,"settings":{"version":1,"bindings":bindings}}),encoding="utf-8")
            with self.assertRaises(ValueError):import_settings(self.path,self.settings)

    def test_legacy_fields_migrate_and_new_defaults_off(self):
        self.path.write_text(json.dumps({"schema_version":1,"settings":{"version":1,"bindings":list(Settings().bindings)}}),encoding="utf-8")
        imported=import_settings(self.path,Settings())
        self.assertEqual(imported,Settings());self.assertFalse(imported.auto_updates)

    def test_invalid_position_and_boolean_preferences_rejected(self):
        for position in ([1], [True,3], [1,100001], "path"):
            with self.assertRaises(ValueError):Settings.from_dict({**Settings().to_dict(),"indicator_position":position})
        for key in ("auto_updates","launch_with_windows","indicator","indicator_topmost","sound_feedback"):
            with self.assertRaises(ValueError):Settings.from_dict({**Settings().to_dict(),key:1})

    def test_new_local_preferences_persist(self):
        save_settings(self.path,self.settings)
        self.assertEqual(load_settings(self.path),(self.settings,None))


class SoundTests(unittest.TestCase):
    def setUp(self):
        self.player=Mock();self.sound=Sounds(self.player)

    def test_disabled_by_default_and_enabled_async(self):
        self.sound.play("enabled");self.player.assert_not_called()
        self.sound.enabled=True;self.sound.play("enabled")
        import winsound
        self.assertTrue(self.player.call_args.args[1]&winsound.SND_ASYNC)
        self.sound.enabled=False;self.sound.play("paused");self.assertEqual(self.player.call_count,1)

    def test_manual_pause_resume_once_and_no_focus_or_repeat_feedback(self):
        engine=Engine(replace(Settings(),sound_feedback=True));engine.enable(True)
        api=Mock();api.focus.return_value=Focus(12,34,True)
        service=InputService(engine,api)
        for focus in (Focus(12,34,True),Focus(56,78,False),Focus(12,34,True)):
            api.focus.return_value=focus;service._dispatch("q",True);service._dispatch("q",False)
        self.assertTrue(service.events.empty())
        service._dispatch("f10",True);service._dispatch("f10",True)
        self.assertEqual(service.events.get_nowait(),("sound","paused"));self.assertTrue(service.events.empty())
        service._dispatch("f10",False);service._dispatch("f10",True)
        self.assertEqual(service.events.get_nowait(),("sound","resumed"))

    def test_unavailable_audio_and_shutdown(self):
        self.sound.enabled=True;self.player.side_effect=RuntimeError("no audio")
        self.sound.play("paused");self.sound.close();self.sound.play("resumed")
        self.assertTrue(self.sound.closed);self.assertEqual(self.player.call_count,2)

    def test_background_status_actions_are_silent(self):
        self.sound.enabled=True
        for state in ("Active", "Waiting for Roblox", "Chat Paused", "updates", "focus"):
            self.sound.play(state)
        self.player.assert_not_called()

    def test_shutdown_stops_previous_sound_after_preference_disabled(self):
        self.sound.enabled=True;self.sound.play("enabled");self.sound.enabled=False
        self.sound.close();self.player.assert_called_with(None,0)


class IndicatorTests(unittest.TestCase):
    def test_offscreen_and_negative_monitor_coordinates(self):
        monitors=[(0,0,1920,1040),(-1280,0,0,1024)]
        self.assertEqual(visible_position((-1200,20),(280,62),monitors),(-1200,20))
        self.assertEqual(visible_position((9000,9000),(280,62),monitors),(1640,978))
        self.assertEqual(visible_position((-1200,20),(280,62),monitors[:1]),(0,20))

    def test_monitor_gap_uses_real_work_area(self):
        self.assertEqual(visible_position((2000,10),(280,62),[(0,0,1920,1040),(2560,0,4480,1040)]),(1640,10))

    def test_native_show_hide_no_duplicate_no_focus_stealing_and_cleanup(self):
        import tkinter as tk
        root=tk.Tk();root.withdraw();self.addCleanup(root.destroy)
        api=WindowsAPI();before=api.user.GetForegroundWindow()
        indicator=Indicator(root,Mock(),Mock());self.addCleanup(indicator.close)
        indicator.show("Remapping Disabled",(-99999,-99999));root.update()
        window=indicator.window
        self.assertTrue(api.user.IsWindowVisible(indicator.hwnd))
        self.assertTrue(indicator.label.winfo_ismapped())
        self.assertEqual(before,api.user.GetForegroundWindow())
        self.assertTrue(indicator.api.user.GetWindowLongPtrW(indicator.hwnd,-20)&0x08000000)
        for status in ("Active — Roblox Focused","Waiting for Roblox","Roblox Not Focused","Manually Paused",
                       "Chat Paused","Remapping Disabled","Error / Recovery Needed","Text Entry Paused"):
            indicator.set_status(status);self.assertIn("Active" if status.startswith("Active") else status,indicator.label.cget("text"))
        with patch.object(indicator.label,"configure") as configure:
            indicator.set_status("Text Entry Paused");configure.assert_not_called()
        indicator.hide();self.assertFalse(indicator.visible);self.assertFalse(api.user.IsWindowVisible(indicator.hwnd))
        indicator.show("Active — Roblox Focused",topmost=False);root.update()
        self.assertIs(indicator.window,window);self.assertEqual(before,api.user.GetForegroundWindow())
        indicator.close();self.assertIsNone(indicator.window)

    def test_display_change_recovery_and_saved_drag_position(self):
        indicator=Indicator.__new__(Indicator);indicator.api=Mock()
        indicator.api.monitors.return_value=[(0,0,1920,1040)]
        indicator.visible=True;indicator.hwnd=12;indicator.topmost=True
        indicator.position=(-1200,20);indicator.on_position=Mock()
        indicator.recover_position()
        self.assertEqual(indicator.position,(0,20));indicator.on_position.assert_called_once_with((0,20))
        indicator._begin_drag(SimpleNamespace(x_root=10,y_root=10))
        indicator._drag(SimpleNamespace(x_root=50,y_root=30));indicator._end_drag(None)
        self.assertEqual(indicator.position,(40,40));indicator.on_position.assert_called_with((40,40))
