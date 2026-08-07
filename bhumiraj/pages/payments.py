"""Payments ledger — every rupee that came in, and who still owes what."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import customtkinter as ctk

from ..config import F_BODY, F_SM, RECEIPTS_DIR, TH
from ..services import money, retailer_outstanding
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page


class PaymentsPage(Page):
    title = "Payments"
    subtitle = "Money received, receipts, and who is still carrying a balance"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=300, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Receipt, bill no, party…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        today = datetime.now()
        self.range_chips = ui.FilterChips(
            bar, ["Today", "7 days", "30 days", "This year", "All"],
            lambda _v: self.refresh(), "30 days")
        self.range_chips.pack(side="left", padx=10)

        ui.button(bar, "📲  WhatsApp", self._whatsapp, "primary", 128, 36,
                  side="right")
        ui.button(bar, "🖨  Print", self._print, "info", 96, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "📄  Open Receipt", self._open, "muted", 140, 36,
                  side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        split = ctk.CTkFrame(outer, fg_color="transparent")
        split.pack(fill="both", expand=True)

        left = ctk.CTkFrame(split, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ui.section(left, "PAYMENTS RECEIVED")
        self.tree, _ = ui.make_table(
            left, ("Receipt", "Date", "Party", "Applied To", "Amount",
                   "Method", "Received By"),
            widths=[122, 106, 172, 142, 112, 108, 132],
            anchors=["w", "w", "w", "w", "e", "w", "w"],
            height=16, on_double=self._open)

        right = ctk.CTkFrame(split, fg_color="transparent", width=380)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)
        ui.section(right, "OUTSTANDING BALANCES")
        self.due_tree, _ = ui.make_table(
            right, ("Party", "Type", "Outstanding"),
            widths=[172, 92, 106], anchors=["w", "w", "e"], height=16,
            on_double=self._goto_party)
        self.refresh()

    def _date_from(self):
        chip = self.range_chips.get()
        now = datetime.now()
        if chip == "Today":
            return now.strftime("%Y-%m-%d")
        if chip == "7 days":
            return (now - timedelta(days=7)).strftime("%Y-%m-%d")
        if chip == "30 days":
            return (now - timedelta(days=30)).strftime("%Y-%m-%d")
        if chip == "This year":
            return f"{now.year}-01-01"
        return "0001-01-01"

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        for r in self.due_tree.get_children():
            self.due_tree.delete(r)

        where = ["DATE(p.payment_date) >= ?"]
        params = [self._date_from()]
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(p.receipt_number LIKE ? OR b.bill_number LIKE ? "
                         " OR r.name LIKE ? OR b.customer_name LIKE ?)")
            params += [like] * 4

        rows = self.db.fetchall(
            "SELECT p.*, b.bill_number, b.customer_name, r.name AS retailer_name, "
            "       u.full_name AS staff_name "
            "FROM payments p LEFT JOIN bills b ON p.bill_id=b.id "
            "LEFT JOIN retailers r ON p.retailer_id=r.id "
            "LEFT JOIN users u ON p.staff_id=u.id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY p.payment_date DESC, p.id DESC", params)

        self._rows = {}
        total = 0.0
        for p in rows:
            total += money(p["amount"])
            party = (p["retailer_name"] or p["customer_name"] or "Walk-in")
            iid = self.tree.insert("", "end", values=(
                p["receipt_number"] or "—", str(p["payment_date"])[:10],
                party, p["bill_number"] or "Advance / credit",
                f"{money(p['amount']):,.2f}", p["payment_method"] or "Cash",
                p["staff_name"] or "—"), tags=("pos",))
            self._rows[iid] = p

        # Outstanding: retailers first, then walk-in customers with dues
        self._due_rows = {}
        total_due = 0.0
        for r in self.db.fetchall(
                "SELECT id, name FROM retailers WHERE is_active=1 ORDER BY name"):
            due = retailer_outstanding(self.db, r["id"])
            if due <= 0.005:
                continue
            total_due += due
            iid = self.due_tree.insert("", "end", values=(
                r["name"], "Retailer", f"{due:,.2f}"), tags=("due",))
            self._due_rows[iid] = ("retailer", r["id"])

        for c in self.db.fetchall(
                "SELECT customer_name, customer_phone, "
                "       SUM(total_amount - paid_amount) due FROM bills "
                "WHERE bill_type='retail' AND payment_status != 'paid' "
                "GROUP BY customer_name, customer_phone "
                "HAVING due > 0.005 ORDER BY due DESC"):
            total_due += money(c["due"])
            iid = self.due_tree.insert("", "end", values=(
                c["customer_name"] or "Walk-in", "Customer",
                f"{money(c['due']):,.2f}"), tags=("partial",))
            self._due_rows[iid] = ("customer", c["customer_phone"])

        for w in self.stats.winfo_children():
            w.destroy()
        ui.stat_card(self.stats, "Payments listed", f"{len(rows):,}",
                     TH.NAVY, 178)
        ui.stat_card(self.stats, "Received in period",
                     self.money_text(total), TH.OK, 216)
        ui.stat_card(self.stats, "Total outstanding",
                     self.money_text(total_due), TH.DANGER, 216)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a payment first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _receipt_pdf(self, payment):
        receipt = payment["receipt_number"]
        if not receipt:
            self.warn("No receipt",
                      "This payment was taken at billing time — open the bill "
                      "PDF instead.")
            return None
        path = os.path.join(RECEIPTS_DIR, f"{receipt}.pdf")
        if not os.path.exists(path):
            try:
                self.docs.generate_receipt(receipt, path)
            except Exception as exc:
                self.error("PDF failed", str(exc))
                return None
        return path

    def _open(self):
        p = self._selected()
        if p:
            path = self._receipt_pdf(p)
            if path:
                self.open_pdf(path)

    def _print(self):
        p = self._selected()
        if p:
            path = self._receipt_pdf(p)
            if path:
                self.print_pdf(path)

    def _whatsapp(self):
        p = self._selected()
        if not p:
            return
        path = self._receipt_pdf(p)
        if not path:
            return
        phone = ""
        name = ""
        if p["retailer_id"]:
            r = self.db.fetchone("SELECT name, phone FROM retailers WHERE id=?",
                                 (p["retailer_id"],))
            if r:
                phone, name = r["phone"], r["name"]
            remaining = retailer_outstanding(self.db, p["retailer_id"])
        else:
            b = self.db.fetchone("SELECT * FROM bills WHERE id=?",
                                 (p["bill_id"],)) if p["bill_id"] else None
            if b:
                phone = b["customer_phone"]
                name = b["customer_name"]
                remaining = money(money(b["total_amount"])
                                  - money(b["paid_amount"]))
            else:
                remaining = 0.0
        if not phone:
            phone = ui.ask_text(self.app, "WhatsApp",
                                "Enter the WhatsApp number:")
            if not phone:
                return
        msg = wa.receipt_message(self.settings.get("shop_name", ""),
                                 self.settings.get("shop_phone", ""),
                                 p["receipt_number"], money(p["amount"]),
                                 name, remaining, self.cur)
        wa.send(self.app, phone, msg, path)
        self.toast("WhatsApp opened — Ctrl+V to attach the receipt.", "info")

    def _goto_party(self):
        sel = self.due_tree.selection()
        if not sel:
            return
        kind, _ident = self._due_rows.get(sel[0], (None, None))
        if kind == "retailer":
            self.app.go("retailers")
        else:
            self.app.go("customers")

    def hotkey_search(self):
        self.search.focus_set()
