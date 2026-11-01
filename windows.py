"""Windows-only window discovery, DPI-aware capture and guarded physical clicks."""
import ctypes as ct
from ctypes import wintypes as wt
import time
import numpy as np
from PIL import ImageGrab

user = ct.WinDLL("user32", use_last_error=True)
user.GetForegroundWindow.restype = wt.HWND
user.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user.GetAncestor.restype = wt.HWND
user.WindowFromPoint.argtypes = [wt.POINT]
user.WindowFromPoint.restype = wt.HWND
for name in ["IsWindow", "IsWindowVisible", "IsIconic", "SetForegroundWindow"]:
    getattr(user, name).argtypes = [wt.HWND]
user.GetWindowRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
user.ShowWindow.argtypes = [wt.HWND, ct.c_int]
user.GetWindowTextLengthW.argtypes = [wt.HWND]
user.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]


def dpi_awareness():
    try:
        user.SetProcessDpiAwarenessContext(ct.c_void_p(-4))
    except Exception:
        user.SetProcessDPIAware()


def find_windows():
    found = []
    @ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        if user.IsWindowVisible(hwnd):
            text = ct.create_unicode_buffer(user.GetWindowTextLengthW(hwnd)+1)
            user.GetWindowTextW(hwnd, text, len(text))
            if "clash" in text.value.casefold() and "自动选择" not in text.value:
                found.append((int(hwnd), text.value))
        return True
    user.EnumWindows(visit, 0)
    return found


def rect(hwnd):
    if not user.IsWindow(hwnd):
        raise RuntimeError("目标 Clash 窗口已关闭")
    value = wt.RECT()
    if not user.GetWindowRect(hwnd, ct.byref(value)):
        raise RuntimeError("无法读取窗口位置")
    return value.left, value.top, value.right, value.bottom


def activate(hwnd, stop):
    if not user.IsWindow(hwnd):
        raise RuntimeError("目标窗口不存在，请刷新窗口列表")
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 9)
    user.SetForegroundWindow(hwnd)
    if stop.wait(.4):
        raise InterruptedError()
    if user.GetForegroundWindow() != hwnd:
        raise RuntimeError("无法将 Clash 切到前台，本轮已跳过")


def capture(hwnd):
    if user.GetForegroundWindow() != hwnd:
        raise RuntimeError("Clash 已离开前台，本轮已跳过")
    bounds = rect(hwnd)
    return np.asarray(ImageGrab.grab(bbox=bounds, all_screens=True).convert("RGB")), bounds


def click(hwnd, bounds, point, stop):
    if stop.is_set():
        raise InterruptedError()
    if rect(hwnd) != bounds or user.GetForegroundWindow() != hwnd:
        raise RuntimeError("窗口位置或前台状态改变，本轮已取消；下轮重新定位")
    x, y = bounds[0]+int(point[0]), bounds[1]+int(point[1])
    under = user.WindowFromPoint(wt.POINT(x,y))
    if user.GetAncestor(under, 2) != hwnd:
        raise RuntimeError("目标点击位置被其他窗口遮挡")
    old = wt.POINT()
    user.GetCursorPos(ct.byref(old))
    user.SetCursorPos(x,y)
    try:
        if stop.is_set():
            raise InterruptedError()
        user.mouse_event(2,0,0,0,0)
        user.mouse_event(4,0,0,0,0)
    finally:
        user.SetCursorPos(old.x,old.y)


def hotkey_loop(stop_program, callback):
    if not user.RegisterHotKey(None, 1, 0x4003, 0x7B):
        callback("hotkey_error", "停止快捷键注册失败，请使用停止按钮")
        return
    msg = wt.MSG()
    try:
        while not stop_program.wait(.05):
            while user.PeekMessageW(ct.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0312:
                    callback("stop", None)
    finally:
        user.UnregisterHotKey(None, 1)
