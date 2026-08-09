"""Send a bill / receipt over WhatsApp.

What this does, exactly:
  1. puts the PDF file itself on the Windows clipboard (CF_HDROP + the
     "Preferred DropEffect" = COPY flag, which some WhatsApp builds require)
  2. opens the customer's WhatsApp chat with the message already typed in
  3. re-copies the file once WhatsApp has finished launching, because the
     launch can wipe the clipboard

The user then just presses **Ctrl+V** in the chat and the PDF attaches.

Deliberately NOT included: bulk blasts and synthetic keystrokes. Nothing here
types or sends on the user's behalf.
"""
from __future__ import annotations

import os
import platform
import urllib.parse
import webbrowser

from .services import normalise_phone


def is_windows():
    return platform.system() == "Windows"


def copy_file_to_clipboard(path, owner_hwnd=None):
    """Put a real file on the clipboard as CF_HDROP. Returns True on success."""
    if not is_windows():
        return False
    if not path or not os.path.exists(path):
        return False
    try:
        import ctypes
        import time
        from ctypes import wintypes

        CF_HDROP = 15
        GMEM_MOVEABLE = 0x0002
        DROPEFFECT_COPY = 0x00000001

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        class DROPFILES(ctypes.Structure):
            _fields_ = [("pFiles", wintypes.DWORD),
                        ("pt_x", wintypes.LONG),
                        ("pt_y", wintypes.LONG),
                        ("fNC", wintypes.BOOL),
                        ("fWide", wintypes.BOOL)]

        abspath = os.path.abspath(path)
        payload = (abspath + "\0\0").encode("utf-16-le")
        df_size = ctypes.sizeof(DROPFILES)
        total = df_size + len(payload)

        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterClipboardFormatW.restype = wintypes.UINT

        # CF_HDROP block — the file itself
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, total)
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            return False
        df = DROPFILES(pFiles=df_size, pt_x=0, pt_y=0, fNC=False, fWide=True)
        ctypes.memmove(ptr, ctypes.byref(df), df_size)
        ctypes.memmove(ptr + df_size, payload, len(payload))
        kernel32.GlobalUnlock(h)

        # "Preferred DropEffect" = COPY — without it some targets refuse paste
        cf_effect = user32.RegisterClipboardFormatW("Preferred DropEffect")
        h_effect = kernel32.GlobalAlloc(GMEM_MOVEABLE, 4)
        if h_effect:
            p_effect = kernel32.GlobalLock(h_effect)
            if p_effect:
                ctypes.memmove(p_effect,
                               ctypes.byref(ctypes.c_uint32(DROPEFFECT_COPY)), 4)
                kernel32.GlobalUnlock(h_effect)

        # WhatsApp Desktop briefly holds the clipboard after launch — retry
        hwnd = wintypes.HWND(int(owner_hwnd)) if owner_hwnd else None
        opened = False
        for _ in range(30):
            if user32.OpenClipboard(hwnd):
                opened = True
                break
            time.sleep(0.05)
        if not opened:
            kernel32.GlobalFree(h)
            if h_effect:
                kernel32.GlobalFree(h_effect)
            return False

        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_HDROP, h):
                user32.CloseClipboard()
                kernel32.GlobalFree(h)
                if h_effect:
                    kernel32.GlobalFree(h_effect)
                return False
            if h_effect and cf_effect:
                user32.SetClipboardData(cf_effect, h_effect)
            user32.CloseClipboard()
            # Clipboard now owns h / h_effect — must NOT free them here.
            return True
        except Exception:
            try:
                user32.CloseClipboard()
            except Exception:
                pass
            return False
    except Exception:
        return False


def open_chat(phone, message):
    """Open the WhatsApp chat with the text pre-filled.

    Prefers WhatsApp Desktop (no browser tab); falls back to wa.me.
    """
    ph = normalise_phone(phone)
    txt = urllib.parse.quote(message or "")
    if is_windows():
        try:
            import ctypes
            url = f"whatsapp://send?phone={ph}&text={txt}"
            rc = ctypes.windll.shell32.ShellExecuteW(None, "open", url,
                                                     None, None, 1)
            if rc > 32:
                return True
        except Exception:
            pass
    try:
        webbrowser.open(f"https://wa.me/{ph}?text={txt}")
        return True
    except Exception:
        return False


def send(widget, phone, message, pdf_path=None, open_pdf=True):
    """Full flow: clipboard the PDF → open the chat → re-copy after launch.

    `widget` is any Tk widget (used for its HWND and its .after timer).
    Returns (opened_ok, clipboard_ok).
    """
    hwnd = None
    try:
        hwnd = widget.winfo_id()
    except Exception:
        hwnd = None

    clip_ok = copy_file_to_clipboard(pdf_path, hwnd) if pdf_path else False
    opened = open_chat(phone, message)

    if pdf_path and os.path.exists(pdf_path):
        if open_pdf:
            try:
                from .ui_helpers import open_file
                open_file(pdf_path)
            except Exception:
                pass
        # Defensive re-copy: launching WhatsApp can clear the clipboard.
        try:
            widget.after(1500, lambda p=pdf_path:
                         copy_file_to_clipboard(p, hwnd))
            widget.after(3000, lambda p=pdf_path:
                         copy_file_to_clipboard(p, hwnd))
        except Exception:
            pass
    return opened, clip_ok


# ─── Message templates ─────────────────────────────────────────────────────
def bill_message(shop_name, shop_phone, bill_number, total, customer_name="",
                 due=0.0, currency="Rs."):
    greeting = f"Namaste *{customer_name}*," if customer_name else "Namaste,"
    lines = [
        greeting, "",
        f"This is *{shop_name}*.", "",
        "Your bill has been generated:",
        f"🧾 *Bill No: {bill_number}*",
        f"💰 *Total: {currency} {total:,.2f}*",
    ]
    if due and due > 0.005:
        lines.append(f"⏳ *Balance Due: {currency} {due:,.2f}*")
    lines += [
        "",
        f"For any queries call us at {shop_phone}.",
        "Thank you for your business! 🙏",
    ]
    return "\n".join(lines)


def receipt_message(shop_name, shop_phone, receipt_number, amount, customer_name="",
                    remaining=0.0, currency="Rs."):
    greeting = f"Namaste *{customer_name}*," if customer_name else "Namaste,"
    lines = [
        greeting, "",
        f"This is *{shop_name}*.", "",
        "We have received your payment:",
        f"🧾 *Receipt No: {receipt_number}*",
        f"✅ *Received: {currency} {amount:,.2f}*",
    ]
    if remaining and remaining > 0.005:
        lines.append(f"⏳ *Remaining Due: {currency} {remaining:,.2f}*")
    else:
        lines.append("🎉 *Your account is fully settled. Thank you!*")
    lines += [
        "",
        f"For any queries call us at {shop_phone}.",
        "Thank you! 🙏",
    ]
    return "\n".join(lines)


def statement_message(shop_name, shop_phone, retailer_name, date_from, date_to,
                      closing_due, currency="Rs."):
    return "\n".join([
        f"Namaste *{retailer_name}*,", "",
        f"This is *{shop_name}*.", "",
        f"Statement of account for *{date_from}* to *{date_to}*:",
        f"💼 *Closing Balance: {currency} {closing_due:,.2f}*", "",
        f"For any queries call us at {shop_phone}.",
        "Thank you! 🙏",
    ])
