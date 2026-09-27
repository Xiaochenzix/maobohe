"""Windows low-level hook. Only button and timestamp are retained."""
import ctypes
from ctypes import wintypes
import threading
import time


class MouseHook:
    def __init__(self, events, commands):
        self.events = events
        self.commands = commands
        self.enabled = threading.Event()
        self.enabled.set()
        self.ready = threading.Event()
        self.error = None
        self.hotkey_ok = False
        self.thread_id = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError('鼠标监听启动超时')
        if self.error:
            raise RuntimeError(self.error)

    def _run(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self.thread_id = kernel.GetCurrentThreadId()
        buttons = {0x0201: 'left', 0x0204: 'right', 0x0207: 'middle'}

        @callback_type
        def callback(code, message, pointer):
            if code >= 0 and message in buttons and self.enabled.is_set():
                self.events.put((time.time(), buttons[message]))
            return user.CallNextHookEx(None, code, message, pointer)

        handle = user.SetWindowsHookExW(14, callback, kernel.GetModuleHandleW(None), 0)
        if not handle:
            self.error = f'Windows 鼠标监听失败（错误 {ctypes.get_last_error()}）'
            self.ready.set()
            return
        self.hotkey_ok = bool(user.RegisterHotKey(None, 1, 0x4000, 0x77))
        self.ready.set()
        msg = wintypes.MSG()
        try:
            while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    # Toggle at the source, so clicks after F8 cannot slip into a batch.
                    if self.enabled.is_set():
                        self.enabled.clear()
                    else:
                        self.enabled.set()
                    self.commands.put('state')
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
        finally:
            user.UnregisterHotKey(None, 1)
            user.UnhookWindowsHookEx(handle)

    def stop(self):
        self.enabled.clear()
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=3)
