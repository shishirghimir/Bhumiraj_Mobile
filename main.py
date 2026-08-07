"""Bhumiraj Mobile & Watch House — Retail + Wholesale Management System.

Chabahil-7, Kathmandu  ·  9808773134
Built by Netanix Labs — netanixctf.com

Run:    python main.py
Build:  BUILD_EXE.bat
"""
from __future__ import annotations

import os
import sys


def _fail(title, message):
    """Show a readable error even when the GUI never came up."""
    print(f"\n{title}\n{'-' * len(title)}\n{message}\n", file=sys.stderr)
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass
    sys.exit(1)


def main():
    if sys.version_info < (3, 9):
        _fail("Python too old",
              "Bhumiraj needs Python 3.9 or newer.\n"
              f"You are running {sys.version.split()[0]}.")

    missing = []
    for module, package in (("customtkinter", "customtkinter"),
                            ("reportlab", "reportlab"),
                            ("PIL", "Pillow")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        _fail("Missing dependencies",
              "These packages are required but not installed:\n\n  "
              + "\n  ".join(missing)
              + "\n\nInstall them with:\n\n    pip install -r requirements.txt")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bhumiraj.app import run
    run()


if __name__ == "__main__":
    main()
