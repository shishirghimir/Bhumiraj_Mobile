"""Walk-in customers — built from bill history plus a saved address book."""
from __future__ import annotations

import customtkinter as ctk

from ..config import F_BODY, F_SM, TH
from ..services import clean_phone, money
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page


class CustomersPage(Page):
    title = "Customers"
    subtitle = "Everyone who has bought over the retail counter"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=320, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Name or phone…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.dues_only = ctk.CTkCheckBox(bar, text="With dues only",
                                         font=ctk.CTkFont(size=F_SM),
                                         command=self.refresh, fg_color=TH.NAVY)
        self.dues_only.pack(side="left", padx=10)

        ui.button(bar, "📋  View Bills", self._bills, "info", 130, 36,
                  side="right")
        ui.button(bar, "📲  WhatsApp", self._whatsapp, "primary", 128, 36,
                  side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        self.tree, _ = ui.make_table(
            outer, ("Customer", "Phone", "Bills", "Total Bought", "Paid",
                    "Outstanding", "Last Purchase"),
            widths=[210, 128, 70, 130, 130, 130, 150],
            anchors=["w", "w", "center", "e", "e", "e", "w"],
            height=17, on_double=self._bills)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["b.bill_type = 'retail'"]
        params = []
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(b.customer_name LIKE ? OR b.customer_phone LIKE ?)")
            params += [like, like]

        having = ("HAVING SUM(b.total_amount - b.paid_amount) > 0.005"
                  if self.dues_only.get() else "")
        rows = self.db.fetchall(
            "SELECT b.customer_name AS name, b.customer_phone AS phone, "
            "       COUNT(*) n, COALESCE(SUM(b.total_amount),0) total, "
            "       COALESCE(SUM(b.paid_amount),0) paid, "
            "       MAX(b.bill_date) last_date "
            "FROM bills b WHERE " + " AND ".join(where) +
            " GROUP BY b.customer_name, b.customer_phone "
            f"{having} ORDER BY MAX(b.bill_date) DESC", params)

        self._rows = {}
        total_out = 0.0
        for r in rows:
            due = money(money(r["total"]) - money(r["paid"]))
            total_out += due
            iid = self.tree.insert("", "end", values=(
                r["name"] or "Walk-in", r["phone"] or "—", r["n"],
                f"{money(r['total']):,.2f}", f"{money(r['paid']):,.2f}",
                f"{due:,.2f}", str(r["last_date"])[:16]),
                tags=("due",) if due > 0.005 else ())
            self._rows[iid] = r

        for w in self.stats.winfo_children():
            w.destroy()
        ui.stat_card(self.stats, "Customers", f"{len(rows):,}", TH.NAVY, 160)
        ui.stat_card(self.stats, "Total outstanding",
                     self.money_text(total_out), TH.DANGER, 210)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a customer first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _bills(self):
        row = self._selected()
        if not row:
            return
        d = ui.modal(self.app, f"Bills — {row['name']}", 800, 560)
        ui.modal_header(d, row["name"] or "Walk-in",
                        row["phone"] or "No phone on file")
        body = ui.modal_body(d, scroll=False)
        tree, _ = ui.make_table(
            body, ("Bill No", "Date", "Items", "Total", "Paid", "Due",
                   "Status"),
            widths=[124, 140, 60, 108, 108, 108, 92],
            anchors=["w", "w", "center", "e", "e", "e", "center"], height=14)
        bills = self.db.fetchall(
            "SELECT b.*, (SELECT COUNT(*) FROM bill_items bi "
            "  WHERE bi.bill_id=b.id) n FROM bills b "
            "WHERE b.bill_type='retail' AND b.customer_name IS ? "
            "  AND IFNULL(b.customer_phone,'') = ? ORDER BY b.id DESC",
            (row["name"], row["phone"] or ""))
        for b in bills:
            due = money(money(b["total_amount"]) - money(b["paid_amount"]))
            tree.insert("", "end", values=(
                b["bill_number"], str(b["bill_date"])[:16], b["n"],
                f"{money(b['total_amount']):,.2f}",
                f"{money(b['paid_amount']):,.2f}", f"{due:,.2f}",
                (b["payment_status"] or "paid").upper()),
                tags=("due",) if due > 0.005 else ())
        ui.button(ui.modal_footer(d), "Close", d.destroy, "muted", 120,
                  side="right")

    def _whatsapp(self):
        row = self._selected()
        if not row:
            return
        phone = clean_phone(row["phone"])
        if not phone:
            self.warn("No phone", "This customer has no phone number saved.")
            return
        due = money(money(row["total"]) - money(row["paid"]))
        shop = self.settings.get("shop_name", "")
        if due > 0.005:
            msg = (f"Namaste *{row['name']}*,\n\nThis is *{shop}*.\n\n"
                   f"Our records show an outstanding balance of "
                   f"*{self.cur} {due:,.2f}*.\n\n"
                   f"Kindly clear it at your convenience.\n"
                   f"Thank you! 🙏")
        else:
            msg = (f"Namaste *{row['name']}*,\n\nThis is *{shop}*.\n\n"
                   f"Thank you for shopping with us! 🙏")
        wa.open_chat(phone, msg)
        self.toast("WhatsApp opened.", "info")

    def hotkey_search(self):
        self.search.focus_set()
