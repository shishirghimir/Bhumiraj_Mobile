"""Settings — shop details, backup folder, import/export, security."""
from __future__ import annotations

import os
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from ..config import (APP_VERSION, BACKUP_INTERVAL_HOURS, F_BODY, F_LBL, F_SM,
                      F_TN, PAYMENT_METHODS, TH, VENDOR, VENDOR_SITE)
from ..security import (hash_answer, hash_password, new_pin_hash,
                        password_strength, strength_score, verify_password)
from ..services import parse_int
from .. import ui_helpers as ui
from .base import Page


class SettingsPage(Page):
    title = "Settings"
    subtitle = "Shop details, automatic backup, and security"

    def build(self):
        outer = ctk.CTkScrollableFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=(4, 12))
        self._shop(outer)
        self._backup(outer)
        self._security(outer)
        self._about(outer)

    def _card(self, parent, title, subtitle=""):
        ui.section(parent, title)
        if subtitle:
            ctk.CTkLabel(parent, text=subtitle,
                         font=ctk.CTkFont(size=F_SM), text_color=TH.TEXT_DIM,
                         justify="left", wraplength=900).pack(anchor="w",
                                                              padx=4)
        card = ctk.CTkFrame(parent, fg_color=TH.PANEL, corner_radius=12,
                            border_width=1, border_color=TH.BORDER)
        card.pack(fill="x", pady=(6, 4))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        return inner

    # ── shop details ────────────────────────────────────────────────
    def _shop(self, parent):
        box = self._card(parent, "SHOP DETAILS",
                         "These appear on every bill, receipt and statement.")
        g = ui.form_grid(box, 2)
        self.e_name = ui.labelled_entry(g[0], "Shop Name",
                                        self.settings.get("shop_name", ""),
                                        required=True)
        self.e_phone = ui.labelled_entry(g[1], "Phone",
                                         self.settings.get("shop_phone", ""),
                                         required=True)
        self.e_addr = ui.labelled_entry(g[0], "Address",
                                        self.settings.get("shop_address", ""))
        self.e_alt = ui.labelled_entry(g[1], "Alternate Phone",
                                       self.settings.get("shop_phone_alt", ""))
        self.e_email = ui.labelled_entry(g[0], "Email",
                                         self.settings.get("shop_email", ""))
        self.e_pan = ui.labelled_entry(g[1], "PAN / VAT No.",
                                       self.settings.get("shop_pan", ""))
        g2 = ui.form_grid(box, 3)
        self.e_cur = ui.labelled_entry(g2[0], "Currency Symbol",
                                       self.settings.get("currency", "Rs."))
        self.c_pay = ui.labelled_combo(g2[1], "Default Payment Method",
                                       PAYMENT_METHODS,
                                       self.settings.get("default_payment",
                                                         "Cash"))
        self.e_low = ui.labelled_entry(
            g2[2], "Low-stock Alert Level",
            str(self.settings.get("low_stock_threshold", 3)))

        ctk.CTkLabel(box, text="Bill Terms & Conditions (one per line)",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(10, 2))
        self.t_terms = ctk.CTkTextbox(box, height=76,
                                      font=ctk.CTkFont(size=F_BODY),
                                      fg_color=TH.PANEL_ALT,
                                      border_color=TH.BORDER, border_width=1)
        self.t_terms.pack(fill="x")
        self.t_terms.insert("1.0", self.settings.get("bill_terms", ""))

        ui.button(box, "💾  Save Shop Details", self._save_shop, "ok", 200, 38
                  ).pack(anchor="w", pady=(12, 0))

    def _save_shop(self):
        name = self.e_name.get().strip()
        if not name:
            self.warn("Shop name", "The shop name cannot be blank.")
            return
        self.settings.update({
            "shop_name": name,
            "shop_phone": self.e_phone.get().strip(),
            "shop_phone_alt": self.e_alt.get().strip(),
            "shop_address": self.e_addr.get().strip(),
            "shop_email": self.e_email.get().strip(),
            "shop_pan": self.e_pan.get().strip(),
            "currency": self.e_cur.get().strip() or "Rs.",
            "default_payment": self.c_pay.get(),
            "low_stock_threshold": parse_int(self.e_low.get(), 3),
            "bill_terms": self.t_terms.get("1.0", "end").strip(),
        })
        self.toast("Shop details saved. New bills will use them.")

    # ── backup ──────────────────────────────────────────────────────
    def _backup(self, parent):
        box = self._card(
            parent, "AUTOMATIC BACKUP",
            "Pick a Google Drive Desktop folder. The database is copied there "
            "automatically EVERY NIGHT at the time below, and copies older "
            "than the retention window are deleted so the folder never fills "
            "up. If the PC was off at that time, the backup is taken the next "
            "time the app is opened — a night is never skipped.")

        folder_row = ctk.CTkFrame(box, fg_color="transparent")
        folder_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(folder_row, text="Backup folder",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w")
        pick = ctk.CTkFrame(folder_row, fg_color="transparent")
        pick.pack(fill="x", pady=(2, 0))
        self.e_folder = ctk.CTkEntry(pick, height=34,
                                     font=ctk.CTkFont(size=F_BODY),
                                     fg_color=TH.PANEL_ALT,
                                     border_color=TH.BORDER)
        self.e_folder.pack(side="left", fill="x", expand=True)
        current = self.settings.get("backup_folder", "")
        if current:
            self.e_folder.insert(0, current)
        else:
            self.e_folder.configure(
                placeholder_text="e.g. C:\\Users\\You\\Google Drive\\Bhumiraj")
        ui.button(pick, "📁  Choose…", self._pick_folder, "info", 128, 34,
                  side="left", padx=(6, 0))

        opts = ui.form_grid(box, 4)
        self.auto_var = ctk.BooleanVar(
            value=bool(self.settings.get("auto_backup", True)))
        ctk.CTkCheckBox(opts[0], text="Nightly backup ON",
                        variable=self.auto_var,
                        font=ctk.CTkFont(size=F_BODY),
                        fg_color=TH.OK).pack(anchor="w", pady=18)
        self.e_time = ui.labelled_entry(
            opts[1], "Backup time (24h, HH:MM)",
            str(self.settings.get("backup_time", "23:55")))
        self.e_keep = ui.labelled_entry(
            opts[2], "Delete backups older than (days)",
            str(self.settings.get("backup_retention_days", 3)))
        last = self.settings.get("last_backup", "") or "Never"
        try:
            nxt = self.app.backup.next_slot().strftime("%d %b, %I:%M %p")
        except Exception:
            nxt = "—"
        self.lbl_last = ctk.CTkLabel(
            opts[3], text=f"Last backup:\n{last}\n\nNext run:\n{nxt}",
            font=ctk.CTkFont(size=F_SM, weight="bold"),
            text_color=TH.ACCENT, justify="left")
        self.lbl_last.pack(anchor="w", pady=10)

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        ui.button(btns, "💾  Save Backup Settings", self._save_backup, "ok",
                  204, 38, side="left")
        ui.button(btns, "⬇  Backup Now", self._backup_now, "primary", 154, 38,
                  side="left", padx=(8, 0))
        ui.button(btns, "📤  Export Database", self._export, "info", 172, 38,
                  side="left", padx=(8, 0))
        ui.button(btns, "📥  Import Database", self._import, "danger", 172, 38,
                  side="left", padx=(8, 0))

        ui.section(box, "BACKUPS IN THAT FOLDER")
        self.bk_tree, _ = ui.make_table(
            box, ("File", "Taken", "Size"),
            widths=[380, 190, 120], anchors=["w", "w", "e"], height=6)
        self._refresh_backups()

    def _pick_folder(self):
        path = filedialog.askdirectory(
            title="Choose the backup folder (a Google Drive folder is ideal)")
        if path:
            self.e_folder.delete(0, "end")
            self.e_folder.insert(0, path)

    def _save_backup(self):
        folder = self.e_folder.get().strip()
        if folder and not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                self.error("Bad folder",
                           f"That folder cannot be used:\n{exc}")
                return
        keep = parse_int(self.e_keep.get(), 3)
        if keep < 1:
            self.warn("Retention", "Keep backups for at least 1 day.")
            return

        raw = self.e_time.get().strip()
        try:
            hh, mm = raw.split(":")
            hh, mm = int(hh), int(mm)
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            self.warn("Backup time",
                      "Enter the time as HH:MM in 24-hour form, "
                      "for example 23:55.")
            return

        self.settings.update({
            "backup_folder": folder,
            "auto_backup": bool(self.auto_var.get()),
            "backup_time": f"{hh:02d}:{mm:02d}",
            "backup_retention_days": keep,
        })
        self._refresh_backups()
        try:
            nxt = self.app.backup.next_slot().strftime("%d %b, %I:%M %p")
            self.lbl_last.configure(
                text=f"Last backup:\n"
                     f"{self.settings.get('last_backup', '') or 'Never'}"
                     f"\n\nNext run:\n{nxt}")
        except Exception:
            pass
        self.toast(f"Saved. Next backup at {hh:02d}:{mm:02d}.")

    def _backup_now(self):
        ok, msg, path = self.app.backup.run(force=True)
        self._refresh_backups()
        self.lbl_last.configure(
            text=f"Last backup:\n{self.settings.get('last_backup', '')}")
        if ok:
            self.info("Backup complete",
                      f"{msg}\n\nSaved as:\n{os.path.basename(path or '')}")
        else:
            self.error("Backup failed", msg)

    def _refresh_backups(self):
        for r in self.bk_tree.get_children():
            self.bk_tree.delete(r)
        for name, _path, size, when in self.app.backup.list_backups():
            self.bk_tree.insert("", "end", values=(
                name, when.strftime("%d %b %Y, %I:%M %p"),
                f"{size / 1024:,.0f} KB"), tags=("pos",))

    def _export(self):
        default = f"bhumiraj_export_{datetime.now():%Y-%m-%d}.db"
        path = filedialog.asksaveasfilename(
            title="Export the database", defaultextension=".db",
            initialfile=default,
            filetypes=[("Bhumiraj database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        try:
            saved = self.app.backup.export_to(path)
        except Exception as exc:
            self.error("Export failed", str(exc))
            return
        self.info("Export complete",
                  f"The database was exported to:\n\n{saved}\n\n"
                  "Keep this file safe — it holds every bill and product.")

    def _import(self):
        if not self.confirm(
                "Import a database",
                "Importing REPLACES all current data with the contents of the "
                "backup file.\n\n"
                "A safety copy of the current database is taken first, and the "
                "file is checked before anything is replaced.\n\n"
                "Continue?", danger=True):
            return
        path = filedialog.askopenfilename(
            title="Choose a Bhumiraj .db backup",
            filetypes=[("Bhumiraj database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        typed = ui.ask_text(self.app, "Confirm import",
                            "Type IMPORT to replace the current database:")
        if (typed or "").strip().upper() != "IMPORT":
            self.toast("Import cancelled.", "warn")
            return
        try:
            safety = self.app.backup.import_from(path)
        except Exception as exc:
            self.error("Import failed",
                       f"Nothing was changed.\n\n{exc}")
            return
        self.info("Import complete",
                  "The database has been replaced.\n\n"
                  + (f"Your previous data was saved as:\n{safety}\n\n"
                     if safety else "")
                  + "You will now be returned to the login screen.")
        self.app.logout(ask=False)

    # ── security ────────────────────────────────────────────────────
    def _security(self, parent):
        box = self._card(parent, "SECURITY",
                         "Passwords are stored with PBKDF2-HMAC-SHA256, salted, "
                         "200,000 iterations — they are never kept as plain "
                         "text and cannot be read back out of the database.")
        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(fill="x")
        ui.button(btns, "🔑  Change My Password", self._change_pw, "gold",
                  206, 38, side="left")
        ui.button(btns, "🔢  Change Recovery PIN", self._change_pin, "info",
                  206, 38, side="left", padx=(8, 0))
        ui.button(btns, "📜  Login History", self._audit, "muted", 168, 38,
                  side="left", padx=(8, 0))

    def _change_pw(self):
        d = ui.modal(self.app, "Change password", 500, 460, resizable=False)
        ui.modal_header(d, "Change your password", "Owner account", TH.WARN)
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
            s = strength_score(e_new.get())
            meter.set(s / 4)
            meter.configure(progress_color=[TH.DANGER, TH.DANGER, TH.WARN,
                                            TH.OK, TH.OK][s])
            hint.configure(text=["Too weak", "Weak", "Fair", "Good",
                                 "Strong"][s])
        e_new.bind("<KeyRelease>", on_type)

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=420,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            row = self.db.fetchone("SELECT * FROM users WHERE id=?",
                                   (self.app.user["id"],))
            if not verify_password(e_old.get(), row["password_hash"]):
                msg.configure(text="Current password is not correct.")
                return
            if e_new.get() != e_conf.get():
                msg.configure(text="The new passwords do not match.")
                return
            ok, why = password_strength(e_new.get())
            if not ok:
                msg.configure(text=why)
                return
            self.db.execute("UPDATE users SET password_hash=?, "
                            "must_change_password=0 WHERE id=?",
                            (hash_password(e_new.get()), row["id"]))
            d.destroy()
            self.info("Password changed", "Your password has been updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Change", save, "ok", 130, side="right")

    def _change_pin(self):
        d = ui.modal(self.app, "Recovery PIN", 520, 460, resizable=False)
        ui.modal_header(d, "Recovery PIN & security question",
                        "Used to reset a forgotten password", TH.INFO)
        body = ui.modal_body(d, scroll=False)
        e_cur = ui.labelled_entry(body, "Your account password", show="•",
                                  required=True)
        e_pin = ui.labelled_entry(body, "New 4-6 digit PIN", show="•",
                                  required=True)
        row = self.db.fetchone("SELECT * FROM admin_pin WHERE id=1")
        e_q = ui.labelled_entry(body, "Security question",
                                row["security_question"] if row else "")
        e_a = ui.labelled_entry(body, "Security answer",
                                placeholder="stored hashed, not readable")
        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            me = self.db.fetchone("SELECT * FROM users WHERE id=?",
                                  (self.app.user["id"],))
            if not verify_password(e_cur.get(), me["password_hash"]):
                msg.configure(text="Your account password is not correct.")
                return
            pin = e_pin.get().strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                msg.configure(text="The PIN must be 4 to 6 digits.")
                return
            answer = e_a.get().strip()
            question = e_q.get().strip() or "What is the shop location?"
            if answer:
                self.db.execute(
                    "UPDATE admin_pin SET pin_hash=?, security_question=?, "
                    "security_answer_hash=? WHERE id=1",
                    (new_pin_hash(pin), question, hash_answer(answer)))
            else:
                self.db.execute(
                    "UPDATE admin_pin SET pin_hash=?, security_question=? "
                    "WHERE id=1", (new_pin_hash(pin), question))
            d.destroy()
            self.info("Recovery updated",
                      "The recovery PIN has been changed. Keep it private.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Save", save, "ok", 130, side="right")

    def _audit(self):
        d = ui.modal(self.app, "Login history", 700, 520)
        ui.modal_header(d, "Login history", "Last 300 sign-in attempts")
        body = ui.modal_body(d, scroll=False)
        tree, _ = ui.make_table(
            body, ("When", "Username", "Result", "Detail"),
            widths=[180, 170, 110, 200],
            anchors=["w", "w", "center", "w"], height=16)
        for r in self.db.fetchall(
                "SELECT * FROM login_audit ORDER BY id DESC LIMIT 300"):
            tree.insert("", "end", values=(
                str(r["at"])[:19], r["username"] or "—",
                "OK" if r["success"] else "FAILED", r["note"] or "—"),
                tags=("pos",) if r["success"] else ("due",))
        ui.button(ui.modal_footer(d), "Close", d.destroy, "muted", 120,
                  side="right")

    # ── about ───────────────────────────────────────────────────────
    def _about(self, parent):
        box = self._card(parent, "ABOUT")
        counts = {
            "Products": self.db.scalar(
                "SELECT COUNT(*) FROM products WHERE is_active=1", None, 0),
            "Handsets (IMEI)": self.db.scalar(
                "SELECT COUNT(*) FROM mobile_units", None, 0),
            "Bills": self.db.scalar("SELECT COUNT(*) FROM bills", None, 0),
            "Retailers": self.db.scalar(
                "SELECT COUNT(*) FROM retailers WHERE is_active=1", None, 0),
            "Staff accounts": self.db.scalar(
                "SELECT COUNT(*) FROM users WHERE is_active=1", None, 0),
        }
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        for label, value in counts.items():
            ui.stat_card(row, label, f"{int(value):,}", TH.NAVY, 168)

        ctk.CTkLabel(
            box,
            text=f"\nBhumiraj Mobile & Watch House  —  Retail + Wholesale "
                 f"Management System\nVersion {APP_VERSION}\n\n"
                 f"Built by {VENDOR}  ·  visit {VENDOR_SITE}",
            font=ctk.CTkFont(size=F_BODY), text_color=TH.TEXT_DIM,
            justify="left").pack(anchor="w", pady=(10, 0))
