"""Exercise the packaged EXE with isolated local-user data and native messages."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import win32con
import win32gui
from tracker import Store
from branding import APP_NAME
from model_library import ModelLibrary


def windows(predicate):
    result = []
    win32gui.EnumWindows(lambda hwnd, unused: result.append(hwnd) if predicate(hwnd) else None, None)
    return result


def wait_for(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError('Timed out waiting for expected packaged-app state')


def main():
    exe = Path(f'dist/{APP_NAME}.exe').resolve()
    previous = set(windows(lambda hwnd: win32gui.GetClassName(hwnd).startswith('ClickBreakTray-')))
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, PROGRAMDATA=directory, LOCALAPPDATA=str(Path(directory) / 'user'))
        # Launch with a downloaded skin to verify bundled images as well as the UI.
        fixture = Store(Path(directory) / 'ClickBreak' / 'data' / 'clicks.sqlite3')
        fixture.set('pet_style', next(iter(ModelLibrary(Path(directory) / 'ClickBreak' / 'data').models)))
        fixture.close()
        process = subprocess.Popen([str(exe)], env=env)
        tray = None
        try:
            tray = wait_for(lambda: windows(lambda hwnd: hwnd not in previous and
                               win32gui.GetClassName(hwnd).startswith('ClickBreakTray-')))[0]
            child_pid = win32gui.GetClassName(tray).split('-')[1]
            import win32process
            def visible_main():
                return windows(lambda hwnd: win32process.GetWindowThreadProcessId(hwnd)[1] == int(child_pid)
                               and win32gui.IsWindowVisible(hwnd)
                               and win32gui.GetWindowText(hwnd).startswith(APP_NAME + ' · 作者'))
            def visible_pet():
                return windows(lambda hwnd: win32process.GetWindowThreadProcessId(hwnd)[1] == int(child_pid)
                               and win32gui.IsWindowVisible(hwnd)
                               and win32gui.GetWindowText(hwnd) == APP_NAME + ' · 桌面宠物')
            wait_for(visible_pet)
            assert not visible_main(), 'Main window unexpectedly visible on startup'
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1005, 0)
            wait_for(lambda: not visible_pet())
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1005, 0)
            wait_for(visible_pet)
            assert not visible_main(), 'Toggling pet unexpectedly opened the main window'
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1001, 0)
            main_window = wait_for(visible_main)[0]
            win32gui.PostMessage(main_window, win32con.WM_CLOSE, 0, 0)
            wait_for(lambda: not visible_main())
            assert visible_pet(), 'Closing main window unexpectedly hid the desktop pet'
            assert process.poll() is None, 'Closing window incorrectly exited the app'
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1001, 0)
            wait_for(visible_main)
            database = Path(directory) / 'ClickBreak' / 'data' / 'clicks.sqlite3'
            store = Store(database)
            store.add_note('打包测试便签', '这是一条隔离测试记录。')
            reminder_id = store.add_reminder('打包测试提醒', time.time() - 1)
            store.close()
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1006, 0)
            wait_for(lambda: windows(lambda hwnd: win32process.GetWindowThreadProcessId(hwnd)[1] == int(child_pid)
                                      and win32gui.IsWindowVisible(hwnd)
                                      and win32gui.GetWindowText(hwnd) == APP_NAME + ' · 小提醒'))
            win32gui.SendMessage(tray, win32con.WM_COMMAND, 1004, 0)
            assert process.wait(timeout=10) == 0
            assert database.exists(), 'Missing machine-wide database'
            store = Store(database)
            assert store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert store.get('device_id')
            assert store.notes()[0][1] == '打包测试便签'
            assert store.due_reminders()[0][0] == reminder_id
            store.close()
            print('PASS: branded EXE; hidden main; pet; tools route; reminder popup; note persistence; pending reminder survives exit.')
        finally:
            if process.poll() is None:
                if tray and win32gui.IsWindow(tray):
                    win32gui.PostMessage(tray, win32con.WM_COMMAND, 1004, 0)
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
