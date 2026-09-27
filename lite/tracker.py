"""Local storage and statistics for ClickBreak. No UI or Windows dependency."""
import csv
import sqlite3
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS hours (
                day TEXT NOT NULL, hour INTEGER NOT NULL,
                left_count INTEGER NOT NULL DEFAULT 0,
                right_count INTEGER NOT NULL DEFAULT 0,
                middle_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(day, hour));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                due REAL NOT NULL, repeat_minutes INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'scheduled');
        ''')

    def get(self, key, default=''):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def initialize_profile(self, default_nickname, legacy_path=None):
        # The write lock ensures concurrent sessions initialize exactly one
        # device identity. Renaming never creates a second profile.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.get('device_id'):
                return
            empty = not self.db.execute('SELECT 1 FROM hours LIMIT 1').fetchone()
            empty = empty and not self.db.execute('SELECT 1 FROM settings LIMIT 1').fetchone()
            if empty and legacy_path and Path(legacy_path).is_file():
                legacy = sqlite3.connect(Path(legacy_path).resolve().as_uri() + '?mode=ro', uri=True)
                try:
                    self.db.executemany('INSERT INTO hours VALUES (?,?,?,?,?)', legacy.execute(
                        'SELECT day,hour,left_count,right_count,middle_count FROM hours').fetchall())
                    self.db.executemany('INSERT INTO settings VALUES (?,?)', legacy.execute(
                        "SELECT key,value FROM settings WHERE key IN ('nickname','goal')").fetchall())
                finally:
                    legacy.close()
            self.db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('nickname', default_nickname))
            self.db.execute('INSERT INTO settings VALUES (?,?)', ('device_id', str(uuid.uuid4())))

    def set(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(value)))

    def record(self, events):
        buckets = {}
        for stamp, button in events:
            moment = datetime.fromtimestamp(stamp)
            key = (moment.strftime('%Y-%m-%d'), moment.hour)
            counts = buckets.setdefault(key, [0, 0, 0])
            counts[{'left': 0, 'right': 1, 'middle': 2}[button]] += 1
        with self.db:
            self.db.executemany('''INSERT INTO hours VALUES (?,?,?,?,?)
                ON CONFLICT(day,hour) DO UPDATE SET
                left_count=left_count+excluded.left_count,
                right_count=right_count+excluded.right_count,
                middle_count=middle_count+excluded.middle_count''',
                [(day, hour, *values) for (day, hour), values in buckets.items()])

    def add_note(self, title='新便签', body=''):
        with self.db:
            return self.db.execute('INSERT INTO notes(title,body,updated) VALUES (?,?,?)',
                                   (title, body, time.time())).lastrowid

    def notes(self):
        return self.db.execute('SELECT id,title,body,updated FROM notes ORDER BY updated DESC,id DESC').fetchall()

    def save_note(self, note_id, title, body):
        with self.db:
            self.db.execute('UPDATE notes SET title=?,body=?,updated=? WHERE id=?',
                            (title.strip()[:60] or '未命名便签', body, time.time(), note_id))

    def delete_note(self, note_id):
        with self.db:
            self.db.execute('DELETE FROM notes WHERE id=?', (note_id,))

    def add_reminder(self, title, due, repeat_minutes=0):
        if not title.strip() or len(title.strip()) > 100:
            raise ValueError('提醒内容需要为 1—100 个字符。')
        if not 0 <= repeat_minutes <= 525600:
            raise ValueError('重复间隔超出范围。')
        with self.db:
            return self.db.execute('INSERT INTO reminders(title,due,repeat_minutes) VALUES (?,?,?)',
                                   (title.strip(), float(due), int(repeat_minutes))).lastrowid

    def reminders(self):
        return self.db.execute('SELECT id,title,due,repeat_minutes,state FROM reminders ORDER BY due,id').fetchall()

    def due_reminders(self, now=None):
        now = time.time() if now is None else now
        with self.db:
            self.db.execute("UPDATE reminders SET state='ringing' WHERE state='scheduled' AND due<=?", (now,))
        return self.db.execute("SELECT id,title,due,repeat_minutes,state FROM reminders WHERE state='ringing' ORDER BY due,id").fetchall()

    def acknowledge_reminder(self, reminder_id, now=None, snooze_minutes=0):
        now = time.time() if now is None else now
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute("SELECT repeat_minutes FROM reminders WHERE id=? AND state='ringing'", (reminder_id,)).fetchone()
            if row is None:
                return
            interval = snooze_minutes or row[0]
            if interval:
                self.db.execute("UPDATE reminders SET state='scheduled',due=? WHERE id=?", (now + interval * 60, reminder_id))
            else:
                self.db.execute("UPDATE reminders SET state='done' WHERE id=?", (reminder_id,))

    def delete_reminder(self, reminder_id):
        with self.db:
            self.db.execute('DELETE FROM reminders WHERE id=?', (reminder_id,))

    def days(self):
        return self.db.execute('''SELECT day, SUM(left_count), SUM(right_count),
            SUM(middle_count), SUM(left_count+right_count+middle_count)
            FROM hours GROUP BY day ORDER BY day DESC''').fetchall()

    def hourly(self, day):
        values = [0] * 24
        for hour, count in self.db.execute('SELECT hour,left_count+right_count+middle_count FROM hours WHERE day=?', (day,)):
            values[hour] = count
        return values

    def streak(self, today):
        active = {row[0] for row in self.days() if row[4] > 0}
        date = datetime.strptime(today, '%Y-%m-%d').date()
        if today not in active:
            date -= timedelta(days=1)
        count = 0
        while date.isoformat() in active:
            count += 1
            date -= timedelta(days=1)
        return count

    def export(self, path):
        with open(path, 'w', encoding='utf-8-sig', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['日期', '左键', '右键', '中键', '总点击次数'])
            writer.writerows(self.days())

    def close(self):
        self.db.close()
