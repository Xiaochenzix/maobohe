a = Analysis(['lite/app.py'], pathex=['lite'], binaries=[],
    datas=[('lite/app.ico','.'),('lite/assets/bongo','assets/bongo'),('lite/assets/frames','assets/frames')],
    hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['numpy','live2d','glfw','OpenGL','PySide6','setuptools','pkg_resources','cffi','pycparser','ssl','_ssl','_hashlib','pydoc_data','unittest','PIL.ImageQt','PIL.ImageCms','PIL.ImageFont','PIL.ImageFilter','PIL.ImageEnhance','PIL.ImageDraw','PIL.ImageOps','PIL._webp'],noarchive=False,optimize=1)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='猫薄荷-轻量版',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=True,console=False,icon=['app.ico'])
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,name='猫薄荷-轻量版')
