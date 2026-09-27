import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import time
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from mouse_hook import MouseHook
from tracker import Store
from tray import TrayIcon
from machine_profile import default_data_dir, prepare_machine_storage, legacy_user_database
from pet import DesktopPet, draw_cat, THEMES, STYLES, parse_phrases, load_phrases, DEFAULT_PHRASES
from branding import APP_NAME, AUTHOR, VERSION, set_icon
from toolbox import ToolManager
from phrase_access import verify_phrase_password
from model_library import ModelLibrary
from model_renderer import ModelRenderer

BG = '#f6f7f1'
PANEL = '#ffffff'
SIDEBAR = '#e9eee3'
TEXT = '#2d4235'
MUTED = '#7b8778'
ACCENT = '#3f7856'
BLUE = '#a87a45'
FONT = 'Microsoft YaHei UI'


def label(parent, text='', size=11, color=TEXT, bold=False, bg=None, **kwargs):
    return tk.Label(parent, text=text, font=(FONT, size, 'bold' if bold else 'normal'),
                    fg=color, bg=bg or parent.cget('bg'), **kwargs)


def button(parent, text, command, primary=False):
    return tk.Button(parent, text=text, command=command, font=(FONT, 10, 'bold'),
                     bg=ACCENT if primary else '#e8eddf', fg='#ffffff' if primary else TEXT,
                     activebackground='#538a68' if primary else '#dce5d5',
                     activeforeground='#ffffff' if primary else TEXT, relief='flat', bd=0,
                     cursor='hand2', padx=18, pady=10)


class App:
    def __init__(self, root, data_dir, preview=False, legacy_path=None):
        self.root = root
        # Use the same pixel scale for point fonts and fixed-size layout on high-DPI Windows.
        self.root.tk.call('tk', 'scaling', 96 / 72)
        self.root.title(f'{APP_NAME} · 作者 {AUTHOR}')
        self.root.geometry('1180x850')
        self.root.minsize(1080, 810)
        self.root.configure(bg=BG)
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app.ico'
        self.icon_path = icon
        self.tray = None
        self.pet = None
        self.pet_canvas = None
        self.pet_phase = 0
        self.phrase_unlocked = False
        if icon.exists():
            self.root.iconbitmap(str(icon))
        self.data_dir = Path(data_dir)
        self.store = Store(self.data_dir / 'clicks.sqlite3')
        self.store.initialize_profile(os.environ.get('COMPUTERNAME', '我的电脑')[:20], legacy_path)
        self.model_library = ModelLibrary(self.data_dir)
        self.model_renderer = ModelRenderer(self.model_library)
        self.root.model_library = self.model_library
        self.root.model_renderer = self.model_renderer
        if self.store.get('pet_style', '经典围巾') not in (*STYLES, *self.model_library.models):
            self.store.set('pet_style', '经典围巾')
        self.events = queue.SimpleQueue()
        self.commands = queue.SimpleQueue()
        self.hook = None
        self.paused = False
        self.session = 0
        self.recent = []
        self.page = ''
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.goal = int(self.store.get('goal', '3000'))
        self.nickname = self.store.get('nickname')
        self.closing = False
        self.preview = preview
        self.storage_error = False
        self.pending = []
        self.pet_count = self.data()[1][4]
        self.last_pet_click = 0
        self.last_pet_side = 'left'
        self.tools = ToolManager(root, self.store, self.open_tools, self.pet_reminder)
        self.setup_style()
        self.layout()
        self.show('overview')
        if not preview:
            try:
                self.hook = MouseHook(self.events, self.commands)
                self.hook.start()
            except Exception as error:
                self.paused = True
                self.hook = None
                messagebox.showerror('无法开始统计', str(error), parent=root)
        self.update_status()
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        self.root.bind('<Unmap>', self.on_minimize)
        self.root.after(500, self.tick)
        self.root.after(50, self.pump_clicks)
        self.root.after(140, self.animate_preview)

    def setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background=PANEL, foreground=TEXT, fieldbackground=PANEL,
                        font=(FONT, 11), rowheight=39, borderwidth=0)
        style.configure('Treeview.Heading', background='#eaf0e4', foreground=MUTED,
                        font=(FONT, 10), relief='flat', padding=10)
        style.map('Treeview', background=[('selected', '#d8e6cc')], foreground=[('selected', TEXT)])
        style.configure('Vertical.TScrollbar', background='#d3dfcb', troughcolor=PANEL, borderwidth=0)
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background='#e3eadc', foreground=TEXT, font=(FONT, 10), padding=(14, 8))
        style.map('TNotebook.Tab', background=[('selected', PANEL)])

    def layout(self):
        side = tk.Frame(self.root, bg=SIDEBAR, width=200)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        label(side, APP_NAME, 18, ACCENT, True).pack(anchor='w', padx=20, pady=(24, 5))
        label(side, f'作者 {AUTHOR}  /  v{VERSION}', 9, MUTED).pack(anchor='w', padx=24)
        mascot = tk.Canvas(side, width=160, height=110, bg=SIDEBAR, highlightthickness=0)
        mascot.pack(pady=(10, 4))
        draw_cat(mascot, 80, 53, 2.5)
        self.nav = {}
        for key, title in [('overview', '◈   点击统计'), ('petroom', '♡   桌宠小屋'), ('tools', '▣   随手小工具'), ('ranking', '♜   摸鱼排行榜'),
                           ('achievements', '◇   成就收藏室'), ('history', '▤   历史记录'),
                           ('settings', '⚙   偏好设置')]:
            item = button(side, title, lambda name=key: self.show(name))
            item.configure(anchor='w', bg=SIDEBAR)
            item.pack(fill='x', padx=12, pady=4)
            self.nav[key] = item
        foot = tk.Frame(side, bg=SIDEBAR)
        foot.pack(side='bottom', fill='x', padx=22, pady=26)
        main = tk.Frame(self.root, bg=BG)
        main.pack(side='left', fill='both', expand=True, padx=28, pady=25)
        header = tk.Frame(main, bg=BG)
        header.pack(fill='x', pady=(0, 22))
        self.status = label(header, '', 10, ACCENT)
        self.status.pack(side='left')
        self.pause_btn = button(header, '暂停统计 · F8', self.toggle)
        self.pause_btn.pack(side='right')
        button(header, '隐藏到托盘', self.hide_window).pack(side='right', padx=(0, 8))
        self.content = tk.Frame(main, bg=BG)
        self.footer = label(main, '', 9, MUTED, anchor='w')
        self.footer.pack(side='bottom', fill='x', pady=(12, 0))
        self.content.pack(fill='both', expand=True)

    def heading(self, title, subtitle=''):
        label(self.content, title, 25, bold=True).pack(anchor='w')
        if subtitle:
            label(self.content, subtitle, 10, MUTED).pack(anchor='w', pady=(7, 20))
        else:
            tk.Frame(self.content, bg=BG, height=18).pack()

    def show(self, page):
        if not self.tools.prepare_leave():
            return
        self.phrase_unlocked = False
        self.page = page
        self.pet_canvas = None
        for child in self.content.winfo_children():
            child.destroy()
        for key, item in self.nav.items():
            item.configure(bg='#d5e2ca' if key == page else SIDEBAR, fg=ACCENT if key == page else MUTED)
        getattr(self, 'build_' + page)()
        self.refresh()

    def panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, **kwargs)

    def build_overview(self):
        hero = tk.Frame(self.content, bg='#edf1df', height=176)
        hero.pack(fill='x', pady=(0, 18))
        hero.pack_propagate(False)
        copy = tk.Frame(hero, bg='#edf1df')
        copy.pack(side='left', padx=24, pady=20)
        label(copy, '点击统计', 25, bold=True).pack(anchor='w', pady=(8, 6))
        label(copy, f'昵称：{self.nickname}', 10, MUTED).pack(anchor='w')
        self.pet_canvas = tk.Canvas(hero, width=222, height=168, bg='#edf1df', highlightthickness=0)
        self.pet_canvas.pack(side='right', padx=25)
        self.draw_preview()
        cards = tk.Frame(self.content, bg=BG)
        cards.pack(fill='x')
        self.stats_labels = {}
        for i, (key, title, suffix) in enumerate([
            ('today', '今日点击', '从今日 00:00 开始'), ('session', '本次启动', '本次软件运行期间'),
            ('total', '累计点击', ''), ('streak', '连续活跃', '天 · 有点击即算活跃')]):
            cards.columnconfigure(i, weight=1, uniform='cards')
            card = self.panel(cards)
            card.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 6, 0 if i == 3 else 6))
            label(card, title, 10, MUTED).pack(anchor='w', padx=18, pady=(12, 1))
            value = label(card, '0', 27, ACCENT if i == 0 else TEXT, True)
            value.pack(anchor='w', padx=18)
            self.stats_labels[key] = value
            label(card, suffix, 8, MUTED).pack(anchor='w', padx=18, pady=(3, 12))
        goal = self.panel(self.content)
        goal.pack(fill='x', pady=12)
        row = tk.Frame(goal, bg=PANEL)
        row.pack(fill='x', padx=20, pady=(16, 8))
        label(row, '今日小目标', 11, bold=True).pack(side='left')
        self.goal_text = label(row, '', 10, ACCENT)
        self.goal_text.pack(side='right')
        self.progress = tk.Canvas(goal, height=8, bg=PANEL, highlightthickness=0)
        self.progress.pack(fill='x', padx=20)
        self.breakdown = label(goal, '', 9, MUTED)
        self.breakdown.pack(anchor='w', padx=20, pady=(10, 15))
        chart_panel = self.panel(self.content)
        chart_panel.pack(fill='both', expand=True)
        chart_header = tk.Frame(chart_panel, bg=PANEL)
        chart_header.pack(fill='x', padx=20, pady=(17, 0))
        label(chart_header, '每小时点击', 12, bold=True).pack(side='left')
        self.rate_label = label(chart_header, '', 9, BLUE)
        self.rate_label.pack(side='right')
        self.chart = tk.Canvas(chart_panel, bg=PANEL, highlightthickness=0, height=170)
        self.chart.pack(fill='both', expand=True, padx=16, pady=(10, 12))
        self.chart.bind('<Configure>', lambda event: self.draw_chart())
        self.progress.bind('<Configure>', lambda event: self.draw_progress())

    def build_petroom(self):
        self.heading('桌宠小屋', '')
        scene = tk.Frame(self.content, bg='#eef1e2', height=240)
        scene.pack(fill='x')
        scene.pack_propagate(False)
        self.pet_canvas = tk.Canvas(scene, bg='#eef1e2', highlightthickness=0, width=250, height=218)
        self.pet_canvas.pack(side='left', padx=30, pady=16)
        words = tk.Frame(scene, bg='#eef1e2')
        words.pack(side='left', fill='both', expand=True, pady=22)
        label(words, '桌面宠物', 23, bold=True).pack(anchor='w')
        label(words, '点击触发动画 · 空闲切换睡姿\n拖动调整位置 · 右键打开菜单', 10, MUTED, justify='left').pack(anchor='w')
        button(words, '显示 / 收起桌面小猫', self.toggle_pet, True).pack(anchor='w', pady=(20, 0))
        tabs = ttk.Notebook(self.content)
        tabs.pack(fill='both', expand=True, pady=(16, 0))
        wardrobe = tk.Frame(tabs, bg=BG)
        speech = tk.Frame(tabs, bg=BG)
        tabs.add(wardrobe, text='  宠物皮肤  ')
        tabs.add(speech, text='  小猫语句  ')
        models = tk.Frame(tabs, bg=BG)
        tabs.add(models, text='  模型管理  ')
        self.build_models(models)
        label(wardrobe, '选择皮肤', 12, bold=True).pack(anchor='w', pady=(12, 8))
        skin_tabs = ttk.Notebook(wardrobe)
        skin_tabs.pack(fill='x')
        for title, choices in [('原版像素猫', STYLES[:6]), ('Bongo Cat', STYLES[6:])]:
            styles = tk.Frame(skin_tabs, bg=BG)
            skin_tabs.add(styles, text='  ' + title + '  ')
            for i, style in enumerate(choices):
                button(styles, style, lambda name=style: self.set_pet_style(name)).grid(row=i // 3, column=i % 3, padx=(0, 10), pady=(8, 0), sticky='ew')
                styles.columnconfigure(i % 3, weight=1)
        if self.store.get('pet_style') in STYLES[6:]:
            skin_tabs.select(1)
        label(wardrobe, '原版像素猫配色', 11, bold=True).pack(anchor='w', pady=(5, 8))
        swatches = tk.Frame(wardrobe, bg=BG)
        swatches.pack(fill='x')
        for theme, colors in THEMES.items():
            item = button(swatches, theme, lambda name=theme: self.set_pet_theme(name))
            item.configure(bg=colors[0])
            item.pack(side='left', padx=(0, 7), expand=True, fill='x')
        self.pet_hint = label(wardrobe, '', 10, ACCENT)
        self.pet_hint.pack(anchor='w', pady=(14, 8))
        label(speech, '每行一句，最多 50 句；每句不超过 24 字，约每 20 秒轮换，留空不显示。', 10, MUTED).pack(anchor='w', pady=12)
        self.phrase_editor = tk.Text(speech, height=6, font=(FONT, 11), bg='#fffaf0', fg=TEXT,
                                     wrap='word', relief='flat', padx=12, pady=10)
        self.phrase_editor.pack(fill='both', expand=True)
        self.phrase_editor.insert('1.0', '\n'.join(load_phrases(self.store)))
        self.phrase_editor.configure(state='disabled')
        buttons = tk.Frame(speech, bg=BG)
        buttons.pack(fill='x', pady=10)
        self.phrase_unlock_button = button(buttons, '解锁编辑', self.unlock_phrases)
        self.phrase_unlock_button.pack(side='left', padx=(0, 10))
        self.phrase_save_button = button(buttons, '保存语句', self.save_phrases, True)
        self.phrase_save_button.configure(state='disabled')
        self.phrase_save_button.pack(side='left')
        self.phrase_reset_button = button(buttons, '清空语句', self.reset_phrases)
        self.phrase_reset_button.configure(state='disabled')
        self.phrase_reset_button.pack(side='left', padx=10)
        button(buttons, '预览语句', self.try_phrase).pack(side='left')
        self.draw_preview()

    def unlock_phrases(self):
        if self.phrase_unlocked:
            return True
        password = simpledialog.askstring('验证密码', '输入密码后可以修改小猫语句。', show='*', parent=self.root)
        if password is None:
            return False
        if not verify_phrase_password(password):
            messagebox.showwarning('密码不正确', '请检查密码后重试。', parent=self.root)
            return False
        self.phrase_unlocked = True
        self.phrase_editor.configure(state='normal')
        self.phrase_save_button.configure(state='normal')
        self.phrase_reset_button.configure(state='normal')
        self.phrase_unlock_button.configure(text='已解锁', state='disabled')
        return True

    def lock_phrases(self):
        self.phrase_unlocked = False
        if self.page == 'petroom' and hasattr(self, 'phrase_editor') and self.phrase_editor.winfo_exists():
            self.phrase_editor.configure(state='disabled')
            self.phrase_save_button.configure(state='disabled')
            self.phrase_reset_button.configure(state='disabled')
            self.phrase_unlock_button.configure(text='解锁编辑', state='normal')

    def set_pet_style(self, style):
        if style.startswith('model:'):
            try:
                self.model_renderer.errors.pop(style, None)
                self.model_renderer.load(style)
            except Exception as error:
                messagebox.showerror('模型加载失败', str(error), parent=self.root)
                return False
        else:
            self.model_renderer.unload()
        self.store.set('pet_style', style)
        if self.pet:
            self.pet.set_style(style)
        self.draw_preview()
        self.refresh()
        return True

    def build_models(self, parent):
        actions = tk.Frame(parent,bg=BG)
        actions.pack(fill='x',pady=8)
        button(actions,'导入 ZIP / 模型文件',self.import_model_file).pack(side='left')
        button(actions,'导入文件夹',self.import_model_folder).pack(side='left',padx=8)
        button(actions,'使用选中模型',self.use_selected_model,True).pack(side='left')
        button(actions,'刷新',self.refresh_models).pack(side='left',padx=8)
        self.model_tree = ttk.Treeview(parent,columns=('name','author','kind'),show='headings',height=7)
        for key,title,width in [('name','模型',240),('author','作者',250),('kind','来源',100)]:
            self.model_tree.heading(key,text=title)
            self.model_tree.column(key,width=width,anchor='w')
        scroll = ttk.Scrollbar(parent,orient='vertical',command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        self.model_tree.pack(fill='both',expand=True)
        self.model_tree.bind('<Double-1>',lambda event:self.use_selected_model())
        self.model_status = label(parent,'',9,MUTED)
        self.model_status.pack(side='bottom',anchor='w',pady=6,before=self.model_tree)
        self.refresh_models()

    def refresh_models(self):
        self.model_library.refresh()
        self.model_tree.delete(*self.model_tree.get_children())
        for key,model in self.model_library.models.items():
            self.model_tree.insert('', 'end',iid=key,values=(model['name'],model['author'],'导入' if model['imported'] else '内置'))
        current=self.store.get('pet_style')
        if current in self.model_library.models: self.model_tree.selection_set(current)
        self.model_status.configure(text=f'共 {len(self.model_library.models)} 个模型 · 支持完整的 Cubism 3 / BongoCat 模型包'
                                    + (' · '+self.model_library.errors[0] if self.model_library.errors else ''))

    def use_selected_model(self):
        selected=self.model_tree.selection()
        if selected:
            if self.set_pet_style(selected[0]):
                self.model_status.configure(text='当前模型：'+self.model_library.models[selected[0]]['name'])

    def import_model_file(self):
        path=filedialog.askopenfilename(parent=self.root,title='选择模型包或模型文件',filetypes=[('模型包','*.zip *.model3.json')])
        if path:self.import_model(path)

    def import_model_folder(self):
        path=filedialog.askdirectory(parent=self.root,title='选择包含 .model3.json 的模型文件夹')
        if path:self.import_model(path)

    def import_model(self,path):
        try:
            models=self.model_library.import_package(path)
            self.refresh_models()
            self.model_tree.selection_set(models[0]['id'])
            self.model_tree.see(models[0]['id'])
            self.use_selected_model()
        except Exception as error:
            messagebox.showerror('无法导入模型',str(error),parent=self.root)

    def save_phrases(self):
        if not self.phrase_unlocked and not self.unlock_phrases():
            return
        try:
            phrases = parse_phrases(self.phrase_editor.get('1.0', 'end-1c'))
            self.store.set('pet_phrases', json.dumps(phrases, ensure_ascii=False))
            if self.pet:
                self.pet.reload_phrases()
            self.lock_phrases()
            messagebox.showinfo('语句已保存', '已保存。留空时不显示语句。', parent=self.root)
        except ValueError as error:
            messagebox.showwarning('请检查语句', str(error), parent=self.root)

    def reset_phrases(self):
        if not self.phrase_unlocked and not self.unlock_phrases():
            return
        self.phrase_editor.delete('1.0', 'end')
        self.phrase_editor.insert('1.0', '\n'.join(DEFAULT_PHRASES))

    def try_phrase(self):
        try:
            phrases = (parse_phrases(self.phrase_editor.get('1.0', 'end-1c')) or DEFAULT_PHRASES) if self.phrase_unlocked else load_phrases(self.store)
        except ValueError as error:
            messagebox.showwarning('请检查语句', str(error), parent=self.root)
            return
        self.start_pet()
        self.pet.show()
        if phrases:
            self.pet.say(phrases[0])

    def build_tools(self):
        self.heading('随手小工具', '')
        self.tools.attach(self.content)

    def open_tools(self):
        self.show_window()
        self.show('tools')

    def pet_reminder(self, title):
        if self.pet:
            self.pet.say('提醒：' + title, 10)

    def draw_preview(self):
        if self.pet_canvas is None or not self.pet_canvas.winfo_exists():
            return
        room = self.page == 'petroom'
        theme = self.store.get('pet_theme', '奶油橘')
        state = 'tap' if time.monotonic() - self.last_pet_click < .3 else 'idle'
        draw_cat(self.pet_canvas, 125 if room else 111, 108 if room else 81,
                 4.7 if room else 3.2, theme, self.pet_phase, state, self.last_pet_side,
                 self.store.get('pet_style', '经典围巾'))

    def animate_preview(self):
        if self.closing:
            return
        self.pet_phase += .2
        if self.root.state() != 'withdrawn':
            self.draw_preview()
        self.root.after(140, self.animate_preview)

    def start_pet(self):
        if self.pet is None:
            self.pet = DesktopPet(self.root, self.store, self.show_window, self.toggle,
                                  lambda: (self.pet_count, self.paused or (self.hook is None and not self.preview)), self.close)

    def toggle_pet(self):
        if self.pet is None:
            self.start_pet()
            self.pet.show()
        else:
            self.pet.toggle()
        self.refresh()

    def set_pet_theme(self, theme):
        self.store.set('pet_theme', theme)
        if self.pet:
            self.pet.set_theme(theme)
        self.draw_preview()
        self.refresh()

    def table(self, columns, widths):
        frame = self.panel(self.content)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for name, width in zip(columns, widths):
            tree.heading(name, text=name)
            tree.column(name, width=width, anchor='center', minwidth=65)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        return tree

    def build_ranking(self):
        self.heading('摸鱼排行榜', '本机历史日榜 · 按每天的点击总数排名，同分日期共享名次')
        self.rank_summary = label(self.content, '', 12, ACCENT)
        self.rank_summary.pack(anchor='w', pady=(0, 18))
        self.rank_table = self.table(['排名', '日期', '点击总数', '称号'], [90, 220, 180, 180])

    def build_achievements(self):
        self.heading('成就收藏室', '')
        grid = tk.Frame(self.content, bg=BG)
        grid.pack(fill='both', expand=True)
        self.badges = []
        definitions = [('初来乍到', '累计完成 1 次点击', 'total', 1),
                       ('小试牛刀', '累计完成 1,000 次点击', 'total', 1000),
                       ('点击收藏家', '累计完成 10,000 次点击', 'total', 10000),
                       ('十万次的坚持', '累计完成 100,000 次点击', 'total', 100000),
                       ('今日高光', '任意一天达到 3,000 次', 'best', 3000),
                       ('常来坐坐', '累计活跃 7 天', 'days', 7)]
        for index, (title, description, key, target) in enumerate(definitions):
            grid.columnconfigure(index % 2, weight=1, uniform='badge')
            grid.rowconfigure(index // 2, weight=1)
            frame = self.panel(grid)
            frame.grid(row=index // 2, column=index % 2, sticky='nsew', padx=(0, 12), pady=(0, 12))
            title_label = label(frame, '◇  ' + title, 15, bold=True)
            title_label.pack(anchor='w', padx=20, pady=(18, 7))
            label(frame, description, 10, MUTED).pack(anchor='w', padx=20)
            progress = label(frame, '', 10, MUTED)
            progress.pack(anchor='w', padx=20, pady=(10, 18))
            self.badges.append((title_label, progress, key, target, title))

    def build_history(self):
        self.heading('历史记录', '按日期查看左键、右键和中键的统计，支持导出到 Excel。')
        button(self.content, '导出 CSV', self.export, True).pack(anchor='w', pady=(0, 18))
        self.history_table = self.table(['日期', '左键', '右键', '中键', '总次数'], [190, 115, 115, 115, 150])

    def build_settings(self):
        self.heading('设置', '')
        frame = self.panel(self.content)
        frame.pack(fill='x')
        label(frame, '你的昵称（每台电脑一个）', 11, bold=True).pack(anchor='w', padx=24, pady=(22, 8))
        self.name_entry = tk.Entry(frame, font=(FONT, 12), bg='#edf1e7', fg=TEXT,
                                   insertbackground=TEXT, relief='flat')
        self.name_entry.insert(0, self.nickname)
        self.name_entry.pack(fill='x', padx=24, ipady=9)
        label(frame, '每日点击目标（1—1,000,000）', 11, bold=True).pack(anchor='w', padx=24, pady=(20, 8))
        self.goal_entry = tk.Entry(frame, font=(FONT, 12), bg='#edf1e7', fg=TEXT,
                                   insertbackground=TEXT, relief='flat')
        self.goal_entry.insert(0, str(self.goal))
        self.goal_entry.pack(fill='x', padx=24, ipady=9)
        button(frame, '保存偏好', self.save_settings, True).pack(anchor='w', padx=24, pady=22)
        label(self.content, '使用说明', 13, bold=True).pack(anchor='w', pady=(25, 9))
        info = ('• 软件打开期间统计全局左键、右键和中键按下；双击计为两次。\n'
                '• F8 暂停 / 恢复；关闭或最小化窗口会隐藏到托盘，继续统计。\n'
                '• 点击托盘图标，选择“打开主界面”查看，选择“退出软件”结束。\n'
                '• 便签和提醒在“随手小工具”中，小猫语句在“桌宠小屋”中。')
        label(self.content, info, 10, MUTED, justify='left').pack(anchor='w')
        button(self.content, '打开数据文件夹', self.open_data).pack(anchor='w', pady=(18, 0))

    def data(self):
        days = self.store.days()
        today = next((row for row in days if row[0] == self.today), (self.today, 0, 0, 0, 0))
        return days, today

    def refresh(self):
        days, today = self.data()
        total = sum(row[4] for row in days)
        if self.page == 'petroom':
            shown = self.pet and self.pet.visible
            style = self.store.get('pet_style','经典围巾')
            title = self.model_library.models.get(style,{}).get('name',style)
            self.pet_hint.configure(text=f'当前：{title}  ·  桌面宠物{"已显示" if shown else "已收起"}')
        elif self.page == 'overview':
            for key, value in dict(today=today[4], session=self.session, total=total,
                                   streak=self.store.streak(self.today)).items():
                self.stats_labels[key].configure(text=f'{value:,}')
            ratio = today[4] / self.goal
            self.goal_text.configure(text=f'{today[4]:,} / {self.goal:,} 次  ·  {ratio:.0%}' + ('  ✓ 已达成' if ratio >= 1 else ''))
            self.breakdown.configure(text=f'左键  {today[1]:,}     /     右键  {today[2]:,}     /     中键  {today[3]:,}')
            self.rate_label.configure(text=f'最近 60 秒  {len(self.recent)} 次')
            self.draw_progress()
            self.draw_chart()
        elif self.page == 'ranking':
            ordered = sorted(days, key=lambda row: (-row[4], row[0]))
            rank = 1 + sum(row[4] > today[4] for row in ordered)
            best = ordered[0][4] if ordered else 0
            self.rank_summary.configure(text=f'个人最高纪录  {best:,} 次 / 天     ·     ' + (f'今天暂列第 {rank} 名' if today[4] else '今天还未上榜'))
            rows = []
            last_count, current_rank = None, 0
            for index, row in enumerate(ordered):
                if row[4] != last_count:
                    current_rank = index + 1
                last_count = row[4]
                title = '点击大师' if row[4] >= 10000 else '摸鱼达人' if row[4] >= 3000 else '轻松一下'
                rows.append((f'{current_rank:02}', row[0] + ('  · 今天' if row[0] == self.today else ''), f'{row[4]:,}', title))
            self.fill_table(self.rank_table, rows)
        elif self.page == 'history':
            self.fill_table(self.history_table, [(row[0], *[f'{v:,}' for v in row[1:]]) for row in days])
        elif self.page == 'achievements':
            values = {'total': total, 'best': max([row[4] for row in days], default=0), 'days': len(days)}
            for title_label, progress, key, target, title in self.badges:
                value = values[key]
                done = value >= target
                title_label.configure(text=('◆  ' if done else '◇  ') + title, fg=ACCENT if done else TEXT)
                progress.configure(text='已解锁 ✓' if done else f'{value:,} / {target:,}  ·  待解锁', fg=ACCENT if done else MUTED)

    def fill_table(self, tree, rows):
        # Preserve selection and scroll while counts refresh.
        existing = tree.get_children()
        for i, row in enumerate(rows):
            if i < len(existing):
                tree.item(existing[i], values=row)
            else:
                tree.insert('', 'end', values=row)
        for item in existing[len(rows):]:
            tree.delete(item)

    def draw_progress(self):
        if self.page != 'overview':
            return
        width = self.progress.winfo_width()
        ratio = min(1, self.data()[1][4] / self.goal)
        self.progress.delete('all')
        self.progress.create_rectangle(0, 0, width, 8, fill='#e7ecdf', outline='')
        if ratio:
            self.progress.create_rectangle(0, 0, width * ratio, 8, fill=ACCENT, outline='')

    def draw_chart(self):
        if self.page != 'overview':
            return
        canvas = self.chart
        canvas.delete('all')
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 50:
            return
        values = self.store.hourly(self.today)
        peak = max(values) or 10
        left, top, bottom = 47, 23, height - 30
        plot_height = max(10, bottom - top)
        step = (width - left - 14) / 24
        for fraction in [0, .5, 1]:
            y = bottom - plot_height * fraction
            canvas.create_line(left, y, width - 10, y, fill='#e9eee4')
            canvas.create_text(left - 8, y, anchor='e', text=str(round(peak * fraction)), fill=MUTED, font=(FONT, 8))
        for hour, value in enumerate(values):
            x = left + hour * step + 3
            if value:
                canvas.create_rectangle(x, bottom - value / peak * plot_height, x + max(2, step - 6), bottom,
                                        fill=ACCENT if hour == datetime.now().hour else '#a3bb95', outline='')
            if hour % 3 == 0 or hour == 23:
                canvas.create_text(x + step / 2 - 3, bottom + 17, text=f'{hour:02}:00', fill=MUTED, font=(FONT, 8))
        if not any(values):
            canvas.create_text(width / 2, height / 2 - 5, text='暂无记录', fill=MUTED, font=(FONT, 11))

    def update_status(self):
        if self.preview:
            text, color = '●  界面预览 · 未启用监听', MUTED
        elif self.storage_error:
            text, color = '●  保存失败 · 已暂停，请检查磁盘空间', '#a5672f'
        elif self.hook is None:
            text, color = '●  鼠标监听未启动', '#a5672f'
        elif self.paused:
            text, color = '●  已暂停', '#a5672f'
        else:
            text, color = '●  正在记录   /   ' + self.today, ACCENT
        self.status.configure(text=text, fg=color)
        suffix = ' · F8' if self.hook and self.hook.hotkey_ok else ''
        self.pause_btn.configure(text=('恢复统计' if self.paused else '暂停统计') + suffix,
                                 state='normal' if self.hook and not self.storage_error else 'disabled')

    def toggle(self):
        if self.hook and not self.storage_error:
            self.paused = self.hook.enabled.is_set()
            self.hook.enabled.clear() if self.paused else self.hook.enabled.set()
            self.update_status()

    def start_tray(self):
        tray = TrayIcon(self.commands, self.icon_path)
        try:
            tray.start()
        except Exception:
            tray.stop()
            raise
        self.tray = tray

    def show_window(self):
        self.nickname = self.store.get('nickname', self.nickname)
        self.root.deiconify()
        self.root.lift()
        if self.page == 'overview':
            self.show('overview')
        else:
            self.refresh()

    def hide_window(self):
        self.lock_phrases()
        if self.tray and self.tray.thread.is_alive():
            self.root.withdraw()
        else:
            self.close()

    def on_minimize(self, event):
        if event.widget == self.root and self.tray and self.root.state() == 'iconic':
            self.root.after_idle(self.hide_window)

    def handle_commands(self):
        while not self.commands.empty():
            command = self.commands.get_nowait()
            if command == 'open':
                self.show_window()
            elif command == 'hide':
                self.hide_window()
            elif command == 'toggle':
                self.toggle()
            elif command == 'pet':
                self.toggle_pet()
            elif command == 'tools':
                self.open_tools()
            elif command == 'exit':
                self.close()
                return
            elif command == 'tray_failed':
                self.tray = None
                self.show_window()
                self.footer.configure(text='系统托盘不可用，窗口关闭时将直接退出。')
            elif command == 'state' and self.hook:
                self.paused = not self.hook.enabled.is_set()
                if self.storage_error:
                    self.paused = True
                    self.hook.enabled.clear()

    def collect_events(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            self.pending.append(event)
            self.recent.append(event[0])
            self.session += 1
            self.pet_count += 1
            self.last_pet_click = time.monotonic()
            self.last_pet_side = 'right' if event[1] == 'right' else 'left'
            if self.pet:
                self.pet.react(event[1])

    def pump_clicks(self):
        if self.closing:
            return
        self.collect_events()
        self.root.after(50, self.pump_clicks)

    def flush(self):
        self.collect_events()
        if self.pending:
            try:
                self.store.record(self.pending)
                self.pending.clear()
                self.storage_error = False
            except Exception:
                self.storage_error = True
                self.paused = True
                if self.hook:
                    self.hook.enabled.clear()
        self.recent = [stamp for stamp in self.recent if time.time() - stamp < 60]

    def tick(self):
        if self.closing:
            return
        self.flush()
        self.handle_commands()
        if self.closing:
            return
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.pet_count = self.data()[1][4] + sum(datetime.fromtimestamp(item[0]).strftime('%Y-%m-%d') == self.today for item in self.pending)
        name = self.store.get('nickname', self.nickname)
        if name != self.nickname:
            self.nickname = name
            if self.page == 'overview' and self.root.state() != 'withdrawn':
                self.show('overview')
        self.goal = int(self.store.get('goal', str(self.goal)))
        self.update_status()
        if self.root.state() != 'withdrawn':
            self.refresh()
        if self.tray:
            self.tray.pet_visible = bool(self.pet and self.pet.visible)
            self.tray.update(self.nickname, self.paused or self.hook is None, self.data()[1][4])
        try:
            self.tools.poll()
        except Exception as error:
            self.footer.configure(text=f'小工具暂未保存或更新，将自动重试：{error}')
            self.root.after(1000, self.tick)
            return
        self.footer.configure(text=('数据尚未保存，将自动重试。' if self.storage_error else '')
                              + ('  ·  F8 被其他程序占用，请使用暂停按钮' if self.hook and not self.hook.hotkey_ok else ''))
        self.root.after(1000, self.tick)

    def save_settings(self):
        try:
            goal = int(self.goal_entry.get())
            if not 1 <= goal <= 1000000:
                raise ValueError()
        except ValueError:
            messagebox.showwarning('目标需要是整数', '请输入 1 到 1,000,000 之间的每日点击目标。', parent=self.root)
            return
        name = self.name_entry.get().strip()[:20] or '摸鱼观察员'
        try:
            self.store.set('goal', goal)
            self.store.set('nickname', name)
        except Exception as error:
            messagebox.showerror('保存失败', str(error), parent=self.root)
            return
        self.goal, self.nickname = goal, name
        self.footer.configure(text='偏好已保存 ✓')
        messagebox.showinfo('已保存', '昵称与每日目标已更新。', parent=self.root)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, title='导出历史统计',
                    defaultextension='.csv', initialfile=f'摸鱼统计-{self.today}.csv', filetypes=[('CSV 表格', '*.csv')])
        if path:
            try:
                self.flush()
                self.store.export(path)
                messagebox.showinfo('导出成功', '已导出全部已保存记录，可用 Excel 打开。', parent=self.root)
            except Exception as error:
                messagebox.showerror('导出失败', str(error), parent=self.root)

    def open_data(self):
        os.startfile(str(self.data_dir.resolve()))

    def close(self):
        if self.closing:
            return
        if not self.tools.prepare_leave():
            messagebox.showerror('便签尚未保存', '请先复制便签内容或恢复磁盘写入后再退出。', parent=self.root)
            return
        self.closing = True
        self.model_renderer.close()
        self.tools.close()
        if self.pet:
            self.pet.close()
            self.pet = None
        if self.tray:
            self.tray.stop()
            self.tray = None
        if self.hook:
            self.hook.stop()
        self.flush()
        if self.pending:
            # Keep unsaved events in a recovery file instead of silently discarding them.
            import json
            try:
                (self.data_dir / f'recovery-{time.time_ns()}.json').write_text(json.dumps(self.pending), encoding='utf-8')
                messagebox.showwarning('部分记录尚未入库', '已把未保存点击写入数据文件夹的 recovery 文件。', parent=self.root)
            except Exception as error:
                messagebox.showerror('未能保存记录', f'{len(self.pending)} 次点击未能保存：{error}', parent=self.root)
        self.store.close()
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('此程序目前支持 Windows 10 / 11。')
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('XiaoCheng.UnknownSoftware')
    except Exception:
        pass
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\ClickBreakDesktopV1' + ('Preview' if args.preview else ''))
    duplicate = ctypes.get_last_error() == 183
    root = tk.Tk()
    root.withdraw()
    if duplicate:
        messagebox.showinfo('软件已经运行', f'{APP_NAME}已在运行。请点击右下角系统托盘图标（可能在“^”里），选择“打开主界面”。', parent=root)
        root.destroy()
        return
    try:
        directory = Path(args.data_dir) if args.data_dir else prepare_machine_storage()
        app = App(root, directory, args.preview,
                  legacy_path=None if args.data_dir else legacy_user_database())
    except Exception as error:
        messagebox.showerror('启动失败', f'无法打开本机共用数据，请检查 ProgramData\\ClickBreak 的写入权限与磁盘空间。\n{error}', parent=root)
        root.destroy()
        return
    if args.preview:
        app.show_window()
    else:
        try:
            app.start_tray()
            app.start_pet()
        except Exception as error:
            app.show_window()
            messagebox.showwarning('托盘不可用', f'{error}\n已显示主界面，关闭窗口可退出软件。', parent=root)
    if args.smoke_test:
        def finish_smoke_test():
            (directory / 'smoke-result.json').write_text(json.dumps({
                'version': VERSION, 'models': len(app.model_library.models),
                'selected': app.store.get('pet_style'), 'rendered': app.model_renderer.last_image is not None,
                'model_errors': app.model_renderer.errors,
            },ensure_ascii=False),encoding='utf8')
            app.close()
        root.after(1800, finish_smoke_test)
    root.mainloop()
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
