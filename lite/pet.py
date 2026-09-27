"""Original round-faced pixel cat and transparent Windows desktop companion."""
import math
import json
import random
import time
import tkinter as tk
import win32api
import win32con
import win32gui
from branding import APP_NAME, set_icon

THEMES = {
    '奶油橘': ('#f8dda8', '#f4bd79', '#de9470'),
    '薄荷绿': ('#dbeacb', '#aecda3', '#79a987'),
    '香芋紫': ('#e5dcf1', '#c8b5df', '#9b89ba'),
    '蜜桃粉': ('#f8dadd', '#e8b2bc', '#cd8d9f'),
    '云朵白': ('#f6f4e9', '#d8dcd8', '#9dafad'),
    '夜空蓝': ('#b9d0e5', '#91acc9', '#71849e'),
}
from cat_skins import STYLES, draw_cat
DEFAULT_PHRASES = []
INVITATIONS = ('摸摸我呀～', '休息一下，陪我玩会儿？', '喵～我在这里！', '伸个懒腰吧～')


def parse_phrases(value):
    rows = list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))
    if len(rows) > 50 or any(len(line) > 24 for line in rows):
        raise ValueError('最多 50 句，每句不超过 24 个字。')
    return rows


def load_phrases(store):
    try:
        rows = json.loads(store.get('pet_phrases', '[]'))
        return [row for row in rows if isinstance(row, str) and row.strip()][:50] or list(DEFAULT_PHRASES)
    except (ValueError, TypeError):
        return list(DEFAULT_PHRASES)
INK = '#4b5145'
KEY = '#ff00ff'


def clamp_position(x, y, width, height, work):
    left, top, right, bottom = work
    return max(left, min(x, right - width)), max(top, min(y, bottom - height))


class DesktopPet:
    WIDTH, HEIGHT = 250, 264

    def __init__(self, root, store, open_main, toggle_pause, status_provider, quit_app):
        self.root, self.store = root, store
        self.open_main, self.toggle_pause = open_main, toggle_pause
        self.status_provider, self.quit_app = status_provider, quit_app
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title(f'{APP_NAME} · 桌面宠物')
        set_icon(self.window)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-toolwindow', True)
        self.window.attributes('-transparentcolor', KEY)
        self.window.configure(bg=KEY)
        self.canvas = tk.Canvas(self.window, width=self.WIDTH, height=self.HEIGHT,
                                bg=KEY, highlightthickness=0, cursor='hand2')
        self.canvas.pack()
        self.timer = None
        self.closed = False
        self.drag = None
        self.menu = None
        self.moved = False
        self.phase = 0
        self.tap_until = 0
        self.happy_until = 0
        self.last_click = time.monotonic()
        self.side = 'left'
        self.theme = store.get('pet_theme', '奶油橘')
        self.style = store.get('pet_style', '经典围巾')
        self.phrases = load_phrases(store)
        self.phrase_index = 0
        self.phrase_until = time.monotonic() + 20
        self.speech = ''
        self.speech_until = 0
        self.proactive = store.get('pet_proactive', '1') == '1'
        self.next_invitation = time.monotonic() + random.uniform(60, 100)
        self.invitation_index = -1
        self.inviting_until = 0
        self.visible = False
        self._restore_position()
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<Button-3>', self.popup)
        self.window.protocol('WM_DELETE_WINDOW', self.hide)
        if store.get('pet_visible', '1') == '1':
            self.show(persist=False)

    def work_area(self, point=None):
        monitor = win32api.MonitorFromPoint(point or win32api.GetCursorPos(), 2)
        return win32api.GetMonitorInfo(monitor)['Work']

    def _restore_position(self):
        work = self.work_area()
        try:
            x = int(self.store.get('pet_x', str(work[2] - self.WIDTH - 30)))
            y = int(self.store.get('pet_y', str(work[3] - self.HEIGHT - 10)))
        except ValueError:
            x, y = work[2] - self.WIDTH - 30, work[3] - self.HEIGHT - 10
        # An unplugged monitor must not strand the pet off-screen.
        x, y = clamp_position(x, y, self.WIDTH, self.HEIGHT, self.work_area((x, y)))
        self.window.geometry(f'{self.WIDTH}x{self.HEIGHT}')
        self.move_to(x, y)

    def move_to(self, x, y):
        self.window.update_idletasks()
        hwnd = win32gui.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        win32gui.SetWindowPos(hwnd, 0, x, y, self.WIDTH, self.HEIGHT,
                             win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER)

    def show(self, persist=True):
        if self.closed:
            return
        if persist:
            self.store.set('pet_visible', '1')
        self.visible = True
        self.next_invitation = time.monotonic() + random.uniform(60, 100)
        self.window.deiconify()
        self.window.lift()
        if self.timer is None:
            self.animate()

    def hide(self):
        self.store.set('pet_visible', '0')
        self.visible = False
        self.window.withdraw()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None

    def toggle(self):
        self.hide() if self.visible else self.show()

    def react(self, button):
        self.side = 'right' if button == 'right' else 'left'
        self.last_click = time.monotonic()
        self.tap_until = self.last_click + .3

    def pet(self):
        self.happy_until = time.monotonic() + 2
        if time.monotonic() < self.inviting_until:
            self.say('呼噜～谢谢你陪我！', 4)
            self.inviting_until = 0
            self.next_invitation = time.monotonic() + random.uniform(90, 150)

    def say(self, sentence, seconds=6):
        self.speech = sentence[:24]
        self.speech_until = time.monotonic() + seconds

    def toggle_proactive(self):
        self.proactive = not self.proactive
        self.store.set('pet_proactive', '1' if self.proactive else '0')
        self.inviting_until = 0
        self.next_invitation = time.monotonic() + random.uniform(60, 100)
        if not self.proactive and self.speech in INVITATIONS:
            self.speech_until = 0

    def reload_phrases(self):
        self.phrases = load_phrases(self.store)
        self.phrase_index = 0

    def press(self, event):
        self.drag = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())
        self.moved = False

    def move(self, event):
        if not self.drag:
            return
        px, py, x, y = self.drag
        dx, dy = event.x_root - px, event.y_root - py
        if abs(dx) + abs(dy) > 4:
            self.moved = True
        if self.moved:
            x, y = clamp_position(x + dx, y + dy, self.WIDTH, self.HEIGHT,
                                   self.work_area((event.x_root, event.y_root)))
            self.move_to(x, y)

    def release(self, event):
        if self.moved:
            self.store.set('pet_x', self.window.winfo_x())
            self.store.set('pet_y', self.window.winfo_y())
        else:
            self.pet()
        self.drag = None

    def popup(self, event):
        if self.menu:
            self.menu.destroy()
        menu = tk.Menu(self.window, tearoff=False, font=('Microsoft YaHei UI', 10))
        self.menu = menu
        menu.add_command(label='打开主界面', command=self.open_main)
        menu.add_command(label='摸摸小猫', command=self.pet)
        menu.add_command(label=f'主动互动：{"开" if self.proactive else "关"}', command=self.toggle_proactive)
        menu.add_command(label='暂停 / 恢复统计', command=self.toggle_pause)
        colors = tk.Menu(menu, tearoff=False)
        for theme in THEMES:
            colors.add_command(label=theme, command=lambda name=theme: self.set_theme(name))
        menu.add_cascade(label='配色', menu=colors)
        styles = tk.Menu(menu, tearoff=False)
        for style in STYLES:
            styles.add_command(label=style, command=lambda name=style: self.set_style(name))
        menu.add_cascade(label='选择皮肤', menu=styles)
        models = tk.Menu(menu,tearoff=False)
        for key, model in self.root.model_library.models.items():
            models.add_command(label=model['name'],command=lambda name=key:self.set_style(name))
        menu.add_cascade(label='选择模型',menu=models)
        menu.add_separator()
        menu.add_command(label='收起小猫（可从托盘找回）', command=self.hide)
        menu.add_command(label='退出软件', command=self.quit_app)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def set_theme(self, theme):
        if theme in THEMES:
            self.store.set('pet_theme', theme)
            self.theme = theme

    def set_style(self, style):
        if style in (*STYLES, *self.root.model_library.models):
            if not style.startswith('model:'): self.root.model_renderer.unload()
            self.store.set('pet_style', style)
            self.style = style

    def animate(self):
        self.timer = None
        if self.closed or not self.visible:
            return
        now = time.monotonic()
        count, paused = self.status_provider()
        if self.proactive and not paused and now >= self.next_invitation:
            if now >= self.speech_until and not self.drag:
                self.invitation_index = (self.invitation_index + 1) % len(INVITATIONS)
                self.say(INVITATIONS[self.invitation_index], 7)
                self.inviting_until = now + 7
                self.tap_until = now + 1.5
                self.side = 'right' if self.side == 'left' else 'left'
                self.next_invitation = now + random.uniform(90, 150)
            else:
                self.next_invitation = now + 10
        state = ('happy' if now < self.happy_until else 'sleep' if paused or (now - self.last_click > 45 and now >= self.tap_until)
                 else 'tap' if now < self.tap_until else 'idle')
        self.phase += .18
        self.canvas.delete('label')
        if self.phrases and now >= self.phrase_until:
            self.phrase_index = (self.phrase_index + 1) % len(self.phrases)
            self.phrase_until = now + 20
        bubble = self.speech if now < self.speech_until else (self.phrases[self.phrase_index] if self.phrases else '')
        if bubble:
            self.canvas.create_rectangle(10, 4, 240, 47, fill='#faf8ed', outline='#dedfcf', tags='label')
            self.canvas.create_text(125, 25, text=bubble, width=215, fill='#597158', font=('Microsoft YaHei UI', 9), tags='label')
        draw_cat(self.canvas, 121, 151, 4, self.theme, self.phase, state, self.side, self.style)
        self.canvas.create_rectangle(48, 238, 202, 263, fill='#e6eddd', outline='', tags='label')
        self.canvas.create_text(125, 250, text=f'{"已暂停" if paused else "今日"}  ·  {count:,} 次',
                                fill='#435d47', font=('Microsoft YaHei UI', 9, 'bold'), tags='label')
        self.timer = self.root.after(100, self.animate)

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.window.destroy()
