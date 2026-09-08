# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

extra_datas = []
extra_bins = []
hiddenimports = []
for package in ["mcp", "rapidocr_onnxruntime", "pychrome", "openai", "pandas", "docx", "pypdf", "fitz", "pptx", "openpyxl"]:
    try:
        d, b, h = collect_all(package)
        extra_datas += d
        extra_bins += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=extra_bins,
    datas=extra_datas + [
        ("LICENSE-UPSTREAM-XIAOZHI-MCP-COMPUTER.txt", "."),
        ("THIRD_PARTY_NOTICES.md", "."),
        ("VERSION", "."),
    ],
    hiddenimports=hiddenimports + [
        "win32crypt", "win32clipboard", "win32con", "pythoncom",
        "pywinauto", "pycaw.pycaw", "comtypes", "mss",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="XiaozhiDesktopAssistant",
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
)
