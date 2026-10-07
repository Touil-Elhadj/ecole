# -*- mode: python ; coding: utf-8 -*-
# إعدادات بناء Ecole.exe (ملف واحد) بـ PyInstaller: pyinstaller ecole.spec
# نستبعد مكوّنات Qt غير المستعملة لتصغير حجم البرنامج.

EXCLUDED_MODULES = [
    "tkinter", "ssl", "PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtOpenGL",
    "unittest", "pydoc", "xmlrpc",
]

# أجزاء من Qt لا يحتاجها البرنامج (يكفي محرك الرسم العادي والإضافة qwindows).
EXCLUDED_BINARIES = (
    "opengl32sw.dll",
    "qt6network.dll", "qt6svg.dll", "qt6opengl.dll",
    "\\imageformats\\", "\\iconengines\\", "\\networkinformation\\", "\\tls\\",
    "\\generic\\", "qdirect2d.dll", "qminimal.dll", "qoffscreen.dll",
    "libssl-",
)


def keep_binary(entry):
    name = entry[0].lower().replace("/", "\\")
    return not any(part in name for part in EXCLUDED_BINARIES)


def keep_data(entry):
    name = entry[0].lower().replace("/", "\\")
    # من ترجمات Qt نحتفظ بالعربية فقط.
    if "\\translations\\" in name:
        return name.endswith("_ar.qm")
    return True


a = Analysis(
    ["main.py"],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if keep_binary(b)]
a.datas = [d for d in a.datas if keep_data(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Ecole",
    console=False,
    upx=False,
    icon="icon.ico" if __import__("os").path.exists("icon.ico") else None,
)
