"""One shared application profile per Windows computer."""
import os
from pathlib import Path
import pywintypes
import win32file
import win32security


def default_data_dir():
    base = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData'))
    return base / 'ClickBreak' / 'data'


def prepare_machine_storage():
    directory = default_data_dir()
    # Grant local Users modify access to this application's new directory only.
    # Files below it inherit this, allowing different Windows accounts to use
    # the same nickname/database without making ProgramData itself writable.
    descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        'D:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;BU)',
        win32security.SDDL_REVISION_1)
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    try:
        win32file.CreateDirectory(str(directory.parent), attributes)
    except pywintypes.error as error:
        if error.winerror != 183:
            raise
    directory.mkdir(exist_ok=True)
    return directory


def legacy_user_database():
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    return local / 'ClickBreak' / 'data' / 'clicks.sqlite3'
