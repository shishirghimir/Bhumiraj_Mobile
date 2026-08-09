"""Reusable CustomTkinter widgets, table helpers, dialogs, printing.

Keeps every page consistent and keeps the page modules short.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .config import (F_BODY, F_LBL, F_SEC, F_SM, F_TITLE, F_TN, LOGO_ICO,
                     PRODUCT_IMG_DIR, STAFF_PHOTOS_DIR, TH)


# ─── File / print ──────────────────────────────────────────────────────────
def open_file(path):
    """Open a file with the OS default application."""
    if not path or not os.path.exists(path):
        messagebox.showwarning("Not found", "That file no longer exists.")
        return False
    try:
        if platform.system() == "Windows":
            os.startfile(path)                     # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return True
    except Exception as exc:
        messagebox.showerror("Open failed", str(exc))
        return False


def print_file(path):
    """Send a PDF to the default printer (falls back to opening it)."""
    if not path or not os.path.exists(path):
        messagebox.showwarning("Not found", "That file no longer exists.")
        return False
    try:
        if platform.system() == "Windows":
            try:
                os.startfile(path, "print")        # noqa: S606
                return True
            except Exception:
                return open_file(path)
        elif platform.system() == "Darwin":
            subprocess.run(["lp", path], check=False)
        else:
            subprocess.run(["lp", path], check=False)
        return True
    except Exception:
        return open_file(path)


def copy_image_into(src, folder, stem):
    """Copy a picked image into the app's data folder. Returns the new path."""
    if not src or not os.path.exists(src):
        return ""
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(src)[1].lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
        ext = ".png"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe = "".join(ch for ch in str(stem) if ch.isalnum() or ch in "-_")[:40]
    dest = os.path.join(folder, f"{safe or 'img'}_{stamp}{ext}")
    try:
        shutil.copy2(src, dest)
        return dest
    except OSError:
        return ""


def pick_image(title="Choose an image"):
    return filedialog.askopenfilename(
        title=title,
        filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                   ("All files", "*.*")])


def pick_product_image(stem):
    src = pick_image("Choose a product photo")
    return copy_image_into(src, PRODUCT_IMG_DIR, stem) if src else ""


def pick_staff_photo(stem):
    src = pick_image("Choose a staff photo")
    return copy_image_into(src, STAFF_PHOTOS_DIR, stem) if src else ""


def load_ctk_image(path, size):
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image
        img = Image.open(path)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None


# ─── Layout primitives ─────────────────────────────────────────────────────
def page_header(parent, title, subtitle=""):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", padx=24, pady=(11, 4))
    ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=F_TITLE, weight="bold"),
                 text_color=TH.TEXT).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(f, text=subtitle, font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(1, 0))
    ctk.CTkFrame(parent, height=1, fg_color=TH.BORDER).pack(fill="x", padx=24,
                                                            pady=(0, 4))
    return f


def section(parent, title):
    ctk.CTkLabel(parent, text=title,
                 font=ctk.CTkFont(size=F_LBL, weight="bold"),
                 text_color=TH.ACCENT).pack(anchor="w", padx=4, pady=(12, 5))


def body_frame(parent):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="both", expand=True, padx=18, pady=(3, 8))
    return f


def toolbar(parent):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", pady=(0, 8))
    return f


def stat_card(parent, title, value, color=None, width=192, click=None,
              subtitle=""):
    card = ctk.CTkFrame(parent, fg_color=TH.PANEL, corner_radius=12,
                        border_width=1, border_color=TH.BORDER,
                        width=width, height=88)
    card.pack(side="left", padx=5, pady=5)
    card.pack_propagate(False)
    strip = ctk.CTkFrame(card, fg_color=color or TH.NAVY, width=5,
                         corner_radius=3)
    strip.pack(side="left", fill="y", padx=(6, 0), pady=8)
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(side="left", fill="both", expand=True, padx=10, pady=8)
    ctk.CTkLabel(inner, text=title.upper(), font=ctk.CTkFont(size=F_TN,
                 weight="bold"), text_color=TH.TEXT_DIM).pack(anchor="w")
    ctk.CTkLabel(inner, text=str(value),
                 font=ctk.CTkFont(size=19, weight="bold"),
                 text_color=color or TH.TEXT).pack(anchor="w", pady=(2, 0))
    if subtitle:
        ctk.CTkLabel(inner, text=subtitle, font=ctk.CTkFont(size=F_TN),
                     text_color=TH.TEXT_DIM).pack(anchor="w")
    if click:
        for w in (card, inner, strip):
            w.bind("<Button-1>", lambda _e=None: click())
            w.configure(cursor="hand2")
        for child in inner.winfo_children():
            child.bind("<Button-1>", lambda _e=None: click())
    return card


def button(parent, text, command, kind="primary", width=140, height=36,
           side=None, padx=4, pady=0, font_size=F_BODY):
    palette = {
        "primary": (TH.NAVY, TH.NAVY_HV),
        "gold": (TH.ACCENT_DIM, TH.ACCENT),
        "ok": (TH.OK, TH.OK_HV),
        "danger": (TH.DANGER, TH.DANGER_HV),
        "info": (TH.INFO, TH.INFO_HV),
        "muted": (TH.MUTED, TH.MUTED_HV),
    }
    fg, hv = palette.get(kind, palette["primary"])
    b = ctk.CTkButton(parent, text=text, command=command, width=width,
                      height=height, fg_color=fg, hover_color=hv,
                      corner_radius=8,
                      font=ctk.CTkFont(size=font_size, weight="bold"))
    if side:
        b.pack(side=side, padx=padx, pady=pady)
    return b


def labelled_entry(parent, label, value="", width=240, show=None,
                   placeholder="", required=False):
    """Returns the entry widget; label carries a gold * when required."""
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.pack(fill="x", pady=4)
    txt = label + (" *" if required else "")
    ctk.CTkLabel(wrap, text=txt, font=ctk.CTkFont(size=F_SM, weight="bold"),
                 text_color=TH.ACCENT if required else TH.TEXT_DIM,
                 anchor="w").pack(anchor="w")
    e = ctk.CTkEntry(wrap, width=width, height=32, show=show,
                     placeholder_text=placeholder,
                     font=ctk.CTkFont(size=F_BODY),
                     fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
    e.pack(fill="x", pady=(2, 0))
    if value not in (None, ""):
        e.insert(0, str(value))
    return e


def labelled_combo(parent, label, values, value="", width=240, required=False,
                   command=None):
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.pack(fill="x", pady=4)
    txt = label + (" *" if required else "")
    ctk.CTkLabel(wrap, text=txt, font=ctk.CTkFont(size=F_SM, weight="bold"),
                 text_color=TH.ACCENT if required else TH.TEXT_DIM,
                 anchor="w").pack(anchor="w")
    c = ctk.CTkComboBox(wrap, values=list(values) or [""], width=width,
                        height=32, font=ctk.CTkFont(size=F_BODY),
                        dropdown_font=ctk.CTkFont(size=F_BODY),
                        fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
                        button_color=TH.NAVY, button_hover_color=TH.NAVY_HV,
                        command=command)
    c.pack(fill="x", pady=(2, 0))
    c.set(str(value) if value not in (None, "") else
          (list(values)[0] if values else ""))
    return c


def form_grid(parent, columns=2):
    """A frame whose children are laid out in N equal columns."""
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x")
    cols = []
    for i in range(columns):
        col = ctk.CTkFrame(f, fg_color="transparent")
        col.pack(side="left", fill="both", expand=True,
                 padx=(0 if i == 0 else 10, 0))
        cols.append(col)
    return cols


# ─── Treeview ──────────────────────────────────────────────────────────────
_TREE_STYLED = False


def style_trees():
    """Dark ttk.Treeview styling that matches the CustomTkinter theme."""
    global _TREE_STYLED
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure("Bh.Treeview",
                 background=TH.PANEL, fieldbackground=TH.PANEL,
                 foreground=TH.TEXT, rowheight=34, borderwidth=0,
                 font=("Segoe UI", 11))
    st.configure("BhBig.Treeview",
                 background=TH.PANEL, fieldbackground=TH.PANEL,
                 foreground=TH.TEXT, rowheight=42, borderwidth=0,
                 font=("Segoe UI", 12))
    st.configure("BhBig.Treeview.Heading",
                 background=TH.SIDEBAR, foreground=TH.ACCENT,
                 relief="flat", font=("Segoe UI", 11, "bold"))
    st.map("BhBig.Treeview",
           background=[("selected", TH.SIDEBAR_HL)],
           foreground=[("selected", "white")])
    st.configure("Bh.Treeview.Heading",
                 background=TH.SIDEBAR, foreground=TH.ACCENT,
                 relief="flat", font=("Segoe UI", 10, "bold"))
    st.map("Bh.Treeview.Heading",
           background=[("active", TH.SIDEBAR_HV)])
    st.map("Bh.Treeview",
           background=[("selected", TH.SIDEBAR_HL)],
           foreground=[("selected", "white")])
    st.configure("Bh.Vertical.TScrollbar", background=TH.MUTED,
                 troughcolor=TH.BG, borderwidth=0, arrowcolor=TH.TEXT_DIM)
    _TREE_STYLED = True


def make_table(parent, columns, widths=None, anchors=None, height=14,
               on_double=None, on_select=None, big=False):
    """Treeview + vertical & horizontal scrollbars in a bordered frame.

    Returns (tree, container_frame). Rows are never clipped — the frame
    expands, and the scrollbars handle any overflow.
    """
    if not _TREE_STYLED:
        style_trees()
    holder = ctk.CTkFrame(parent, fg_color=TH.PANEL, corner_radius=10,
                          border_width=1, border_color=TH.BORDER)
    holder.pack(fill="both", expand=True, pady=(4, 0))

    inner = tk.Frame(holder, bg=TH.PANEL, highlightthickness=0, bd=0)
    inner.pack(fill="both", expand=True, padx=6, pady=6)

    tree = ttk.Treeview(inner, columns=columns, show="headings",
                        height=height,
                        style="BhBig.Treeview" if big else "Bh.Treeview")
    vsb = ttk.Scrollbar(inner, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(inner, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    inner.grid_rowconfigure(0, weight=1)
    inner.grid_columnconfigure(0, weight=1)

    widths = widths or [130] * len(columns)
    anchors = anchors or ["w"] * len(columns)
    for col, w, a in zip(columns, widths, anchors):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor=a, minwidth=max(50, int(w * 0.55)),
                    stretch=True)

    tree.tag_configure("oos", foreground=TH.OOS)
    tree.tag_configure("low", foreground=TH.LOW)
    tree.tag_configure("pos", foreground=TH.POS)
    tree.tag_configure("due", foreground=TH.OOS)
    tree.tag_configure("partial", foreground=TH.LOW)
    tree.tag_configure("wholesale", foreground=TH.WHOLESALE)
    tree.tag_configure("muted", foreground=TH.TEXT_DIM)

    if on_double:
        tree.bind("<Double-1>", lambda _e: on_double())
    if on_select:
        tree.bind("<<TreeviewSelect>>", lambda _e: on_select())
    return tree, holder


def tree_selected_value(tree, index=0):
    sel = tree.selection()
    if not sel:
        return None
    vals = tree.item(sel[0], "values")
    return vals[index] if vals and len(vals) > index else None


def sortable(tree, columns, refresh_callback):
    """Wire click-to-sort on the given columns.

    refresh_callback(col_name, descending) does the actual re-query.
    """
    state = {"col": None, "desc": False}

    def clicked(col):
        state["desc"] = not state["desc"] if state["col"] == col else False
        state["col"] = col
        refresh_callback(col, state["desc"])

    for col in columns:
        tree.heading(col, text=col, command=lambda c=col: clicked(c))
    return state


# ─── Dialogs ───────────────────────────────────────────────────────────────
def centre_on(win, parent, w, h):
    try:
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - w) // 2
        y = parent.winfo_y() + (parent.winfo_height() - h) // 3
        win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
    except Exception:
        win.geometry(f"{w}x{h}")


def modal(parent, title, w=620, h=560, resizable=True):
    """A properly-behaved modal CTkToplevel."""
    d = ctk.CTkToplevel(parent)
    d.title(title)
    d.configure(fg_color=TH.BG)
    centre_on(d, parent, w, h)
    d.transient(parent)
    d.resizable(resizable, resizable)
    try:
        if os.path.exists(LOGO_ICO):
            d.after(220, lambda: d.iconbitmap(LOGO_ICO))
    except Exception:
        pass
    d.after(60, d.grab_set)
    d.lift()
    d.focus_force()
    return d


def modal_header(dialog, title, subtitle="", color=None):
    band = ctk.CTkFrame(dialog, fg_color=color or TH.NAVY, height=58,
                        corner_radius=0)
    band.pack(fill="x")
    band.pack_propagate(False)
    box = ctk.CTkFrame(band, fg_color="transparent")
    box.pack(side="left", padx=18, pady=8)
    ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=F_SEC, weight="bold"),
                 text_color="white").pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(box, text=subtitle, font=ctk.CTkFont(size=F_TN),
                     text_color="#c8d4f0").pack(anchor="w")
    ctk.CTkFrame(dialog, height=2, fg_color=TH.ACCENT).pack(fill="x")
    return band


def modal_body(dialog, scroll=True):
    if scroll:
        f = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
    else:
        f = ctk.CTkFrame(dialog, fg_color="transparent")
    f.pack(fill="both", expand=True, padx=18, pady=12)
    return f


def modal_footer(dialog):
    ctk.CTkFrame(dialog, height=1, fg_color=TH.BORDER).pack(fill="x")
    f = ctk.CTkFrame(dialog, fg_color="transparent", height=58)
    f.pack(fill="x", padx=18, pady=10)
    return f


def confirm(parent, title, message, danger=False):
    if danger:
        return messagebox.askyesno(title, message, icon="warning", parent=parent)
    return messagebox.askyesno(title, message, parent=parent)


def info(parent, title, message):
    messagebox.showinfo(title, message, parent=parent)


def warn(parent, title, message):
    messagebox.showwarning(title, message, parent=parent)


def error(parent, title, message):
    messagebox.showerror(title, message, parent=parent)


def ask_text(parent, title, prompt, initial="", show=None, width=420):
    """Single-field prompt. Returns the string or None if cancelled."""
    result = {"value": None}
    d = modal(parent, title, width, 220, resizable=False)
    modal_header(d, title)
    body = modal_body(d, scroll=False)
    ctk.CTkLabel(body, text=prompt, font=ctk.CTkFont(size=F_BODY),
                 text_color=TH.TEXT, wraplength=width - 60,
                 justify="left").pack(anchor="w", pady=(4, 6))
    entry = ctk.CTkEntry(body, height=34, show=show,
                         font=ctk.CTkFont(size=F_BODY),
                         fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
    entry.pack(fill="x")
    if initial:
        entry.insert(0, str(initial))
    entry.focus_set()

    def ok(_e=None):
        result["value"] = entry.get().strip()
        d.destroy()

    foot = modal_footer(d)
    button(foot, "Cancel", d.destroy, "muted", 110, side="right")
    button(foot, "OK", ok, "ok", 110, side="right")
    entry.bind("<Return>", ok)
    d.bind("<Escape>", lambda _e: d.destroy())
    parent.wait_window(d)
    return result["value"]


def toast(parent, message, kind="ok", ms=2600):
    """Brief non-blocking banner in the top-right of the window."""
    colors_ = {"ok": TH.OK, "warn": TH.WARN, "error": TH.DANGER,
               "info": TH.INFO}
    try:
        t = ctk.CTkFrame(parent, fg_color=colors_.get(kind, TH.OK),
                         corner_radius=8)
        ctk.CTkLabel(t, text=message, font=ctk.CTkFont(size=F_BODY,
                     weight="bold"), text_color="white",
                     wraplength=380, justify="left").pack(padx=16, pady=10)
        t.place(relx=0.99, rely=0.02, anchor="ne")
        t.after(ms, t.destroy)
    except Exception:
        pass


class FilterChips(ctk.CTkFrame):
    """Toggle 'chips' used to filter a list.

    The chips REFLOW onto as many rows as they need whenever the frame is
    resized, so none of them are ever cut off or hidden behind a scrollbar.
    """

    def __init__(self, parent, options, on_change, default="All"):
        super().__init__(parent, fg_color="transparent", width=200, height=38)
        # Stop this frame from inflating its parent's requested width — without
        # this the parent grows to fit the chips, so measuring the parent to
        # decide when to wrap becomes circular and the chips never wrap.
        self.grid_propagate(False)
        self.on_change = on_change
        self.value = default
        self.buttons = {}
        self._widths = {}
        self._last_width = 0

        for label in options:
            width = max(70, len(label) * 8 + 24)
            b = ctk.CTkButton(
                self, text=label, height=30, corner_radius=15,
                font=ctk.CTkFont(size=F_SM, weight="bold"), width=width,
                fg_color=TH.NAVY if label == default else "transparent",
                text_color="white" if label == default else TH.TEXT_DIM,
                border_width=1,
                border_color=TH.NAVY if label == default else TH.BORDER,
                hover_color=TH.SIDEBAR_HV,
                command=lambda v=label: self.select(v))
            self.buttons[label] = b
            self._widths[label] = width + 8

        # Watch the PARENT for resizes — that is what actually changes.
        parent.bind("<Configure>", self._reflow, add="+")
        self.after(60, lambda: self._reflow(None))
        self.after(350, lambda: self._reflow(None))

    def _reflow(self, _event=None):
        # Measure the PARENT, not self: once chips are gridded, this frame's
        # own width reports the space the grid wants (which may overflow), so
        # measuring self would never trigger a wrap.
        avail = 0
        try:
            avail = self.master.winfo_width()
        except Exception:
            avail = 0
        if avail <= 1:
            try:
                avail = self.winfo_width()
            except Exception:
                avail = 0
        if avail <= 1:
            self.after(120, lambda: self._reflow(None))
            return
        avail -= 8                       # breathing room at the right edge
        if abs(avail - self._last_width) < 8 and self._last_width:
            return
        self._last_width = avail

        row = col = 0
        used = 0
        widest = 0
        for label, b in self.buttons.items():
            w = self._widths[label]
            if used + w > avail and col > 0:
                row += 1
                col = 0
                used = 0
            b.grid(row=row, column=col, padx=3, pady=3, sticky="w")
            used += w
            col += 1
            widest = max(widest, used)

        # Size the frame to what was actually laid out. Height alone is not
        # enough: when the chips are packed inline (side="left") the frame
        # keeps its placeholder width and the last chips get clipped.
        self.grid_propagate(False)
        self.configure(height=(row + 1) * 36,
                       width=max(min(widest, avail), 60))

    def select(self, value):
        self.value = value
        for label, b in self.buttons.items():
            active = (label == value)
            b.configure(fg_color=TH.NAVY if active else "transparent",
                        text_color="white" if active else TH.TEXT_DIM,
                        border_color=TH.NAVY if active else TH.BORDER)
        if self.on_change:
            self.on_change(value)

    def get(self):
        return self.value


def required_missing(fields):
    """fields: [(label, value)] → list of labels that are blank."""
    return [label for label, value in fields
            if not str(value or "").strip()]
