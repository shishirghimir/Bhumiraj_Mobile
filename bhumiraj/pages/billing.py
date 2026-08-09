"""New Bill — retail (walk-in) and wholesale (retailer) in one screen.

Layout follows the IOS Nepal billing screen the shop already knows:
  • the search box drops its results DOWN underneath it and collapses again
    when empty, instead of a product table permanently filling the screen
  • the BILL ITEMS table is the main area — full width, every detail visible
  • Qty and Rate are edited IN PLACE: double-click the cell, type, press Enter
"""
from __future__ import annotations

import os
from datetime import datetime

import customtkinter as ctk

from ..config import (BILL_RETAIL, BILL_WHOLESALE, BILLS_DIR, F_BODY, F_LBL,
                      F_SEC, F_SM, F_TN, KIND_SERVICE, PAYMENT_METHODS,
                      PLAN_FULL, PLAN_INSTALLMENT, QUALITY_OPTS, TH,
                      WARRANTY_OPTS)
from ..services import (attrs_summary, check_stock_available, clean_phone,
                        compute_totals, installment_schedule, log_stock, money,
                        pack_attrs, parse_amount, parse_int, price_for,
                        unpack_attrs, warranty_expiry)
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page

CHIPS = [
    ("All", None),
    ("Mobiles", "c.kind = 'mobile'"),
    ("Watches", "c.kind = 'watch'"),
    ("Chargers", "(c.name LIKE '%Charger%' OR c.name LIKE '%Cable%' "
                 " OR c.name LIKE '%Power Bank%')"),
    ("Sunglasses", "c.kind = 'eyewear'"),
    ("Accessories",
     "(c.kind = 'accessory' AND c.name NOT LIKE '%Charger%' "
     " AND c.name NOT LIKE '%Cable%' AND c.name NOT LIKE '%Power Bank%')"),
    ("Services", "c.kind = 'service'"),
    ("Others", "c.kind = 'general'"),
]

MAX_DROP_ROWS = 7
COL_QTY = "#6"
COL_RATE = "#7"
COL_DELETE = "#9"


class BillingPage(Page):
    title = "New Bill"
    subtitle = "Retail counter sale or wholesale invoice to a retailer"

    # ══════════════════════════════════════════════════════════════
    def build(self):
        self.cart = []
        self.bill_type = BILL_RETAIL
        self.retailer_id = None
        self._chip_sql = None
        self._rows = {}
        self._line_iids = []
        self._cell_editor = None

        outer = self.body()

        mode = ctk.CTkFrame(outer, fg_color=TH.PANEL, corner_radius=10,
                            border_width=1, border_color=TH.BORDER)
        mode.pack(fill="x", pady=(0, 6))
        inner = ctk.CTkFrame(mode, fg_color="transparent")
        inner.pack(padx=12, pady=8, fill="x")
        ctk.CTkLabel(inner, text="BILL TYPE",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(side="left", padx=(0, 10))
        self.btn_retail = ui.button(inner, "🛒  RETAIL  (Walk-in)",
                                    lambda: self._set_type(BILL_RETAIL),
                                    "ok", 196, 34, side="left")
        self.btn_ws = ui.button(inner, "🏪  WHOLESALE  (Retailer)",
                                lambda: self._set_type(BILL_WHOLESALE),
                                "muted", 212, 34, side="left")
        self.mode_hint = ctk.CTkLabel(
            inner, text="Retail prices are being used.",
            font=ctk.CTkFont(size=F_SM), text_color=TH.TEXT_DIM)
        self.mode_hint.pack(side="left", padx=14)

        split = ctk.CTkFrame(outer, fg_color="transparent")
        split.pack(fill="both", expand=True)
        right = ctk.CTkFrame(split, fg_color=TH.PANEL, corner_radius=12,
                             border_width=1, border_color=TH.BORDER, width=396)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        left = ctk.CTkFrame(split, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self._build_left(left)
        self._build_right(right)
        self._redraw_cart()
        self.search_entry.focus_set()

    def _set_type(self, kind):
        if self.cart and kind != self.bill_type:
            if not self.confirm(
                    "Switch bill type",
                    "Switching between retail and wholesale will clear the "
                    "current bill and re-price the items.\n\nContinue?"):
                return
            self.cart = []
        self.bill_type = kind
        retail = kind == BILL_RETAIL
        self.btn_retail.configure(
            fg_color=TH.OK if retail else TH.MUTED,
            hover_color=TH.OK_HV if retail else TH.MUTED_HV)
        self.btn_ws.configure(
            fg_color=TH.MUTED if retail else "#5b3fa8",
            hover_color=TH.MUTED_HV if retail else "#452f80")
        self.mode_hint.configure(
            text="Retail prices are being used." if retail
            else "Wholesale prices are being used.")
        self.party_box.pack_forget()
        self._build_party()
        self._search()
        self._redraw_cart()

    # ══════════════════════════════════════════════════════════════
    # LEFT — search dropdown, then the bill items table
    # ══════════════════════════════════════════════════════════════
    def _build_left(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x")
        self.search_entry = ctk.CTkEntry(
            bar, height=42, font=ctk.CTkFont(size=F_LBL),
            placeholder_text="🔍  Type to search — name, brand, model, SKU… "
                             "then click a result to add it",
            fg_color=TH.PANEL_ALT, border_color=TH.NAVY, border_width=2)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_key)
        self.search_entry.bind("<Down>", self._focus_results)
        self.search_entry.bind("<Return>", self._enter_add)
        self.search_entry.bind("<Escape>", lambda _e: self._hide_results())

        ctk.CTkLabel(bar, text="Qty", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(
                         side="left", padx=(10, 4))
        self.add_qty = ctk.CTkEntry(bar, width=56, height=42, justify="center",
                                    font=ctk.CTkFont(size=F_BODY),
                                    fg_color=TH.PANEL_ALT,
                                    border_color=TH.BORDER)
        self.add_qty.pack(side="left")
        self.add_qty.insert(0, "1")
        ui.button(bar, "Clear", self._clear_search, "muted", 78, 42,
                  side="left", padx=(8, 0))

        self.chips = ui.FilterChips(parent, [c[0] for c in CHIPS],
                                    self._on_chip)
        self.chips.pack(fill="x", pady=(4, 0))

        # ── collapsible results dropdown ────────────────────────────
        self.drop = ctk.CTkFrame(parent, fg_color=TH.PANEL_ALT,
                                 corner_radius=8, border_width=1,
                                 border_color=TH.NAVY)
        self.drop_head = ctk.CTkLabel(
            self.drop, text="", font=ctk.CTkFont(size=F_SM, weight="bold"),
            text_color=TH.ACCENT, anchor="w")
        self.drop_head.pack(fill="x", padx=10, pady=(6, 2))
        self.results, _ = ui.make_table(
            self.drop, ("Product", "Brand", "Model", "Quality / Details",
                        "Stock", "Price"),
            widths=[220, 118, 136, 250, 68, 100],
            anchors=["w", "w", "w", "w", "center", "e"],
            height=MAX_DROP_ROWS, big=True)
        self.results.bind("<ButtonRelease-1>", self._on_result_click)
        self.results.bind("<Double-1>", self._on_result_double)
        self.results.bind("<Return>", lambda _e: self._add_selected())
        self.results.bind("<Escape>", lambda _e: self._hide_results())

        # ── bill items: the main area ───────────────────────────────
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(10, 2))
        ctk.CTkLabel(head, text="ITEMS ON THIS BILL",
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color=TH.ACCENT).pack(side="left")
        ctk.CTkLabel(head,
                     text="   double-click Qty or Rate to change it",
                     font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(side="left")
        self.item_count = ctk.CTkLabel(head, text="0 items",
                                       font=ctk.CTkFont(size=F_SM),
                                       text_color=TH.TEXT_DIM)
        self.item_count.pack(side="right")

        # ── edit bar for the selected line ──────────────────────────
        editbar = ctk.CTkFrame(parent, fg_color=TH.PANEL, corner_radius=8,
                               border_width=1, border_color=TH.NAVY)
        editbar.pack(side="bottom", fill="x", pady=(6, 0))
        pad = ctk.CTkFrame(editbar, fg_color="transparent")
        pad.pack(fill="x", padx=10, pady=8)
        self.sel_lbl = ctk.CTkLabel(
            pad, text="Select a line to change its quantity or price",
            font=ctk.CTkFont(size=F_SM, weight="bold"),
            text_color=TH.TEXT_DIM, anchor="w")
        self.sel_lbl.pack(side="left", padx=(0, 12))

        ui.button(pad, "🗑  Delete", self._remove_selected, "danger", 104, 34,
                  side="right")
        ui.button(pad, "✎  Details", self._edit_selected_line, "info", 104, 34,
                  side="right", padx=(6, 0))
        ui.button(pad, "✔  Update", self._apply_line, "ok", 106, 34,
                  side="right", padx=(6, 0))
        self.ed_price = ctk.CTkEntry(pad, width=104, height=34,
                                     justify="right",
                                     font=ctk.CTkFont(size=F_BODY),
                                     fg_color=TH.PANEL_ALT,
                                     border_color=TH.BORDER)
        self.ed_price.pack(side="right", padx=(4, 8))
        ctk.CTkLabel(pad, text="Price", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(side="right")
        self.ed_qty = ctk.CTkEntry(pad, width=64, height=34, justify="center",
                                   font=ctk.CTkFont(size=F_BODY),
                                   fg_color=TH.PANEL_ALT,
                                   border_color=TH.BORDER)
        self.ed_qty.pack(side="right", padx=(4, 12))
        ctk.CTkLabel(pad, text="Qty", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(side="right")
        self.ed_qty.bind("<Return>", lambda _e: self._apply_line())
        self.ed_price.bind("<Return>", lambda _e: self._apply_line())

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(side="bottom", fill="x", pady=(6, 0))
        ui.button(actions, "Clear whole bill", self._clear_cart, "muted", 140,
                  30, side="right", font_size=F_SM)

        self.items, _ = ui.make_table(
            parent, ("#", "Product", "Brand", "Model", "Quality / IMEI",
                     "Qty", "Rate", "Amount", "✕"),
            widths=[34, 200, 104, 122, 214, 62, 98, 112, 34],
            anchors=["center", "w", "w", "w", "w", "center", "e", "e",
                     "center"],
            height=10, big=True)
        self.items.bind("<Double-1>", self._on_item_double)
        self.items.bind("<ButtonRelease-1>", self._on_item_click)
        self.items.bind("<<TreeviewSelect>>", lambda _e: self._on_line_select())
        self.items.bind("<Delete>", lambda _e: self._remove_selected())

    # ── search ──────────────────────────────────────────────────────
    def _on_chip(self, label):
        self._chip_sql = dict(CHIPS).get(label)
        self._search()

    def _on_key(self, event=None):
        if event and event.keysym in ("Down", "Up", "Return", "Escape"):
            return
        self._search()

    def _clear_search(self):
        self.search_entry.delete(0, "end")
        self._hide_results()
        self.search_entry.focus_set()

    def _hide_results(self):
        self.drop.pack_forget()

    def _show_results(self, n):
        if not self.drop.winfo_ismapped():
            self.drop.pack(fill="x", pady=(4, 0), after=self.chips)
        try:
            self.results.configure(height=max(min(n, MAX_DROP_ROWS), 1))
        except Exception:
            pass

    def _focus_results(self, _e=None):
        kids = self.results.get_children()
        if kids:
            self.results.focus_set()
            self.results.selection_set(kids[0])
            self.results.focus(kids[0])
        return "break"

    def _enter_add(self, _e=None):
        kids = self.results.get_children()
        if kids:
            self.results.selection_set(kids[0])
            self._add_selected()
        return "break"

    def _search(self):
        for row in self.results.get_children():
            self.results.delete(row)
        self._rows = {}

        text = self.search_entry.get().strip()
        if not text and not self._chip_sql:
            self.drop_head.configure(text="")
            self._hide_results()
            return

        where = ["p.is_active = 1",
                 "(p.stock_quantity > 0 OR c.kind = 'service')"]
        params = []
        if self._chip_sql:
            where.append(self._chip_sql)
        for word in text.split():
            like = f"%{word}%"
            where.append("(p.name LIKE ? OR p.brand LIKE ? OR p.model LIKE ? "
                         " OR p.sku LIKE ? OR p.barcode LIKE ? "
                         " OR p.variant LIKE ? OR p.attrs LIKE ? "
                         " OR c.name LIKE ?)")
            params += [like] * 8

        rows = self.db.fetchall(
            "SELECT p.*, c.name AS cat_name, c.kind AS cat_kind "
            "FROM products p JOIN categories c ON p.category_id = c.id "
            "WHERE " + " AND ".join(where) + " ORDER BY p.brand, p.name",
            params)

        for r in rows:
            price = price_for(r, self.bill_type)
            qty = int(r["stock_quantity"])
            if r["is_serialized"]:
                qty = int(self.db.scalar(
                    "SELECT COUNT(*) FROM mobile_units WHERE product_id=? "
                    "AND status='in_stock'", (r["id"],), 0))
            details = attrs_summary(unpack_attrs(r["attrs"]), limit=4) \
                or r["cat_name"]
            if r["is_serialized"]:
                details = "📱 IMEI  ·  " + details
            if r["warranty_months"]:
                details += f"  ·  {r['warranty_months']}m warranty"
            tag = "low" if 0 < qty <= int(r["min_stock_level"] or 0) else ""
            iid = self.results.insert(
                "", "end",
                values=(r["name"], r["brand"] or "—", r["model"] or "—",
                        details,
                        "Service" if r["cat_kind"] == KIND_SERVICE else qty,
                        f"{price:,.2f}"),
                tags=(tag,) if tag else ())
            self._rows[iid] = r

        if rows:
            self.drop_head.configure(
                text=f"{len(rows)} product(s) — CLICK to add   ·   "
                     f"phones: DOUBLE-CLICK to pick the IMEI")
            self._show_results(len(rows))
        else:
            self.drop_head.configure(text="No product matches that search.")
            self._show_results(1)

    # ── adding ──────────────────────────────────────────────────────
    def _row_under(self, event):
        try:
            iid = self.results.identify_row(event.y)
        except Exception:
            iid = None
        return self._rows.get(iid) if iid else None

    def _on_result_click(self, event):
        row = self._row_under(event)
        if not row:
            return
        if row["is_serialized"]:
            self.drop_head.configure(
                text="📱 IMEI-tracked phone — DOUBLE-CLICK to choose the "
                     "handset and the payment plan.")
            return
        self._add_row(row)

    def _on_result_double(self, event):
        row = self._row_under(event)
        if row:
            self._add_row(row)
        return "break"

    def _add_selected(self):
        sel = self.results.selection()
        if not sel:
            self.toast("Pick a product from the list first.", "warn")
            return
        row = self._rows.get(sel[0])
        if row:
            self._add_row(row)

    def _add_row(self, row):
        qty = max(parse_int(self.add_qty.get(), 1), 1)
        if row["is_serialized"]:
            units = self.db.fetchall(
                "SELECT * FROM mobile_units WHERE product_id=? "
                "AND status='in_stock' ORDER BY id", (row["id"],))
            if units:
                self._pick_handset(row, units)
                return
            self.warn("No handsets in stock",
                      f"There are no unsold IMEI units for {row['name']}.\n\n"
                      "Add the IMEI numbers on the product (Products → Edit) "
                      "or in the Mobiles tab.")
            return
        if row["cat_kind"] != KIND_SERVICE and int(row["stock_quantity"]) <= 0:
            self.warn("Out of stock", f"{row['name']} has no stock left.")
            return
        self._push_item(row, quantity=qty,
                        unit_price=price_for(row, self.bill_type))
        self.add_qty.delete(0, "end")
        self.add_qty.insert(0, "1")

    def _push_item(self, product, quantity=1, unit_price=0.0, unit=None,
                   warranty_months=None, plan=PLAN_FULL, down=0.0, months=0):
        """Add a line, merging with an identical non-serialised line."""
        imei = unit["imei"] if unit else ""
        if not unit:
            for it in self.cart:
                if it["product_id"] == product["id"] and not it["mobile_unit_id"]:
                    available = int(product["stock_quantity"])
                    if it["quantity"] + quantity > available:
                        self.warn("Stock limit",
                                  f"Only {available} of {product['name']} "
                                  "in stock.")
                        return
                    it["quantity"] += quantity
                    it["total_price"] = money(it["quantity"] * it["unit_price"])
                    self._redraw_cart()
                    return

        self.cart.append({
            "product_id": product["id"],
            "mobile_unit_id": unit["id"] if unit else None,
            "name": product["name"],
            "brand": product["brand"] or "",
            "model": product["model"] or "",
            "sku": product["sku"] or "",
            "imei": imei,
            "attrs": product["attrs"] or "{}",
            "quality": unpack_attrs(product["attrs"]).get("quality", ""),
            "quantity": int(quantity),
            "unit_price": money(unit_price),
            "total_price": money(quantity * money(unit_price)),
            "cogs_price": money(unit["cost_price"] if unit
                                else product["cost_price"]),
            "warranty_months": int(product["warranty_months"] or 0)
            if warranty_months is None else int(warranty_months),
            "plan": plan,
            "down": money(down),
            "months": int(months),
            "kind": product["cat_kind"],
        })
        self._redraw_cart()
        self.toast(f"Added {product['name']}")

    def _pick_handset(self, product, units):
        """Choose the exact handset + warranty + payment plan."""
        d = ui.modal(self.app, "Select handset", 620, 620)
        ui.modal_header(d, f"{product['brand']} {product['name']}",
                        "Pick the exact handset being sold")
        body = ui.modal_body(d)

        ctk.CTkLabel(body, text="Available handsets",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w")
        tree, _ = ui.make_table(
            body, ("IMEI", "Colour", "Storage", "Condition", "Price"),
            widths=[168, 92, 78, 96, 92],
            anchors=["w", "w", "w", "w", "e"], height=7)
        umap = {}
        for u in units:
            price = money(u["sell_price"]) or price_for(product, self.bill_type)
            iid = tree.insert("", "end", values=(
                u["imei"], u["color"] or "—", u["storage"] or "—",
                u["condition"] or "New", f"{price:,.2f}"))
            umap[iid] = u
        kids = tree.get_children()
        if kids:
            tree.selection_set(kids[0])

        ui.section(body, "Sale terms")
        grid = ui.form_grid(body, 2)
        default_price = price_for(product, self.bill_type)
        e_price = ui.labelled_entry(grid[0], "Selling Price",
                                    f"{default_price:.2f}", required=True)
        c_warr = ui.labelled_combo(grid[1], "Warranty (months)", WARRANTY_OPTS,
                                   str(product["warranty_months"] or 0))

        plan_box = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        plan_box.pack(fill="x", pady=8)
        pad = ctk.CTkFrame(plan_box, fg_color="transparent")
        pad.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(pad, text="PAYMENT PLAN",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w")
        plan_var = ctk.StringVar(value=PLAN_FULL)
        emi_holder = ctk.CTkFrame(pad, fg_color="transparent")

        def on_plan():
            if plan_var.get() == PLAN_INSTALLMENT:
                emi_holder.pack(fill="x", pady=(8, 0))
            else:
                emi_holder.pack_forget()

        ctk.CTkRadioButton(pad, text="Full payment", variable=plan_var,
                           value=PLAN_FULL, command=on_plan,
                           font=ctk.CTkFont(size=F_BODY),
                           fg_color=TH.OK).pack(anchor="w", pady=(6, 2))
        ctk.CTkRadioButton(pad, text="Instalment / EMI (with IMEI record)",
                           variable=plan_var, value=PLAN_INSTALLMENT,
                           command=on_plan, font=ctk.CTkFont(size=F_BODY),
                           fg_color=TH.WARN).pack(anchor="w")

        ecols = ui.form_grid(emi_holder, 2)
        e_down = ui.labelled_entry(ecols[0], "Down payment", "0")
        e_months = ui.labelled_entry(ecols[1], "Number of months", "6")
        emi_preview = ctk.CTkLabel(emi_holder, text="",
                                   font=ctk.CTkFont(size=F_SM, weight="bold"),
                                   text_color=TH.ACCENT, justify="left")
        emi_preview.pack(anchor="w", pady=(4, 0))

        def preview(_e=None):
            total = parse_amount(e_price.get())
            down, financed, rows = installment_schedule(
                total, parse_amount(e_down.get()), parse_int(e_months.get()))
            if rows:
                emi_preview.configure(
                    text=f"{len(rows)} instalments — "
                         f"{self.cur} {rows[0]:,.2f} per month "
                         f"(last: {self.cur} {rows[-1]:,.2f})   ·   "
                         f"financed {self.cur} {financed:,.2f}")
            else:
                emi_preview.configure(text="Enter a valid number of months.")
        for w in (e_down, e_months, e_price):
            w.bind("<KeyRelease>", preview)

        def add():
            sel = tree.selection()
            if not sel:
                self.warn("Pick a handset", "Select which IMEI is being sold.")
                return
            unit = umap[sel[0]]
            price = parse_amount(e_price.get())
            if price <= 0:
                self.warn("Price", "Enter a selling price greater than zero.")
                return
            plan = plan_var.get()
            down = parse_amount(e_down.get()) if plan == PLAN_INSTALLMENT else 0
            months = parse_int(e_months.get()) if plan == PLAN_INSTALLMENT else 0
            if plan == PLAN_INSTALLMENT:
                if months <= 0:
                    self.warn("Instalments",
                              "Enter how many months the instalments run for.")
                    return
                if down > price:
                    self.warn("Down payment",
                              "Down payment cannot exceed the handset price.")
                    return
            if any(it.get("mobile_unit_id") == unit["id"] for it in self.cart):
                self.warn("Already added",
                          f"IMEI {unit['imei']} is already on this bill.")
                return
            # Read EVERY widget before the dialog is destroyed — touching a
            # widget after destroy() raises TclError "invalid command name".
            warranty = parse_int(c_warr.get())
            d.destroy()
            self._push_item(product, 1, price, unit, warranty, plan, down,
                            months)

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Add to Bill", add, "ok", 150, side="right")
        tree.bind("<Double-1>", lambda _e: add())
        preview()

    # ══════════════════════════════════════════════════════════════
    # BILL ITEMS TABLE
    # ══════════════════════════════════════════════════════════════
    def _redraw_cart(self):
        self._kill_editor()
        for iid in self.items.get_children():
            self.items.delete(iid)
        self._line_iids = []

        for i, it in enumerate(self.cart, 1):
            extra = []
            if it.get("quality"):
                extra.append(it["quality"])
            if it["imei"]:
                extra.append(f"IMEI {it['imei']}")
            summary = attrs_summary(unpack_attrs(it["attrs"]), limit=3)
            if summary:
                extra.append(summary)
            if it["warranty_months"]:
                extra.append(f"{it['warranty_months']}m warranty")
            if it["plan"] == PLAN_INSTALLMENT:
                extra.append(f"EMI × {it['months']}m")
            iid = self.items.insert("", "end", values=(
                i, it["name"], it["brand"] or "—", it["model"] or "—",
                "  ·  ".join(extra) or "—", it["quantity"],
                f"{it['unit_price']:,.2f}", f"{it['total_price']:,.2f}",
                "✕"))
            self._line_iids.append(iid)

        n = len(self.cart)
        self.item_count.configure(text=f"{n} item{'s' if n != 1 else ''}")
        self._recalc()

    def _index_of(self, iid):
        try:
            return self._line_iids.index(iid)
        except ValueError:
            return None

    def _on_line_select(self):
        """Load the selected line into the edit boxes."""
        idx = self._selected_index()
        if idx is None or idx >= len(self.cart):
            self.sel_lbl.configure(
                text="Select a line to change its quantity or price",
                text_color=TH.TEXT_DIM)
            return
        it = self.cart[idx]
        self.ed_qty.delete(0, "end")
        self.ed_qty.insert(0, str(it["quantity"]))
        self.ed_price.delete(0, "end")
        self.ed_price.insert(0, f"{it['unit_price']:.2f}")
        label = " ".join(x for x in (it["brand"], it["name"]) if x)
        self.sel_lbl.configure(text=f"Editing:  {label[:34]}",
                               text_color=TH.ACCENT)

    def _apply_line(self):
        """Apply the qty / price boxes to the selected line."""
        idx = self._selected_index()
        if idx is None or idx >= len(self.cart):
            self.toast("Select a line on the bill first.", "warn")
            return
        it = self.cart[idx]
        qty = 1 if it["mobile_unit_id"] else max(
            parse_int(self.ed_qty.get(), it["quantity"]), 1)
        stock = self._stock_for(it)
        if stock is not None and qty > stock:
            qty = max(int(stock), 1)
            self.toast(f"Only {stock} of {it['name']} in stock.", "warn")
        price = max(parse_amount(self.ed_price.get(), it["unit_price"]), 0.0)
        it["quantity"] = qty
        it["unit_price"] = price
        it["total_price"] = money(qty * price)
        self._redraw_cart()
        if idx < len(self._line_iids):
            self.items.selection_set(self._line_iids[idx])
        self.toast("Line updated.")

    def _selected_index(self):
        sel = self.items.selection()
        if not sel:
            return None
        return self._index_of(sel[0])

    # ── inline cell editing ─────────────────────────────────────────
    def _kill_editor(self):
        ed = self._cell_editor
        self._cell_editor = None
        if ed is not None:
            try:
                ed.destroy()
            except Exception:
                pass

    def _on_item_click(self, event):
        """A single click on the ✕ column removes that line."""
        if self.items.identify_column(event.x) != COL_DELETE:
            return
        iid = self.items.identify_row(event.y)
        if not iid:
            return
        idx = self._index_of(iid)
        if idx is not None:
            self._remove(idx)
        return "break"

    def _on_item_double(self, event):
        """Double-clicking Qty or Rate edits it right there in the table."""
        iid = self.items.identify_row(event.y)
        col = self.items.identify_column(event.x)
        if not iid:
            return "break"
        idx = self._index_of(iid)
        if idx is None:
            return "break"
        if col not in (COL_QTY, COL_RATE):
            self._edit_line(idx)
            return "break"

        it = self.cart[idx]
        if col == COL_QTY and it["mobile_unit_id"]:
            self.toast("An IMEI handset is always quantity 1.", "warn")
            return "break"

        bbox = self.items.bbox(iid, col)
        if not bbox:
            return "break"
        x, y, w, h = bbox
        self._open_cell_editor(idx, col, x, y, w, h)
        return "break"

    def _open_cell_editor(self, idx, col, x, y, w, h):
        """Float an entry over the cell so it is edited in place."""
        if idx >= len(self.cart):
            return None
        it = self.cart[idx]
        self._kill_editor()

        current = (str(it["quantity"]) if col == COL_QTY
                   else f"{it['unit_price']:.2f}")
        # CustomTkinter requires width/height on the CONSTRUCTOR — passing them
        # to place() raises "'width' and 'height' arguments must be passed to
        # the constructor of the widget, not the place method".
        ed = ctk.CTkEntry(self.items, width=max(int(w), 40),
                          height=max(int(h), 24),
                          font=ctk.CTkFont(size=F_BODY),
                          justify="center" if col == COL_QTY else "right",
                          fg_color=TH.PANEL_ALT, border_color=TH.ACCENT,
                          border_width=2)
        ed.place(x=int(x), y=int(y))
        ed.insert(0, current)
        try:
            ed.select_range(0, "end")
        except Exception:
            pass
        ed.focus_set()
        self._cell_editor = ed

        def commit(_e=None):
            # read the value BEFORE the widget goes away
            if getattr(ed, "_done", False):
                return
            ed._done = True
            raw = ed.get()
            self._kill_editor()
            self._apply_cell(idx, col, raw)

        def cancel(_e=None):
            ed._done = True
            self._kill_editor()

        ed._commit = commit
        ed._cancel = cancel
        ed.bind("<Return>", commit)
        ed.bind("<KP_Enter>", commit)
        ed.bind("<FocusOut>", commit)
        ed.bind("<Escape>", cancel)
        return ed

    def _apply_cell(self, idx, col, raw):
        if idx >= len(self.cart):
            return
        it = self.cart[idx]
        if col == COL_QTY:
            qty = max(parse_int(raw, it["quantity"]), 1)
            stock = self._stock_for(it)
            if stock is not None and qty > stock:
                qty = max(int(stock), 1)
                self.toast(f"Only {stock} of {it['name']} in stock.", "warn")
            it["quantity"] = qty
        else:
            price = parse_amount(raw, it["unit_price"])
            it["unit_price"] = max(price, 0.0)
        it["total_price"] = money(it["quantity"] * it["unit_price"])
        self._redraw_cart()
        if idx < len(self._line_iids):
            self.items.selection_set(self._line_iids[idx])

    def _stock_for(self, it):
        if it.get("kind") == KIND_SERVICE:
            return None
        if it.get("mobile_unit_id"):
            return 1
        return int(self.db.scalar(
            "SELECT stock_quantity FROM products WHERE id=?",
            (it["product_id"],), 0))

    # ── line actions ────────────────────────────────────────────────
    def _remove_selected(self):
        idx = self._selected_index()
        if idx is None:
            self.toast("Select a line on the bill first.", "warn")
            return
        self._remove(idx)

    def _remove(self, idx):
        if 0 <= idx < len(self.cart):
            self.cart.pop(idx)
            self._redraw_cart()

    def _edit_selected_line(self):
        idx = self._selected_index()
        if idx is None:
            self.toast("Select a line on the bill first.", "warn")
            return
        self._edit_line(idx)

    def _edit_line(self, idx):
        """Change what this line PRINTS — model, quality, warranty."""
        if idx >= len(self.cart):
            return
        it = self.cart[idx]
        d = ui.modal(self.app, "Edit bill line", 540, 470)
        ui.modal_header(d, it["name"], "These details print on the bill")
        body = ui.modal_body(d)

        e_name = ui.labelled_entry(body, "Product Name", it["name"],
                                   required=True)
        g = ui.form_grid(body, 2)
        e_brand = ui.labelled_entry(g[0], "Brand", it["brand"])
        e_model = ui.labelled_entry(g[1], "Model", it["model"])
        g2 = ui.form_grid(body, 2)
        c_quality = ui.labelled_combo(g2[0], "Quality / Grade", QUALITY_OPTS,
                                      it.get("quality", ""))
        c_warr = ui.labelled_combo(g2[1], "Warranty (months)", WARRANTY_OPTS,
                                   str(it["warranty_months"]))
        if it["imei"]:
            ctk.CTkLabel(body, text=f"IMEI: {it['imei']}",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.ACCENT).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(body,
                     text="Tip: quantity and rate are changed by "
                          "double-clicking them in the table.",
                     font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(8, 0))

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=460,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            name = e_name.get().strip()
            if not name:
                msg.configure(text="Product name cannot be blank.")
                return
            new = {
                "name": name,
                "brand": e_brand.get().strip(),
                "model": e_model.get().strip(),
                "quality": c_quality.get().strip(),
                "warranty_months": parse_int(c_warr.get()),
            }
            d.destroy()
            it.update(new)
            self._redraw_cart()
            self.toast("Bill line updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Save line", save, "ok", 140, side="right")

    def _clear_cart(self):
        if self.cart and not self.confirm("Clear bill",
                                          "Remove all items from this bill?"):
            return
        self.cart = []
        self.ent_disc.delete(0, "end")
        self.ent_disc.insert(0, "0")
        self.ent_paid.delete(0, "end")
        self.ent_paid.insert(0, "0")
        self._redraw_cart()

    # ══════════════════════════════════════════════════════════════
    # RIGHT — customer, totals, actions
    # ══════════════════════════════════════════════════════════════
    def _build_party(self):
        self.party_box = ctk.CTkFrame(self.cart_top, fg_color="transparent")
        self.party_box.pack(fill="x")
        if self.bill_type == BILL_RETAIL:
            cols = ui.form_grid(self.party_box, 2)
            self.cust_name = ui.labelled_entry(cols[0], "Customer Name",
                                               placeholder="Walk-in", width=150)
            self.cust_phone = ui.labelled_entry(cols[1], "Phone",
                                                placeholder="98XXXXXXXX",
                                                width=150)
            self.retailer_id = None
        else:
            rows = self.db.fetchall(
                "SELECT id, name, shop_name, phone FROM retailers "
                "WHERE is_active=1 ORDER BY name")
            self._retailers = {}
            values = []
            for r in rows:
                label = r["name"] + (f" — {r['shop_name']}"
                                     if r["shop_name"] else "")
                values.append(label)
                self._retailers[label] = r
            if not values:
                ctk.CTkLabel(self.party_box,
                             text="No retailers yet.\nAsk the owner to add one "
                                  "in the Retailers tab.",
                             font=ctk.CTkFont(size=F_SM), text_color=TH.WARN,
                             justify="left").pack(anchor="w", pady=6)
                self.retailer_combo = None
            else:
                self.retailer_combo = ui.labelled_combo(
                    self.party_box, "Retailer", values, values[0],
                    required=True, command=self._on_retailer_pick)
                self._on_retailer_pick(values[0])

    def _on_retailer_pick(self, label):
        r = getattr(self, "_retailers", {}).get(label)
        self.retailer_id = r["id"] if r else None
        # Staff never see a retailer's outstanding / sales history.
        if self.admin and self.retailer_id:
            from ..services import retailer_outstanding
            due = retailer_outstanding(self.db, self.retailer_id)
            self.party_note.configure(
                text=f"Current outstanding: {self.money_text(due)}",
                text_color=TH.DANGER if due > 0.005 else TH.POS)
        else:
            self.party_note.configure(text="")

    def _build_right(self, parent):
        head = ctk.CTkFrame(parent, fg_color=TH.NAVY, height=44,
                            corner_radius=0)
        head.pack(fill="x")
        head.pack_propagate(False)
        ctk.CTkLabel(head, text="🧾  BILL SUMMARY",
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color="white").pack(side="left", padx=14)

        self.cart_top = ctk.CTkFrame(parent, fg_color="transparent")
        self.cart_top.pack(fill="x", padx=12, pady=(8, 0))
        self.party_note = ctk.CTkLabel(
            self.cart_top, text="",
            font=ctk.CTkFont(size=F_SM, weight="bold"), text_color=TH.DANGER)
        self.party_note.pack(anchor="w", pady=(2, 0))
        self._build_party()
        self.party_note.lift()

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=10, pady=(2, 10))
        opts = ctk.CTkFrame(parent, fg_color="transparent")
        opts.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        tot = ctk.CTkFrame(parent, fg_color=TH.PANEL_ALT, corner_radius=10)
        tot.pack(side="bottom", fill="x", padx=10, pady=(0, 6))

        self.lbl_sub = self._total_row(tot, "Subtotal")
        drow = ctk.CTkFrame(tot, fg_color="transparent")
        drow.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(drow, text="Discount", font=ctk.CTkFont(size=F_BODY),
                     text_color=TH.TEXT_DIM).pack(side="left")
        self.ent_disc = ctk.CTkEntry(drow, width=110, height=28,
                                     justify="right",
                                     font=ctk.CTkFont(size=F_BODY),
                                     fg_color=TH.PANEL, border_color=TH.BORDER)
        self.ent_disc.pack(side="right")
        self.ent_disc.insert(0, "0")
        self.ent_disc.bind("<KeyRelease>", lambda _e: self._recalc())

        self.lbl_total = self._total_row(tot, "TOTAL", bold=True,
                                         color=TH.ACCENT, big=True)
        prow = ctk.CTkFrame(tot, fg_color="transparent")
        prow.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(prow, text="Paid", font=ctk.CTkFont(size=F_BODY),
                     text_color=TH.TEXT_DIM).pack(side="left")
        self.ent_paid = ctk.CTkEntry(prow, width=110, height=28,
                                     justify="right",
                                     font=ctk.CTkFont(size=F_BODY),
                                     fg_color=TH.PANEL, border_color=TH.BORDER)
        self.ent_paid.pack(side="right")
        self.ent_paid.insert(0, "0")
        self.ent_paid.bind("<KeyRelease>", lambda _e: self._recalc())
        ctk.CTkButton(prow, text="Full", width=44, height=26,
                      font=ctk.CTkFont(size=F_TN, weight="bold"),
                      fg_color=TH.OK, hover_color=TH.OK_HV,
                      command=self._pay_full).pack(side="right", padx=6)
        self.lbl_due = self._total_row(tot, "Balance Due", bold=True,
                                       color=TH.DANGER)

        ocols = ui.form_grid(opts, 2)
        self.cmb_method = ui.labelled_combo(
            ocols[0], "Payment Method", PAYMENT_METHODS,
            self.settings.get("default_payment", "Cash"), width=150)
        self.ent_notes = ui.labelled_entry(ocols[1], "Note (optional)",
                                           width=150)

        self.btn_complete = ctk.CTkButton(
            actions, text="✅   COMPLETE BILL   (F2)",
            command=lambda: self._save("ask"), height=52, corner_radius=10,
            fg_color=TH.OK, hover_color=TH.OK_HV,
            font=ctk.CTkFont(size=F_LBL, weight="bold"))
        self.btn_complete.pack(fill="x", pady=(0, 6))
        row1 = ctk.CTkFrame(actions, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ui.button(row1, "🖨  Complete & Print", lambda: self._save("print"),
                  "primary", 178, 34, side="left", font_size=F_SM)
        ui.button(row1, "📲  Complete & WhatsApp",
                  lambda: self._save("whatsapp"), "info", 178, 34,
                  side="left", padx=(6, 0), font_size=F_SM)
        ui.button(actions, "Save without printing", lambda: self._save("none"),
                  "muted", 362, 30, font_size=F_SM).pack(fill="x", pady=2)

    def _total_row(self, parent, label, bold=False, color=None, big=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text=label,
                     font=ctk.CTkFont(size=F_LBL if big else F_BODY,
                                      weight="bold" if bold else "normal"),
                     text_color=color or TH.TEXT_DIM).pack(side="left")
        val = ctk.CTkLabel(row, text=f"{self.cur} 0.00",
                           font=ctk.CTkFont(size=F_SEC if big else F_BODY,
                                            weight="bold"),
                           text_color=color or TH.TEXT)
        val.pack(side="right")
        return val

    def _pay_full(self):
        t = compute_totals(self.cart, parse_amount(self.ent_disc.get()), 0)
        self.ent_paid.delete(0, "end")
        self.ent_paid.insert(0, f"{t['total']:.2f}")
        self._recalc()

    def _recalc(self):
        t = compute_totals(self.cart, parse_amount(self.ent_disc.get()),
                           parse_amount(self.ent_paid.get()))
        self.lbl_sub.configure(text=f"{self.cur} {t['subtotal']:,.2f}")
        self.lbl_total.configure(text=f"{self.cur} {t['total']:,.2f}")
        self.lbl_due.configure(
            text=f"{self.cur} {t['due']:,.2f}",
            text_color=TH.POS if t["due"] <= 0.005 else TH.DANGER)
        btn = getattr(self, "btn_complete", None)
        if btn is not None:
            if self.cart:
                btn.configure(text=f"✅   COMPLETE BILL   ·   "
                                   f"{self.cur} {t['total']:,.2f}",
                              state="normal", fg_color=TH.OK)
            else:
                btn.configure(text="✅   COMPLETE BILL   (F2)",
                              state="disabled", fg_color=TH.MUTED)
        return t

    # ── hotkeys ─────────────────────────────────────────────────────
    def hotkey_save(self):
        self._save("ask")

    def hotkey_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    # ══════════════════════════════════════════════════════════════
    # SAVE
    # ══════════════════════════════════════════════════════════════
    def _save(self, action):
        self._kill_editor()
        if not self.cart:
            self.warn("Empty bill", "Add at least one product first.")
            return

        if self.bill_type == BILL_WHOLESALE:
            if not self.retailer_id:
                self.warn("Retailer required",
                          "Choose which retailer this wholesale invoice is for.")
                return
            r = self.db.fetchone("SELECT * FROM retailers WHERE id=?",
                                 (self.retailer_id,))
            cust_name = r["name"] if r else ""
            cust_phone = r["phone"] if r else ""
        else:
            cust_name = self.cust_name.get().strip() or "Walk-in"
            cust_phone = clean_phone(self.cust_phone.get())

        problems = check_stock_available(self.db, self.cart)
        if problems:
            self.error("Stock problem", "\n".join(problems))
            return

        totals = self._recalc()
        method = self.cmb_method.get()
        notes = self.ent_notes.get().strip()
        has_emi = any(it["plan"] == PLAN_INSTALLMENT for it in self.cart)
        plan_type = PLAN_INSTALLMENT if has_emi else PLAN_FULL

        if totals["due"] > 0.005 and self.bill_type == BILL_RETAIL and not has_emi:
            if not self.confirm(
                    "Unpaid balance",
                    f"This bill has a balance due of "
                    f"{self.money_text(totals['due'])}.\n\nSave it as credit?"):
                return

        bill_no = self.db.next_bill_number(self.bill_type)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = now[:10]

        try:
            with self.db.transaction() as cur:
                cur.execute(
                    "INSERT INTO bills (bill_number, bill_type, retailer_id, "
                    " customer_id, customer_name, customer_phone, staff_id, "
                    " bill_date, subtotal, discount_amount, total_amount, "
                    " paid_amount, due_amount, payment_status, payment_method, "
                    " plan_type, notes) "
                    "VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (bill_no, self.bill_type, self.retailer_id, cust_name,
                     cust_phone, self.staff_id(), now, totals["subtotal"],
                     totals["discount"], totals["total"], totals["paid"],
                     totals["due"], totals["status"], method, plan_type, notes))
                bill_id = cur.lastrowid

                for it in self.cart:
                    # snapshot carries any per-line edits (model, quality) so
                    # the printed bill shows exactly what the counter agreed
                    snap = unpack_attrs(it["attrs"])
                    if it.get("quality"):
                        snap["quality"] = it["quality"]
                    cur.execute(
                        "INSERT INTO bill_items (bill_id, product_id, "
                        " mobile_unit_id, product_name, product_brand, "
                        " product_model, product_sku, imei, attrs_snapshot, "
                        " quantity, unit_price, total_price, cogs_price, "
                        " warranty_months) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (bill_id, it["product_id"], it["mobile_unit_id"],
                         it["name"], it["brand"], it["model"], it["sku"],
                         it["imei"], pack_attrs(snap), it["quantity"],
                         it["unit_price"], it["total_price"], it["cogs_price"],
                         it["warranty_months"]))

                    if it["mobile_unit_id"]:
                        cur.execute(
                            "UPDATE mobile_units SET status='sold', bill_id=?, "
                            "sold_date=?, sell_price=? WHERE id=?",
                            (bill_id, today, it["unit_price"],
                             it["mobile_unit_id"]))

                    if it.get("kind") != KIND_SERVICE:
                        cur.execute(
                            "UPDATE products SET stock_quantity = "
                            " MAX(stock_quantity - ?, 0), "
                            " updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (it["quantity"], it["product_id"]))
                        new_qty = cur.execute(
                            "SELECT stock_quantity FROM products WHERE id=?",
                            (it["product_id"],)).fetchone()
                        log_stock(cur, it["product_id"], "sale",
                                  -it["quantity"],
                                  new_qty[0] if new_qty else 0,
                                  bill_no, self.staff_id(),
                                  it["mobile_unit_id"])

                    if it["imei"]:
                        expiry = warranty_expiry(today, it["warranty_months"])
                        cur.execute(
                            "INSERT INTO imei_register (imei, product_id, "
                            " mobile_unit_id, product_name, brand, model, "
                            " color, storage, bill_id, bill_number, "
                            " customer_name, customer_phone, sold_date, "
                            " warranty_months, warranty_expiry, plan_type, "
                            " total_amount, down_payment, installment_amount, "
                            " installment_months, status) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (it["imei"], it["product_id"], it["mobile_unit_id"],
                             it["name"], it["brand"], it["model"],
                             unpack_attrs(it["attrs"]).get("color", ""),
                             unpack_attrs(it["attrs"]).get("storage", ""),
                             bill_id, bill_no, cust_name, cust_phone, today,
                             it["warranty_months"], expiry, it["plan"],
                             it["total_price"], it["down"],
                             (installment_schedule(it["total_price"], it["down"],
                                                   it["months"])[2] or [0])[0]
                             if it["plan"] == PLAN_INSTALLMENT else 0,
                             it["months"],
                             "active" if it["plan"] == PLAN_INSTALLMENT
                             else "closed"))

                if totals["paid"] > 0.005:
                    cur.execute(
                        "INSERT INTO payments (receipt_number, bill_id, "
                        " retailer_id, amount, payment_method, payment_date, "
                        " notes, staff_id) VALUES (?,?,?,?,?,?,?,?)",
                        ("", bill_id, self.retailer_id, totals["paid"],
                         method, today, "Paid at billing", self.staff_id()))
        except Exception as exc:
            self.error("Could not save", f"The bill was not saved:\n\n{exc}")
            return

        pdf_path = os.path.join(BILLS_DIR, f"{bill_no}.pdf")
        try:
            self.docs.generate_bill(bill_id, pdf_path)
            self.app.remember_pdf(pdf_path)
        except Exception as exc:
            self.warn("PDF problem",
                      f"The bill was saved but the PDF failed:\n{exc}")
            pdf_path = None

        self._after_save(bill_no, totals, pdf_path, cust_name, cust_phone,
                         action)

    def _after_save(self, bill_no, totals, pdf_path, name, phone, action):
        if action == "print" and pdf_path:
            self.print_pdf(pdf_path)
        elif action == "whatsapp" and pdf_path:
            self._whatsapp(bill_no, totals, pdf_path, name, phone)

        self._success_dialog(bill_no, totals, pdf_path, name, phone)

        self.cart = []
        self.ent_disc.delete(0, "end")
        self.ent_disc.insert(0, "0")
        self.ent_paid.delete(0, "end")
        self.ent_paid.insert(0, "0")
        self.ent_notes.delete(0, "end")
        if self.bill_type == BILL_RETAIL:
            self.cust_name.delete(0, "end")
            self.cust_phone.delete(0, "end")
        self._redraw_cart()
        self._clear_search()

    def _whatsapp(self, bill_no, totals, pdf_path, name, phone):
        if not phone:
            phone = ui.ask_text(self.app, "WhatsApp",
                                "Enter the customer's WhatsApp number:")
            if not phone:
                return
        msg = wa.bill_message(self.settings.get("shop_name", ""),
                              self.settings.get("shop_phone", ""),
                              bill_no, totals["total"], name, totals["due"],
                              self.cur)
        wa.send(self.app, phone, msg, pdf_path)
        self.toast("WhatsApp opened — press Ctrl+V in the chat to attach the "
                   "PDF.", "info")

    def _success_dialog(self, bill_no, totals, pdf_path, name, phone):
        d = ui.modal(self.app, f"Bill {bill_no}", 520, 400, resizable=False)
        ui.modal_header(d, "✅  BILL SAVED", bill_no, TH.OK)
        body = ui.modal_body(d, scroll=False)

        card = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        card.pack(fill="x", pady=(2, 14))

        def row(label, value, color=None, big=False):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(r, text=label,
                         font=ctk.CTkFont(size=F_LBL if big else F_BODY,
                                          weight="bold" if big else "normal"),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=value,
                         font=ctk.CTkFont(size=F_SEC if big else F_BODY,
                                          weight="bold"),
                         text_color=color or TH.TEXT).pack(side="right")

        row("Total", f"{self.cur} {totals['total']:,.2f}", TH.ACCENT, True)
        row("Paid", f"{self.cur} {totals['paid']:,.2f}", TH.POS)
        if totals["due"] > 0.005:
            row("Balance Due", f"{self.cur} {totals['due']:,.2f}", TH.DANGER)

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x")

        def act(kind):
            d.destroy()
            if kind == "print" and pdf_path:
                self.print_pdf(pdf_path)
            elif kind == "open" and pdf_path:
                self.open_pdf(pdf_path)
            elif kind == "wa" and pdf_path:
                self._whatsapp(bill_no, totals, pdf_path, name, phone)

        ui.button(btns, "🖨  PRINT", lambda: act("print"), "ok", 148, 50,
                  side="left")
        ui.button(btns, "📄  OPEN PDF", lambda: act("open"), "info", 148, 50,
                  side="left", padx=(6, 0))
        ui.button(btns, "📲  WHATSAPP", lambda: act("wa"), "primary", 148, 50,
                  side="left", padx=(6, 0))
        ui.button(ui.modal_footer(d), "DONE", d.destroy, "muted", 120,
                  side="right")
