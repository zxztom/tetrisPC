"""The requested bot's Windows capture and keyboard driver.

Only the project's TETR.IO executable may be targeted. The bot stops when
focus changes, and F8 or Esc aborts it. Capture never reads process memory.
"""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import os
import time
import threading

if os.name != "nt":
    raise RuntimeError("实时控制目前只支持 Windows。")

user = ctypes.WinDLL("user32", use_last_error=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
gdi = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
user.GetForegroundWindow.restype = w.HWND
user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user.IsWindowVisible.argtypes = [w.HWND]
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel.CloseHandle.argtypes = [w.HANDLE]
user.SetForegroundWindow.argtypes = [w.HWND]
user.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
user.MapVirtualKeyW.restype = w.UINT


class GameNotFound(RuntimeError):
    pass


def find_game():
    from .solver import ROOT
    expected = str((ROOT / "tetrio-desktop/TETR.IO.exe").resolve()).lower()
    found = []
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            name, length = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            if kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
                if name.value.lower() == expected:
                    title = ctypes.create_unicode_buffer(1024)
                    user.GetWindowTextW(hwnd, title, 1024)
                    if title.value == "TETR.IO":
                        found.append({"hwnd": int(hwnd), "pid": pid.value, "title": title.value})
        finally:
            kernel.CloseHandle(handle)
        return True
    callback = callback_type(visit)
    user.EnumWindows(callback, 0)
    if not found:
        raise GameNotFound("请打开本项目中的 TETR.IO。")
    if len(found) != 1:
        raise RuntimeError("请保留一个 TETR.IO 游戏窗口，以免操作错误的窗口。")
    return found[0]


def focus(hwnd):
    user.ShowWindow(hwnd, 9)
    user.SetForegroundWindow(hwnd)
    if int(user.GetForegroundWindow() or 0)!=hwnd:
        # A start-button click authorizes bringing the game forward. Attach
        # only for the focus transfer, then detach both input queues.
        user.AttachThreadInput.argtypes=[w.DWORD,w.DWORD,w.BOOL]
        kernel.GetCurrentThreadId.restype=w.DWORD
        caller=kernel.GetCurrentThreadId()
        msg=w.MSG()
        user.PeekMessageW(ctypes.byref(msg),None,0,0,0)
        foreground=user.GetForegroundWindow()
        gui=user.GetWindowThreadProcessId(foreground,None)
        target_gui=user.GetWindowThreadProcessId(hwnd,None)
        attached=user.AttachThreadInput(caller,gui,True)
        target_attached=user.AttachThreadInput(caller,target_gui,True) if target_gui!=gui else False
        try:
            user.BringWindowToTop(hwnd)
            user.SetForegroundWindow(hwnd)
        finally:
            if target_attached:user.AttachThreadInput(caller,target_gui,False)
            if attached:user.AttachThreadInput(caller,gui,False)
    time.sleep(.15)
    if int(user.GetForegroundWindow() or 0) != hwnd:
        raise RuntimeError("无法将 TETR.IO 切到前台。请点击游戏窗口后重试。")


def bounds(hwnd):
    rect = w.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("游戏窗口已关闭。")
    return rect.left, rect.top, rect.right, rect.bottom


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),
              ('bits',w.WORD),('compression',w.DWORD),('image_size',w.DWORD),
              ('xppm',w.LONG),('yppm',w.LONG),('used',w.DWORD),('important',w.DWORD)]


user.GetDC.argtypes=[w.HWND];user.GetDC.restype=w.HDC
user.ReleaseDC.argtypes=[w.HWND,w.HDC]
gdi.CreateCompatibleDC.argtypes=[w.HDC];gdi.CreateCompatibleDC.restype=w.HDC
gdi.CreateDIBSection.argtypes=[w.HDC,ctypes.POINTER(BITMAPINFOHEADER),w.UINT,
                              ctypes.POINTER(ctypes.c_void_p),w.HANDLE,w.DWORD]
gdi.CreateDIBSection.restype=w.HANDLE
gdi.SelectObject.argtypes=[w.HDC,w.HANDLE];gdi.SelectObject.restype=w.HANDLE
gdi.DeleteObject.argtypes=[w.HANDLE];gdi.DeleteDC.argtypes=[w.HDC]
gdi.SetStretchBltMode.argtypes=[w.HDC,ctypes.c_int]
gdi.StretchBlt.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                        w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.DWORD]
_capture_local=threading.local()

def set_capture_backend(name='gdi'):
    _capture_local.backend=name
    _capture_local.capture_failure=None

def capture_backend():
    return 'dxgi' if getattr(_capture_local,'camera',None) is not None else 'gdi'


def close_capture():
    camera=getattr(_capture_local,'camera',None)
    if camera is not None:
        camera.release();_capture_local.camera=None
    cached=getattr(_capture_local,'buffer',None)
    if cached:
        size,dc,bitmap,old,pixels=cached
        gdi.SelectObject(dc,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(dc)
        _capture_local.buffer=None


def capture(hwnd, require_focus=True, scale=1,region=None):
    """Capture only this window into a reusable, thread-local bitmap.

    The source is the visible screen, just as with ImageGrab; no process
    internals are read. Half resolution still gives ~27 pixels per cell.
    """
    from PIL import Image
    if require_focus and int(user.GetForegroundWindow() or 0) != hwnd:
        raise InterruptedError("游戏失去焦点，已停止按键。")
    left,top,right,bottom=bounds(hwnd);width=right-left;height=bottom-top
    if width<=0 or height<=0:raise RuntimeError('游戏窗口不可见。')
    if region is not None:
        x1,y1,x2,y2=region
        if not (0<=x1<x2<=width and 0<=y1<y2<=height):raise ValueError('游戏窗口尺寸发生变化，请重新开始。')
        left+=x1;top+=y1;width=x2-x1;height=y2-y1
    size=(max(1,round(width*scale)),max(1,round(height*scale)))
    if getattr(_capture_local,'backend','gdi')=='dxgi' and not getattr(_capture_local,'capture_failure',None):
        try:
            camera=getattr(_capture_local,'camera',None)
            if camera is None:
                import sys
                from .solver import ROOT
                dependency=str(ROOT/'tools/capture')
                if dependency not in sys.path:sys.path.append(dependency)
                import dxcam
                camera=dxcam.create(output_color='BGRA',processor_backend='numpy',max_buffer_len=2)
                _capture_local.camera=camera
            # DXGI coordinates are monitor-relative; only this game's
            # rectangle is returned or interpreted. Focus checks above
            # still stop the bot when the user switches applications.
            output=camera._output.desc.DesktopCoordinates
            rect=(left-output.left,top-output.top,left+width-output.left,top+height-output.top)
            frame=camera.grab(region=rect,new_frame_only=False)
            if frame is None:raise RuntimeError('DXGI 尚未提供帧。')
            from .capture_image import dxgi_image
            return dxgi_image(frame,size)
        except Exception as error:
            _capture_local.capture_failure=type(error).__name__+': '+str(error)
            camera=getattr(_capture_local,'camera',None)
            if camera is not None:
                camera.release();_capture_local.camera=None
            # Ordinary GDI remains usable on unsupported devices/monitors.
    screen=user.GetDC(None)
    try:
        cached=getattr(_capture_local,'buffer',None)
        if not cached or cached[0]!=size:
            close_capture();dc=gdi.CreateCompatibleDC(screen)
            header=BITMAPINFOHEADER(size=ctypes.sizeof(BITMAPINFOHEADER),width=size[0],height=-size[1],planes=1,bits=32)
            pixels=ctypes.c_void_p();bitmap=gdi.CreateDIBSection(screen,ctypes.byref(header),0,ctypes.byref(pixels),None,0)
            if not dc or not bitmap or not pixels.value:
                if bitmap:gdi.DeleteObject(bitmap)
                if dc:gdi.DeleteDC(dc)
                raise RuntimeError('无法创建游戏截图缓冲区。')
            old=gdi.SelectObject(dc,bitmap);cached=(size,dc,bitmap,old,pixels)
            gdi.SetStretchBltMode(dc,3)  # COLORONCOLOR; geometry is calibrated at full size.
            _capture_local.buffer=cached
        _,dc,bitmap,old,pixels=cached
        if not gdi.StretchBlt(dc,0,0,*size,screen,left,top,width,height,0x00CC0020):
            raise RuntimeError('无法读取游戏画面。')
        gdi.GdiFlush()
        data=ctypes.string_at(pixels,size[0]*size[1]*4)
        return Image.frombytes('RGB',size,data,'raw','BGRX')
    finally:user.ReleaseDC(None,screen)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("data", INPUTUNION)]


user.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user.SendInput.restype = w.UINT
DEFAULT_KEYS = {"left": 0x25, "right": 0x27, "down": 0x28,
                "cw": 0x26, "ccw": 0x11, "hard_drop": 0x20,
                "hold": 0x10, "retry": ord("R"), "forfeit": 0x1B}


def emergency_pressed():
    return bool(user.GetAsyncKeyState(0x77) & 0x8000 or user.GetAsyncKeyState(0x1B) & 0x8000)


class EmergencyKeys:
    """Latch brief emergency taps independently of vision/search polling."""
    def __init__(self):
        self.pressed=threading.Event();self.closed=threading.Event();self.ready=threading.Event()
        self.thread=threading.Thread(target=self.listen,daemon=True);self.thread.start()
        self.ready.wait(1)

    def listen(self):
        registered=[]
        try:
            for index,key in enumerate((0x77,0x1B),0x5043):
                if user.RegisterHotKey(None,index,0x4000,key):registered.append(index)
            self.ready.set();msg=w.MSG()
            while not self.closed.is_set():
                while user.PeekMessageW(ctypes.byref(msg),None,0,0,1):
                    if msg.message==0x0312 and msg.wParam in registered:self.pressed.set()
                self.closed.wait(.01)
        finally:
            for index in registered:user.UnregisterHotKey(None,index)
            self.ready.set()

    def close(self):
        self.closed.set();self.thread.join(timeout=1)


def _keyboard_input(action, down, keys=None):
    vk = (keys or DEFAULT_KEYS)[action]
    extended=0x21<=vk<=0x2E or vk in (0xA3,0xA5,0x6F,0x10D)
    scan=user.MapVirtualKeyW(vk&0xFF,0)
    flags=8 | (0 if down else 2) | (1 if extended else 0)
    return INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(wVk=0,wScan=scan,dwFlags=flags)))


def key_event(hwnd, action, down, keys=None):
    if down and int(user.GetForegroundWindow() or 0) != hwnd:
        raise InterruptedError("游戏失去焦点，已停止按键。")
    event = _keyboard_input(action,down,keys)
    if user.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise RuntimeError("Windows 未接受游戏按键。")


def tap(hwnd, action, keys=None, duration=.024, gap=.035, cancelled=lambda: False):
    if cancelled() or emergency_pressed():
        raise InterruptedError("已停止自动操作。")
    if duration==0:
        # Queue the release with the press. Sleeping between separate calls
        # can turn a nominal 1ms tap into an 82ms DAS hold under scheduling
        # jitter. Same-key neutral-frame spacing remains in Runner.send.
        if int(user.GetForegroundWindow() or 0)!=hwnd:
            raise InterruptedError("游戏失去焦点，已停止按键。")
        events=(INPUT*2)(_keyboard_input(action,True,keys),_keyboard_input(action,False,keys))
        if user.SendInput(2,events,ctypes.sizeof(INPUT))!=2:
            key_event(hwnd,action,False,keys)
            raise RuntimeError("Windows 未完整接受成对点按，已释放按键。")
        if gap:time.sleep(gap)
        return
    key_event(hwnd,action,True,keys)
    try:
        end=time.perf_counter()+duration
        while time.perf_counter()<end:
            if action!="forfeit" and (cancelled() or emergency_pressed()):
                raise InterruptedError("已停止自动操作。")
            time.sleep(min(.02,max(0,end-time.perf_counter())))
    finally:
        key_event(hwnd,action,False,keys)
    time.sleep(gap)
