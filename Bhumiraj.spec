# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Bhumiraj Mobile & Watch House (Retail + Wholesale).

Build with:  BUILD_EXE.bat   (or: python -m PyInstaller --clean --noconfirm Bhumiraj.spec)
Output:      dist\\Bhumiraj\\Bhumiraj.exe

UPX is deliberately OFF — packed PyInstaller binaries trip Windows Defender
heuristics, and a shop machine flagging its own till app is not worth the
few MB saved.
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

try:
    import customtkinter as _ctk
    CTK_DIR = os.path.dirname(_ctk.__file__)
except Exception:
    CTK_DIR = None

datas = []
for asset in ("logo.png", "logo_bill.png", "logo_small.png", "logo.ico"):
    if os.path.exists(asset):
        datas.append((asset, "."))
if CTK_DIR:
    datas.append((CTK_DIR, "customtkinter"))
datas += collect_data_files("reportlab")

hidden = [
    "customtkinter",
    "PIL", "PIL._imagingtk", "PIL.Image", "PIL.ImageTk",
    "PIL._tkinter_finder",
    "reportlab", "reportlab.pdfgen", "reportlab.lib",
    "reportlab.platypus", "reportlab.pdfbase",
    "reportlab.pdfbase.pdfmetrics", "reportlab.pdfbase.ttfonts",
    "tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog",
    "sqlite3",
]
hidden += collect_submodules("reportlab")
hidden += collect_submodules("customtkinter")
# every page is imported lazily inside app._make_page — name them explicitly
hidden += collect_submodules("bhumiraj")

a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "numpy",
              "notebook", "IPython", "pytest", "fitz", "pdf2image"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Bhumiraj",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.ico" if os.path.exists("logo.ico") else None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False,
    upx_exclude=[],
    name="Bhumiraj",
)
