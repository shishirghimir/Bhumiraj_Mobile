"""My Profile — what a staff member can see and change about themselves."""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..config import F_BODY, F_LBL, F_SM, F_TN, TH
from ..security import (hash_password, password_strength, staff_password_strength,
                        strength_score, verify_password)
from ..services import is_admin, money
from .. import ui_helpers as ui
from .base import Page


class ProfilePage(Page):
    title = "My Profile"
    subtitle = "Your details and your own sales record"

    def build(self):
        outer = ctk.CTkScrollableFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=(4, 12))

        u = self.db.fetchone("SELECT * FROM users WHERE id=?",
                             (self.app.user["id"],))
        if not u:
            ctk.CTkLabel(outer, text="Account not found.",
                         text_color=TH.DANGER).pack(pady=30)
            return

        card = ctk.CTkFrame(outer, fg_color=TH.PANEL, corner_radius=12,
                            border_width=1, border_color=TH.BORDER)
        card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        img = ui.load_ctk_image(u["photo_path"], (108, 108))
        photo = ctk.CTkLabel(inner, text="" if img else "No\nphoto", image=img,
                             width=110, height=110, corner_radius=55,
                             fg_color=TH.PANEL_ALT,
                             font=ctk.CTkFont(size=F_SM),
                             text_color=TH.TEXT_DIM)
        photo.pack(side="left")
        if img:
            photo.image = img

        details = ctk.CTkFrame(inner, fg_color="transparent")
        details.pack(side="left", fill="both", expand=True, padx=18)
        ctk.CTkLabel(details, text=u["full_name"],
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TH.TEXT).pack(anchor="w")
        ctk.CTkLabel(details,
                     text=f"@{u['username']}  ·  "
                          f"{'Owner / Admin' if is_admin(dict(u)) else 'Counter Staff'}",
                     font=ctk.CTkFont(size=F_BODY, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w", pady=(1, 8))
        for label, value in (("Phone", u["phone"]), ("Email", u["email"]),
                             ("Address", u["address"]),
                             ("Joined", u["joined_date"]),
                             ("Last login", u["last_login"] or "This session")):
            r = ctk.CTkFrame(details, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=label, width=120, anchor="w",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=str(value or "—"), anchor="w",
                         font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.TEXT).pack(side="left")

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(side="right", padx=6)
        ui.button(actions, "🔑  Change Password", self._change_pw, "gold",
                  188, 38).pack(pady=3)
        ui.button(actions, "📷  Update Photo", self._change_photo, "info",
                  188, 34).pack(pady=3)

        ui.section(outer, "YOUR SALES")
        cards = ctk.CTkFrame(outer, fg_color="transparent")
        cards.pack(fill="x")
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        n_today = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE staff_id=? AND DATE(bill_date)=?",
            (u["id"], today), 0))
        n_month = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE staff_id=? "
            "AND strftime('%Y-%m', bill_date)=?", (u["id"], month), 0))
        n_all = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE staff_id=?", (u["id"],), 0))
        ui.stat_card(cards, "Bills today", f"{n_today:,}", TH.NAVY, 160)
        ui.stat_card(cards, "Bills this month", f"{n_month:,}", TH.INFO, 180)
        ui.stat_card(cards, "Bills all time", f"{n_all:,}", TH.OK, 170)
        if self.admin:
            total = money(self.db.scalar(
                "SELECT COALESCE(SUM(total_amount),0) FROM bills "
                "WHERE staff_id=?", (u["id"],), 0))
            ui.stat_card(cards, "Sales value", self.money_text(total),
                         TH.ACCENT_DIM, 200)

        ui.section(outer, "YOUR RECENT BILLS")
        tree, _ = ui.make_table(
            outer, ("Bill No", "Type", "Date", "Customer", "Items", "Total",
                    "Status"),
            widths=[128, 100, 148, 220, 60, 118, 96],
            anchors=["w", "w", "w", "w", "center", "e", "center"], height=12)
        for b in self.db.fetchall(
                "SELECT b.*, (SELECT COUNT(*) FROM bill_items bi "
                " WHERE bi.bill_id=b.id) n FROM bills b "
                "WHERE b.staff_id=? ORDER BY b.id DESC LIMIT 100", (u["id"],)):
            tree.insert("", "end", values=(
                b["bill_number"],
                "Wholesale" if b["bill_type"] == "wholesale" else "Retail",
                str(b["bill_date"])[:16], b["customer_name"] or "Walk-in",
                b["n"], f"{money(b['total_amount']):,.2f}",
                (b["payment_status"] or "paid").upper()))

    def _change_photo(self):
        path = ui.pick_staff_photo(self.app.user["username"])
        if not path:
            return
        self.db.execute("UPDATE users SET photo_path=? WHERE id=?",
                        (path, self.app.user["id"]))
        self.toast("Photo updated.")
        self.app.go("profile", force=True)

    def _change_pw(self):
        d = ui.modal(self.app, "Change password", 500, 470, resizable=False)
        ui.modal_header(d, "Change your password", "Choose something only you "
                                                   "know", TH.WARN)
        body = ui.modal_body(d, scroll=False)
        e_old = ui.labelled_entry(body, "Current password", show="•",
                                  required=True)
        e_new = ui.labelled_entry(body, "New password", show="•",
                                  required=True)
        e_conf = ui.labelled_entry(body, "Confirm new password", show="•",
                                   required=True)
        meter = ctk.CTkProgressBar(body, height=8)
        meter.pack(fill="x", pady=(8, 2))
        meter.set(0)
        hint = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=F_TN),
                            text_color=TH.TEXT_DIM)
        hint.pack(anchor="w")

        def on_type(_e=None):
            score = strength_score(e_new.get())
            meter.set(score / 4)
            meter.configure(progress_color=[TH.DANGER, TH.DANGER, TH.WARN,
                                            TH.OK, TH.OK][score])
            hint.configure(text=["Too weak", "Weak", "Fair", "Good",
                                 "Strong"][score])
        e_new.bind("<KeyRelease>", on_type)

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=420,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            row = self.db.fetchone("SELECT * FROM users WHERE id=?",
                                   (self.app.user["id"],))
            if not verify_password(e_old.get(), row["password_hash"]):
                msg.configure(text="Your current password is not correct.")
                return
            if e_new.get() != e_conf.get():
                msg.configure(text="The new passwords do not match.")
                return
            checker = (password_strength if is_admin(dict(row))
                       else staff_password_strength)
            ok, why = checker(e_new.get())
            if not ok:
                msg.configure(text=why)
                return
            self.db.execute(
                "UPDATE users SET password_hash=?, must_change_password=0 "
                "WHERE id=?", (hash_password(e_new.get()), row["id"]))
            d.destroy()
            self.info("Password changed",
                      "Your password has been updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Change", save, "ok", 130, side="right")
