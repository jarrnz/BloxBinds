"""Small visible-screen samples; retain hashes only, never screenshots or inventory state."""
import ctypes as C
import hashlib
from ctypes import wintypes as W


class Header(C.Structure):
    _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                ("image_size", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG),
                ("used", W.DWORD), ("important", W.DWORD)]


class Info(C.Structure):
    _fields_ = [("header", Header), ("colors", W.DWORD * 3)]


def fingerprint(api, point, radius):
    if not 20 <= radius <= 40:
        raise OSError("Target appearance sample too small; recalibrate wider slot spacing.")
    user, gdi = api.user, C.WinDLL("gdi32", use_last_error=True)
    declare = api._declare
    declare(user, "GetDC", [W.HWND], W.HDC)
    declare(user, "ReleaseDC", [W.HWND, W.HDC], C.c_int)
    declare(gdi, "CreateCompatibleDC", [W.HDC], W.HDC)
    declare(gdi, "CreateCompatibleBitmap", [W.HDC, C.c_int, C.c_int], W.HBITMAP)
    declare(gdi, "SelectObject", [W.HDC, W.HANDLE], W.HANDLE)
    declare(gdi, "DeleteObject", [W.HANDLE], W.BOOL)
    declare(gdi, "DeleteDC", [W.HDC], W.BOOL)
    declare(gdi, "BitBlt", [W.HDC,C.c_int,C.c_int,C.c_int,C.c_int,W.HDC,C.c_int,C.c_int,W.DWORD], W.BOOL)
    declare(gdi, "GetDIBits", [W.HDC,W.HBITMAP,W.UINT,W.UINT,W.LPVOID,C.POINTER(Info),W.UINT], C.c_int)
    dc = memory = bitmap = old = None
    side = radius*2
    try:
        dc = user.GetDC(None)
        if not dc:
            raise OSError("Screen sampling unavailable.")
        memory = gdi.CreateCompatibleDC(dc)
        bitmap = gdi.CreateCompatibleBitmap(dc, side, side)
        if not memory or not bitmap:
            raise OSError("Screen sample allocation failed.")
        old = gdi.SelectObject(memory, bitmap)
        if not old or old == C.c_void_p(-1).value:
            old = None
            raise OSError("Screen sample selection failed.")
        if not gdi.BitBlt(memory,0,0,side,side,dc,point[0]-radius,point[1]-radius,0x00CC0020):
            raise OSError("Visible screen sampling failed.")
        gdi.SelectObject(memory, old)  # GetDIBits requires the bitmap not to be selected.
        old = None
        info = Info(header=Header(size=C.sizeof(Header),width=side,height=-side,planes=1,bits=32))
        pixels = C.create_string_buffer(side*side*4)
        if gdi.GetDIBits(dc,bitmap,0,side,pixels,C.byref(info),0) != side:
            raise OSError("Visible screen pixels unavailable.")
        # Ignore undefined alpha; hash all visible RGB pixels in the target patch.
        data = pixels.raw
        rgb = bytes(v for i,v in enumerate(data) if i%4 != 3)
        return hashlib.sha256(rgb).hexdigest()
    finally:
        if old and memory:
            gdi.SelectObject(memory, old)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        if dc:
            user.ReleaseDC(None, dc)
