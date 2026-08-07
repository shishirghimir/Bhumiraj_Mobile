"""Dashboard.

The owner sees the full picture — revenue, profit, dues, stock value.
Staff see an operational view only: how many bills they wrote, what is low on
stock, warranties expiring. No revenue, no profit, no outstanding totals.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import customtkinter as ctk

from ..config import F_BODY, F_LBL, F_SM, F_TN, TH
from ..services import money, stock_value
from .. import ui_helpers as ui
from .base import Page


class DashboardPage(Page):
    @property
    def title(self):
        hour = datetime.now().hour
        greet = ("Good morning" if hour < 12
                 else "Good afternoon" if hour < 17 else "Good evening")
        return f"{greet}, {self.app.user['full_name']}"

    @property
    def subtitle(self):
        return datetime.now().strftime("%A, %d %B %Y")

    def build(self):
        outer = ctk.CTkScrollableFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=(4, 12))

        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        if self.admin:
            self._admin_view(outer, today, month)
        else:
            self._staff_view(outer, today, month)

        self._low_stock(outer)
        self._recent_bills(outer)
        if self.admin:
            self._top_products(outer)
        self._warranty_soon(outer)

    # ── owner ───────────────────────────────────────────────────────
    def _admin_view(self, parent, today, month):
        d_sales = money(self.db.scalar(
            "SELECT COALESCE(SUM(total_amount),0) FROM bills "
            "WHERE DATE(bill_date)=?", (today,), 0))
        d_cash = money(self.db.scalar(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE DATE(payment_date)=?", (today,), 0))
        d_count = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE DATE(bill_date)=?", (today,), 0))
        m_sales = money(self.db.scalar(
            "SELECT COALESCE(SUM(total_amount),0) FROM bills "
            "WHERE strftime('%Y-%m', bill_date)=?", (month,), 0))
        m_cogs = money(self.db.scalar(
            "SELECT COALESCE(SUM(bi.quantity * bi.cogs_price),0) "
            "FROM bill_items bi JOIN bills b ON bi.bill_id=b.id "
            "WHERE strftime('%Y-%m', b.bill_date)=?", (month,), 0))
        m_exp = money(self.db.scalar(
            "SELECT COALESCE(SUM(amount),0) FROM expenses "
            "WHERE strftime('%Y-%m', expense_date)=?", (month,), 0))
        m_ret = money(self.db.scalar(
            "SELECT COALESCE(SUM(refund_amount),0) FROM returns "
            "WHERE strftime('%Y-%m', return_date)=?", (month,), 0))
        dues = money(self.db.scalar(
            "SELECT COALESCE(SUM(total_amount - paid_amount),0) FROM bills "
            "WHERE payment_status != 'paid'", None, 0))
        gross = money(m_sales - m_cogs)
        net = money(gross - m_exp - m_ret)

        ui.section(parent, "TODAY")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x")
        ui.stat_card(r1, "Today's Sales", self.money_text(d_sales), TH.NAVY,
                     206, lambda: self.app.go("bills"))
        ui.stat_card(r1, "Cash Received", self.money_text(d_cash), TH.OK, 206)
        ui.stat_card(r1, "Bills Today", f"{d_count:,}", TH.INFO, 156,
                     lambda: self.app.go("bills"))
        ui.stat_card(r1, "Total Dues", self.money_text(dues), TH.DANGER, 206,
                     lambda: self.app.go("payments"))

        ui.section(parent, f"THIS MONTH  ·  {datetime.now():%B %Y}")
        r2 = ctk.CTkFrame(parent, fg_color="transparent")
        r2.pack(fill="x")
        ui.stat_card(r2, "Revenue", self.money_text(m_sales), TH.NAVY, 190)
        ui.stat_card(r2, "Cost of Goods", self.money_text(m_cogs), TH.WARN, 190)
        ui.stat_card(r2, "Gross Profit", self.money_text(gross),
                     TH.POS if gross >= 0 else TH.DANGER, 190)
        ui.stat_card(r2, "Expenses", self.money_text(m_exp), TH.MUTED, 174)
        ui.stat_card(r2, "Net Profit", self.money_text(net),
                     TH.OK if net >= 0 else TH.DANGER, 190,
                     lambda: self.app.go("reports"))

        ui.section(parent, "INVENTORY & PARTIES")
        r3 = ctk.CTkFrame(parent, fg_color="transparent")
        r3.pack(fill="x")
        n_prod = int(self.db.scalar(
            "SELECT COUNT(*) FROM products WHERE is_active=1", None, 0))
        n_phone = int(self.db.scalar(
            "SELECT COUNT(*) FROM mobile_units WHERE status='in_stock'",
            None, 0))
        n_ret = int(self.db.scalar(
            "SELECT COUNT(*) FROM retailers WHERE is_active=1", None, 0))
        ui.stat_card(r3, "Products", f"{n_prod:,}", TH.NAVY, 156,
                     lambda: self.app.go("products"))
        ui.stat_card(r3, "Handsets in Stock", f"{n_phone:,}", TH.ACCENT_DIM,
                     186, lambda: self.app.go("mobiles"))
        ui.stat_card(r3, "Retailers", f"{n_ret:,}", TH.WHOLESALE, 156,
                     lambda: self.app.go("retailers"))
        ui.stat_card(r3, "Stock Value (cost)",
                     self.money_text(stock_value(self.db, True)), TH.OK, 214)

    # ── staff ───────────────────────────────────────────────────────
    def _staff_view(self, parent, today, month):
        me = self.staff_id()
        my_today = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE staff_id=? AND DATE(bill_date)=?",
            (me, today), 0))
        my_month = int(self.db.scalar(
            "SELECT COUNT(*) FROM bills WHERE staff_id=? "
            "AND strftime('%Y-%m', bill_date)=?", (me, month), 0))
        items_today = int(self.db.scalar(
            "SELECT COALESCE(SUM(bi.quantity),0) FROM bill_items bi "
            "JOIN bills b ON bi.bill_id=b.id "
            "WHERE b.staff_id=? AND DATE(b.bill_date)=?", (me, today), 0))
        phones_today = int(self.db.scalar(
            "SELECT COUNT(*) FROM bill_items bi JOIN bills b "
            "ON bi.bill_id=b.id WHERE b.staff_id=? AND DATE(b.bill_date)=? "
            "AND bi.imei != ''", (me, today), 0))

        ui.section(parent, "YOUR COUNTER TODAY")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x")
        ui.stat_card(r1, "Bills You Made Today", f"{my_today:,}", TH.NAVY, 220,
                     lambda: self.app.go("bills"))
        ui.stat_card(r1, "Items Sold Today", f"{items_today:,}", TH.OK, 190)
        ui.stat_card(r1, "Phones Sold Today", f"{phones_today:,}",
                     TH.ACCENT_DIM, 196)
        ui.stat_card(r1, "Bills This Month", f"{my_month:,}", TH.INFO, 190)

        tip = ctk.CTkFrame(parent, fg_color=TH.PANEL, corner_radius=10,
                           border_width=1, border_color=TH.BORDER)
        tip.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(
            tip,
            text="Press F1 for a new bill  ·  F3 to jump to search  ·  "
                 "Ctrl+P to reprint the last bill\n"
                 "Sales totals and profit are visible to the shop owner only.",
            font=ctk.CTkFont(size=F_SM), text_color=TH.TEXT_DIM,
            justify="left").pack(anchor="w", padx=14, pady=10)

    # ── shared panels ───────────────────────────────────────────────
    def _low_stock(self, parent):
        rows = self.db.fetchall(
            "SELECT p.name, p.brand, p.model, p.stock_quantity, "
            "       p.min_stock_level, c.name AS cat "
            "FROM products p JOIN categories c ON p.category_id=c.id "
            "WHERE p.is_active=1 AND c.kind != 'service' "
            "  AND p.stock_quantity <= p.min_stock_level "
            "ORDER BY p.stock_quantity ASC LIMIT 12")
        if not rows:
            return
        ui.section(parent, f"⚠  LOW / OUT OF STOCK  ({len(rows)} shown)")
        tree, _ = ui.make_table(
            parent, ("Product", "Brand", "Model", "Category", "In Stock",
                     "Alert At"),
            widths=[220, 120, 130, 150, 84, 84],
            anchors=["w", "w", "w", "w", "center", "center"],
            height=min(len(rows), 6))
        for r in rows:
            qty = int(r["stock_quantity"])
            tree.insert("", "end", values=(
                r["name"], r["brand"] or "—", r["model"] or "—", r["cat"],
                qty, r["min_stock_level"]),
                tags=("oos",) if qty <= 0 else ("low",))

    def _recent_bills(self, parent):
        where = "" if self.admin else "WHERE b.staff_id = ?"
        params = () if self.admin else (self.staff_id(),)
        rows = self.db.fetchall(
            "SELECT b.bill_number, b.bill_type, b.bill_date, b.customer_name, "
            "       b.total_amount, b.payment_status, u.full_name AS staff "
            "FROM bills b LEFT JOIN users u ON b.staff_id=u.id "
            f"{where} ORDER BY b.id DESC LIMIT 10", params)
        if not rows:
            return
        ui.section(parent, "RECENT BILLS" if self.admin else "YOUR RECENT BILLS")
        cols = ["Bill No", "Type", "Date", "Customer", "Amount", "Status"]
        widths = [120, 92, 138, 200, 108, 92]
        anchors = ["w", "w", "w", "w", "e", "center"]
        if self.admin:
            cols.append("Staff")
            widths.append(130)
            anchors.append("w")
        tree, _ = ui.make_table(parent, tuple(cols), widths, anchors,
                                height=min(len(rows), 8),
                                on_double=lambda: self.app.go("bills"))
        for b in rows:
            status = (b["payment_status"] or "paid").upper()
            vals = [b["bill_number"],
                    "Wholesale" if b["bill_type"] == "wholesale" else "Retail",
                    str(b["bill_date"])[:16], b["customer_name"] or "Walk-in",
                    f"{money(b['total_amount']):,.2f}", status]
            if self.admin:
                vals.append(b["staff"] or "—")
            tree.insert("", "end", values=tuple(vals),
                        tags=("due",) if status == "UNPAID"
                        else ("partial",) if status == "PARTIAL" else ())

    def _top_products(self, parent):
        month = datetime.now().strftime("%Y-%m")
        rows = self.db.fetchall(
            "SELECT bi.product_name, bi.product_brand, bi.product_model, "
            "       SUM(bi.quantity) qty, SUM(bi.total_price) amt "
            "FROM bill_items bi JOIN bills b ON bi.bill_id=b.id "
            "WHERE strftime('%Y-%m', b.bill_date)=? "
            "GROUP BY bi.product_name, bi.product_brand, bi.product_model "
            "ORDER BY qty DESC LIMIT 8", (month,))
        if not rows:
            return
        ui.section(parent, "TOP SELLERS THIS MONTH")
        tree, _ = ui.make_table(
            parent, ("Product", "Brand", "Model", "Qty Sold", "Revenue"),
            widths=[240, 130, 140, 92, 120],
            anchors=["w", "w", "w", "center", "e"], height=min(len(rows), 8))
        for r in rows:
            tree.insert("", "end", values=(
                r["product_name"], r["product_brand"] or "—",
                r["product_model"] or "—", r["qty"],
                f"{money(r['amt']):,.2f}"), tags=("pos",))

    def _warranty_soon(self, parent):
        soon = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.db.fetchall(
            "SELECT imei, product_name, brand, customer_name, customer_phone, "
            "       warranty_expiry FROM imei_register "
            "WHERE warranty_expiry != '' AND warranty_expiry BETWEEN ? AND ? "
            "ORDER BY warranty_expiry LIMIT 8", (today, soon))
        if not rows:
            return
        ui.section(parent, "🛡  WARRANTIES EXPIRING IN 30 DAYS")
        tree, _ = ui.make_table(
            parent, ("IMEI", "Handset", "Brand", "Customer", "Phone",
                     "Expires"),
            widths=[160, 180, 110, 160, 116, 110],
            anchors=["w", "w", "w", "w", "w", "center"],
            height=min(len(rows), 6),
            on_double=lambda: self.app.go("imei"))
        for r in rows:
            tree.insert("", "end", values=(
                r["imei"], r["product_name"], r["brand"] or "—",
                r["customer_name"] or "—", r["customer_phone"] or "—",
                r["warranty_expiry"]), tags=("low",))
