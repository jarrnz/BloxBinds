import ctypes as C
import sys
import os
import hashlib
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
            # Tk update does not wait for desktop composition/window fade-in.
            # Settle only this test window; keep all twelve strict equality checks.
            root.after(300, root.quit)
            root.mainloop()
            root.update()
            api=WindowsAPI();mouse=MouseAPI(api)
            dwm=C.WinDLL("dwmapi")
            api._declare(dwm,"DwmFlush",[],C.c_long)
            self.assertEqual(dwm.DwmFlush(),0,"Desktop composition did not flush")
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
            expected=hashlib.sha256(bytes((0xac,0x68,0x24))*(48*48)).hexdigest()
            self.assertEqual(samples[0],expected,"Sample did not contain the known solid test window")
            self.assertLessEqual(after,before+1)
        finally:
            root.destroy()
