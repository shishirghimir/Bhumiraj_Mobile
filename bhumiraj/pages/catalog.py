"""Product Catalog — a printable / shareable price list PDF."""
from __future__ import annotations

import os
from datetime import datetime

import customtkinter as ctk

from ..config import CATALOG_DIR, F_BODY, F_LBL, F_SM, F_TN, TH
from ..services import money
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page


class CatalogPage(Page):
    title = "Product Catalog"
    subtitle = "Build a price list PDF to print or send to a customer"

    def build(self):
        outer = self.body()
        split = ctk.CTkFrame(outer, fg_color="transparent")
        split.pack(fill="both", expand=True)

        left = ctk.CTkFrame(split, fg_color=TH.PANEL, corner_radius=12,
                            border_width=1, border_color=TH.BORDER, width=380)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        right = ctk.CTkFrame(split, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True)

        # ── options ────────────────────────────────────────────────
        pad = ctk.CTkScrollableFrame(left, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(pad, text="CATALOG OPTIONS",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(pad, text="Which prices to show",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(4, 2))
        self.price_mode = ctk.StringVar(value="retail")
        for label, value, hint in (
                ("Retail price only", "retail", "For walk-in customers"),
                ("Wholesale price only", "wholesale", "For retailers"),
                ("Both prices", "both", "Internal reference"),
                ("No prices", "none", "Stock list only")):
            ctk.CTkRadioButton(pad, text=f"{label}   ({hint})",
                               variable=self.price_mode, value=value,
                               font=ctk.CTkFont(size=F_SM),
                               fg_color=TH.NAVY).pack(anchor="w", pady=2)
        ctk.CTkLabel(pad,
                     text="Cost price is never printed on a catalog.",
                     font=ctk.CTkFont(size=F_TN),
                     text_color=TH.WARN).pack(anchor="w", pady=(4, 8))

        self.with_images = ctk.CTkCheckBox(
            pad, text="Include product photos", font=ctk.CTkFont(size=F_SM),
            fg_color=TH.NAVY)
        self.with_images.pack(anchor="w", pady=3)
        self.with_images.select()

        self.in_stock_only = ctk.CTkCheckBox(
            pad, text="Only items currently in stock",
            font=ctk.CTkFont(size=F_SM), fg_color=TH.NAVY)
        self.in_stock_only.pack(anchor="w", pady=3)
        self.in_stock_only.select()

        ctk.CTkFrame(pad, height=1, fg_color=TH.BORDER).pack(fill="x", pady=10)
        ctk.CTkLabel(pad, text="Categories to include",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w")
        row = ctk.CTkFrame(pad, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ui.button(row, "Select all", lambda: self._toggle_all(True), "muted",
                  106, 28, side="left")
        ui.button(row, "Clear all", lambda: self._toggle_all(False), "muted",
                  106, 28, side="left", padx=(6, 0))

        self.cat_vars = {}
        cats = self.db.fetchall(
            "SELECT c.id, c.name, "
            " (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id "
            "  AND p.is_active=1) n FROM categories c ORDER BY c.name")
        for c in cats:
            if not c["n"]:
                continue
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(pad, text=f"{c['name']}  ({c['n']})",
                            variable=var, font=ctk.CTkFont(size=F_SM),
                            fg_color=TH.NAVY,
                            command=self._preview).pack(anchor="w", pady=1)
            self.cat_vars[c["id"]] = var

        # ── actions ────────────────────────────────────────────────
        acts = ctk.CTkFrame(left, fg_color="transparent")
        acts.pack(fill="x", padx=12, pady=(0, 12))
        ui.button(acts, "📖  Build & Open Catalog",
                  lambda: self._build("open"), "ok", 340, 44).pack(pady=3)
        r2 = ctk.CTkFrame(acts, fg_color="transparent")
        r2.pack(fill="x")
        ui.button(r2, "🖨  Print", lambda: self._build("print"), "info",
                  166, 36, side="left")
        ui.button(r2, "📲  WhatsApp", lambda: self._build("wa"), "primary",
                  166, 36, side="left", padx=(8, 0))

        # ── preview ────────────────────────────────────────────────
        ui.section(right, "WHAT WILL BE IN THE CATALOG")
        self.preview, _ = ui.make_table(
            right, ("Product", "Brand", "Model", "Category", "Wholesale",
                    "Retail", "Stock"),
            widths=[210, 120, 130, 150, 106, 100, 70],
            anchors=["w", "w", "w", "w", "e", "e", "center"], height=18)
        self.count_lbl = ctk.CTkLabel(right, text="",
                                      font=ctk.CTkFont(size=F_SM),
                                      text_color=TH.TEXT_DIM)
        self.count_lbl.pack(anchor="w", pady=(6, 0))

        self.with_images.configure(command=self._preview)
        self.in_stock_only.configure(command=self._preview)
        self._preview()

    def _toggle_all(self, value):
        for var in self.cat_vars.values():
            if value:
                var.set(True)
            else:
                var.set(False)
        self._preview()

    def _selected_cats(self):
        return [cid for cid, var in self.cat_vars.items() if var.get()]

    def _rows(self):
        cat_ids = self._selected_cats()
        if not cat_ids:
            return []
        where = ["p.is_active = 1",
                 "p.category_id IN (%s)" % ",".join("?" * len(cat_ids))]
        params = list(cat_ids)
        if self.in_stock_only.get():
            where.append("p.stock_quantity > 0")
        return self.db.fetchall(
            "SELECT p.*, c.name AS cat_name FROM products p "
            "JOIN categories c ON p.category_id = c.id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY c.name, p.brand, p.name", params)

    def _preview(self):
        for r in self.preview.get_children():
            self.preview.delete(r)
        rows = self._rows()
        for p in rows:
            qty = int(p["stock_quantity"])
            self.preview.insert("", "end", values=(
                p["name"], p["brand"] or "—", p["model"] or "—",
                p["cat_name"], f"{money(p['wholesale_price']):,.2f}",
                f"{money(p['sell_price']):,.2f}", qty),
                tags=("oos",) if qty <= 0 else ())
        self.count_lbl.configure(
            text=f"{len(rows):,} product(s) will be printed across "
                 f"{len(self._selected_cats())} category(ies).")

    def _build(self, action):
        cat_ids = self._selected_cats()
        if not cat_ids:
            self.warn("No categories", "Tick at least one category.")
            return
        rows = self._rows()
        if not rows:
            self.warn("Nothing to print",
                      "No products match those options.\n\n"
                      "Try unticking 'Only items currently in stock'.")
            return

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        path = os.path.join(CATALOG_DIR, f"Catalog_{stamp}.pdf")
        try:
            self.docs.generate_catalog(
                path, cat_ids, self.price_mode.get(),
                bool(self.with_images.get()), bool(self.in_stock_only.get()))
            self.app.remember_pdf(path)
        except Exception as exc:
            self.error("Catalog failed", str(exc))
            return

        if action == "print":
            self.print_pdf(path)
        elif action == "wa":
            phone = ui.ask_text(self.app, "WhatsApp",
                                "Enter the number to send the catalog to:")
            if not phone:
                return
            shop = self.settings.get("shop_name", "")
            msg = (f"Namaste,\n\nThis is *{shop}*.\n\n"
                   f"Here is our latest product catalog "
                   f"({len(rows)} items).\n\n"
                   f"For orders call {self.settings.get('shop_phone', '')}.\n"
                   "Thank you! 🙏")
            wa.send(self.app, phone, msg, path)
            self.toast("WhatsApp opened — Ctrl+V to attach.", "info")
        else:
            self.open_pdf(path)
            self.toast(f"Catalog built with {len(rows)} products.")
