"""One brand and icon for every window, tray and packaged executable."""
from pathlib import Path
import sys

APP_NAME = '猫薄荷'
AUTHOR = '某不知名人士'
VERSION = '2.3.3 轻量版'


def icon_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app.ico'


def set_icon(window):
    path = icon_path()
    if path.exists():
        window.iconbitmap(str(path))
