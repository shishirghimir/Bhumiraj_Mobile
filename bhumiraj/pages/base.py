"""Shared base class for every page."""
from __future__ import annotations

import customtkinter as ctk

from ..config import TH
from .. import ui_helpers as ui


class Page(ctk.CTkFrame):
    """A screen. Subclasses implement build() and (optionally) refresh()."""

    title = ""
    subtitle = ""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.db = app.db
        self.settings = app.settings
        self.docs = app.docs
        self.pack(fill="both", expand=True)
        if self.title:
            ui.page_header(self, self.title, self.subtitle)
        self.build()

    # ── to override ─────────────────────────────────────────────────
    def build(self):
        raise NotImplementedError

    def refresh(self):
        pass

    # ── conveniences ────────────────────────────────────────────────
    @property
    def admin(self):
        return self.app.is_admin()

    @property
    def cur(self):
        return self.app.currency()

    def staff_id(self):
        return self.app.staff_id()

    def money_text(self, value):
        from ..services import money
        return f"{self.cur} {money(value):,.2f}"

    def toast(self, message, kind="ok"):
        ui.toast(self.app, message, kind)

    def info(self, title, message):
        ui.info(self.app, title, message)

    def warn(self, title, message):
        ui.warn(self.app, title, message)

    def error(self, title, message):
        ui.error(self.app, title, message)

    def confirm(self, title, message, danger=False):
        return ui.confirm(self.app, title, message, danger)

    def deny_staff(self, what="do that"):
        """Guard used everywhere staff must be blocked."""
        if self.admin:
            return False
        self.warn("Not allowed",
                  f"Only the shop owner can {what}.\n"
                  "Please ask the owner to do this.")
        return True

    def body(self):
        return ui.body_frame(self)

    def open_pdf(self, path):
        self.app.remember_pdf(path)
        ui.open_file(path)

    def print_pdf(self, path):
        self.app.remember_pdf(path)
        ui.print_file(path)
