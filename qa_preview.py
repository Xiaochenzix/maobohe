"""Capture only this application's window using isolated test data."""
import ctypes
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import tkinter as tk
from PIL import Image, ImageDraw, ImageGrab
from app import App
from pet import draw_cat, STYLES


class IconCanvas:
    """Render the same code-native geometry at icon size."""
    def __init__(self, image):
        self.draw = ImageDraw.Draw(image)

    def delete(self, tag):
        pass

    def create_rectangle(self, *coords, **options):
        self.draw.rectangle(coords, fill=options['fill'])

    def create_polygon(self, *coords, **options):
        self.draw.polygon(list(zip(coords[::2], coords[1::2])), fill=options['fill'])


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    output = Path('.qa')
    output.mkdir(exist_ok=True)
    # The original cat is shared by all application icons.
    icon = Image.new('RGBA', (256, 256), '#e9eee3')
    draw_cat(IconCanvas(icon), 128, 128, 5.5)
    icon.save('app.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    with tempfile.TemporaryDirectory() as directory:
        root = tk.Tk()
        app = App(root, directory, preview=True)
        # The preview opens with genuinely empty data; fixtures never enter the release.
        root.update()
        root.after(400, lambda: None)
        for page in ('overview', 'petroom', 'tools', 'ranking', 'achievements', 'history', 'settings'):
            app.show(page)
            root.update()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / f'{page}.png')
            if page == 'petroom':
                notebook = next(child for child in app.content.winfo_children() if child.winfo_class() == 'TNotebook')
                notebook.select(1)
                root.update()
                ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / 'phrases.png')
            if page == 'tools':
                pane = app.tools.pane
                pane.new_note()
                pane.note_title.set('待办事项')
                pane.note_body.insert('1.0', '1. 整理文件\n2. 核对清单')
                pane.save_note()
                root.update()
                ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / 'notes.png')
                pane.notebook.select(pane.reminder_tab)
                root.update()
                ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / 'reminders.png')
        app.start_pet()
        root.update()
        pet = app.pet.window
        x, y = pet.winfo_rootx(), pet.winfo_rooty()
        ImageGrab.grab((x, y, x + pet.winfo_width(), y + pet.winfo_height())).save(output / 'desktop-pet.png')
        styles = tk.Toplevel(root)
        styles.title('宠物造型预览')
        canvas = tk.Canvas(styles, width=900, height=540, bg='#f6f7f1', highlightthickness=0)
        canvas.pack()
        for index, style in enumerate(STYLES[:6]):
            cx, cy = 150 + index % 3 * 300, 135 + index // 3 * 270
            draw_cat(canvas, cx, cy, 4.5, style=style)
            # Keep earlier pets; the renderer only replaces its tagged live sprite.
            canvas.dtag('cat', 'cat')
            canvas.create_text(cx, cy + 105, text=style, fill='#3f7856', font=('Microsoft YaHei UI', 12))
        root.update()
        x, y = styles.winfo_rootx(), styles.winfo_rooty()
        ImageGrab.grab((x, y, x + 900, y + 540)).save(output / 'styles.png')
        canvas.delete('all')
        for index, style in enumerate(STYLES[6:]):
            cx, cy = 150 + index % 3 * 300, 135 + index // 3 * 270
            draw_cat(canvas, cx, cy, 4.5, style=style)
            canvas.dtag('cat', 'cat')
            canvas.create_text(cx, cy + 105, text=style, fill='#3f7856', font=('Microsoft YaHei UI', 12))
        root.update()
        ImageGrab.grab((x, y, x + 900, y + 540)).save(output / 'bongo-styles.png')
        styles.destroy()
        app.close()


if __name__ == '__main__':
    main()
