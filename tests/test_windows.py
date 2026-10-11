import ctypes
import queue
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bloxbinds.engine import Engine
from bloxbinds.settings import Settings
from bloxbinds.win32 import CLIENT_NAMES, Focus, INPUT, InputService, SingleInstance, WindowsAPI


def settings():
    return Settings(("q", "mouse4", "3", "4", "5", "6", "7", "8", "9"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(settings())
        self.engine.enable(True)
        self.api = Mock()
        self.api.focus.return_value = Focus(123, 456, True, False)
        self.api.user.GetAsyncKeyState.return_value = 0
        self.service = InputService(self.engine, self.api)

    def run_output(self):
        self.service._output.put(None)
        self.service._send_loop()

    def test_dispatch_and_output(self):
        self.assertTrue(self.service._dispatch("q", True))
        self.run_output()
        self.api.tap_slot.assert_called_once_with(1, ())

    def test_output_focus_change_discards_job(self):
        self.service._dispatch("q", True)
        self.api.focus.return_value = Focus(999, 111, False)
        self.run_output()
        self.api.tap_slot.assert_not_called()

    def test_other_roblox_window_discards_job(self):
        self.service._dispatch("q", True)
        self.api.focus.return_value = Focus(999, 111, True)
        self.run_output()
        self.api.tap_slot.assert_not_called()

    def test_emergency_discards_queued_job(self):
        self.service._dispatch("q", True)
        self.service._modifiers = {0xA2, 0xA4}
        self.service._dispatch("f12", True)
        self.run_output()
        self.api.tap_slot.assert_not_called()
        self.assertFalse(self.engine.enabled)
        self.assertEqual(self.service.events.get_nowait()[0], "emergency")

    def test_native_text_discards_output(self):
        self.service._dispatch("q", True)
        self.api.focus.return_value = Focus(123, 456, True, True)
        self.run_output()
        self.api.tap_slot.assert_not_called()

    def test_output_failure_disables(self):
        self.service._dispatch("q", True)
        self.api.tap_slot.side_effect = OSError("Input rejected")
        self.run_output()
        self.assertFalse(self.engine.enabled)
        self.assertEqual(self.service.events.get_nowait(), ("error", "Input rejected"))

    def test_shutdown_stops_worker_and_posts_quit(self):
        self.service._worker = threading.Thread(target=self.service._send_loop)
        self.service._worker.start()
        self.service._thread_id = 77
        self.service.stop()
        self.service.stop()
        self.assertTrue(self.engine.closed)
        self.assertFalse(self.service._worker.is_alive())
        self.api.user.PostThreadMessageW.assert_called_with(77, 0x12, 0, 0)

    def test_shutdown_drains_worker_before_stopping_hooks(self):
        order = []
        self.service._worker = Mock()
        self.service._thread = Mock()
        self.service._worker.is_alive.return_value = False
        self.service._thread.is_alive.return_value = False
        self.service._worker.join.side_effect = lambda **kw: order.append("worker")
        self.service._thread.join.side_effect = lambda **kw: order.append("hooks")
        self.service._thread_id = 77
        self.api.user.PostThreadMessageW.side_effect = lambda *args: order.append("quit")
        self.service.stop()
        self.assertEqual(order, ["worker", "quit", "hooks"])

    def test_shutdown_failure_is_reported(self):
        thread = Mock()
        thread.name = "blocked-thread"
        thread.is_alive.return_value = True
        self.service._thread = thread
        with self.assertRaisesRegex(RuntimeError, "did not shut down"):
            self.service.stop()


@unittest.skipUnless(sys.platform == "win32", "Windows API tests")
class NativeTests(unittest.TestCase):
    def test_single_instance_rejects_existing_mutex_and_releases_handle(self):
        api = Mock()
        def create(*args):
            ctypes.set_last_error(183)
            return 99
        api.kernel.CreateMutexW.side_effect = create
        with self.assertRaisesRegex(OSError, "already running"):
            SingleInstance(api)
        api.kernel.CloseHandle.assert_called_once_with(99)

    def test_input_abi(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_real_metadata_focus_query(self):
        api = WindowsAPI()
        focus = api.focus()
        self.assertIsInstance(focus, Focus)
        self.assertFalse(api.is_client(0))

    def test_studio_is_excluded(self):
        self.assertNotIn("robloxstudiobeta.exe", CLIENT_NAMES)

    def test_sendinput_builds_balanced_tagged_scan_code_batch(self):
        api = WindowsAPI()
        captured = []
        def send(count, batch, size):
            captured.extend((batch[i].ki.wVk, batch[i].ki.wScan,
                             batch[i].ki.dwFlags, batch[i].ki.dwExtraInfo) for i in range(count))
            return count
        # Capture the Windows API boundary; do not send keys to another application.
        api.user = SimpleNamespace(MapVirtualKeyW=lambda vk, mode: 2, SendInput=send)
        api.tap_slot(1, (0xA2, 0xA0))
        self.assertEqual([e[2] for e in captured], [2, 2, 8, 10, 0, 0])
        self.assertTrue(all(e[3] == 0x424C4F58 for e in captured))
        self.assertEqual(captured[2][:2], (0, 2))
