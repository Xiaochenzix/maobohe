import csv
from datetime import datetime
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

from tracker import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'clicks.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def record(self, date, button='left'):
        self.store.record([(datetime.fromisoformat(date).timestamp(), button)])

    def test_midnight_buttons_and_restart(self):
        self.record('2026-09-26T23:59:59')
        self.record('2026-09-27T00:00:00', 'right')
        self.record('2026-09-27T00:00:01', 'middle')
        self.record('2026-09-27T00:00:02', 'right')
        self.assertEqual(self.store.days(), [('2026-09-27', 0, 2, 1, 3), ('2026-09-26', 1, 0, 0, 1)])
        self.assertEqual(self.store.hourly('2026-09-27')[0], 3)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(sum(row[4] for row in self.store.days()), 4)

    def test_streak_empty_today_and_gap(self):
        self.assertEqual(self.store.streak('2026-09-27'), 0)
        for day in (24, 25, 26):
            self.record(f'2026-09-{day}T12:00:00')
        self.assertEqual(self.store.streak('2026-09-27'), 3)
        self.assertEqual(self.store.streak('2026-09-28'), 0)
        self.record('2026-09-27T12:00:00')
        self.assertEqual(self.store.streak('2026-09-27'), 4)

    def test_csv_and_preferences(self):
        self.store.set('nickname', '中文名字')
        self.assertEqual(self.store.get('nickname'), '中文名字')
        self.record('2026-09-27T12:00:00')
        path = Path(self.temp.name) / 'export.csv'
        self.store.export(path)
        with path.open(encoding='utf-8-sig', newline='') as source:
            rows = list(csv.reader(source))
        self.assertEqual(rows[0], ['日期', '左键', '右键', '中键', '总点击次数'])
        self.assertEqual(rows[1], ['2026-09-27', '1', '0', '0', '1'])

    def test_rename_keeps_one_device_and_history(self):
        self.store.initialize_profile('电脑 A')
        device = self.store.get('device_id')
        self.record('2026-09-27T12:00:00')
        self.store.set('nickname', '小王')
        self.store.initialize_profile('不同 Windows 用户')
        self.store.set('nickname', '小李')
        self.assertEqual(self.store.get('nickname'), '小李')
        self.assertEqual(self.store.get('device_id'), device)
        self.assertEqual(self.store.days()[0][4], 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM settings WHERE key='nickname'").fetchone()[0], 1)

    def test_legacy_migrates_once_without_merging_other_users(self):
        legacy_path = Path(self.temp.name) / 'legacy.sqlite3'
        legacy = Store(legacy_path)
        legacy.set('nickname', '原来的昵称')
        legacy.record([(time.time(), 'left')])
        legacy.close()
        self.store.initialize_profile('电脑 A', legacy_path)
        self.assertEqual(self.store.get('nickname'), '原来的昵称')
        self.assertEqual(self.store.days()[0][4], 1)
        legacy = Store(legacy_path)
        legacy.set('nickname', '其他用户')
        legacy.record([(time.time(), 'right')])
        legacy.close()
        self.store.initialize_profile('电脑 B', legacy_path)
        self.assertEqual(self.store.get('nickname'), '原来的昵称')
        self.assertEqual(self.store.days()[0][4], 1)

    def test_notes_survive_restart_and_delete_only_selected(self):
        first = self.store.add_note('甲', '内容 A')
        second = self.store.add_note('乙', '内容 B')
        self.store.save_note(first, '改名后的便签', '第一行\n第二行')
        self.store.close()
        self.store = Store(self.path)
        notes = {row[0]: row for row in self.store.notes()}
        self.assertEqual(notes[first][1:3], ('改名后的便签', '第一行\n第二行'))
        self.store.delete_note(second)
        self.assertEqual([row[0] for row in self.store.notes()], [first])

    def test_reminder_overdue_restart_snooze_and_completion(self):
        reminder = self.store.add_reminder('记得喝水', 100)
        self.assertEqual(self.store.due_reminders(99), [])
        self.assertEqual(self.store.due_reminders(100)[0][0], reminder)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.due_reminders(200)[0][4], 'ringing')
        self.store.acknowledge_reminder(reminder, now=200, snooze_minutes=5)
        self.assertEqual(self.store.due_reminders(499), [])
        self.assertEqual(self.store.due_reminders(500)[0][0], reminder)
        self.store.acknowledge_reminder(reminder, now=500)
        self.assertEqual(self.store.due_reminders(999), [])
        self.assertEqual(self.store.reminders()[0][4], 'done')

    def test_repeating_reminder_acknowledgement_is_idempotent(self):
        reminder = self.store.add_reminder('活动一下', 100, 10)
        self.store.due_reminders(1000)
        self.store.acknowledge_reminder(reminder, now=1000)
        self.assertEqual(self.store.reminders()[0][2], 1600)
        self.store.acknowledge_reminder(reminder, now=1100)
        self.assertEqual(self.store.reminders()[0][2], 1600)
        self.assertEqual(self.store.due_reminders(1600)[0][0], reminder)
        self.store.delete_reminder(reminder)
        self.assertEqual(self.store.due_reminders(2000), [])


class WindowsTests(unittest.TestCase):
    def test_phrase_password_blocks_changes_and_relocks_after_save(self):
        import tkinter as tk
        import json
        from app import App
        from phrase_access import verify_phrase_password
        self.assertTrue(verify_phrase_password('xiaochen123'))
        self.assertFalse(verify_phrase_password('wrong'))
        self.assertFalse(verify_phrase_password(None))
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, directory, preview=True)
            try:
                app.show('petroom')
                original = app.phrase_editor.get('1.0', 'end-1c')
                self.assertEqual(app.phrase_editor.cget('state'), 'disabled')
                with patch('app.simpledialog.askstring', return_value=None):
                    app.save_phrases()
                self.assertEqual(app.store.get('pet_phrases'), '')
                with patch('app.simpledialog.askstring', return_value='wrong'), patch('app.messagebox.showwarning') as warning:
                    app.reset_phrases()
                    warning.assert_called_once()
                self.assertEqual(app.phrase_editor.get('1.0', 'end-1c'), original)
                self.assertFalse(app.phrase_unlocked)
                with patch('app.simpledialog.askstring', return_value='xiaochen123') as prompt:
                    self.assertTrue(app.unlock_phrases())
                    self.assertEqual(prompt.call_args.kwargs['show'], '*')
                app.phrase_editor.delete('1.0', 'end')
                app.phrase_editor.insert('1.0', '只写我喜欢的话\n记得喝水')
                with patch('app.messagebox.showinfo'):
                    app.save_phrases()
                self.assertEqual(json.loads(app.store.get('pet_phrases')), ['只写我喜欢的话', '记得喝水'])
                self.assertFalse(app.phrase_unlocked)
                self.assertEqual(app.phrase_editor.cget('state'), 'disabled')
                with patch('app.simpledialog.askstring', return_value='wrong'), patch('app.messagebox.showwarning'):
                    app.save_phrases()
                self.assertEqual(json.loads(app.store.get('pet_phrases')), ['只写我喜欢的话', '记得喝水'])
                with patch('app.simpledialog.askstring', return_value='xiaochen123'):
                    app.unlock_phrases()
                app.show('overview')
                app.show('petroom')
                self.assertFalse(app.phrase_unlocked)
                app.start_tray()
                with patch('app.simpledialog.askstring', return_value='xiaochen123'):
                    app.unlock_phrases()
                app.hide_window()
                self.assertFalse(app.phrase_unlocked)
                self.assertEqual(app.phrase_editor.cget('state'), 'disabled')
            finally:
                app.close()

    def test_notes_navigation_pinning_and_reminder_popup_without_main(self):
        import tkinter as tk
        from app import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, directory, preview=True)
            try:
                app.show('tools')
                pane = app.tools.pane
                pane.new_note()
                note_id = pane.note_id
                pane.note_title.set('自动保存测试')
                pane.note_body.insert('1.0', '切换页面前也需要保存。')
                pane.pin_note()
                self.assertTrue(app.tools.stickies[note_id].window.winfo_exists())
                app.show('overview')
                self.assertEqual(app.store.notes()[0][1:3], ('自动保存测试', '切换页面前也需要保存。'))
                app.store.add_reminder('到点了', time.time() - 1)
                app.tools.poll()
                root.update()
                self.assertTrue(app.tools.alert.winfo_viewable())
                self.assertEqual(root.state(), 'withdrawn')
                app.tools.finish_alert()
                self.assertEqual(app.store.reminders()[0][4], 'done')
                self.assertIsNone(app.tools.alert)
            finally:
                app.close()

    def test_pet_styles_and_custom_speech(self):
        import tkinter as tk
        import json
        from app import App
        from pet import STYLES, parse_phrases, load_phrases
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, directory, preview=True)
            try:
                app.start_pet()
                for style in STYLES:
                    app.pet.set_style(style)
                    app.pet.animate()
                    self.assertEqual(app.store.get('pet_style'), style)
                from pet import draw_cat
                for style in STYLES[6:]:
                    for state in ('idle', 'tap', 'happy', 'sleep'):
                        for side in ('left', 'right'):
                            draw_cat(app.pet.canvas, 121, 151, 4, phase=1, state=state, side=side, style=style)
                            self.assertTrue(app.pet.canvas.find_withtag('cat'))
                from bongo_skins import layer
                self.assertNotEqual(layer('paw-left.png').tobytes(), layer('paw-left.png', True).tobytes())
                self.assertNotEqual(layer('paw-right.png').tobytes(), layer('paw-right.png', True).tobytes())
                rows = parse_phrases('你好，小猫\n\n记得喝水\n你好，小猫')
                self.assertEqual(rows, ['你好，小猫', '记得喝水'])
                app.store.set('pet_phrases', json.dumps(rows))
                app.pet.reload_phrases()
                self.assertEqual(app.pet.phrases, rows)
                with self.assertRaises(ValueError):
                    parse_phrases('猫' * 25)
                app.store.set('pet_phrases', 'invalid json')
                self.assertEqual(load_phrases(app.store), [])
                app.pet.reload_phrases()
                app.pet.animate()
                app.show('petroom')
                app.try_phrase()  # Empty speech must not index an empty list.
            finally:
                app.close()

    def test_pet_remains_independent_and_clicks_are_not_double_counted(self):
        import tkinter as tk
        from app import App
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, directory, preview=True)
            app.start_pet()
            pet = app.pet
            try:
                root.update()
                self.assertEqual(root.state(), 'withdrawn')
                self.assertTrue(pet.window.winfo_viewable())
                app.events.put((time.time(), 'left'))
                app.events.put((time.time(), 'right'))
                app.collect_events()
                self.assertEqual(pet.side, 'right')
                self.assertGreater(pet.tap_until, time.monotonic())
                self.assertEqual(app.pet_count, 2)
                app.flush()
                app.flush()
                self.assertEqual(app.data()[1][4], 2)
                pet.set_theme('香芋紫')
                self.assertEqual(app.store.get('pet_theme'), '香芋紫')
                pet.hide()
                root.update()
                self.assertFalse(pet.window.winfo_viewable())
                self.assertEqual(app.store.get('pet_visible'), '0')
                self.assertIsNone(pet.timer)
                app.events.put((time.time(), 'middle'))
                app.flush()
                self.assertEqual(app.data()[1][4], 3)
                pet.show()
                root.update()
                x, y = pet.window.winfo_x(), pet.window.winfo_y()
                pet.press(SimpleNamespace(x_root=x + 100, y_root=y + 100))
                pet.move(SimpleNamespace(x_root=x + 80, y_root=y + 80))
                root.update()
                pet.release(None)
                self.assertTrue(pet.moved)
                self.assertEqual(int(app.store.get('pet_x')), pet.window.winfo_x())
                self.assertEqual(int(app.store.get('pet_y')), pet.window.winfo_y())
                self.assertEqual(root.state(), 'withdrawn')
            finally:
                app.close()
            self.assertIsNone(pet.timer)

    def test_pet_stays_inside_monitor_work_area(self):
        from pet import clamp_position
        self.assertEqual(clamp_position(2000, 1200, 230, 236, (0, 0, 1920, 1040)), (1690, 804))
        self.assertEqual(clamp_position(-3000, -500, 230, 236, (-1920, 0, 0, 1040)), (-1920, 0))
        self.assertEqual(clamp_position(-500, 100, 230, 236, (-1920, 0, 0, 1040)), (-500, 100))

    def test_one_profile_per_computer_across_windows_users(self):
        from app import default_data_dir
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ('computer-a', 'computer-b')]
            for index, root in enumerate(roots):
                with patch.dict('os.environ', {'PROGRAMDATA': str(root), 'LOCALAPPDATA': str(root / 'user-a')}):
                    self.assertEqual(default_data_dir(), root / 'ClickBreak' / 'data')
                    store = Store(default_data_dir() / 'clicks.sqlite3')
                    store.initialize_profile('默认名称')
                    store.set('nickname', f'用户{index}')
                    store.record([(time.time(), 'left')] * (index + 1))
                    store.close()
                with patch.dict('os.environ', {'PROGRAMDATA': str(root), 'LOCALAPPDATA': str(root / 'user-b')}):
                    store = Store(default_data_dir() / 'clicks.sqlite3')
                    store.initialize_profile('另一个用户')
                    self.assertEqual(store.get('nickname'), f'用户{index}')
                    self.assertEqual(store.days()[0][4], index + 1)
                    store.close()

    def test_machine_directory_grants_inherited_modify_to_local_users(self):
        from machine_profile import prepare_machine_storage
        import win32security
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'PROGRAMDATA': directory}):
                folder = prepare_machine_storage()
                self.assertEqual(prepare_machine_storage(), folder)
                database = folder / 'clicks.sqlite3'
                store = Store(database)
                store.close()
                descriptor = win32security.GetFileSecurity(str(database), win32security.DACL_SECURITY_INFORMATION)
                acl = descriptor.GetSecurityDescriptorDacl()
                user_aces = [acl.GetAce(i) for i in range(acl.GetAceCount())
                             if win32security.ConvertSidToStringSid(acl.GetAce(i)[2]) == 'S-1-5-32-545']
                self.assertTrue(user_aces)
                self.assertEqual(user_aces[0][1] & 0x1301bf, 0x1301bf)

    def test_real_tray_hidden_counting_open_hide_and_exit(self):
        import tkinter as tk
        import win32con
        import win32gui
        from app import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, directory, preview=True)
            app.start_tray()
            tray = app.tray
            try:
                root.update()
                self.assertEqual(root.state(), 'withdrawn')
                self.assertTrue(win32gui.IsWindow(tray.hwnd))
                app.events.put((time.time(), 'left'))
                app.tick()
                self.assertEqual(app.data()[1][4], 1)
                self.assertEqual(root.state(), 'withdrawn')
                # Exercise native tray command routing without moving the user's mouse.
                win32gui.SendMessage(tray.hwnd, win32con.WM_COMMAND, tray.OPEN, 0)
                app.handle_commands()
                root.update()
                self.assertEqual(root.state(), 'normal')
                app.hide_window()  # Same handler as window's X button.
                root.update()
                self.assertEqual(root.state(), 'withdrawn')
                win32gui.SendMessage(tray.hwnd, win32con.WM_COMMAND, tray.OPEN, 0)
                app.handle_commands()
                root.update()
                root.iconify()
                root.update()
                self.assertEqual(root.state(), 'withdrawn')
                app.events.put((time.time(), 'right'))
                win32gui.SendMessage(tray.hwnd, win32con.WM_COMMAND, tray.EXIT, 0)
                app.handle_commands()
                self.assertFalse(tray.thread.is_alive())
                saved = Store(Path(directory) / 'clicks.sqlite3')
                self.assertEqual(saved.days()[0][4], 2)
                saved.close()
            finally:
                if not app.closing:
                    app.close()

    def test_hook_lifecycle_and_hotkey_state(self):
        import ctypes
        from mouse_hook import MouseHook
        hook = MouseHook(queue.SimpleQueue(), queue.SimpleQueue())
        hook.start()
        try:
            self.assertTrue(hook.thread.is_alive())
            ctypes.windll.user32.PostThreadMessageW(hook.thread_id, 0x0312, 1, 0)
            self.assertEqual(hook.commands.get(timeout=3), 'state')
            self.assertFalse(hook.enabled.is_set())
            ctypes.windll.user32.PostThreadMessageW(hook.thread_id, 0x0312, 1, 0)
            self.assertEqual(hook.commands.get(timeout=3), 'state')
            self.assertTrue(hook.enabled.is_set())
        finally:
            hook.stop()
        self.assertFalse(hook.thread.is_alive())

    def test_all_pages_and_close_flush(self):
        import tkinter as tk
        from app import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            app = App(root, directory, preview=True)
            app.events.put((time.time(), 'left'))
            app.events.put((time.time(), 'right'))
            app.tick()
            for page in ('overview', 'petroom', 'tools', 'ranking', 'achievements', 'history', 'settings'):
                app.show(page)
                root.update()
            self.assertEqual(app.data()[1][4], 2)
            app.events.put((time.time(), 'middle'))
            app.close()
            saved = Store(Path(directory) / 'clicks.sqlite3')
            self.assertEqual(saved.days()[0][4], 3)
            saved.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
