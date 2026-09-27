"""Local notes, desktop sticky notes, and persistent reminders."""
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk, messagebox
from branding import APP_NAME, AUTHOR, set_icon

BG, FG, GREEN, MUTED = '#f6f7f1', '#2d4235', '#3f7856', '#7b8778'
FONT = 'Microsoft YaHei UI'


def text(parent, value, size=10, color=FG):
    return tk.Label(parent, text=value, bg=parent.cget('bg'), fg=color, font=(FONT, size), anchor='w')


def action(parent, title, command):
    return tk.Button(parent, text=title, command=command, bg='#e2ebda', fg=FG,
                     activebackground='#d0dfc5', relief='flat', padx=12, pady=8,
                     font=(FONT, 10), cursor='hand2')


class StickyNote:
    def __init__(self, manager, note):
        self.manager, self.note_id = manager, note[0]
        self.window = tk.Toplevel(manager.root)
        self.window.title(f'{APP_NAME} · 便签')
        self.window.configure(bg='#fff5cf')
        self.window.geometry('360x320')
        self.window.minsize(280, 230)
        self.window.attributes('-topmost', True)
        set_icon(self.window)
        self.title = text(self.window, note[1], 13)
        self.title.pack(fill='x', padx=18, pady=(15, 8))
        self.body = tk.Text(self.window, wrap='word', font=(FONT, 11), bg='#fff9df', fg=FG,
                            relief='flat', padx=12, pady=12)
        self.body.pack(fill='both', expand=True, padx=14)
        row = tk.Frame(self.window, bg='#fff5cf')
        row.pack(fill='x', padx=14, pady=12)
        action(row, '打开编辑', lambda: manager.edit_note(self.note_id)).pack(side='left')
        action(row, '收起便签', self.close).pack(side='right')
        self.update(note)
        self.window.protocol('WM_DELETE_WINDOW', self.close)

    def update(self, note):
        self.title.configure(text=note[1])
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', note[2])
        self.body.configure(state='disabled')

    def close(self):
        self.manager.stickies.pop(self.note_id, None)
        self.window.destroy()


class ToolManager:
    def __init__(self, root, store, open_tools, on_reminder=None):
        self.root, self.store, self.open_tools = root, store, open_tools
        self.on_reminder = on_reminder
        self.pane = None
        self.stickies = {}
        self.alert = None
        self.alert_id = None

    def prepare_leave(self):
        return not self.pane or not self.pane.winfo_exists() or self.pane.save_note()

    def attach(self, parent):
        self.pane = ToolsPane(parent, self)
        self.pane.pack(fill='both', expand=True)

    def pin(self, note_id):
        note = next((n for n in self.store.notes() if n[0] == note_id), None)
        if not note:
            return
        if note_id in self.stickies:
            self.stickies[note_id].window.lift()
        else:
            self.stickies[note_id] = StickyNote(self, note)

    def edit_note(self, note_id):
        self.open_tools()
        if self.pane:
            self.pane.select_note(note_id)

    def sync_note(self, note_id):
        note = next((n for n in self.store.notes() if n[0] == note_id), None)
        if note and note_id in self.stickies:
            self.stickies[note_id].update(note)

    def poll(self, now=None):
        rows = self.store.due_reminders(now)
        if self.alert and self.alert_id not in {r[0] for r in rows}:
            self.alert.destroy()
            self.alert = None
            self.alert_id = None
        if rows and self.alert is None:
            self.show_alert(rows[0])
        if self.pane and self.pane.winfo_exists():
            self.pane.refresh_reminders()

    def show_alert(self, row):
        self.alert_id = row[0]
        self.alert = tk.Toplevel(self.root)
        self.alert.title(f'{APP_NAME} · 小提醒')
        self.alert.configure(bg=BG)
        self.alert.geometry('430x340')
        self.alert.resizable(False, False)
        self.alert.attributes('-topmost', True)
        set_icon(self.alert)
        text(self.alert, '提醒', 17, GREEN).pack(anchor='w', padx=24, pady=(22, 10))
        tk.Label(self.alert, text=row[1], bg=BG, fg=FG, wraplength=380, justify='left',
                 font=(FONT, 12)).pack(fill='x', padx=24)
        text(self.alert, '计划时间：' + datetime.fromtimestamp(row[2]).strftime('%m-%d %H:%M'), 9, MUTED).pack(anchor='w', padx=24, pady=12)
        bar = tk.Frame(self.alert, bg=BG)
        bar.pack(side='bottom', fill='x', padx=24, pady=20)
        action(bar, '5 分钟后再提醒', lambda: self.finish_alert(5)).pack(side='left')
        action(bar, '知道啦', self.finish_alert).pack(side='right')
        self.alert.protocol('WM_DELETE_WINDOW', lambda: self.finish_alert(5))
        if self.on_reminder:
            self.on_reminder(row[1])

    def finish_alert(self, snooze=0):
        if self.alert_id is None:
            return
        self.store.acknowledge_reminder(self.alert_id, snooze_minutes=snooze)
        self.alert.destroy()
        self.alert = None
        self.alert_id = None

    def close(self):
        for item in list(self.stickies.values()):
            item.close()
        if self.alert:
            self.alert.destroy()
            self.alert = None
        # Ringing reminders intentionally remain pending for the next launch.


class ToolsPane(tk.Frame):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=BG)
        self.manager, self.store = manager, manager.store
        self.note_id = None
        self.loading = False
        self.save_timer = None
        self.signature = None
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        self.note_tab = tk.Frame(self.notebook, bg=BG)
        self.reminder_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.note_tab, text='  便签本  ')
        self.notebook.add(self.reminder_tab, text='  提醒与专注  ')
        self.build_notes()
        self.build_reminders()
        self.bind('<Destroy>', self.destroyed)

    def destroyed(self, event):
        if event.widget == self and self.save_timer:
            self.after_cancel(self.save_timer)
            self.save_timer = None

    def build_notes(self):
        bar = tk.Frame(self.note_tab, bg=BG)
        bar.pack(fill='x', pady=12)
        action(bar, '＋ 新建便签', self.new_note).pack(side='left')
        action(bar, '置顶到桌面', self.pin_note).pack(side='left', padx=8)
        action(bar, '删除便签', self.delete_note).pack(side='right')
        body = tk.Frame(self.note_tab, bg=BG)
        body.pack(fill='both', expand=True)
        self.note_list = tk.Listbox(body, width=23, bg='#eaf0e3', fg=FG, relief='flat',
                                   font=(FONT, 10), selectbackground='#cfdfc0', selectforeground=FG,
                                   exportselection=False, activestyle='none')
        self.note_list.pack(side='left', fill='y', padx=(0, 14))
        self.note_list.bind('<<ListboxSelect>>', self.note_selected)
        editor = tk.Frame(body, bg=BG)
        editor.pack(fill='both', expand=True)
        self.note_title = tk.StringVar()
        self.title_entry = tk.Entry(editor, textvariable=self.note_title, bg='#ffffff', fg=FG,
                                    relief='flat', font=(FONT, 12))
        self.title_entry.pack(fill='x', ipady=10, pady=(0, 10))
        paper = tk.Frame(editor, bg=BG)
        paper.pack(fill='both', expand=True)
        self.note_body = tk.Text(paper, wrap='word', bg='#fffaf0', fg=FG, relief='flat', height=12,
                                 font=(FONT, 11), padx=14, pady=14, undo=True)
        scrollbar = ttk.Scrollbar(paper, orient='vertical', command=self.note_body.yview)
        self.note_body.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.note_body.pack(side='left', fill='both', expand=True)
        self.note_title.trace_add('write', lambda *args: self.dirty())
        self.note_body.bind('<<Modified>>', self.body_changed)
        self.note_status = text(self.note_tab, '', 9, MUTED)
        self.note_status.pack(fill='x', pady=(10, 4))
        self.note_rows = []
        self.refresh_notes()
        if self.note_rows:
            self.select_note(self.note_rows[0][0])
        else:
            self.set_editor_state('disabled')

    def set_editor_state(self, state):
        self.title_entry.configure(state=state)
        self.note_body.configure(state=state)

    def body_changed(self, event):
        if self.note_body.edit_modified():
            self.note_body.edit_modified(False)
            self.dirty()

    def dirty(self):
        if self.loading or self.note_id is None:
            return
        if (self.note_title.get(), self.note_body.get('1.0', 'end-1c')) == self.signature:
            return
        if self.save_timer:
            self.after_cancel(self.save_timer)
        self.note_status.configure(text='正在编辑，稍后自动保存…')
        self.save_timer = self.after(700, self.save_note)

    def save_note(self):
        if self.save_timer:
            self.after_cancel(self.save_timer)
            self.save_timer = None
        if self.note_id is None:
            return True
        values = (self.note_title.get(), self.note_body.get('1.0', 'end-1c'))
        if values == self.signature:
            return True
        try:
            self.store.save_note(self.note_id, *values)
            self.signature = values
            self.refresh_notes()
            self.manager.sync_note(self.note_id)
            self.note_status.configure(text='已自动保存 · ' + datetime.now().strftime('%H:%M:%S'))
            return True
        except Exception as error:
            self.note_status.configure(text=f'保存失败，内容仍在编辑框中：{error}')
            return False

    def refresh_notes(self):
        self.note_rows = self.store.notes()
        self.note_list.delete(0, 'end')
        for index, row in enumerate(self.note_rows):
            self.note_list.insert('end', '  ' + row[1])
            if row[0] == self.note_id:
                self.note_list.selection_set(index)

    def note_selected(self, event):
        selection = self.note_list.curselection()
        if selection and selection[0] < len(self.note_rows):
            self.select_note(self.note_rows[selection[0]][0])

    def select_note(self, note_id):
        if not self.save_note():
            return
        row = next((r for r in self.store.notes() if r[0] == note_id), None)
        if not row:
            return
        self.loading = True
        self.set_editor_state('normal')
        self.note_id = note_id
        self.note_title.set(row[1])
        self.note_body.delete('1.0', 'end')
        self.note_body.insert('1.0', row[2])
        self.note_body.edit_modified(False)
        self.signature = (row[1], row[2])
        self.loading = False
        self.refresh_notes()
        self.notebook.select(self.note_tab)

    def new_note(self):
        if self.save_note():
            self.select_note(self.store.add_note())

    def pin_note(self):
        if self.note_id and self.save_note():
            self.manager.pin(self.note_id)

    def delete_note(self):
        if self.note_id and messagebox.askyesno('删除便签', '确定删除这张便签？', parent=self):
            note_id = self.note_id
            self.note_id = None
            self.store.delete_note(note_id)
            if note_id in self.manager.stickies:
                self.manager.stickies[note_id].close()
            self.refresh_notes()
            if self.note_rows:
                self.select_note(self.note_rows[0][0])
            else:
                self.loading = True
                self.note_title.set('')
                self.note_body.delete('1.0', 'end')
                self.loading = False
                self.set_editor_state('disabled')

    def build_reminders(self):
        quick = tk.Frame(self.reminder_tab, bg=BG)
        quick.pack(fill='x', pady=12)
        for title, minutes in [('5 分钟后喝水', 5), ('专注 25 分钟', 25), ('45 分钟后活动', 45)]:
            action(quick, title, lambda t=title, m=minutes: self.quick_reminder(t, m)).pack(side='left', padx=(0, 10))
        form = tk.Frame(self.reminder_tab, bg='#ffffff')
        form.pack(fill='x', pady=(0, 12))
        text(form, '提醒内容', 10).grid(row=0, column=0, sticky='w', padx=14, pady=10)
        self.reminder_title = tk.Entry(form, font=(FONT, 11), bg='#eef2e8', relief='flat')
        self.reminder_title.grid(row=0, column=1, columnspan=3, sticky='ew', padx=14, ipady=7)
        form.columnconfigure(1, weight=1)
        text(form, '多少分钟后').grid(row=1, column=0, sticky='w', padx=14)
        self.delay = tk.StringVar(value='10')
        tk.Entry(form, textvariable=self.delay, width=9, font=(FONT, 11)).grid(row=1, column=1, sticky='w', padx=14)
        text(form, '重复间隔（分钟，0=不重复）').grid(row=1, column=2, sticky='w')
        self.repeat = tk.StringVar(value='0')
        tk.Entry(form, textvariable=self.repeat, width=8, font=(FONT, 11)).grid(row=1, column=3, padx=14)
        text(form, '或指定时间').grid(row=2, column=0, sticky='w', padx=14, pady=12)
        self.exact = tk.StringVar()
        tk.Entry(form, textvariable=self.exact, width=22, font=(FONT, 10)).grid(row=2, column=1, sticky='w', padx=14)
        text(form, 'YYYY-MM-DD HH:MM（本地时间）', 9, MUTED).grid(row=2, column=2, columnspan=2, sticky='w')
        action(form, '添加提醒', self.add_reminder).grid(row=3, column=1, sticky='w', padx=14, pady=(0, 12))
        self.reminder_tree = ttk.Treeview(self.reminder_tab, columns=('title', 'due', 'repeat', 'state'), show='headings', height=5)
        for name, title, width in [('title', '提醒内容', 290), ('due', '时间', 170), ('repeat', '重复', 90), ('state', '状态', 110)]:
            self.reminder_tree.heading(name, text=title)
            self.reminder_tree.column(name, width=width, minwidth=70)
        scroll = ttk.Scrollbar(self.reminder_tab, orient='vertical', command=self.reminder_tree.yview)
        self.reminder_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.reminder_tree.pack(fill='both', expand=True)
        bottom = tk.Frame(self.reminder_tab, bg=BG)
        bottom.pack(fill='x', pady=10)
        action(bottom, '删除选中提醒', self.delete_reminder).pack(side='right')
        text(bottom, '运行时弹窗提醒；退出期间错过的提醒会在下次启动补发。', 9, MUTED).pack(side='left')
        self.reminder_snapshot = None
        self.refresh_reminders()

    def quick_reminder(self, title, minutes):
        self.store.add_reminder(title, time.time() + minutes * 60)
        self.refresh_reminders()

    def add_reminder(self):
        try:
            repeat = int(self.repeat.get())
            exact = self.exact.get().strip()
            if exact:
                due = datetime.strptime(exact, '%Y-%m-%d %H:%M').timestamp()
            else:
                delay = int(self.delay.get())
                if not 1 <= delay <= 525600:
                    raise ValueError('分钟数需要在 1—525600 之间。')
                due = time.time() + delay * 60
            if due <= time.time():
                raise ValueError('请选择将来的提醒时间。')
            self.store.add_reminder(self.reminder_title.get(), due, repeat)
            self.reminder_title.delete(0, 'end')
            self.refresh_reminders()
        except ValueError as error:
            messagebox.showwarning('请检查提醒设置', str(error), parent=self)

    def refresh_reminders(self):
        rows = self.store.reminders()
        if rows == self.reminder_snapshot:
            return
        self.reminder_snapshot = rows
        selected = self.reminder_tree.selection()
        self.reminder_tree.delete(*self.reminder_tree.get_children())
        for row in rows:
            self.reminder_tree.insert('', 'end', iid=str(row[0]), values=(row[1], datetime.fromtimestamp(row[2]).strftime('%m-%d %H:%M'),
                f'{row[3]} 分钟' if row[3] else '一次', {'scheduled': '等待提醒', 'ringing': '待确认', 'done': '已完成'}[row[4]]))
        for item in selected:
            if self.reminder_tree.exists(item):
                self.reminder_tree.selection_set(item)

    def delete_reminder(self):
        for item in self.reminder_tree.selection():
            self.store.delete_reminder(int(item))
        self.refresh_reminders()
