"""Windows notification icon with its own message loop; no Tk calls off-thread."""
import os
import threading
import pywintypes  # Required by the Win32 extensions; include its DLL in frozen builds.
import win32api
import win32con
import win32gui
from branding import APP_NAME, AUTHOR


class TrayIcon:
    MESSAGE = win32con.WM_APP + 20
    UPDATE = win32con.WM_APP + 21
    OPEN, HIDE, TOGGLE, EXIT = range(1001, 1005)
    PET = 1005
    TOOLS = 1006

    def __init__(self, commands, icon_path):
        self.commands = commands
        self.icon_path = str(icon_path)
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.hwnd = None
        self.error = None
        self.paused = False
        self.pet_visible = True
        self.tip = f'{APP_NAME} · 作者 {AUTHOR}'

    def start(self):
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError('系统托盘启动超时')
        if self.error:
            raise RuntimeError(f'系统托盘启动失败：{self.error}')

    def _add_icon(self):
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (
            self.hwnd, 1, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            self.MESSAGE, self.icon, self.tip))

    def _run(self):
        name = f'ClickBreakTray-{os.getpid()}-{id(self)}'
        instance = win32api.GetModuleHandle(None)
        self.icon = None
        registered = False
        try:
            self.taskbar_created = win32gui.RegisterWindowMessage('TaskbarCreated')
            wc = win32gui.WNDCLASS()
            wc.hInstance = instance
            wc.lpszClassName = name
            wc.lpfnWndProc = self._window_proc
            win32gui.RegisterClass(wc)
            registered = True
            self.hwnd = win32gui.CreateWindow(name, name, 0, 0, 0, 0, 0, 0, 0, instance, None)
            self.icon = win32gui.LoadImage(0, self.icon_path, win32con.IMAGE_ICON,
                                          0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
            self._add_icon()
            self.ready.set()
            win32gui.PumpMessages()
        except Exception as error:
            self.error = str(error)
            self.commands.put('tray_failed')
            self.ready.set()
        finally:
            if self.hwnd and win32gui.IsWindow(self.hwnd):
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 1))
                win32gui.DestroyWindow(self.hwnd)
            if self.icon:
                win32gui.DestroyIcon(self.icon)
            if registered:
                win32gui.UnregisterClass(name, instance)
            self.hwnd = None

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == self.MESSAGE:
            if lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONUP, win32con.WM_CONTEXTMENU):
                self._menu()
            return 0
        if message == win32con.WM_COMMAND:
            command = {self.OPEN: 'open', self.HIDE: 'hide', self.TOGGLE: 'toggle', self.EXIT: 'exit', self.PET: 'pet', self.TOOLS: 'tools'}.get(wparam & 0xffff)
            if command:
                self.commands.put(command)
            return 0
        if message == self.UPDATE:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, (
                hwnd, 1, win32gui.NIF_TIP, self.MESSAGE, self.icon, self.tip))
            return 0
        if message == self.taskbar_created:
            self._add_icon()
            return 0
        if message == win32con.WM_CLOSE:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 1))
            win32gui.DestroyWindow(hwnd)
            return 0
        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def _menu(self):
        menu = win32gui.CreatePopupMenu()
        try:
            for command, title in [(self.OPEN, '打开主界面'), (self.HIDE, '隐藏主界面'),
                                   (self.TOOLS, '便签与提醒'),
                                   (self.PET, '收起桌面小猫' if self.pet_visible else '显示桌面小猫'),
                                   (self.TOGGLE, '恢复统计' if self.paused else '暂停统计')]:
                win32gui.AppendMenu(menu, win32con.MF_STRING, command, title)
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, '')
            win32gui.AppendMenu(menu, win32con.MF_STRING, self.EXIT, '退出软件')
            x, y = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(menu, win32con.TPM_RIGHTBUTTON, x, y, 0, self.hwnd, None)
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(menu)

    def update(self, nickname, paused, count):
        tip = f'{APP_NAME} · {nickname} · {"已暂停" if paused else "正在记录"} · 今日 {count:,} 次'[:120]
        self.paused = paused
        if tip != self.tip:
            self.tip = tip
            if self.hwnd:
                win32gui.PostMessage(self.hwnd, self.UPDATE, 0, 0)

    def stop(self):
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        self.thread.join(timeout=3)
