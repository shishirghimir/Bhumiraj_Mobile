"""Reports — revenue, COGS, profit, staff and product performance. Admin only."""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..config import F_BODY, F_LBL, F_SM, TH
from ..services import money
from .. import ui_helpers as ui
from .base import Page


class ReportsPage(Page):
    title = "Reports"
    subtitle = "Where the money came from and where it went"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        now = datetime.now()

        ctk.CTkLabel(bar, text="Year", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(side="left")
        self.year = ctk.CTkComboBox(
            bar, values=[str(y) for y in range(now.year - 5, now.year + 2)],
            width=104, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh())
        self.year.pack(side="left", padx=(6, 12))
        self.year.set(str(now.year))

        ctk.CTkLabel(bar, text="Month", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(side="left")
        self.month = ctk.CTkComboBox(
            bar, values=["Whole year"] + [f"{m:02d}" for m in range(1, 13)],
            width=118, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh())
        self.month.pack(side="left", padx=6)
        self.month.set(f"{now.month:02d}")

        self.type_chips = ui.FilterChips(
            bar, ["All", "Retail", "Wholesale"], lambda _v: self.refresh(),
            "All")
        self.type_chips.pack(side="left", padx=12)

        self.box = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self.box.pack(fill="both", expand=True)
        self.refresh()

    def _period(self, prefix="b"):
        y, m = self.year.get(), self.month.get()
        if m == "Whole year":
            clause = f"strftime('%Y', {prefix}.bill_date) = ?"
            params = [y]
            label = f"Year {y}"
        else:
            clause = f"strftime('%Y-%m', {prefix}.bill_date) = ?"
            params = [f"{y}-{m}"]
            label = datetime.strptime(f"{y}-{m}", "%Y-%m").strftime("%B %Y")

        kind = self.type_chips.get()
        if kind == "Retail":
            clause += f" AND {prefix}.bill_type = 'retail'"
            label += "  ·  Retail only"
        elif kind == "Wholesale":
            clause += f" AND {prefix}.bill_type = 'wholesale'"
            label += "  ·  Wholesale only"
        return clause, params, label

    def refresh(self):
        for w in self.box.winfo_children():
            w.destroy()
        clause, params, label = self._period()

        rev = self.db.fetchone(
            f"SELECT COALESCE(SUM(b.total_amount),0) r, "
            f" COALESCE(SUM(b.paid_amount),0) p, COUNT(*) n "
            f"FROM bills b WHERE {clause}", params)
        cogs = money(self.db.scalar(
            "SELECT COALESCE(SUM(bi.quantity * bi.cogs_price),0) "
            "FROM bill_items bi JOIN bills b ON bi.bill_id = b.id "
            f"WHERE {clause}", params, 0))

        y, m = self.year.get(), self.month.get()
        if m == "Whole year":
            exp_clause, exp_params = "strftime('%Y', expense_date) = ?", [y]
            ret_clause, ret_params = "strftime('%Y', return_date) = ?", [y]
        else:
            exp_clause = "strftime('%Y-%m', expense_date) = ?"
            exp_params = [f"{y}-{m}"]
            ret_clause = "strftime('%Y-%m', return_date) = ?"
            ret_params = [f"{y}-{m}"]

        expenses = money(self.db.scalar(
            f"SELECT COALESCE(SUM(amount),0) FROM expenses WHERE {exp_clause}",
            exp_params, 0))
        refunds = money(self.db.scalar(
            f"SELECT COALESCE(SUM(refund_amount),0) FROM returns "
            f"WHERE {ret_clause}", ret_params, 0))

        revenue = money(rev["r"])
        collected = money(rev["p"])
        gross = money(revenue - cogs)
        net = money(gross - expenses - refunds)
        margin = (gross / revenue * 100) if revenue > 0 else 0.0
        outstanding = money(revenue - collected)

        ui.section(self.box, f"PERFORMANCE  —  {label}")
        r1 = ctk.CTkFrame(self.box, fg_color="transparent")
        r1.pack(fill="x")
        ui.stat_card(r1, "Revenue", self.money_text(revenue), TH.NAVY, 196)
        ui.stat_card(r1, "Cost of Goods", self.money_text(cogs), TH.WARN, 196)
        ui.stat_card(r1, "Gross Profit", self.money_text(gross),
                     TH.POS if gross >= 0 else TH.DANGER, 196)
        ui.stat_card(r1, "Gross Margin", f"{margin:.1f}%", TH.INFO, 160)

        r2 = ctk.CTkFrame(self.box, fg_color="transparent")
        r2.pack(fill="x")
        ui.stat_card(r2, "Expenses", self.money_text(expenses), TH.MUTED, 186)
        ui.stat_card(r2, "Refunds", self.money_text(refunds), TH.DANGER, 186)
        ui.stat_card(r2, "NET PROFIT", self.money_text(net),
                     TH.OK if net >= 0 else TH.DANGER, 210)
        ui.stat_card(r2, "Bills", f"{rev['n']:,}", TH.INFO, 130)
        ui.stat_card(r2, "Still Outstanding", self.money_text(outstanding),
                     TH.DANGER if outstanding > 0.005 else TH.POS, 210)

        # ── monthly breakdown when a whole year is selected ─────────
        if m == "Whole year":
            ui.section(self.box, "MONTH BY MONTH")
            tree, _ = ui.make_table(
                self.box, ("Month", "Bills", "Revenue", "COGS", "Gross Profit",
                           "Margin"),
                widths=[130, 80, 132, 132, 138, 92],
                anchors=["w", "center", "e", "e", "e", "center"], height=12)
            for mm in range(1, 13):
                key = f"{y}-{mm:02d}"
                extra = ""
                kind = self.type_chips.get()
                if kind == "Retail":
                    extra = " AND b.bill_type='retail'"
                elif kind == "Wholesale":
                    extra = " AND b.bill_type='wholesale'"
                agg = self.db.fetchone(
                    "SELECT COALESCE(SUM(b.total_amount),0) r, COUNT(*) n "
                    "FROM bills b WHERE strftime('%Y-%m', b.bill_date)=?"
                    + extra, (key,))
                mc = money(self.db.scalar(
                    "SELECT COALESCE(SUM(bi.quantity*bi.cogs_price),0) "
                    "FROM bill_items bi JOIN bills b ON bi.bill_id=b.id "
                    "WHERE strftime('%Y-%m', b.bill_date)=?" + extra,
                    (key,), 0))
                mr = money(agg["r"])
                if agg["n"] == 0 and mr == 0:
                    continue
                mg = money(mr - mc)
                tree.insert("", "end", values=(
                    datetime.strptime(key, "%Y-%m").strftime("%B"),
                    agg["n"], f"{mr:,.2f}", f"{mc:,.2f}", f"{mg:,.2f}",
                    f"{(mg / mr * 100) if mr else 0:.1f}%"),
                    tags=("pos",) if mg >= 0 else ("due",))

        # ── staff performance ───────────────────────────────────────
        ui.section(self.box, "STAFF PERFORMANCE")
        tree, _ = ui.make_table(
            self.box, ("Staff", "Bills", "Revenue", "Collected", "Outstanding",
                       "Avg Bill"),
            widths=[190, 80, 140, 140, 140, 120],
            anchors=["w", "center", "e", "e", "e", "e"], height=8)
        for s in self.db.fetchall(
                "SELECT u.full_name, COUNT(b.id) n, "
                " COALESCE(SUM(b.total_amount),0) r, "
                " COALESCE(SUM(b.paid_amount),0) p "
                "FROM bills b JOIN users u ON b.staff_id = u.id "
                f"WHERE {clause} GROUP BY b.staff_id "
                "ORDER BY r DESC", params):
            rr = money(s["r"])
            pp = money(s["p"])
            tree.insert("", "end", values=(
                s["full_name"], s["n"], f"{rr:,.2f}", f"{pp:,.2f}",
                f"{money(rr - pp):,.2f}",
                f"{money(rr / s['n']) if s['n'] else 0:,.2f}"), tags=("pos",))

        # ── best sellers ────────────────────────────────────────────
        ui.section(self.box, "BEST SELLING PRODUCTS")
        tree2, _ = ui.make_table(
            self.box, ("Product", "Brand", "Model", "Qty Sold", "Revenue",
                       "Est. Profit"),
            widths=[220, 130, 140, 92, 130, 130],
            anchors=["w", "w", "w", "center", "e", "e"], height=10)
        for p in self.db.fetchall(
                "SELECT bi.product_name, bi.product_brand, bi.product_model, "
                " SUM(bi.quantity) q, SUM(bi.total_price) amt, "
                " SUM(bi.quantity * bi.cogs_price) c "
                "FROM bill_items bi JOIN bills b ON bi.bill_id = b.id "
                f"WHERE {clause} "
                "GROUP BY bi.product_name, bi.product_brand, bi.product_model "
                "ORDER BY q DESC LIMIT 25", params):
            profit = money(money(p["amt"]) - money(p["c"]))
            tree2.insert("", "end", values=(
                p["product_name"], p["product_brand"] or "—",
                p["product_model"] or "—", p["q"],
                f"{money(p['amt']):,.2f}", f"{profit:,.2f}"),
                tags=("pos",) if profit >= 0 else ("due",))

        # ── category mix ────────────────────────────────────────────
        ui.section(self.box, "SALES BY CATEGORY")
        tree3, _ = ui.make_table(
            self.box, ("Category", "Qty Sold", "Revenue", "Share"),
            widths=[240, 110, 150, 110],
            anchors=["w", "center", "e", "center"], height=9)
        cat_rows = self.db.fetchall(
            "SELECT c.name, SUM(bi.quantity) q, SUM(bi.total_price) amt "
            "FROM bill_items bi JOIN bills b ON bi.bill_id = b.id "
            "LEFT JOIN products p ON bi.product_id = p.id "
            "LEFT JOIN categories c ON p.category_id = c.id "
            f"WHERE {clause} GROUP BY c.name ORDER BY amt DESC", params)
        for c in cat_rows:
            amt = money(c["amt"])
            tree3.insert("", "end", values=(
                c["name"] or "(deleted product)", c["q"], f"{amt:,.2f}",
                f"{(amt / revenue * 100) if revenue else 0:.1f}%"))

        # ── payment method mix ──────────────────────────────────────
        ui.section(self.box, "HOW CUSTOMERS PAID")
        tree4, _ = ui.make_table(
            self.box, ("Method", "Bills", "Amount Billed"),
            widths=[220, 110, 160], anchors=["w", "center", "e"], height=7)
        for pm in self.db.fetchall(
                "SELECT b.payment_method m, COUNT(*) n, "
                " COALESCE(SUM(b.total_amount),0) t FROM bills b "
                f"WHERE {clause} GROUP BY b.payment_method ORDER BY t DESC",
                params):
            tree4.insert("", "end", values=(
                pm["m"] or "Cash", pm["n"], f"{money(pm['t']):,.2f}"))
