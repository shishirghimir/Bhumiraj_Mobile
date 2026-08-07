"""Retailers (wholesale customers) — profile, ledger, FIFO payments, statement.

Admin-only page. Staff can bill a retailer but never see their money history.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import customtkinter as ctk

from ..config import (BILLS_DIR, F_BODY, F_LBL, F_SEC, F_SM, F_TN,
                      PAYMENT_METHODS, RECEIPTS_DIR, TH)
from ..services import (clean_phone, money, parse_amount, plan_fifo_allocation,
                        record_retailer_payment, retailer_outstanding)
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page


class RetailersPage(Page):
    title = "Retailers"
    subtitle = "Wholesale customers, their dues and their statements"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=310, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Name, shop, phone, city…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.dues_only = ctk.CTkCheckBox(bar, text="With dues only",
                                         font=ctk.CTkFont(size=F_SM),
                                         command=self.refresh, fg_color=TH.NAVY)
        self.dues_only.pack(side="left", padx=10)

        ui.button(bar, "🗑  Delete", self._delete, "danger", 100, 36,
                  side="right")
        ui.button(bar, "📄  Statement", self._statement, "info", 126, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "💰  Record Payment", self._payment, "gold", 164, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "👁  Profile", self._profile, "primary", 108, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "➕  Add Retailer", lambda: self._form(None), "ok",
                  148, 36, side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        self.tree, _ = ui.make_table(
            outer, ("Name", "Shop", "Phone", "City", "Bills", "Total Business",
                    "Paid", "Outstanding", "Last Bill"),
            widths=[168, 168, 116, 106, 60, 130, 122, 126, 128],
            anchors=["w", "w", "w", "w", "center", "e", "e", "e", "w"],
            height=17, on_double=self._profile)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["r.is_active = 1"]
        params = []
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(r.name LIKE ? OR r.shop_name LIKE ? OR r.phone LIKE ? "
                         " OR r.city LIKE ? OR r.address LIKE ?)")
            params += [like] * 5

        rows = self.db.fetchall(
            "SELECT r.*, "
            " (SELECT COUNT(*) FROM bills b WHERE b.retailer_id=r.id) n, "
            " (SELECT COALESCE(SUM(b.total_amount),0) FROM bills b "
            "   WHERE b.retailer_id=r.id) total, "
            " (SELECT COALESCE(SUM(b.paid_amount),0) FROM bills b "
            "   WHERE b.retailer_id=r.id) paid, "
            " (SELECT MAX(b.bill_date) FROM bills b "
            "   WHERE b.retailer_id=r.id) last_bill "
            "FROM retailers r WHERE " + " AND ".join(where) +
            " ORDER BY r.name", params)

        self._rows = {}
        total_out = 0.0
        shown = 0
        for r in rows:
            due = retailer_outstanding(self.db, r["id"])
            if self.dues_only.get() and due <= 0.005:
                continue
            shown += 1
            total_out += due
            iid = self.tree.insert("", "end", values=(
                r["name"], r["shop_name"] or "—", r["phone"] or "—",
                r["city"] or "—", r["n"], f"{money(r['total']):,.2f}",
                f"{money(r['paid']):,.2f}", f"{due:,.2f}",
                str(r["last_bill"])[:16] if r["last_bill"] else "—"),
                tags=("due",) if due > 0.005 else ("pos",))
            self._rows[iid] = r

        for w in self.stats.winfo_children():
            w.destroy()
        ui.stat_card(self.stats, "Retailers", f"{shown:,}", TH.WHOLESALE, 158)
        ui.stat_card(self.stats, "Total outstanding",
                     self.money_text(total_out), TH.DANGER, 216)
        collected = money(self.db.scalar(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE retailer_id IS NOT NULL AND strftime('%Y-%m', payment_date)=?",
            (datetime.now().strftime("%Y-%m"),), 0))
        ui.stat_card(self.stats, "Collected this month",
                     self.money_text(collected), TH.OK, 220)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a retailer first.", "warn")
            return None
        return self._rows.get(sel[0])

    # ── add / edit ──────────────────────────────────────────────────
    def _form(self, row):
        editing = row is not None
        d = ui.modal(self.app, "Edit retailer" if editing else "Add retailer",
                     640, 620)
        ui.modal_header(d, "Edit retailer" if editing else "Add retailer",
                        "Wholesale customer details")
        body = ui.modal_body(d)

        g = ui.form_grid(body, 2)
        e_name = ui.labelled_entry(g[0], "Contact Name",
                                   row["name"] if editing else "",
                                   required=True)
        e_shop = ui.labelled_entry(g[1], "Shop Name",
                                   row["shop_name"] if editing else "")
        e_phone = ui.labelled_entry(g[0], "Phone",
                                    row["phone"] if editing else "",
                                    required=True, placeholder="98XXXXXXXX")
        e_alt = ui.labelled_entry(g[1], "Alternate Phone",
                                  row["alt_phone"] if editing else "")
        e_email = ui.labelled_entry(g[0], "Email",
                                    row["email"] if editing else "")
        e_city = ui.labelled_entry(g[1], "City",
                                   row["city"] if editing else "")
        e_addr = ui.labelled_entry(body, "Address",
                                   row["address"] if editing else "")
        g2 = ui.form_grid(body, 3)
        e_pan = ui.labelled_entry(g2[0], "PAN / VAT No.",
                                  row["pan_number"] if editing else "")
        e_open = ui.labelled_entry(
            g2[1], "Opening Balance (they owe)",
            f"{money(row['opening_balance']):.2f}" if editing else "0")
        e_limit = ui.labelled_entry(
            g2[2], "Credit Limit (0 = none)",
            f"{money(row['credit_limit']):.2f}" if editing else "0")
        e_notes = ui.labelled_entry(body, "Notes",
                                    row["notes"] if editing else "")

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=560,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            name = e_name.get().strip()
            phone = clean_phone(e_phone.get())
            missing = ui.required_missing([("Contact Name", name),
                                           ("Phone", phone)])
            if missing:
                msg.configure(text="Please fill in: " + ", ".join(missing))
                return
            clash = self.db.fetchone(
                "SELECT id FROM retailers WHERE phone=? AND id != ?",
                (phone, row["id"] if editing else -1))
            if clash:
                msg.configure(text="Another retailer already uses that phone "
                                   "number.")
                return
            params = (name, e_shop.get().strip(), phone,
                      clean_phone(e_alt.get()), e_email.get().strip(),
                      e_addr.get().strip(), e_city.get().strip(),
                      e_pan.get().strip(), parse_amount(e_open.get()),
                      parse_amount(e_limit.get()), e_notes.get().strip())
            try:
                if editing:
                    self.db.execute(
                        "UPDATE retailers SET name=?, shop_name=?, phone=?, "
                        " alt_phone=?, email=?, address=?, city=?, "
                        " pan_number=?, opening_balance=?, credit_limit=?, "
                        " notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        params + (row["id"],))
                else:
                    self.db.execute(
                        "INSERT INTO retailers (name, shop_name, phone, "
                        " alt_phone, email, address, city, pan_number, "
                        " opening_balance, credit_limit, notes) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", params)
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return
            d.destroy()
            self.refresh()
            self.toast("Retailer saved.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💾  Save", save, "ok", 140, side="right")

    # ── profile ─────────────────────────────────────────────────────
    def _profile(self):
        row = self._selected()
        if not row:
            return
        rid = row["id"]
        d = ui.modal(self.app, f"Retailer — {row['name']}", 940, 700)
        due = retailer_outstanding(self.db, rid)
        ui.modal_header(d, row["name"],
                        f"{row['shop_name'] or ''}  ·  {row['phone'] or ''}",
                        "#3b2f7a")
        body = ui.modal_body(d, scroll=False)

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 8))
        agg = self.db.fetchone(
            "SELECT COUNT(*) n, COALESCE(SUM(total_amount),0) t, "
            " COALESCE(SUM(paid_amount),0) p FROM bills WHERE retailer_id=?",
            (rid,))
        ui.stat_card(cards, "Total business", self.money_text(agg["t"]),
                     TH.NAVY, 190)
        ui.stat_card(cards, "Paid", self.money_text(agg["p"]), TH.OK, 176)
        ui.stat_card(cards, "Outstanding", self.money_text(due),
                     TH.DANGER if due > 0.005 else TH.POS, 190)
        ui.stat_card(cards, "Bills", f"{agg['n']:,}", TH.INFO, 130)

        tabs = ctk.CTkTabview(body, fg_color=TH.PANEL,
                              segmented_button_selected_color=TH.NAVY)
        tabs.pack(fill="both", expand=True)
        t_bills = tabs.add("Bills")
        t_pay = tabs.add("Payments")
        t_info = tabs.add("Details")

        bt, _ = ui.make_table(
            t_bills, ("Bill No", "Date", "Items", "Total", "Paid", "Due",
                      "Status"),
            widths=[126, 140, 60, 112, 112, 112, 92],
            anchors=["w", "w", "center", "e", "e", "e", "center"], height=12)
        bill_map = {}
        for b in self.db.fetchall(
                "SELECT b.*, (SELECT COUNT(*) FROM bill_items bi "
                " WHERE bi.bill_id=b.id) n FROM bills b "
                "WHERE b.retailer_id=? ORDER BY b.bill_date DESC, b.id DESC",
                (rid,)):
            bdue = money(money(b["total_amount"]) - money(b["paid_amount"]))
            iid = bt.insert("", "end", values=(
                b["bill_number"], str(b["bill_date"])[:16], b["n"],
                f"{money(b['total_amount']):,.2f}",
                f"{money(b['paid_amount']):,.2f}", f"{bdue:,.2f}",
                (b["payment_status"] or "paid").upper()),
                tags=("due",) if bdue > 0.005 else ())
            bill_map[iid] = b

        def open_bill():
            sel = bt.selection()
            if not sel:
                return
            b = bill_map[sel[0]]
            path = os.path.join(BILLS_DIR, f"{b['bill_number']}.pdf")
            if not os.path.exists(path):
                try:
                    self.docs.generate_bill(b["id"], path)
                except Exception as exc:
                    self.error("PDF failed", str(exc))
                    return
            self.open_pdf(path)
        bt.bind("<Double-1>", lambda _e: open_bill())

        pt, _ = ui.make_table(
            t_pay, ("Receipt", "Date", "Applied To", "Amount", "Method",
                    "Reference"),
            widths=[126, 120, 150, 116, 116, 170],
            anchors=["w", "w", "w", "e", "w", "w"], height=12)
        for p in self.db.fetchall(
                "SELECT p.*, b.bill_number FROM payments p "
                "LEFT JOIN bills b ON p.bill_id=b.id "
                "WHERE p.retailer_id=? ORDER BY p.payment_date DESC, p.id DESC",
                (rid,)):
            pt.insert("", "end", values=(
                p["receipt_number"] or "—", str(p["payment_date"])[:10],
                p["bill_number"] or "Advance / credit",
                f"{money(p['amount']):,.2f}", p["payment_method"] or "Cash",
                p["reference"] or "—"), tags=("pos",))

        info = ctk.CTkScrollableFrame(t_info, fg_color="transparent")
        info.pack(fill="both", expand=True)
        for label, value in (
                ("Contact name", row["name"]), ("Shop", row["shop_name"]),
                ("Phone", row["phone"]), ("Alternate phone", row["alt_phone"]),
                ("Email", row["email"]), ("Address", row["address"]),
                ("City", row["city"]), ("PAN / VAT", row["pan_number"]),
                ("Opening balance",
                 self.money_text(row["opening_balance"])),
                ("Credit limit",
                 self.money_text(row["credit_limit"]) or "None"),
                ("Notes", row["notes"]),
                ("Added on", str(row["created_at"])[:10])):
            r = ctk.CTkFrame(info, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=label, width=150, anchor="w",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=str(value or "—"), anchor="w",
                         font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.TEXT, wraplength=560,
                         justify="left").pack(side="left", fill="x", expand=True)

        foot = ui.modal_footer(d)
        ui.button(foot, "Close", d.destroy, "muted", 100, side="right")
        ui.button(foot, "✏️  Edit", lambda: (d.destroy(), self._form(row)),
                  "primary", 110, side="right")
        ui.button(foot, "📄  Statement",
                  lambda: (d.destroy(), self._statement()), "info", 130,
                  side="right")
        ui.button(foot, "💰  Record Payment",
                  lambda: (d.destroy(), self._payment()), "gold", 168,
                  side="right")
        ui.button(foot, "📄  Open Bill PDF", open_bill, "muted", 148,
                  side="left")

    # ── FIFO payment ────────────────────────────────────────────────
    def _payment(self):
        row = self._selected()
        if not row:
            return
        rid = row["id"]
        due = retailer_outstanding(self.db, rid)
        if due <= 0.005:
            if not self.confirm("No dues",
                                f"{row['name']} has no outstanding balance.\n\n"
                                "Record an advance payment anyway?"):
                return

        d = ui.modal(self.app, "Record payment", 720, 660)
        ui.modal_header(d, f"Payment from {row['name']}",
                        "Applied to the OLDEST unpaid bills first (FIFO)",
                        TH.OK)
        body = ui.modal_body(d)

        ctk.CTkLabel(body, text=f"Outstanding: {self.money_text(due)}",
                     font=ctk.CTkFont(size=F_SEC, weight="bold"),
                     text_color=TH.DANGER if due > 0.005 else TH.POS).pack(
                         anchor="w", pady=(0, 8))

        g = ui.form_grid(body, 2)
        e_amt = ui.labelled_entry(g[0], "Amount received",
                                  f"{due:.2f}" if due > 0 else "",
                                  required=True)
        c_method = ui.labelled_combo(g[1], "Method", PAYMENT_METHODS,
                                     self.settings.get("default_payment", "Cash"))
        g2 = ui.form_grid(body, 2)
        e_date = ui.labelled_entry(g2[0], "Date",
                                   datetime.now().strftime("%Y-%m-%d"))
        e_ref = ui.labelled_entry(g2[1], "Reference (cheque / txn)")
        e_note = ui.labelled_entry(body, "Note")

        ui.section(body, "How this payment will be applied")
        prev, _ = ui.make_table(
            body, ("Bill No", "Bill Date", "Due Before", "Applied",
                   "Due After", "New Status"),
            widths=[126, 118, 116, 116, 116, 108],
            anchors=["w", "w", "e", "e", "e", "center"], height=8)
        summary = ctk.CTkLabel(body, text="",
                               font=ctk.CTkFont(size=F_BODY, weight="bold"),
                               text_color=TH.ACCENT, justify="left")
        summary.pack(anchor="w", pady=(6, 0))

        def preview(_e=None):
            for r in prev.get_children():
                prev.delete(r)
            amount = parse_amount(e_amt.get())
            open_bills = self.db.fetchall(
                "SELECT id, bill_number, bill_date, total_amount, paid_amount "
                "FROM bills WHERE retailer_id=? AND payment_status != 'paid' "
                "ORDER BY DATE(bill_date) ASC, id ASC", (rid,))
            allocations, leftover = plan_fifo_allocation(open_bills, amount)
            for a in allocations:
                prev.insert("", "end", values=(
                    a["bill_number"], str(a["bill_date"])[:10],
                    f"{a['before_due']:,.2f}", f"{a['applied']:,.2f}",
                    f"{a['after_due']:,.2f}", a["status"].upper()),
                    tags=("pos",) if a["after_due"] <= 0.005 else ("partial",))
            parts = [f"{len(allocations)} bill(s) will be updated"]
            if leftover > 0.005:
                parts.append(f"{self.cur} {leftover:,.2f} kept as advance")
            remaining = money(due - amount)
            if remaining > 0.005:
                parts.append(f"remaining due {self.cur} {remaining:,.2f}")
            elif amount >= due - 0.005 and due > 0:
                parts.append("account fully settled ✅")
            summary.configure(text="   ·   ".join(parts))
        e_amt.bind("<KeyRelease>", preview)
        preview()

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=620,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            amount = parse_amount(e_amt.get())
            if amount <= 0.005:
                msg.configure(text="Enter an amount greater than zero.")
                return
            try:
                receipt, allocations, leftover = record_retailer_payment(
                    self.db, rid, amount, c_method.get(), e_date.get().strip(),
                    e_ref.get().strip(), e_note.get().strip(), self.staff_id())
            except Exception as exc:
                msg.configure(text=str(exc))
                return
            d.destroy()
            self.refresh()
            path = os.path.join(RECEIPTS_DIR, f"{receipt}.pdf")
            try:
                self.docs.generate_receipt(receipt, path)
                self.app.remember_pdf(path)
            except Exception:
                path = None
            self._receipt_done(receipt, amount, allocations, leftover, path,
                               row)

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💰  Record Payment", save, "ok", 178, side="right")

    def _receipt_done(self, receipt, amount, allocations, leftover, path, row):
        d = ui.modal(self.app, f"Receipt {receipt}", 560, 470, resizable=False)
        ui.modal_header(d, "✅  PAYMENT RECORDED", receipt, TH.OK)
        body = ui.modal_body(d)
        ctk.CTkLabel(body, text=f"{self.cur} {money(amount):,.2f} received "
                                f"from {row['name']}",
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color=TH.POS, wraplength=480,
                     justify="left").pack(anchor="w", pady=(0, 8))
        lines = "\n".join(
            f"  • {a['bill_number']}:  {self.cur} {a['applied']:,.2f} applied  "
            f"→  due {self.cur} {a['after_due']:,.2f}" for a in allocations)
        if leftover > 0.005:
            lines += f"\n  • {self.cur} {leftover:,.2f} kept as advance credit"
        ctk.CTkLabel(body, text=lines or "  • kept as advance credit",
                     font=ctk.CTkFont(size=F_SM), text_color=TH.TEXT,
                     justify="left", wraplength=480).pack(anchor="w")
        new_due = retailer_outstanding(self.db, row["id"])
        ctk.CTkLabel(body,
                     text=f"\nRemaining outstanding: {self.money_text(new_due)}",
                     font=ctk.CTkFont(size=F_BODY, weight="bold"),
                     text_color=TH.DANGER if new_due > 0.005 else TH.POS).pack(
                         anchor="w")

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", pady=(12, 0))

        def act(kind):
            d.destroy()
            if not path:
                return
            if kind == "print":
                self.print_pdf(path)
            elif kind == "open":
                self.open_pdf(path)
            elif kind == "wa":
                msg = wa.receipt_message(
                    self.settings.get("shop_name", ""),
                    self.settings.get("shop_phone", ""), receipt, amount,
                    row["name"], new_due, self.cur)
                wa.send(self.app, row["phone"], msg, path)

        ui.button(btns, "🖨  PRINT", lambda: act("print"), "ok", 140, 44,
                  side="left")
        ui.button(btns, "📄  OPEN", lambda: act("open"), "info", 140, 44,
                  side="left", padx=(6, 0))
        ui.button(btns, "📲  WHATSAPP", lambda: act("wa"), "primary", 148, 44,
                  side="left", padx=(6, 0))
        ui.button(ui.modal_footer(d), "DONE", d.destroy, "muted", 120,
                  side="right")

    # ── statement ───────────────────────────────────────────────────
    def _statement(self):
        row = self._selected()
        if not row:
            return
        d = ui.modal(self.app, "Statement of account", 520, 380,
                     resizable=False)
        ui.modal_header(d, "Statement of account", row["name"], "#3b2f7a")
        body = ui.modal_body(d, scroll=False)

        today = datetime.now()
        g = ui.form_grid(body, 2)
        e_from = ui.labelled_entry(g[0], "From (YYYY-MM-DD)",
                                   (today - timedelta(days=90)
                                    ).strftime("%Y-%m-%d"), required=True)
        e_to = ui.labelled_entry(g[1], "To (YYYY-MM-DD)",
                                 today.strftime("%Y-%m-%d"), required=True)

        quick = ctk.CTkFrame(body, fg_color="transparent")
        quick.pack(fill="x", pady=6)

        def set_range(days):
            e_from.delete(0, "end")
            e_from.insert(0, (today - timedelta(days=days)).strftime("%Y-%m-%d"))
            e_to.delete(0, "end")
            e_to.insert(0, today.strftime("%Y-%m-%d"))

        for label, days in (("Last 30 days", 30), ("Last 90 days", 90),
                            ("Last year", 365)):
            ui.button(quick, label, lambda d_=days: set_range(d_), "muted",
                      118, 30, side="left", padx=3)

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(8, 0))

        def make(action):
            d_from, d_to = e_from.get().strip(), e_to.get().strip()
            for value in (d_from, d_to):
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    msg.configure(text="Dates must look like 2026-08-04.")
                    return
            if d_from > d_to:
                msg.configure(text="'From' date must be before 'To' date.")
                return
            path = os.path.join(
                RECEIPTS_DIR,
                f"Statement_{row['name'].replace(' ', '_')}_{d_from}_{d_to}.pdf")
            try:
                self.docs.generate_statement(row["id"], d_from, d_to, path)
                self.app.remember_pdf(path)
            except Exception as exc:
                msg.configure(text=f"Could not build the statement: {exc}")
                return
            d.destroy()
            if action == "print":
                self.print_pdf(path)
            elif action == "wa":
                closing = retailer_outstanding(self.db, row["id"])
                message = wa.statement_message(
                    self.settings.get("shop_name", ""),
                    self.settings.get("shop_phone", ""), row["name"],
                    d_from, d_to, closing, self.cur)
                wa.send(self.app, row["phone"], message, path)
                self.toast("WhatsApp opened — Ctrl+V to attach.", "info")
            else:
                self.open_pdf(path)

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 96, side="right")
        ui.button(foot, "📲  WhatsApp", lambda: make("wa"), "primary", 128,
                  side="right")
        ui.button(foot, "🖨  Print", lambda: make("print"), "info", 104,
                  side="right")
        ui.button(foot, "📄  Open", lambda: make("open"), "ok", 104,
                  side="right")

    def _delete(self):
        row = self._selected()
        if not row:
            return
        n = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE retailer_id=?", (row["id"],), 0))
        due = retailer_outstanding(self.db, row["id"])
        if due > 0.005:
            self.warn("Outstanding balance",
                      f"{row['name']} still owes {self.money_text(due)}.\n\n"
                      "Settle the account before removing them.")
            return
        if n:
            if not self.confirm(
                    "Archive retailer",
                    f"{row['name']} has {n} bill(s) in history.\n\n"
                    "They will be ARCHIVED (hidden from the list) so those "
                    "bills stay intact. Continue?"):
                return
            self.db.execute("UPDATE retailers SET is_active=0 WHERE id=?",
                            (row["id"],))
            self.toast("Retailer archived.")
        else:
            if not self.confirm("Delete retailer",
                                f"Permanently delete {row['name']}?",
                                danger=True):
                return
            self.db.execute("DELETE FROM retailers WHERE id=?", (row["id"],))
            self.toast("Retailer deleted.")
        self.refresh()

    def hotkey_search(self):
        self.search.focus_set()
