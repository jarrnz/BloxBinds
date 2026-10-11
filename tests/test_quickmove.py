import ctypes
import tempfile
import unittest
from dataclasses import replace
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from bloxbinds.engine import Engine
from bloxbinds.mouse import MouseAPI
from bloxbinds.quickmove import Calibration, Geometry, QuickMove, load_calibration, save_calibration
from bloxbinds.settings import Settings
from bloxbinds.win32 import Focus, INPUT, InputService

def profile():
    return Calibration((1000,800,144),(100,100,800,500),tuple((100+i*80,700) for i in range(9)),("a"*64,)*9).validate()
def geometry(left=0,width=1000,dpi=144):
    return Geometry(12,34,left,0,width,800,dpi)

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.quick=QuickMove(profile());self.quick.enable(True);self.quick.set_compatibility("Compatible")
    def test_defaults_off_unknown_inactive(self):
        q=QuickMove(profile())
        self.assertFalse(q.enabled);self.assertFalse(q.active);self.assertEqual(q.compatibility,"Unknown")
        self.assertIsNone(q.take(1,geometry(),(200,200),7))
    def test_unknown_unsupported_and_uncalibrated_block(self):
        for status in ("Unknown","Unsupported"):
            self.quick.set_compatibility(status)
            with self.assertRaises(ValueError): self.quick.activate(geometry())
        self.quick.set_compatibility("Compatible")
        for p in (None,replace(profile(),empty_hashes=())):
            self.quick.profile=p
            with self.assertRaises(ValueError): self.quick.activate(geometry())
    def test_nine_slots_without_per_item_confirmation(self):
        self.quick.activate(geometry())
        for slot in range(1,10):
            m=self.quick.take(slot,geometry(),(200,200),7)
            self.assertEqual(m.target,profile().slots[slot-1]);self.assertTrue(self.quick.valid(m))
            self.quick.complete(m);self.assertTrue(self.quick.active)
        self.assertIn("No verified",self.quick.status())
    def test_attempted_target_cannot_be_reused_after_mode_toggle(self):
        self.quick.activate(geometry());m=self.quick.take(9,geometry(),(200,200),7);self.quick.complete(m)
        self.quick.cancel();self.quick.activate(geometry())
        self.assertIsNone(self.quick.take(9,geometry(),(200,200),7))
    def test_source_bounds_and_busy_guard(self):
        self.quick.activate(geometry())
        for p in ((50,50),(100,100),(200,700)):
            self.assertIsNone(self.quick.take(1,geometry(),p,7))
        self.quick.take(1,geometry(),(200,200),7)
        self.assertIsNone(self.quick.take(2,geometry(),(200,200),7))
    def test_window_changes_cancel_without_resuming(self):
        for g in (geometry(width=1100),geometry(dpi=192),geometry(left=20)):
            self.quick.activate(geometry());self.assertIsNone(self.quick.take(1,g,(200,200),7))
            self.assertFalse(self.quick.active);self.assertIsNone(self.quick.take(1,geometry(),(200,200),7))
        with self.assertRaises(ValueError): self.quick.activate(geometry(width=1100))
    def test_relative_coordinates_negative_monitor(self):
        g=geometry(left=-1000);self.quick.activate(g)
        self.assertEqual(self.quick.take(9,g,(-800,200),7).target,(-260,700))
    def test_disable_cancels_inflight(self):
        self.quick.activate(geometry());m=self.quick.take(1,geometry(),(200,200),7)
        self.quick.enable(False);self.assertFalse(self.quick.valid(m))
    def test_calibration_and_refresh_use_swallowed_clicks(self):
        self.quick.begin_calibration()
        for p in [(100,100),(800,500),*profile().slots]:
            _,saved=self.quick.capture(geometry(),p);self.assertIsNone(saved)
        _,saved=self.quick.capture(geometry(),(200,200));self.assertEqual(saved.slots,profile().slots)
        self.assertFalse(self.quick.calibrating)
        self.quick.begin_calibration(refresh=True)
        _,saved=self.quick.capture(geometry(),(200,200));self.assertEqual(saved.slots,profile().slots)
    def test_partial_calibration_and_geometry_change(self):
        self.quick.begin_calibration();self.assertIsNone(self.quick.profile)
        self.quick.capture(geometry(),(100,100))
        with self.assertRaises(ValueError):self.quick.capture(geometry(width=1100),(800,500))
        self.assertEqual(self.quick.points,[])
    def test_invalid_profiles(self):
        for p in (replace(profile(),region=(800,500,100,100)),replace(profile(),slots=((200,200),)*9),
                  replace(profile(),empty_hashes=("bad",)*9),replace(profile(),slots=((0,700),)*9)):
            with self.assertRaises(ValueError):p.validate()
    def test_persistence_legacy_and_corruption(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"quickmove.json";self.assertEqual(load_calibration(p),(None,None))
            save_calibration(p,profile());self.assertEqual(load_calibration(p),(profile(),None))
            data=profile().to_dict();data.pop("empty_hashes");p.write_text(json.dumps(data),encoding="utf-8")
            self.assertEqual(load_calibration(p)[0].empty_hashes,())
            p.write_text("{ bad",encoding="utf-8");self.assertIsNone(load_calibration(p)[0])
    def test_status(self):
        self.assertEqual(self.quick.status(focused=False),"Roblox Not Focused")
        self.assertEqual(self.quick.status(remapping=False),"Disabled")
        self.assertEqual(self.quick.status(),"Inventory Mode Off")
        self.quick.activate(geometry());self.assertIn("Ready",self.quick.status())

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine=Engine(Settings());self.engine.enable(True);self.api=Mock()
        self.api.focus.return_value=Focus(12,34,True,False);self.api.user.GetAsyncKeyState.return_value=0
        self.service=InputService(self.engine,self.api);self.service._last_focus=(12,34)
        self.quick=self.service.quickmove;self.quick.profile=profile();self.quick.enable(True);self.quick.set_compatibility("Compatible")
        self.mouse=Mock();self.mouse.snapshot.return_value=geometry(),(200,200);self.mouse.geometry.return_value=geometry()
        self.mouse.belongs.return_value=True;self.mouse.drag.side_effect=lambda move,allowed: allowed()
        self.service._mouse_api=self.mouse
    def mode(self):
        self.service._modifiers={0xA2,0xA0};self.service._dispatch("f6",True);self.service._dispatch("f6",False);self.service._modifiers=set()
    def drain(self):
        self.service._output.put(None);self.service._send_loop()
    def test_identity_drag_only_in_mode(self):
        self.assertFalse(self.service._dispatch("1",True));self.service._dispatch("1",False)
        self.mode();self.assertTrue(self.service._dispatch("1",True));self.drain()
        self.mouse.drag.assert_called_once();self.api.tap_slot.assert_not_called();self.assertTrue(self.quick.active)
    def test_custom_keyboard_and_side_buttons_reused(self):
        for key in ("r","mouse4","mouse5","ctrl+q"):
            self.engine.apply(Settings(("1","2","3","4","5","6","7","8",key)));self.engine.enable(True);self.mode()
            self.service._modifiers={0xA2} if key=="ctrl+q" else set();physical="q" if key=="ctrl+q" else key
            self.service._dispatch(physical,True);job=self.service._output.get_nowait();self.assertEqual(job[3].target,(740,700))
            self.quick.complete(job[3]);self.quick.used.clear();self.quick.cancel();self.service._dispatch(physical,False);self.service._modifiers=set()
    def test_gameplay_hotbar_preserved(self):
        self.engine.apply(Settings(("q","2","3","4","5","6","7","8","9")));self.engine.enable(True)
        self.service._dispatch("q",True);self.drain();self.api.tap_slot.assert_called_once_with(1,());self.mouse.drag.assert_not_called()
    def test_backquote_does_not_pause_but_chat_blocks_inventory_mode(self):
        self.service._dispatch("backquote",True);self.service._dispatch("backquote",False);self.assertFalse(self.engine.text_paused);self.mode();self.assertTrue(self.quick.active)
        self.service._dispatch("enter",True);self.service._dispatch("enter",False);self.mode();self.assertFalse(self.quick.active);self.assertTrue(self.engine.text_paused)
    def test_manual_pause_cannot_be_overridden_by_inventory_shortcut(self):
        self.service._dispatch("f10", True)
        self.service._dispatch("f10", False)
        for _ in range(2):
            self.assertFalse(self.service._dispatch("backquote", True))
            self.assertFalse(self.service._dispatch("backquote", False))
        self.mode()
        self.assertFalse(self.quick.active)
        self.assertTrue(self.engine.text_paused)
        self.mouse.snapshot.assert_not_called()
        self.service._dispatch("f10", True)
        self.service._dispatch("f10", False)
        self.mode()
        self.assertTrue(self.quick.active)

    def test_backquote_cancels_inventory_and_stale_drag_then_hotbar_works(self):
        attempts = []
        def drag(move, allowed):
            attempts.append(allowed())
            return attempts[-1]
        self.mouse.drag.side_effect = drag
        self.engine.apply(Settings(("q", "2", "3", "4", "5", "6", "7", "8", "9")))
        self.engine.enable(True)
        self.mode()
        self.service._dispatch("q", True)
        self.service._dispatch("q", False)
        for _ in range(2):
            self.assertFalse(self.service._dispatch("backquote", True))
            self.assertFalse(self.service._dispatch("backquote", False))
        self.assertFalse(self.quick.active)
        self.assertFalse(self.engine.text_paused)
        self.service._dispatch("q", True)
        self.drain()
        self.assertEqual(attempts, [False])  # The drag guard refused the stale job.
        self.api.tap_slot.assert_called_once_with(1, ())

    def test_focus_return_preserves_manual_pause_without_rearming_inventory(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                self.setUp()
                self.engine.apply(Settings(("q", "2", "3", "4", "5", "6", "7", "8", "9")))
                self.engine.enable(True)
                self.mode()
                if paused:
                    self.service._dispatch("f10", True)
                    self.service._dispatch("f10", False)
                self.service._dispatch("backquote", True)
                self.service._dispatch("backquote", False)
                self.api.focus.return_value = Focus(56, 78, False, False)
                self.service._dispatch("q", True)
                self.service._dispatch("q", False)
                self.api.focus.return_value = Focus(12, 34, True, False)
                self.service._dispatch("q", True)
                self.drain()
                self.assertFalse(self.quick.active)
                self.assertEqual(self.engine.text_paused, paused)
                self.mouse.drag.assert_not_called()
                if paused:
                    self.api.tap_slot.assert_not_called()
                else:
                    self.api.tap_slot.assert_called_once_with(1, ())

    def test_inventory_activation_does_not_clear_pause_arriving_during_snapshot(self):
        def snapshot(focus):
            self.engine.process("f10", True, focused=True)
            self.engine.process("f10", False)
            return geometry(), (200, 200)
        self.mouse.snapshot.side_effect = snapshot
        self.mode()
        self.assertTrue(self.engine.text_paused)
        self.service._dispatch("1", True)
        self.drain()
        self.mouse.drag.assert_not_called()
        self.api.tap_slot.assert_not_called()

    def test_native_text_refused(self):
        self.api.focus.return_value=Focus(12,34,True,True);self.mode();self.assertFalse(self.quick.active)
    def test_repeat_does_not_duplicate_job(self):
        self.mode()
        for _ in range(4):self.service._dispatch("1",True)
        self.assertEqual(self.service._output.qsize(),1)
    def test_unsafe_source_has_no_gameplay_fallback(self):
        self.mode();self.mouse.snapshot.return_value=geometry(),(50,50)
        self.assertTrue(self.service._dispatch("1",True));self.drain();self.mouse.drag.assert_not_called();self.api.tap_slot.assert_not_called()
    def test_snapshot_failure_does_not_fall_back_to_hotbar(self):
        self.engine.apply(Settings(("q","2","3","4","5","6","7","8","9")));self.engine.enable(True)
        self.mode();self.mouse.snapshot.side_effect=OSError("uncertain")
        self.assertTrue(self.service._dispatch("q",True));self.drain()
        self.api.tap_slot.assert_not_called();self.mouse.drag.assert_not_called()
    def test_unknown_mode_refused(self):
        self.quick.set_compatibility("Unknown");self.mode();self.assertFalse(self.quick.active)
    def test_emergency_cancels_queued_drag(self):
        self.mode();self.service._dispatch("1",True);self.service._modifiers={0xA2,0xA4};self.service._dispatch("f12",True);self.drain()
        self.assertFalse(self.engine.enabled);self.assertFalse(self.quick.active);self.api.tap_slot.assert_not_called()
    def test_focus_loss_does_not_resume(self):
        self.mode();self.api.focus.return_value=Focus(56,78,False,False);self.service._dispatch("q",True)
        self.api.focus.return_value=Focus(12,34,True,False);self.service._dispatch("q",False);self.assertFalse(self.quick.active)
    def test_resize_between_queue_and_drag(self):
        self.mode();self.service._dispatch("1",True);self.mouse.geometry.return_value=geometry(width=1100);self.drain()
        self.assertFalse(self.mouse.drag.call_args.args[1]())
    def test_shortcut_conflict_preserves_binding(self):
        self.engine.apply(Settings(("ctrl+shift+f6","2","3","4","5","6","7","8","9")));self.engine.enable(True);self.mode()
        self.assertFalse(self.quick.active);self.assertEqual(self.service._output.qsize(),1)
    def test_calibration_clicks_never_send_input(self):
        self.quick.begin_calibration();self.assertTrue(self.service._capture_click(True));self.assertTrue(self.service._capture_click(False))
        self.assertFalse(self.service._capture_click(False));self.api.tap_slot.assert_not_called();self.mouse.drag.assert_not_called()

class DragGuardTests(unittest.TestCase):
    def setUp(self):
        self.mouse = MouseAPI.__new__(MouseAPI)
        self.mouse.user = SimpleNamespace(GetAsyncKeyState=lambda vk: 0,
                                          GetSystemMetrics=lambda i: {76: -1000, 77: 0, 78: 3000, 79: 1000}[i])
        self.mouse.physical_coordinates = lambda: nullcontext()
        self.mouse.cursor = lambda: (200, 200)
        self.mouse._send = Mock()
        self.mouse.fingerprint = Mock(return_value="a"*64)
        quick = QuickMove(profile())
        quick.enable(True)
        quick.set_compatibility("Compatible")
        quick.activate(geometry())
        self.move = quick.take(1, geometry(), (200, 200), 1)

    def test_uncertain_detection_performs_no_mouse_actions(self):
        self.assertFalse(self.mouse.drag(self.move, lambda: False))
        self.mouse._send.assert_not_called()

    def test_cancel_after_button_down_balances_release_without_moving(self):
        allowed = Mock(side_effect=[True, True, False])
        with patch('bloxbinds.mouse.time.sleep'):
            self.assertFalse(self.mouse.drag(self.move, allowed))
        self.assertEqual(self.mouse._send.call_args_list, [unittest.mock.call(flags=2), unittest.mock.call(flags=4)])

    def test_success_uses_normal_drag_and_always_releases(self):
        with patch('bloxbinds.mouse.time.sleep'):
            self.assertTrue(self.mouse.drag(self.move, lambda: True))
        self.assertEqual(self.mouse._send.call_args_list[0], unittest.mock.call(flags=2))
        self.assertEqual(self.mouse._send.call_args_list[-2], unittest.mock.call((100, 700)))
        self.assertEqual(self.mouse._send.call_args_list[-1], unittest.mock.call(flags=4))

    def test_physical_button_held_prevents_drag(self):
        self.mouse.user.GetAsyncKeyState = lambda vk: 0x8000 if vk == 1 else 0
        self.assertFalse(self.mouse.drag(self.move, lambda: True))
        self.mouse._send.assert_not_called()

    def test_mouse_failure_still_attempts_release(self):
        self.mouse._send.side_effect = [OSError('rejected'), None]
        with self.assertRaises(OSError):
            self.mouse.drag(self.move, lambda: True)
        self.assertEqual(self.mouse._send.call_args_list[-1], unittest.mock.call(flags=4))

    def test_mouse_coordinates_are_tagged_virtual_desktop(self):
        events = []
        def capture(count, pointer, size):
            event = ctypes.cast(pointer, ctypes.POINTER(INPUT)).contents
            events.append((event.type, event.mi.dx, event.mi.dy, event.mi.dwFlags, event.mi.dwExtraInfo))
            return count
        self.mouse.user.SendInput = capture
        self.mouse._send = MouseAPI._send.__get__(self.mouse)
        self.mouse._send((-1000, 0))
        self.assertEqual(events, [(0, 0, 0, 0xE001, 0x424C4F58)])
        self.mouse._send((1999, 999))
        self.assertEqual(events[-1][1:3], (65535, 65535))

    def test_out_of_desktop_target_is_refused_before_button_down(self):
        from dataclasses import replace
        outside = replace(self.move, target=(5000, 700))
        self.assertFalse(self.mouse.drag(outside, lambda: True))
        self.mouse._send.assert_not_called()

    def test_empty_appearance_mismatch_blocks_all_mouse_actions(self):
        self.mouse.fingerprint.return_value="b"*64
        self.assertFalse(self.mouse.drag(self.move,lambda:True));self.mouse._send.assert_not_called()
    def test_sample_failure_blocks_all_mouse_actions(self):
        self.mouse.fingerprint.side_effect=OSError("uncertain")
        with self.assertRaises(OSError):self.mouse.drag(self.move,lambda:True)
        self.mouse._send.assert_not_called()

    def test_held_modifier_timeout_refuses_drag(self):
        self.mouse.user.GetAsyncKeyState=lambda vk:0x8000 if vk==0x11 else 0
        with patch('bloxbinds.mouse.time.monotonic',side_effect=[0,1]):
            self.assertFalse(self.mouse.drag(self.move,lambda:True))
        self.mouse._send.assert_not_called()
