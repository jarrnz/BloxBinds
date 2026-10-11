import ctypes as C
import sys
import os
import unittest
from ctypes import wintypes as W

@unittest.skipUnless(sys.platform=="win32" and not os.environ.get("CI"),"Requires an interactive Windows desktop")
class ScreenTests(unittest.TestCase):
    def test_hash_only_sample_on_own_window_and_gdi_cleanup(self):
        import tkinter as tk
        from bloxbinds.mouse import MouseAPI
        from bloxbinds.win32 import WindowsAPI
        root=tk.Tk();root.title("BloxBinds safe screen test");root.geometry("220x120+30+30")
        root.configure(background="#2468ac");root.attributes("-topmost",True)
        try:
            root.update()
            api=WindowsAPI();mouse=MouseAPI(api)
            hwnd=api.user.GetAncestor(root.winfo_id(),2)
            with mouse.physical_coordinates():
                origin=W.POINT()
                self.assertTrue(api.user.ClientToScreen(hwnd,C.byref(origin)))
                point=(origin.x+65,origin.y+65)
                kernel=api.kernel
                api._declare(kernel,"GetCurrentProcess",[],W.HANDLE)
                api._declare(api.user,"GetGuiResources",[W.HANDLE,W.DWORD],W.DWORD)
                before=api.user.GetGuiResources(kernel.GetCurrentProcess(),0)
                self.assertGreater(before,0,"GDI resource query failed")
                samples=[mouse.fingerprint(hwnd,point,24) for _ in range(12)]
                after=api.user.GetGuiResources(kernel.GetCurrentProcess(),0)
            self.assertEqual(len(samples[0]),64)
            self.assertEqual(len(set(samples)),1)
            self.assertLessEqual(after,before+1)
        finally:
            root.destroy()
