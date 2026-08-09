"""Staff — the owner creates and manages every counter account here.

Full personal details, photo, salary, password reset, enable/disable, and a
per-staff sales view. No attendance register: this is an account + details
tab, exactly as asked.
"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..config import F_BODY, F_LBL, F_SEC, F_SM, F_TN, ROLE_ADMIN, TH
from ..security import (hash_password, password_strength, random_password,
                        staff_password_strength, strength_score)
from ..services import clean_phone, money, parse_amount
from .. import ui_helpers as ui
from .base import Page


class StaffPage(Page):
    title = "Staff"
    subtitle = "Create counter accounts, keep their details, reset passwords"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=280, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Name, username, phone…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.show_inactive = ctk.CTkCheckBox(
            bar, text="Show disabled", font=ctk.CTkFont(size=F_SM),
            command=self.refresh, fg_color=TH.NAVY)
        self.show_inactive.pack(side="left", padx=10)

        ui.button(bar, "🗑  Delete", self._delete, "danger", 100, 36,
                  side="right")
        ui.button(bar, "🚫  Enable/Disable", self._toggle, "muted", 156, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "🔑  Reset Password", self._reset_pw, "gold", 162, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "👁  Details", self._profile, "info", 110, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "➕  Add Staff", lambda: self._form(None), "ok", 132, 36,
                  side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        self.tree, _ = ui.make_table(
            outer, ("Name", "Username", "Role", "Phone", "Joined", "Salary",
                    "Bills Made", "Last Login", "Status"),
            widths=[176, 130, 88, 118, 106, 108, 92, 148, 92],
            anchors=["w", "w", "center", "w", "w", "e", "center", "w",
                     "center"],
            height=17, on_double=self._profile)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["1=1"]
        params = []
        if not self.show_inactive.get():
            where.append("u.is_active = 1")
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(u.full_name LIKE ? OR u.username LIKE ? "
                         " OR u.phone LIKE ?)")
            params += [like] * 3

        rows = self.db.fetchall(
            "SELECT u.*, (SELECT COUNT(*) FROM bills b WHERE b.staff_id=u.id) "
            "  AS n_bills FROM users u WHERE " + " AND ".join(where) +
            " ORDER BY (u.role='admin') DESC, u.full_name", params)

        self._rows = {}
        for u in rows:
            iid = self.tree.insert("", "end", values=(
                u["full_name"], u["username"],
                "OWNER" if u["role"] == ROLE_ADMIN else "Staff",
                u["phone"] or "—", u["joined_date"] or "—",
                f"{money(u['salary']):,.2f}" if u["salary"] else "—",
                u["n_bills"], u["last_login"] or "Never",
                "Active" if u["is_active"] else "Disabled"),
                tags=("pos" if u["is_active"] else "muted",))
            self._rows[iid] = u

        for w in self.stats.winfo_children():
            w.destroy()
        active = sum(1 for u in rows if u["is_active"])
        payroll = money(sum(money(u["salary"]) for u in rows if u["is_active"]))
        ui.stat_card(self.stats, "Team members", f"{len(rows):,}", TH.NAVY, 168)
        ui.stat_card(self.stats, "Active accounts", f"{active:,}", TH.OK, 176)
        ui.stat_card(self.stats, "Monthly payroll", self.money_text(payroll),
                     TH.ACCENT_DIM, 210)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a staff member first.", "warn")
            return None
        return self._rows.get(sel[0])

    # ── add / edit ──────────────────────────────────────────────────
    def _form(self, row):
        editing = row is not None
        d = ui.modal(self.app, "Edit staff" if editing else "Add staff member",
                     700, 700)
        ui.modal_header(d, "Edit staff" if editing else "Add staff member",
                        "The owner creates every account")
        body = ui.modal_body(d)

        state = {"photo": row["photo_path"] if editing else ""}

        photo_row = ctk.CTkFrame(body, fg_color="transparent")
        photo_row.pack(fill="x", pady=(0, 6))
        preview = ctk.CTkLabel(photo_row, text="No photo", width=104,
                               height=104, fg_color=TH.PANEL_ALT,
                               corner_radius=52,
                               font=ctk.CTkFont(size=F_SM),
                               text_color=TH.TEXT_DIM)
        preview.pack(side="left")

        def draw():
            img = ui.load_ctk_image(state["photo"], (100, 100))
            if img:
                preview.configure(image=img, text="")
                preview.image = img
            else:
                preview.configure(image=None, text="No photo")
        draw()

        btns = ctk.CTkFrame(photo_row, fg_color="transparent")
        btns.pack(side="left", padx=14)

        def choose():
            path = ui.pick_staff_photo(row["username"] if editing else "staff")
            if path:
                state["photo"] = path
                draw()
        ui.button(btns, "📷  Choose photo", choose, "info", 150, 32).pack(pady=2)
        ui.button(btns, "Remove", lambda: (state.update(photo=""), draw()),
                  "muted", 150, 28).pack(pady=2)

        ui.section(body, "Account")
        g = ui.form_grid(body, 2)
        e_full = ui.labelled_entry(g[0], "Full Name",
                                   row["full_name"] if editing else "",
                                   required=True)
        e_user = ui.labelled_entry(g[1], "Username",
                                   row["username"] if editing else "",
                                   required=True,
                                   placeholder="used to log in")
        if editing and row["role"] == ROLE_ADMIN:
            e_user.configure(state="disabled")

        pw_holder = ctk.CTkFrame(body, fg_color="transparent")
        e_pw = None
        if not editing:
            pw_holder.pack(fill="x")
            g_pw = ui.form_grid(pw_holder, 2)
            e_pw = ui.labelled_entry(g_pw[0], "Temporary Password",
                                     random_password(), required=True)
            ctk.CTkLabel(
                g_pw[1],
                text="The staff member must change this the first time they "
                     "log in.\nMinimum 6 characters with a letter and a "
                     "number.",
                font=ctk.CTkFont(size=F_TN), text_color=TH.TEXT_DIM,
                justify="left", wraplength=280).pack(anchor="w", pady=22)

        ui.section(body, "Personal details")
        g2 = ui.form_grid(body, 2)
        e_phone = ui.labelled_entry(g2[0], "Phone",
                                    row["phone"] if editing else "",
                                    required=True)
        e_email = ui.labelled_entry(g2[1], "Email",
                                    row["email"] if editing else "")
        e_addr = ui.labelled_entry(body, "Address",
                                   row["address"] if editing else "")
        g3 = ui.form_grid(body, 3)
        e_cit = ui.labelled_entry(g3[0], "Citizenship / ID No.",
                                  row["citizenship_no"] if editing else "")
        e_join = ui.labelled_entry(
            g3[1], "Joined Date",
            row["joined_date"] if editing
            else datetime.now().strftime("%Y-%m-%d"))
        e_sal = ui.labelled_entry(
            g3[2], "Monthly Salary",
            f"{money(row['salary']):.2f}" if editing else "0")
        e_notes = ui.labelled_entry(body, "Notes",
                                    row["notes"] if editing else "")

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=600,
                           justify="left")
        msg.pack(anchor="w", pady=(8, 0))

        def save():
            full = e_full.get().strip()
            user = e_user.get().strip()
            phone = clean_phone(e_phone.get())
            missing = ui.required_missing([("Full Name", full),
                                           ("Username", user),
                                           ("Phone", phone)])
            if missing:
                msg.configure(text="Please fill in: " + ", ".join(missing))
                return
            if " " in user:
                msg.configure(text="Username cannot contain spaces.")
                return
            clash = self.db.fetchone(
                "SELECT id FROM users WHERE username=? COLLATE NOCASE "
                "AND id != ?", (user, row["id"] if editing else -1))
            if clash:
                msg.configure(text="That username is already taken.")
                return

            joined = e_join.get().strip()
            if joined:
                try:
                    datetime.strptime(joined, "%Y-%m-%d")
                except ValueError:
                    msg.configure(text="Joined date must look like 2026-08-04.")
                    return

            common = (full, phone, e_email.get().strip(), e_addr.get().strip(),
                      state["photo"], e_cit.get().strip(),
                      parse_amount(e_sal.get()), joined,
                      e_notes.get().strip())
            try:
                if editing:
                    self.db.execute(
                        "UPDATE users SET full_name=?, phone=?, email=?, "
                        " address=?, photo_path=?, citizenship_no=?, salary=?, "
                        " joined_date=?, notes=?, username=? WHERE id=?",
                        common + (user, row["id"]))
                else:
                    pw = e_pw.get()
                    ok, why = staff_password_strength(pw)
                    if not ok:
                        msg.configure(text=why)
                        return
                    self.db.execute(
                        "INSERT INTO users (username, password_hash, role, "
                        " full_name, phone, email, address, photo_path, "
                        " citizenship_no, salary, joined_date, notes, "
                        " is_active, must_change_password) "
                        "VALUES (?,?,'staff',?,?,?,?,?,?,?,?,?,1,1)",
                        (user, hash_password(pw)) + common)
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return

            # `pw` was read above, while the dialog was still alive — never
            # touch e_pw after destroy() or Tk raises "invalid command name".
            new_password = "" if editing else pw
            d.destroy()
            self.refresh()
            if editing:
                self.toast("Staff details updated.")
            else:
                self.info(
                    "Staff account created",
                    f"Username:  {user}\n"
                    f"Temporary password:  {new_password}\n\n"
                    "Give these to the staff member. They will be asked to set "
                    "their own password the first time they log in.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💾  Save", save, "ok", 140, side="right")

    # ── details ─────────────────────────────────────────────────────
    def _profile(self):
        u = self._selected()
        if not u:
            return
        d = ui.modal(self.app, f"Staff — {u['full_name']}", 880, 660)
        ui.modal_header(d, u["full_name"],
                        f"@{u['username']}  ·  "
                        f"{'Owner' if u['role'] == ROLE_ADMIN else 'Counter staff'}")
        body = ui.modal_body(d, scroll=False)

        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        img = ui.load_ctk_image(u["photo_path"], (110, 110))
        photo = ctk.CTkLabel(top, text="" if img else "No\nphoto", image=img,
                             width=112, height=112, corner_radius=56,
                             fg_color=TH.PANEL_ALT,
                             font=ctk.CTkFont(size=F_SM),
                             text_color=TH.TEXT_DIM)
        photo.pack(side="left")
        if img:
            photo.image = img

        details = ctk.CTkFrame(top, fg_color="transparent")
        details.pack(side="left", fill="both", expand=True, padx=16)
        for label, value in (
                ("Phone", u["phone"]), ("Email", u["email"]),
                ("Address", u["address"]),
                ("Citizenship / ID", u["citizenship_no"]),
                ("Joined", u["joined_date"]),
                ("Monthly salary", self.money_text(u["salary"])),
                ("Last login", u["last_login"] or "Never"),
                ("Status", "Active" if u["is_active"] else "Disabled"),
                ("Notes", u["notes"])):
            r = ctk.CTkFrame(details, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=label, width=140, anchor="w",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=str(value or "—"), anchor="w",
                         font=ctk.CTkFont(size=F_BODY), text_color=TH.TEXT,
                         wraplength=520, justify="left").pack(
                             side="left", fill="x", expand=True)

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 6))
        agg = self.db.fetchone(
            "SELECT COUNT(*) n, COALESCE(SUM(total_amount),0) t "
            "FROM bills WHERE staff_id=?", (u["id"],))
        month = datetime.now().strftime("%Y-%m")
        m_agg = self.db.fetchone(
            "SELECT COUNT(*) n, COALESCE(SUM(total_amount),0) t FROM bills "
            "WHERE staff_id=? AND strftime('%Y-%m', bill_date)=?",
            (u["id"], month))
        ui.stat_card(cards, "Bills (all time)", f"{agg['n']:,}", TH.NAVY, 170)
        ui.stat_card(cards, "Sales (all time)", self.money_text(agg["t"]),
                     TH.ACCENT_DIM, 200)
        ui.stat_card(cards, "Bills this month", f"{m_agg['n']:,}", TH.INFO, 180)
        ui.stat_card(cards, "Sales this month", self.money_text(m_agg["t"]),
                     TH.OK, 200)

        ui.section(body, "RECENT BILLS BY THIS STAFF MEMBER")
        tree, _ = ui.make_table(
            body, ("Bill No", "Type", "Date", "Customer", "Total", "Status"),
            widths=[126, 100, 146, 210, 116, 96],
            anchors=["w", "w", "w", "w", "e", "center"], height=9)
        for b in self.db.fetchall(
                "SELECT * FROM bills WHERE staff_id=? ORDER BY id DESC LIMIT 60",
                (u["id"],)):
            tree.insert("", "end", values=(
                b["bill_number"],
                "Wholesale" if b["bill_type"] == "wholesale" else "Retail",
                str(b["bill_date"])[:16], b["customer_name"] or "Walk-in",
                f"{money(b['total_amount']):,.2f}",
                (b["payment_status"] or "paid").upper()))

        foot = ui.modal_footer(d)
        ui.button(foot, "Close", d.destroy, "muted", 100, side="right")
        ui.button(foot, "✏️  Edit", lambda: (d.destroy(), self._form(u)),
                  "primary", 110, side="right")

    # ── password / status ───────────────────────────────────────────
    def _reset_pw(self):
        u = self._selected()
        if not u:
            return
        d = ui.modal(self.app, "Reset password", 520, 430, resizable=False)
        ui.modal_header(d, "Reset password",
                        f"{u['full_name']}  (@{u['username']})", TH.WARN)
        body = ui.modal_body(d, scroll=False)

        suggestion = random_password()
        e_pw = ui.labelled_entry(body, "New password", suggestion,
                                 required=True)
        meter = ctk.CTkProgressBar(body, height=8)
        meter.pack(fill="x", pady=(8, 2))
        hint = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=F_TN),
                            text_color=TH.TEXT_DIM)
        hint.pack(anchor="w")

        def on_type(_e=None):
            score = strength_score(e_pw.get())
            meter.set(score / 4)
            meter.configure(progress_color=[TH.DANGER, TH.DANGER, TH.WARN,
                                            TH.OK, TH.OK][score])
            hint.configure(text=["Too weak", "Weak", "Fair", "Good",
                                 "Strong"][score])
        e_pw.bind("<KeyRelease>", on_type)
        on_type()

        force = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(body, text="Ask them to change it at next login",
                        variable=force, font=ctk.CTkFont(size=F_SM),
                        fg_color=TH.NAVY).pack(anchor="w", pady=8)
        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w")

        def save():
            pw = e_pw.get()
            checker = (password_strength if u["role"] == ROLE_ADMIN
                       else staff_password_strength)
            ok, why = checker(pw)
            if not ok:
                msg.configure(text=why)
                return
            self.db.execute(
                "UPDATE users SET password_hash=?, must_change_password=? "
                "WHERE id=?",
                (hash_password(pw), 1 if force.get() else 0, u["id"]))
            d.destroy()
            self.refresh()
            self.info("Password reset",
                      f"New password for @{u['username']}:\n\n{pw}\n\n"
                      "Share it with them privately.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Reset", save, "ok", 130, side="right")

    def _toggle(self):
        u = self._selected()
        if not u:
            return
        if u["id"] == self.app.user["id"]:
            self.warn("Not allowed", "You cannot disable your own account.")
            return
        if u["role"] == ROLE_ADMIN:
            others = int(self.db.scalar(
                "SELECT COUNT(*) FROM users WHERE role='admin' "
                "AND is_active=1 AND id != ?", (u["id"],), 0))
            if u["is_active"] and others == 0:
                self.warn("Not allowed",
                          "This is the only active owner account.")
                return
        new = 0 if u["is_active"] else 1
        word = "enable" if new else "disable"
        if not self.confirm(f"{word.title()} account",
                            f"{word.title()} the account for "
                            f"{u['full_name']}?"):
            return
        self.db.execute("UPDATE users SET is_active=? WHERE id=?",
                        (new, u["id"]))
        self.refresh()
        self.toast(f"Account {word}d.")

    def _delete(self):
        u = self._selected()
        if not u:
            return
        if u["id"] == self.app.user["id"]:
            self.warn("Not allowed", "You cannot delete your own account.")
            return
        if u["role"] == ROLE_ADMIN:
            self.warn("Not allowed",
                      "Owner accounts cannot be deleted — disable it instead.")
            return
        n = int(self.db.scalar("SELECT COUNT(*) FROM bills WHERE staff_id=?",
                               (u["id"],), 0))
        if n:
            self.warn("Has bill history",
                      f"{u['full_name']} has made {n} bill(s).\n\n"
                      "Disable the account instead so those bills keep their "
                      "record of who sold what.")
            return
        if not self.confirm("Delete staff account",
                            f"Permanently delete the account for "
                            f"{u['full_name']}?", danger=True):
            return
        self.db.execute("DELETE FROM users WHERE id=?", (u["id"],))
        self.refresh()
        self.toast("Staff account deleted.")

    def hotkey_search(self):
        self.search.focus_set()
