"""IMEI / Warranty register + instalment (EMI) collection.

Every handset that leaves the shop is here: who bought it, what warranty it
carries, and — if it was sold on instalments — how much is still owed.
"""
from __future__ import annotations

import os
from datetime import datetime

import customtkinter as ctk

from ..config import (F_BODY, F_LBL, F_SEC, F_SM, F_TN, PAYMENT_METHODS,
                      PLAN_INSTALLMENT, RECEIPTS_DIR, TH, WARRANTY_OPTS)
from ..services import (installment_progress, installment_schedule, money,
                        parse_amount, parse_int, warranty_expiry,
                        warranty_state)
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page


class WarrantyPage(Page):
    title = "Warranty & Instalments"
    subtitle = "IMEI register — warranty status and EMI collection"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=320, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  IMEI, customer, phone, bill no…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.chips = ui.FilterChips(
            bar, ["All", "EMI Running", "Warranty Active", "Expired"],
            lambda _v: self.refresh(), "All")
        self.chips.pack(side="left", padx=10)

        ui.button(bar, "🧾  Payment History", self._history, "info", 156, 36,
                  side="right")
        ui.button(bar, "💰  Collect Instalment", self._collect, "gold", 178, 36,
                  side="right", padx=(0, 6))
        if self.admin:
            ui.button(bar, "✏️  Edit", self._edit, "primary", 96, 36,
                      side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        self.tree, _ = ui.make_table(
            outer, ("IMEI", "Handset", "Customer", "Phone", "Sold On", "Plan",
                    "Price", "Paid", "Balance", "Warranty", "Expires"),
            widths=[142, 178, 148, 110, 100, 92, 100, 100, 100, 94, 100],
            anchors=["w", "w", "w", "w", "w", "center", "e", "e", "e",
                     "center", "w"],
            height=17, on_double=self._history)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["1=1"]
        params = []
        chip = self.chips.get()
        today = datetime.now().strftime("%Y-%m-%d")
        if chip == "EMI Running":
            where.append("r.plan_type = 'installment' AND r.status = 'active'")
        elif chip == "Warranty Active":
            where.append("r.warranty_expiry != '' AND r.warranty_expiry >= ?")
            params.append(today)
        elif chip == "Expired":
            where.append("r.warranty_expiry != '' AND r.warranty_expiry < ?")
            params.append(today)
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(r.imei LIKE ? OR r.customer_name LIKE ? "
                         " OR r.customer_phone LIKE ? OR r.bill_number LIKE ? "
                         " OR r.product_name LIKE ? OR r.brand LIKE ? "
                         " OR r.model LIKE ?)")
            params += [like] * 7

        rows = self.db.fetchall(
            "SELECT r.* FROM imei_register r WHERE " + " AND ".join(where) +
            " ORDER BY r.id DESC", params)

        self._rows = {}
        emi_due_total = 0.0
        emi_count = 0
        for r in rows:
            total, paid, due, _status = installment_progress(self.db, r["id"])
            state, days = warranty_state(r["warranty_expiry"])
            handset = " ".join(x for x in (r["brand"], r["product_name"],
                                           r["model"]) if x)
            is_emi = r["plan_type"] == PLAN_INSTALLMENT
            if is_emi and due > 0.005:
                emi_due_total += due
                emi_count += 1
            tag = ("due" if is_emi and due > 0.005
                   else "low" if state == "Expired" else "pos")
            iid = self.tree.insert("", "end", values=(
                r["imei"], handset[:34], r["customer_name"] or "—",
                r["customer_phone"] or "—", str(r["sold_date"])[:10],
                "EMI" if is_emi else "Full",
                f"{money(total):,.2f}", f"{money(paid):,.2f}",
                f"{money(due):,.2f}",
                f"{state}" + (f" ({days}d)" if state == "Active"
                              and days <= 60 else ""),
                r["warranty_expiry"] or "—"), tags=(tag,))
            self._rows[iid] = r

        for w in self.stats.winfo_children():
            w.destroy()
        ui.stat_card(self.stats, "Handsets registered", f"{len(rows):,}",
                     TH.NAVY, 196)
        ui.stat_card(self.stats, "EMI accounts open", f"{emi_count:,}",
                     TH.WARN, 176)
        ui.stat_card(self.stats, "EMI outstanding",
                     self.money_text(emi_due_total), TH.DANGER, 210)
        active = int(self.db.scalar(
            "SELECT COUNT(*) FROM imei_register "
            "WHERE warranty_expiry != '' AND warranty_expiry >= ?",
            (datetime.now().strftime("%Y-%m-%d"),), 0))
        ui.stat_card(self.stats, "Warranties active", f"{active:,}",
                     TH.OK, 190)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a handset record first.", "warn")
            return None
        return self._rows.get(sel[0])

    # ── collect an instalment ───────────────────────────────────────
    def _collect(self):
        reg = self._selected()
        if not reg:
            return
        total, paid, due, _st = installment_progress(self.db, reg["id"])
        if due <= 0.005:
            self.info("Fully paid",
                      "This handset has been paid off in full.")
            return

        d = ui.modal(self.app, "Collect instalment", 580, 590)
        ui.modal_header(d, "Collect instalment",
                        f"{reg['brand']} {reg['product_name']}  ·  "
                        f"IMEI {reg['imei']}", "#7a4a12")
        body = ui.modal_body(d)

        card = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        card.pack(fill="x", pady=(0, 10))
        for label, value, color in (
                ("Customer", reg["customer_name"] or "—", None),
                ("Phone", reg["customer_phone"] or "—", None),
                ("Handset price", self.money_text(total), None),
                ("Paid so far", self.money_text(paid), TH.POS),
                ("Balance", self.money_text(due), TH.DANGER),
                ("Agreed monthly",
                 self.money_text(reg["installment_amount"]), TH.ACCENT)):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(r, text=label, font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=str(value),
                         font=ctk.CTkFont(size=F_BODY, weight="bold"),
                         text_color=color or TH.TEXT).pack(side="right")

        suggested = money(reg["installment_amount"]) or due
        if suggested > due:
            suggested = due
        e_amt = ui.labelled_entry(body, "Amount received",
                                  f"{suggested:.2f}", required=True)
        g = ui.form_grid(body, 2)
        c_method = ui.labelled_combo(g[0], "Method", PAYMENT_METHODS,
                                     self.settings.get("default_payment", "Cash"))
        e_date = ui.labelled_entry(g[1], "Date",
                                   datetime.now().strftime("%Y-%m-%d"))
        e_note = ui.labelled_entry(body, "Note")

        after = ctk.CTkLabel(body, text="",
                             font=ctk.CTkFont(size=F_BODY, weight="bold"),
                             text_color=TH.ACCENT)
        after.pack(anchor="w", pady=(6, 0))

        def preview(_e=None):
            amt = parse_amount(e_amt.get())
            left = money(due - amt)
            if amt > due + 0.005:
                after.configure(
                    text=f"That is more than the balance "
                         f"({self.money_text(due)}).", text_color=TH.DANGER)
            elif left <= 0.005:
                after.configure(text="✅ This clears the handset in full.",
                                text_color=TH.POS)
            else:
                after.configure(text=f"Balance after this payment: "
                                     f"{self.money_text(left)}",
                                text_color=TH.ACCENT)
        e_amt.bind("<KeyRelease>", preview)
        preview()

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=500,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            amount = parse_amount(e_amt.get())
            if amount <= 0.005:
                msg.configure(text="Enter an amount greater than zero.")
                return
            if amount > due + 0.005:
                msg.configure(text=f"Cannot take more than the balance "
                                   f"({self.money_text(due)}).")
                return
            receipt = self.db.next_installment_receipt()
            try:
                with self.db.transaction() as cur:
                    cur.execute(
                        "INSERT INTO imei_payments (register_id, "
                        " receipt_number, payment_date, amount, "
                        " payment_method, notes, staff_id) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (reg["id"], receipt, e_date.get().strip(), amount,
                         c_method.get(), e_note.get().strip(),
                         self.staff_id()))
                    if money(due - amount) <= 0.005:
                        cur.execute(
                            "UPDATE imei_register SET status='closed' "
                            "WHERE id=?", (reg["id"],))
                pay_id = self.db.scalar(
                    "SELECT id FROM imei_payments WHERE receipt_number=? "
                    "ORDER BY id DESC LIMIT 1", (receipt,), None)
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return

            d.destroy()
            self.refresh()
            path = os.path.join(RECEIPTS_DIR, f"{receipt}.pdf")
            try:
                self.docs.generate_installment_receipt(pay_id, path)
                self.app.remember_pdf(path)
            except Exception:
                path = None
            self._done_dialog(receipt, amount, money(due - amount), path, reg)

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💰  Record", save, "ok", 150, side="right")

    def _done_dialog(self, receipt, amount, remaining, path, reg):
        d = ui.modal(self.app, f"Receipt {receipt}", 520, 400, resizable=False)
        ui.modal_header(d, "✅  INSTALMENT RECEIVED", receipt, TH.OK)
        body = ui.modal_body(d, scroll=False)
        ctk.CTkLabel(body, text=f"{self.cur} {money(amount):,.2f} received",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TH.POS).pack(anchor="w")
        ctk.CTkLabel(body,
                     text=("🎉 Handset fully paid off!" if remaining <= 0.005
                           else f"Remaining balance: "
                                f"{self.money_text(remaining)}"),
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color=TH.POS if remaining <= 0.005 else TH.DANGER
                     ).pack(anchor="w", pady=(4, 14))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x")

        def act(kind):
            d.destroy()
            if not path:
                return
            if kind == "print":
                self.print_pdf(path)
            elif kind == "open":
                self.open_pdf(path)
            elif kind == "wa":
                phone = reg["customer_phone"] or ui.ask_text(
                    self.app, "WhatsApp", "Enter the WhatsApp number:")
                if phone:
                    msg = wa.receipt_message(
                        self.settings.get("shop_name", ""),
                        self.settings.get("shop_phone", ""), receipt, amount,
                        reg["customer_name"] or "", remaining, self.cur)
                    wa.send(self.app, phone, msg, path)

        ui.button(btns, "🖨  PRINT", lambda: act("print"), "ok", 142, 46,
                  side="left")
        ui.button(btns, "📄  OPEN", lambda: act("open"), "info", 142, 46,
                  side="left", padx=(6, 0))
        ui.button(btns, "📲  WHATSAPP", lambda: act("wa"), "primary", 142, 46,
                  side="left", padx=(6, 0))
        ui.button(ui.modal_footer(d), "DONE", d.destroy, "muted", 120,
                  side="right")

    # ── history ─────────────────────────────────────────────────────
    def _history(self):
        reg = self._selected()
        if not reg:
            return
        total, paid, due, status = installment_progress(self.db, reg["id"])
        d = ui.modal(self.app, f"IMEI {reg['imei']}", 760, 620)
        ui.modal_header(
            d, " ".join(x for x in (reg["brand"], reg["product_name"],
                                    reg["model"]) if x),
            f"IMEI {reg['imei']}  ·  Bill {reg['bill_number'] or '—'}")
        body = ui.modal_body(d, scroll=False)

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 8))
        ui.stat_card(cards, "Price", self.money_text(total), TH.NAVY, 168)
        ui.stat_card(cards, "Paid", self.money_text(paid), TH.OK, 168)
        ui.stat_card(cards, "Balance", self.money_text(due),
                     TH.DANGER if due > 0.005 else TH.POS, 168)
        state, days = warranty_state(reg["warranty_expiry"])
        ui.stat_card(cards, "Warranty",
                     state + (f"  ·  {days}d" if state == "Active" else ""),
                     TH.POS if state == "Active" else TH.MUTED, 190)

        info = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        info.pack(fill="x", pady=(0, 8))
        grid = ctk.CTkFrame(info, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=10)
        pairs = [
            ("Customer", reg["customer_name"] or "—"),
            ("Phone", reg["customer_phone"] or "—"),
            ("Sold on", str(reg["sold_date"])[:10] or "—"),
            ("Colour / Storage",
             " · ".join(x for x in (reg["color"], reg["storage"]) if x) or "—"),
            ("Plan", "Instalment / EMI"
             if reg["plan_type"] == PLAN_INSTALLMENT else "Full payment"),
            ("Down payment", self.money_text(reg["down_payment"])),
            ("Monthly", self.money_text(reg["installment_amount"])),
            ("Months", str(reg["installment_months"] or "—")),
            ("Warranty", f"{reg['warranty_months']} months"),
            ("Expires", reg["warranty_expiry"] or "—"),
        ]
        for i, (label, value) in enumerate(pairs):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 28),
                      pady=2)
            ctk.CTkLabel(cell, text=label + ":", width=130, anchor="w",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(cell, text=str(value), anchor="w",
                         font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.TEXT).pack(side="left")

        ui.section(body, "PAYMENT HISTORY")
        tree, _ = ui.make_table(
            body, ("Receipt", "Date", "Amount", "Method", "Note",
                   "Received By"),
            widths=[120, 110, 110, 110, 180, 130],
            anchors=["w", "w", "e", "w", "w", "w"], height=8)
        pay_map = {}
        if money(reg["down_payment"]) > 0:
            tree.insert("", "end", values=(
                "—", str(reg["sold_date"])[:10],
                f"{money(reg['down_payment']):,.2f}", "At sale",
                "Down payment", "—"), tags=("muted",))
        for p in self.db.fetchall(
                "SELECT p.*, u.full_name FROM imei_payments p "
                "LEFT JOIN users u ON p.staff_id=u.id "
                "WHERE p.register_id=? ORDER BY p.payment_date, p.id",
                (reg["id"],)):
            iid = tree.insert("", "end", values=(
                p["receipt_number"] or "—", str(p["payment_date"])[:10],
                f"{money(p['amount']):,.2f}", p["payment_method"] or "Cash",
                p["notes"] or "—", p["full_name"] or "—"), tags=("pos",))
            pay_map[iid] = p

        def reprint():
            sel = tree.selection()
            if not sel or sel[0] not in pay_map:
                self.toast("Select a payment row.", "warn")
                return
            p = pay_map[sel[0]]
            stem = p["receipt_number"] or ("IP-%s" % p["id"])
            path = os.path.join(RECEIPTS_DIR, stem + ".pdf")
            try:
                self.docs.generate_installment_receipt(p["id"], path)
            except Exception as exc:
                self.error("PDF failed", str(exc))
                return
            self.open_pdf(path)

        foot = ui.modal_footer(d)
        ui.button(foot, "Close", d.destroy, "muted", 100, side="right")
        ui.button(foot, "📄  Reprint Receipt", reprint, "info", 168,
                  side="right")

    # ── edit warranty terms ─────────────────────────────────────────
    def _edit(self):
        if self.deny_staff("edit warranty records"):
            return
        reg = self._selected()
        if not reg:
            return
        d = ui.modal(self.app, "Edit warranty record", 560, 520)
        ui.modal_header(d, "Edit warranty record", f"IMEI {reg['imei']}")
        body = ui.modal_body(d)

        g = ui.form_grid(body, 2)
        e_cust = ui.labelled_entry(g[0], "Customer Name",
                                   reg["customer_name"], required=True)
        e_phone = ui.labelled_entry(g[1], "Phone", reg["customer_phone"])
        c_warr = ui.labelled_combo(g[0], "Warranty (months)", WARRANTY_OPTS,
                                   str(reg["warranty_months"]))
        e_sold = ui.labelled_entry(g[1], "Sold Date",
                                   str(reg["sold_date"])[:10])
        g2 = ui.form_grid(body, 2)
        e_monthly = ui.labelled_entry(
            g2[0], "Monthly instalment",
            f"{money(reg['installment_amount']):.2f}")
        e_months = ui.labelled_entry(g2[1], "Months",
                                     str(reg["installment_months"] or 0))
        e_note = ui.labelled_entry(body, "Notes", reg["notes"])

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=480,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            name = e_cust.get().strip()
            if not name:
                msg.configure(text="Customer name is required.")
                return
            sold = e_sold.get().strip()
            try:
                datetime.strptime(sold, "%Y-%m-%d")
            except ValueError:
                msg.configure(text="Sold date must look like 2026-08-04.")
                return
            months = parse_int(c_warr.get())
            self.db.execute(
                "UPDATE imei_register SET customer_name=?, customer_phone=?, "
                " warranty_months=?, warranty_expiry=?, sold_date=?, "
                " installment_amount=?, installment_months=?, notes=? "
                "WHERE id=?",
                (name, e_phone.get().strip(), months,
                 warranty_expiry(sold, months), sold,
                 parse_amount(e_monthly.get()), parse_int(e_months.get()),
                 e_note.get().strip(), reg["id"]))
            d.destroy()
            self.refresh()
            self.toast("Record updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Save", save, "ok", 130, side="right")

    def hotkey_search(self):
        self.search.focus_set()
