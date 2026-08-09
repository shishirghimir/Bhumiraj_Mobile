"""Products / Stock.

Admin manages everything. Staff get a read-only view and — importantly —
never see the cost price: only Wholesale and Retail.

The product form asks different questions per category kind (a phone asks
colour/storage/RAM/network, a watch asks movement/strap/water resistance…),
driven by KIND_FIELDS in config.py.
"""
from __future__ import annotations

import customtkinter as ctk

from ..config import (F_BODY, F_LBL, F_SM, F_TN, KIND_FIELDS, KIND_LABELS,
                      KIND_MOBILE, KIND_SERVICE, PRODUCT_IMG_DIR, TH,
                      WARRANTY_OPTS)
from ..services import (adjust_stock, attrs_summary, delete_product, make_sku,
                        money, pack_attrs, parse_amount, parse_int,
                        stock_value, unpack_attrs)
from .. import ui_helpers as ui
from .base import Page


class ProductsPage(Page):
    title = "Products & Stock"

    @property
    def subtitle(self):
        return ("Add, edit and price every item the shop sells"
                if self.app.is_admin()
                else "Stock list — view only. Ask the owner to change stock.")

    def build(self):
        outer = self.body()

        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=340, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Search name, brand, model, SKU…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        cats = self.db.fetchall("SELECT id, name FROM categories ORDER BY name")
        self._cat_by_name = {c["name"]: c["id"] for c in cats}
        self.cat_filter = ctk.CTkComboBox(
            bar, values=["All categories"] + [c["name"] for c in cats],
            width=200, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh())
        self.cat_filter.pack(side="left", padx=6)
        self.cat_filter.set("All categories")

        self.low_only = ctk.CTkCheckBox(bar, text="Low stock only",
                                        font=ctk.CTkFont(size=F_SM),
                                        command=self.refresh, fg_color=TH.NAVY)
        self.low_only.pack(side="left", padx=8)

        if self.admin:
            ui.button(bar, "🗑  Delete", self._delete, "danger", 110, 36,
                      side="right")
            ui.button(bar, "📊  Adjust Stock", self._adjust, "info", 140, 36,
                      side="right", padx=(0, 6))
            ui.button(bar, "✏️  Edit", self._edit, "primary", 100, 36,
                      side="right", padx=(0, 6))
            ui.button(bar, "➕  Add Product", lambda: self._form(None), "ok",
                      148, 36, side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        cols = (["Product", "Brand", "Model", "Category", "Details",
                 "Cost", "Wholesale", "Retail", "Stock", "SKU"]
                if self.admin else
                ["Product", "Brand", "Model", "Category", "Details",
                 "Wholesale", "Retail", "Stock", "SKU"])
        widths = ([190, 100, 110, 120, 150, 78, 84, 78, 62, 100]
                  if self.admin else
                  [210, 110, 120, 130, 170, 90, 84, 66, 110])
        anchors = (["w", "w", "w", "w", "w", "e", "e", "e", "center", "w"]
                   if self.admin else
                   ["w", "w", "w", "w", "w", "e", "e", "center", "w"])
        self.tree, _ = ui.make_table(outer, cols, widths, anchors, height=17,
                                     on_double=self._edit if self.admin
                                     else self._view)
        self.refresh()

    # ── data ────────────────────────────────────────────────────────
    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["p.is_active = 1"]
        params = []
        cat = self.cat_filter.get()
        if cat != "All categories" and cat in self._cat_by_name:
            where.append("p.category_id = ?")
            params.append(self._cat_by_name[cat])
        if self.low_only.get():
            where.append("p.stock_quantity <= p.min_stock_level")
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(p.name LIKE ? OR p.brand LIKE ? OR p.model LIKE ? "
                         " OR p.sku LIKE ? OR p.barcode LIKE ? OR p.attrs LIKE ?)")
            params += [like] * 6

        rows = self.db.fetchall(
            "SELECT p.*, c.name AS cat_name, c.kind AS cat_kind "
            "FROM products p JOIN categories c ON p.category_id = c.id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY p.brand, p.name", params)

        self._rows = {}
        for r in rows:
            qty = int(r["stock_quantity"])
            tag = ("oos" if qty <= 0
                   else "low" if qty <= int(r["min_stock_level"] or 0) else "")
            details = attrs_summary(unpack_attrs(r["attrs"]), limit=3)
            base = [r["name"], r["brand"] or "—", r["model"] or "—",
                    r["cat_name"], details or "—"]
            if self.admin:
                base.append(f"{money(r['cost_price']):,.2f}")
            base += [f"{money(r['wholesale_price']):,.2f}",
                     f"{money(r['sell_price']):,.2f}",
                     "—" if r["cat_kind"] == KIND_SERVICE else qty,
                     r["sku"] or "—"]
            iid = self.tree.insert("", "end", values=tuple(base),
                                   tags=(tag,) if tag else ())
            self._rows[iid] = r

        for w in self.stats.winfo_children():
            w.destroy()
        total = len(rows)
        low = sum(1 for r in rows
                  if 0 < int(r["stock_quantity"]) <= int(r["min_stock_level"] or 0))
        oos = sum(1 for r in rows if int(r["stock_quantity"]) <= 0
                  and r["cat_kind"] != KIND_SERVICE)
        ui.stat_card(self.stats, "Products listed", f"{total:,}", TH.NAVY, 170)
        ui.stat_card(self.stats, "Low stock", f"{low:,}", TH.WARN, 150)
        ui.stat_card(self.stats, "Out of stock", f"{oos:,}", TH.DANGER, 150)
        if self.admin:
            ui.stat_card(self.stats, "Stock value (cost)",
                         self.money_text(stock_value(self.db, True)),
                         TH.OK, 208)
            ui.stat_card(self.stats, "Stock value (retail)",
                         self.money_text(stock_value(self.db, False)),
                         TH.ACCENT_DIM, 214)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a product first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _view(self):
        row = self._selected()
        if row:
            self._form(row, read_only=True)

    def _edit(self):
        if self.deny_staff("edit products"):
            return
        row = self._selected()
        if row:
            self._form(row)

    # ── form ────────────────────────────────────────────────────────
    def _form(self, row=None, read_only=False):
        editing = row is not None
        d = ui.modal(self.app, "Product details" if read_only else
                     ("Edit product" if editing else "Add a new product"),
                     760, 720)
        ui.modal_header(
            d, "Product details" if read_only else
            ("Edit product" if editing else "Add a new product"),
            "Fields marked * are required")
        body = ui.modal_body(d)

        cats = self.db.fetchall("SELECT * FROM categories ORDER BY name")
        cat_names = [c["name"] for c in cats]
        cat_map = {c["name"]: c for c in cats}
        current_cat = None
        if editing:
            current_cat = self.db.fetchone("SELECT * FROM categories WHERE id=?",
                                           (row["category_id"],))

        ui.section(body, "Basics")
        g1 = ui.form_grid(body, 2)
        e_name = ui.labelled_entry(g1[0], "Product Name",
                                   row["name"] if editing else "",
                                   required=True,
                                   placeholder="e.g. Galaxy A15")
        c_cat = ui.labelled_combo(
            g1[1], "Category", cat_names,
            current_cat["name"] if current_cat else (cat_names[0] if cat_names
                                                     else ""),
            required=True)
        e_brand = ui.labelled_entry(g1[0], "Brand", row["brand"] if editing else "",
                                    required=True, placeholder="e.g. Samsung")
        e_model = ui.labelled_entry(g1[1], "Model / Model No.",
                                    row["model"] if editing else "",
                                    required=True, placeholder="e.g. SM-A155F")
        e_sku = ui.labelled_entry(g1[0], "SKU (blank = auto)",
                                  row["sku"] if editing else "")
        e_barcode = ui.labelled_entry(g1[1], "Barcode",
                                      row["barcode"] if editing else "")

        ui.section(body, "Pricing")
        note = ("All three prices are stored. Staff can only see Wholesale "
                "and Retail — the cost price stays with the owner.")
        ctk.CTkLabel(body, text=note, font=ctk.CTkFont(size=F_TN),
                     text_color=TH.TEXT_DIM, wraplength=680,
                     justify="left").pack(anchor="w", pady=(0, 2))
        g2 = ui.form_grid(body, 3)
        e_cost = None
        if self.admin:
            e_cost = ui.labelled_entry(
                g2[0], "Cost Price (CP)",
                f"{money(row['cost_price']):.2f}" if editing else "0",
                required=True)
        else:
            ctk.CTkLabel(g2[0], text="Cost Price\nOwner only",
                         font=ctk.CTkFont(size=F_SM, weight="bold"),
                         text_color=TH.MUTED, justify="left").pack(anchor="w",
                                                                   pady=10)
        e_ws = ui.labelled_entry(
            g2[1], "Wholesale Price",
            f"{money(row['wholesale_price']):.2f}" if editing else "0",
            required=True)
        e_retail = ui.labelled_entry(
            g2[2], "Retail Price",
            f"{money(row['sell_price']):.2f}" if editing else "0",
            required=True)

        margin_lbl = ctk.CTkLabel(body, text="",
                                  font=ctk.CTkFont(size=F_SM, weight="bold"),
                                  text_color=TH.POS)
        margin_lbl.pack(anchor="w", pady=(2, 0))

        def show_margin(_e=None):
            if not self.admin or not e_cost:
                return
            cp = parse_amount(e_cost.get())
            rp = parse_amount(e_retail.get())
            wp = parse_amount(e_ws.get())
            if cp <= 0:
                margin_lbl.configure(text="")
                return
            rm = (rp - cp) / cp * 100 if cp else 0
            wm = (wp - cp) / cp * 100 if cp else 0
            margin_lbl.configure(
                text=f"Retail margin {rm:+.1f}%  ·  Wholesale margin {wm:+.1f}%"
                     f"   (profit {self.cur} {money(rp - cp):,.2f} retail)",
                text_color=TH.POS if rp >= cp else TH.DANGER)
        for w in (e_cost, e_ws, e_retail):
            if w:
                w.bind("<KeyRelease>", show_margin)

        ui.section(body, "Stock & warranty")
        g3 = ui.form_grid(body, 3)
        e_qty = ui.labelled_entry(
            g3[0], "Stock Quantity",
            str(row["stock_quantity"]) if editing else "0")
        e_min = ui.labelled_entry(
            g3[1], "Low-stock Alert At",
            str(row["min_stock_level"]) if editing else "2")
        c_warr = ui.labelled_combo(
            g3[2], "Warranty (months)", WARRANTY_OPTS,
            str(row["warranty_months"]) if editing else "0")
        g3b = ui.form_grid(body, 2)
        e_unit = ui.labelled_entry(g3b[0], "Unit",
                                   row["unit"] if editing else "pcs")
        serial_var = ctk.BooleanVar(
            value=bool(row["is_serialized"]) if editing else False)
        ctk.CTkCheckBox(g3b[1], text="Track each unit by IMEI",
                        variable=serial_var, font=ctk.CTkFont(size=F_SM),
                        fg_color=TH.NAVY,
                        command=lambda: toggle_imei()).pack(anchor="w", pady=22)

        # ── IMEI numbers, right here in the product form ────────────
        # Not every phone is sold IMEI-tracked, so this whole block only
        # appears when "Track each unit by IMEI" is ticked. Entering the
        # numbers here means the shop never has to add the product and then
        # go to the Mobiles tab to type the IMEIs a second time.
        imei_box = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        imei_pad = ctk.CTkFrame(imei_box, fg_color="transparent")
        imei_pad.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(imei_pad, text="IMEI NUMBERS",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w")
        imei_help = ctk.CTkLabel(
            imei_pad,
            text="Type or scan ONE IMEI PER LINE — one line for each handset "
                 "in the box.\nThe stock quantity is set automatically from "
                 "how many you enter.",
            font=ctk.CTkFont(size=F_TN), text_color=TH.TEXT_DIM,
            justify="left")
        imei_help.pack(anchor="w", pady=(2, 6))
        e_imeis = ctk.CTkTextbox(imei_pad, height=110,
                                 font=ctk.CTkFont(size=F_BODY),
                                 fg_color=TH.PANEL, border_color=TH.BORDER,
                                 border_width=1)
        e_imeis.pack(fill="x")
        imei_count = ctk.CTkLabel(imei_pad, text="0 handsets entered",
                                  font=ctk.CTkFont(size=F_SM, weight="bold"),
                                  text_color=TH.TEXT_DIM)
        imei_count.pack(anchor="w", pady=(4, 0))

        def read_imeis():
            raw = e_imeis.get("1.0", "end").strip()
            return [ln.strip() for ln in raw.splitlines() if ln.strip()]

        def on_imei_type(_e=None):
            n = len(read_imeis())
            imei_count.configure(
                text=f"{n} handset{'s' if n != 1 else ''} entered"
                     + ("  →  stock will be set to " + str(n) if n else ""),
                text_color=TH.POS if n else TH.TEXT_DIM)
            if n:
                e_qty.delete(0, "end")
                e_qty.insert(0, str(n))
        e_imeis.bind("<KeyRelease>", on_imei_type)

        if editing:
            existing_units = int(self.db.scalar(
                "SELECT COUNT(*) FROM mobile_units WHERE product_id=?",
                (row["id"],), 0))
            if existing_units:
                imei_help.configure(
                    text=f"This product already has {existing_units} handset(s) "
                         f"registered.\nAnything you type here is ADDED to "
                         f"them — manage existing ones in the Mobiles tab.")

        def toggle_imei():
            if serial_var.get():
                imei_box.pack(fill="x", pady=(8, 0))
                e_qty.configure(state="disabled")
            else:
                imei_box.pack_forget()
                e_qty.configure(state="normal")
            on_imei_type()

        # ── dynamic per-kind fields ─────────────────────────────────
        ui.section(body, "Details")
        kind_hint = ctk.CTkLabel(body, text="",
                                 font=ctk.CTkFont(size=F_TN),
                                 text_color=TH.ACCENT)
        kind_hint.pack(anchor="w")
        dyn_holder = ctk.CTkFrame(body, fg_color="transparent")
        dyn_holder.pack(fill="x")
        dyn_widgets = {}
        existing_attrs = unpack_attrs(row["attrs"]) if editing else {}

        def rebuild_dynamic(_value=None):
            for w in dyn_holder.winfo_children():
                w.destroy()
            dyn_widgets.clear()
            cat = cat_map.get(c_cat.get())
            kind = cat["kind"] if cat else "general"
            kind_hint.configure(
                text=f"Showing the fields that matter for a "
                     f"{KIND_LABELS.get(kind, 'product')}.")
            fields = KIND_FIELDS.get(kind, [])
            grid = ui.form_grid(dyn_holder, 2)
            for i, (key, label, widget, options) in enumerate(fields):
                col = grid[i % 2]
                val = existing_attrs.get(key, "")
                if widget == "combo":
                    dyn_widgets[key] = ui.labelled_combo(col, label,
                                                         options or [""], val)
                else:
                    dyn_widgets[key] = ui.labelled_entry(col, label, val)
            # Picking a Mobile category turns IMEI tracking on and reveals the
            # IMEI box straight away — but the shop can still untick it for a
            # phone they don't want tracked unit-by-unit.
            if kind == KIND_MOBILE and not editing and not serial_var.get():
                serial_var.set(True)
            toggle_imei()
        c_cat.configure(command=rebuild_dynamic)
        rebuild_dynamic()

        ui.section(body, "Photo & description")
        img_row = ctk.CTkFrame(body, fg_color="transparent")
        img_row.pack(fill="x", pady=4)
        state = {"image": row["image_path"] if editing else ""}
        preview = ctk.CTkLabel(img_row, text="No photo", width=110, height=110,
                               fg_color=TH.PANEL_ALT, corner_radius=8,
                               font=ctk.CTkFont(size=F_SM),
                               text_color=TH.TEXT_DIM)
        preview.pack(side="left")

        def draw_preview():
            img = ui.load_ctk_image(state["image"], (104, 104))
            if img:
                preview.configure(image=img, text="")
                preview.image = img
            else:
                preview.configure(image=None, text="No photo")
        draw_preview()

        def choose_image():
            path = ui.pick_product_image(e_name.get() or "product")
            if path:
                state["image"] = path
                draw_preview()

        def clear_image():
            state["image"] = ""
            draw_preview()

        img_btns = ctk.CTkFrame(img_row, fg_color="transparent")
        img_btns.pack(side="left", padx=12)
        ui.button(img_btns, "📷  Choose photo", choose_image, "info", 158, 34
                  ).pack(pady=2)
        ui.button(img_btns, "Remove photo", clear_image, "muted", 158, 30
                  ).pack(pady=2)
        ctk.CTkLabel(img_btns,
                     text="Used in the product catalog PDF.",
                     font=ctk.CTkFont(size=F_TN),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(4, 0))

        e_desc = ctk.CTkTextbox(body, height=68, font=ctk.CTkFont(size=F_BODY),
                                fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
                                border_width=1)
        e_desc.pack(fill="x", pady=(8, 0))
        if editing and row["description"]:
            e_desc.insert("1.0", row["description"])

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=680,
                           justify="left")
        msg.pack(anchor="w", pady=(8, 0))

        # ── save ────────────────────────────────────────────────────
        def save():
            name = e_name.get().strip()
            brand = e_brand.get().strip()
            model = e_model.get().strip()

            missing = ui.required_missing([
                ("Product Name", name), ("Brand", brand),
                ("Model", model), ("Category", c_cat.get()),
            ])
            if missing:
                msg.configure(
                    text="Please fill in: " + ", ".join(missing)
                    + ".\nBrand and Model are required so they print on the "
                      "bill correctly.")
                return

            cat = cat_map.get(c_cat.get())
            if not cat:
                msg.configure(text="Pick a valid category.")
                return

            cost = parse_amount(e_cost.get()) if e_cost else (
                money(row["cost_price"]) if editing else 0.0)
            ws = parse_amount(e_ws.get())
            retail = parse_amount(e_retail.get())
            if retail <= 0:
                msg.configure(text="Retail price must be greater than zero.")
                return
            if ws <= 0:
                ws = retail
            if self.admin and cost > retail:
                if not self.confirm(
                        "Selling below cost",
                        f"Retail price ({self.cur} {retail:,.2f}) is lower than "
                        f"the cost price ({self.cur} {cost:,.2f}).\n\n"
                        "Save anyway?"):
                    return

            # ── IMEIs typed into this form ──────────────────────────
            imeis = read_imeis() if serial_var.get() else []
            if imeis:
                bad = [i for i in imeis
                       if not i.isdigit() or not (10 <= len(i) <= 20)]
                if bad:
                    msg.configure(
                        text="These IMEIs look wrong (digits only, 10–20 "
                             "long): " + ", ".join(bad[:4]))
                    return
                if len(set(imeis)) != len(imeis):
                    dupes = {i for i in imeis if imeis.count(i) > 1}
                    msg.configure(text="The same IMEI is typed twice: "
                                       + ", ".join(list(dupes)[:4]))
                    return
                taken = [i for i in imeis if self.db.fetchone(
                    "SELECT 1 FROM mobile_units WHERE imei=?", (i,))]
                if taken:
                    msg.configure(
                        text="Already registered to another handset: "
                             + ", ".join(taken[:4]))
                    return

            qty = len(imeis) if imeis else parse_int(e_qty.get())
            if editing and imeis:
                qty = int(row["stock_quantity"]) + len(imeis)
            if qty < 0:
                msg.configure(text="Stock quantity cannot be negative.")
                return
            if serial_var.get() and not editing and not imeis:
                if not self.confirm(
                        "No IMEI numbers",
                        "IMEI tracking is on but you have not entered any IMEI "
                        "numbers.\n\nSave the product with zero stock and add "
                        "the handsets later?"):
                    return

            attrs = pack_attrs({k: w.get() for k, w in dyn_widgets.items()})
            sku = e_sku.get().strip()
            if not sku:
                sku = make_sku(self.db, cat["code"], name, brand)
            clash = self.db.fetchone(
                "SELECT id FROM products WHERE sku=? AND id != ?",
                (sku, row["id"] if editing else -1))
            if clash:
                msg.configure(text=f"SKU '{sku}' is already used by another "
                                   "product.")
                return

            desc = e_desc.get("1.0", "end").strip()
            params = (name, cat["id"], sku, e_barcode.get().strip(), brand,
                      model, cost, ws, retail, qty, parse_int(e_min.get(), 2),
                      e_unit.get().strip() or "pcs",
                      parse_int(c_warr.get()), 1 if serial_var.get() else 0,
                      attrs, desc, state["image"])
            colour = (dyn_widgets["color"].get().strip()
                      if "color" in dyn_widgets else "")
            storage = (dyn_widgets["storage"].get().strip()
                       if "storage" in dyn_widgets else "")
            ram = dyn_widgets["ram"].get().strip() if "ram" in dyn_widgets else ""

            try:
                from ..services import log_stock
                # One transaction for the product AND its handsets, so a bad
                # IMEI can never leave a product saved with half its units.
                with self.db.transaction() as cur:
                    if editing:
                        old_qty = int(row["stock_quantity"])
                        cur.execute(
                            "UPDATE products SET name=?, category_id=?, sku=?, "
                            " barcode=?, brand=?, model=?, cost_price=?, "
                            " wholesale_price=?, sell_price=?, "
                            " stock_quantity=?, min_stock_level=?, unit=?, "
                            " warranty_months=?, is_serialized=?, attrs=?, "
                            " description=?, image_path=?, "
                            " updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            params + (row["id"],))
                        pid = row["id"]
                        if qty != old_qty:
                            log_stock(cur, pid, "edit", qty - old_qty, qty,
                                      "Edited in product form", self.staff_id())
                    else:
                        cur.execute(
                            "INSERT INTO products (name, category_id, sku, "
                            " barcode, brand, model, cost_price, "
                            " wholesale_price, sell_price, stock_quantity, "
                            " min_stock_level, unit, warranty_months, "
                            " is_serialized, attrs, description, image_path) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            params)
                        pid = cur.lastrowid
                        log_stock(cur, pid, "opening", qty, qty,
                                  "Product created", self.staff_id())

                    for imei in imeis:
                        cur.execute(
                            "INSERT INTO mobile_units (product_id, imei, "
                            " color, storage, ram, condition, cost_price, "
                            " sell_price, status) "
                            "VALUES (?,?,?,?,?,'New',?,?,'in_stock')",
                            (pid, imei, colour, storage, ram, cost, retail))
                    if imeis:
                        log_stock(cur, pid, "imei_intake", len(imeis), qty,
                                  f"{len(imeis)} handset(s) entered on the "
                                  f"product form", self.staff_id())
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return

            d.destroy()
            self.refresh()
            if imeis:
                self.toast(f"Product saved with {len(imeis)} handset(s) "
                           f"registered.")
            else:
                self.toast("Product saved." if editing else "Product added.")

        foot = ui.modal_footer(d)
        if read_only:
            ui.button(foot, "Close", d.destroy, "muted", 120, side="right")
            for widget in body.winfo_children():
                _disable_tree(widget)
        else:
            ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
            ui.button(foot, "💾  Save Product", save, "ok", 168, side="right")
        show_margin()

    # ── stock adjust / delete ───────────────────────────────────────
    def _adjust(self):
        if self.deny_staff("adjust stock"):
            return
        row = self._selected()
        if not row:
            return

        d = ui.modal(self.app, "Adjust stock", 460, 400, resizable=False)
        ui.modal_header(d, "Adjust stock", row["name"])
        body = ui.modal_body(d, scroll=False)
        ctk.CTkLabel(body, text=f"Current stock:  {row['stock_quantity']} "
                                f"{row['unit'] or 'pcs'}",
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w", pady=(0, 8))
        e_delta = ui.labelled_entry(body, "Change (+ adds, − removes)", "0",
                                    required=True, placeholder="e.g. 10 or -3")
        c_reason = ui.labelled_combo(
            body, "Reason",
            ["New purchase", "Damaged", "Lost / stolen", "Return to supplier",
             "Stock count correction", "Sample / gift", "Other"],
            "New purchase")
        e_note = ui.labelled_entry(body, "Note")
        result = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=F_SM),
                              text_color=TH.TEXT_DIM)
        result.pack(anchor="w", pady=(6, 0))

        def preview(_e=None):
            new = int(row["stock_quantity"]) + parse_int(e_delta.get())
            result.configure(
                text=f"New stock will be: {new}",
                text_color=TH.DANGER if new < 0 else TH.POS)
        e_delta.bind("<KeyRelease>", preview)
        preview()

        def apply():
            delta = parse_int(e_delta.get())
            if delta == 0:
                self.warn("Nothing to do", "Enter a non-zero change.")
                return
            reason = c_reason.get()
            if e_note.get().strip():
                reason += f" — {e_note.get().strip()}"
            try:
                adjust_stock(self.db, row["id"], delta, reason, self.staff_id())
            except ValueError as exc:
                self.warn("Cannot adjust", str(exc))
                return
            d.destroy()
            self.refresh()
            self.toast("Stock updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Apply", apply, "ok", 130, side="right")

    def _delete(self):
        if self.deny_staff("delete products"):
            return
        row = self._selected()
        if not row:
            return
        sold = int(self.db.scalar(
            "SELECT COUNT(*) FROM bill_items WHERE product_id=?",
            (row["id"],), 0))
        units = int(self.db.scalar(
            "SELECT COUNT(*) FROM mobile_units WHERE product_id=?",
            (row["id"],), 0))
        extra = ""
        if sold:
            extra += (f"\n\nThis product appears on {sold} bill line(s). "
                      "Those bills keep their own copy of the name and price, "
                      "so old bills will still print correctly.")
        if units:
            extra += f"\n\n{units} IMEI unit record(s) will also be deleted."

        if not self.confirm(
                "Delete product permanently",
                f"Permanently delete '{row['name']}'?\n\n"
                f"This cannot be undone.{extra}", danger=True):
            return
        confirm_text = ui.ask_text(
            self.app, "Confirm delete",
            "Type DELETE to permanently remove this product:")
        if (confirm_text or "").strip().upper() != "DELETE":
            self.toast("Delete cancelled.", "warn")
            return
        try:
            delete_product(self.db, row["id"], self.staff_id())
        except Exception as exc:
            self.error("Delete failed", str(exc))
            return
        self.refresh()
        self.toast("Product deleted permanently.")

    def hotkey_search(self):
        self.search.focus_set()


def _disable_tree(widget):
    """Recursively disable inputs so a staff 'view' form is truly read-only."""
    try:
        if isinstance(widget, (ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkTextbox,
                               ctk.CTkCheckBox, ctk.CTkButton)):
            widget.configure(state="disabled")
    except Exception:
        pass
    for child in getattr(widget, "winfo_children", lambda: [])():
        _disable_tree(child)
