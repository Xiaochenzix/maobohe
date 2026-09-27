"""Validated, atomic import of Cubism 3 model packages; no package code is run."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import zipfile

BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'models'
MAX_BYTES = 300 * 1024 * 1024
ALLOWED = {'.json', '.moc3', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.md', '.wav', '.mp3', '.flac', '.ogg'}


def safe_path(root, value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('模型文件路径无效。')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('模型包含越界路径。')
    result = (root / str(path)).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('模型包含越界路径。')
    return result


def validate(entry):
    entry = Path(entry)
    data = json.loads(entry.read_text(encoding='utf-8-sig'))
    refs = data.get('FileReferences', {})
    if data.get('Version') != 3 or not refs.get('Moc') or not refs.get('Textures'):
        raise ValueError('需要完整的 Cubism 3 模型（.model3.json、.moc3 和贴图）。')
    files = [refs['Moc'], *refs['Textures']]
    for key in ('Physics', 'Pose', 'DisplayInfo', 'UserData'):
        if refs.get(key): files.append(refs[key])
    for row in refs.get('Expressions', []): files.append(row['File'])
    for rows in refs.get('Motions', {}).values():
        for row in rows:
            files.append(row['File'])
            if row.get('Sound'): files.append(row['Sound'])
    for name in files:
        p = safe_path(entry.parent, name)
        if not p.is_file(): raise ValueError('缺少模型文件：' + str(name))
    moc = safe_path(entry.parent, refs['Moc'])
    with moc.open('rb') as stream:
        if stream.read(4) != b'MOC3': raise ValueError('MOC3 文件无效。')
    return data


def entries(root):
    found = sorted(root.rglob('*.model3.json'))
    # Community packages sometimes include auxiliary/demo JSON beside cat.model3.json.
    parents = {p.parent for p in found}
    return [next((p for p in found if p.parent == d and p.name == 'cat.model3.json'),
                 next(p for p in found if p.parent == d)) for d in sorted(parents)]


class ModelLibrary:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'models'
        self.root.mkdir(parents=True, exist_ok=True)
        self.models = {}
        self.errors = []
        self.refresh()

    def refresh(self):
        self.models.clear()
        self.errors.clear()
        for root, prefix in [(BUNDLE, 'bundled'), (self.root, 'imported')]:
            if not root.exists(): continue
            for entry in entries(root):
                try:
                    validate(entry)
                    meta_path = entry.parent / 'model-info.json'
                    meta = json.loads(meta_path.read_text(encoding='utf8')) if meta_path.exists() else {}
                    identity = hashlib.sha256(str(entry.relative_to(root)).encode()).hexdigest()[:16]
                    key = 'model:' + prefix + ':' + identity
                    self.models[key] = dict(id=key, path=entry, name=meta.get('name', entry.parent.name),
                                            author=meta.get('author', '用户导入'), source=meta.get('source', ''),
                                            imported=prefix == 'imported')
                except (ValueError, OSError, KeyError, TypeError) as error:
                    self.errors.append(f'{entry.parent.name}：{error}')

    def import_package(self, source):
        source = Path(source)
        if not source.exists(): raise ValueError('模型文件不存在。')
        with tempfile.TemporaryDirectory(prefix='model-import-') as temporary:
            stage = Path(temporary)
            if source.is_file() and source.suffix.lower() == '.zip':
                with zipfile.ZipFile(source) as archive:
                    members = archive.infolist()
                    if len(members) > 4000 or sum(m.file_size for m in members) > MAX_BYTES:
                        raise ValueError('模型包过大（最多 300 MB / 4000 个文件）。')
                    for member in members:
                        target = safe_path(stage, member.filename.rstrip('/'))
                        if (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError('模型包不能包含符号链接。')
                        if member.is_dir() or target.suffix.lower() not in ALLOWED: continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
            else:
                folder = source if source.is_dir() else source.parent
                total = 0
                paths = list(folder.rglob('*'))
                if len(paths) > 4000: raise ValueError('模型文件夹过大。')
                for src in paths:
                    if src.is_symlink(): raise ValueError('模型文件夹不能包含符号链接。')
                    if not src.is_file() or src.suffix.lower() not in ALLOWED: continue
                    total += src.stat().st_size
                    if total > MAX_BYTES: raise ValueError('模型文件夹超过 300 MB。')
                    dst = stage / src.relative_to(folder)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
            models = entries(stage)
            if not models: raise ValueError('没有找到 .model3.json，暂不支持 Cubism 2 或仅图片模型。')
            for model in models: validate(model)
            digest = hashlib.sha256()
            for file in sorted(stage.rglob('*')):
                if file.is_file():
                    digest.update(str(file.relative_to(stage)).encode())
                    digest.update(file.read_bytes())
            destination = self.root / digest.hexdigest()[:24]
            if not destination.exists():
                pending = Path(tempfile.mkdtemp(prefix='.pending-', dir=self.root))
                try:
                    shutil.copytree(stage, pending, dirs_exist_ok=True)
                    # Preserve a useful name when the ZIP has files directly at its root.
                    if any(p.parent == stage for p in models) and not (pending / 'model-info.json').exists():
                        (pending / 'model-info.json').write_text(json.dumps({'name': source.stem}), encoding='utf8')
                    os.replace(pending, destination)
                except Exception:
                    shutil.rmtree(pending)
                    raise
        self.refresh()
        return [m for m in self.models.values() if m['path'].is_relative_to(destination)]
