"""Mobiles (IMEI) — one row per physical handset.

This is the dedicated phone tab: every unit is tracked by its own IMEI with
colour, storage, condition and cost, so the shop always knows exactly which
handset is on the shelf and which one went out on which bill.
"""
from __future__ import annotations

import customtkinter as ctk

from ..config import (COLOR_OPTS, CONDITION_OPTS, F_BODY, F_LBL, F_SM, F_TN,
                      KIND_MOBILE, RAM_OPTS, STORAGE_OPTS, TH)
from ..services import (log_stock, money, parse_amount, unpack_attrs)
from .. import ui_helpers as ui
from .base import Page

STATUS_LABEL = {"in_stock": "In Stock", "sold": "Sold", "returned": "Returned"}


class MobilesPage(Page):
    title = "Mobiles — IMEI Stock"

    @property
    def subtitle(self):
        return ("Every handset tracked individually by IMEI"
                if self.app.is_admin()
                else "Handset list — view only")

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=330, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  IMEI, model, brand, colour, customer…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.status_filter = ui.FilterChips(
            bar, ["All", "In Stock", "Sold", "Returned"],
            lambda _v: self.refresh(), "In Stock")
        self.status_filter.pack(side="left", padx=10)

        if self.admin:
            ui.button(bar, "🗑  Delete", self._delete, "danger", 104, 36,
                      side="right")
            ui.button(bar, "✏️  Edit", self._edit, "primary", 96, 36,
                      side="right", padx=(0, 6))
            ui.button(bar, "➕  Add Handsets", lambda: self._form(None), "ok",
                      154, 36, side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        cols = (["IMEI", "Brand", "Model", "Colour", "Storage", "RAM",
                 "Condition", "Cost", "Price", "Status", "Sold To", "Bill"]
                if self.admin else
                ["IMEI", "Brand", "Model", "Colour", "Storage", "RAM",
                 "Condition", "Price", "Status", "Sold To", "Bill"])
        widths = ([146, 96, 120, 88, 76, 68, 96, 84, 88, 82, 132, 108]
                  if self.admin else
                  [150, 100, 130, 92, 80, 72, 100, 92, 86, 140, 112])
        anchors = (["w", "w", "w", "w", "w", "w", "w", "e", "e", "center",
                    "w", "w"] if self.admin else
                   ["w", "w", "w", "w", "w", "w", "w", "e", "center", "w", "w"])
        self.tree, _ = ui.make_table(outer, tuple(cols), widths, anchors,
                                     height=17,
                                     on_double=self._edit if self.admin
                                     else None)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        where = ["1=1"]
        params = []
        status = self.status_filter.get()
        rev = {v: k for k, v in STATUS_LABEL.items()}
        if status in rev:
            where.append("u.status = ?")
            params.append(rev[status])
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(u.imei LIKE ? OR u.imei2 LIKE ? OR u.serial_no LIKE ? "
                         " OR u.color LIKE ? OR p.name LIKE ? OR p.brand LIKE ? "
                         " OR p.model LIKE ? OR b.customer_name LIKE ? "
                         " OR b.bill_number LIKE ?)")
            params += [like] * 9

        rows = self.db.fetchall(
            "SELECT u.*, p.name, p.brand, p.model, p.sell_price AS list_price, "
            "       b.bill_number, b.customer_name "
            "FROM mobile_units u JOIN products p ON u.product_id = p.id "
            "LEFT JOIN bills b ON u.bill_id = b.id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY (u.status='in_stock') DESC, u.id DESC", params)

        self._rows = {}
        for u in rows:
            price = money(u["sell_price"]) or money(u["list_price"])
            vals = [u["imei"], u["brand"] or "—", u["model"] or u["name"],
                    u["color"] or "—", u["storage"] or "—", u["ram"] or "—",
                    u["condition"] or "New"]
            if self.admin:
                vals.append(f"{money(u['cost_price']):,.2f}")
            vals += [f"{price:,.2f}",
                     STATUS_LABEL.get(u["status"], u["status"]),
                     u["customer_name"] or "—", u["bill_number"] or "—"]
            tag = ("pos" if u["status"] == "in_stock"
                   else "muted" if u["status"] == "sold" else "low")
            iid = self.tree.insert("", "end", values=tuple(vals), tags=(tag,))
            self._rows[iid] = u

        for w in self.stats.winfo_children():
            w.destroy()
        in_stock = int(self.db.scalar(
            "SELECT COUNT(*) FROM mobile_units WHERE status='in_stock'",
            None, 0))
        sold = int(self.db.scalar(
            "SELECT COUNT(*) FROM mobile_units WHERE status='sold'", None, 0))
        ui.stat_card(self.stats, "Handsets in stock", f"{in_stock:,}",
                     TH.OK, 190)
        ui.stat_card(self.stats, "Sold", f"{sold:,}", TH.MUTED, 140)
        ui.stat_card(self.stats, "Listed here", f"{len(rows):,}", TH.NAVY, 158)
        if self.admin:
            value = money(self.db.scalar(
                "SELECT COALESCE(SUM(cost_price),0) FROM mobile_units "
                "WHERE status='in_stock'", None, 0))
            ui.stat_card(self.stats, "Stock value (cost)",
                         self.money_text(value), TH.ACCENT_DIM, 216)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a handset first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _edit(self):
        if self.deny_staff("edit handsets"):
            return
        row = self._selected()
        if row:
            self._form(row)

    # ── add / edit ──────────────────────────────────────────────────
    def _form(self, row=None):
        if self.deny_staff("add or edit handsets"):
            return
        editing = row is not None
        d = ui.modal(self.app, "Edit handset" if editing else "Add handsets",
                     680, 640)
        ui.modal_header(d, "Edit handset" if editing else "Add handsets",
                        "IMEI is required — it is what the warranty is tied to")
        body = ui.modal_body(d)

        phones = self.db.fetchall(
            "SELECT p.*, c.kind FROM products p "
            "JOIN categories c ON p.category_id=c.id "
            "WHERE p.is_active=1 AND (c.kind = ? OR p.is_serialized = 1) "
            "ORDER BY p.brand, p.name", (KIND_MOBILE,))
        if not phones:
            ctk.CTkLabel(body,
                         text="No mobile products exist yet.\n\n"
                              "Add a product in a Mobile category first "
                              "(Products → Add Product), then come back here "
                              "to register its IMEI units.",
                         font=ctk.CTkFont(size=F_BODY), text_color=TH.WARN,
                         justify="left").pack(anchor="w", pady=20)
            ui.button(ui.modal_footer(d), "Close", d.destroy, "muted", 120,
                      side="right")
            return

        labels = []
        pmap = {}
        for p in phones:
            label = " ".join(x for x in (p["brand"], p["name"], p["model"]) if x)
            labels.append(label)
            pmap[label] = p

        current_label = labels[0]
        if editing:
            for lab, p in pmap.items():
                if p["id"] == row["product_id"]:
                    current_label = lab
                    break

        c_prod = ui.labelled_combo(body, "Handset Model", labels,
                                   current_label, required=True)
        if editing:
            c_prod.configure(state="disabled")

        g = ui.form_grid(body, 2)
        e_imei = ui.labelled_entry(g[0], "IMEI 1",
                                   row["imei"] if editing else "",
                                   required=True, placeholder="15 digits")
        e_imei2 = ui.labelled_entry(g[1], "IMEI 2 (dual SIM)",
                                    row["imei2"] if editing else "")
        e_serial = ui.labelled_entry(g[0], "Serial No.",
                                     row["serial_no"] if editing else "")
        e_color = ui.labelled_combo(g[1], "Colour", COLOR_OPTS,
                                    row["color"] if editing else "",
                                    required=True)
        c_storage = ui.labelled_combo(g[0], "Storage", STORAGE_OPTS,
                                      row["storage"] if editing else "")
        c_ram = ui.labelled_combo(g[1], "RAM", RAM_OPTS,
                                  row["ram"] if editing else "")
        c_cond = ui.labelled_combo(g[0], "Condition", CONDITION_OPTS,
                                   row["condition"] if editing else "New")
        e_cost = ui.labelled_entry(
            g[1], "Cost Price (CP)",
            f"{money(row['cost_price']):.2f}" if editing else "",
            required=True)
        e_price = ui.labelled_entry(
            g[0], "Selling Price",
            f"{money(row['sell_price']):.2f}" if editing else "")
        e_note = ui.labelled_entry(g[1], "Note",
                                   row["notes"] if editing else "")

        bulk_holder = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT,
                                   corner_radius=10)
        e_bulk = None
        if not editing:
            bulk_holder.pack(fill="x", pady=10)
            pad = ctk.CTkFrame(bulk_holder, fg_color="transparent")
            pad.pack(fill="x", padx=12, pady=10)
            ctk.CTkLabel(pad, text="ADD SEVERAL AT ONCE (optional)",
                         font=ctk.CTkFont(size=F_TN, weight="bold"),
                         text_color=TH.ACCENT).pack(anchor="w")
            ctk.CTkLabel(pad,
                         text="Paste one IMEI per line to register a whole box "
                              "of handsets in one go. They all share the "
                              "colour / storage / price above.",
                         font=ctk.CTkFont(size=F_TN), text_color=TH.TEXT_DIM,
                         justify="left", wraplength=580).pack(anchor="w",
                                                              pady=(2, 6))
            e_bulk = ctk.CTkTextbox(pad, height=96,
                                    font=ctk.CTkFont(size=F_BODY),
                                    fg_color=TH.PANEL, border_color=TH.BORDER,
                                    border_width=1)
            e_bulk.pack(fill="x")

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=600,
                           justify="left")
        msg.pack(anchor="w", pady=(8, 0))

        def save():
            product = pmap.get(c_prod.get())
            if not product:
                msg.configure(text="Choose which handset model this is.")
                return
            colour = e_color.get().strip()
            cost = parse_amount(e_cost.get())
            price = parse_amount(e_price.get()) or money(product["sell_price"])

            imeis = []
            if e_bulk is not None:
                bulk = e_bulk.get("1.0", "end").strip()
                if bulk:
                    imeis = [ln.strip() for ln in bulk.splitlines() if ln.strip()]
            if not imeis:
                one = e_imei.get().strip()
                if one:
                    imeis = [one]

            if not imeis:
                msg.configure(text="Enter at least one IMEI.")
                return
            missing = ui.required_missing([("Colour", colour)])
            if missing:
                msg.configure(text="Please fill in: " + ", ".join(missing))
                return
            if cost <= 0:
                msg.configure(text="Enter the cost price for this handset.")
                return

            bad = [i for i in imeis if not i.isdigit() or not (10 <= len(i) <= 20)]
            if bad:
                msg.configure(
                    text=f"These IMEIs look wrong (digits only, 10-20 long): "
                         f"{', '.join(bad[:4])}")
                return
            if len(set(imeis)) != len(imeis):
                msg.configure(text="The same IMEI appears twice in your list.")
                return

            for imei in imeis:
                clash = self.db.fetchone(
                    "SELECT id FROM mobile_units WHERE imei=? AND id != ?",
                    (imei, row["id"] if editing else -1))
                if clash:
                    msg.configure(text=f"IMEI {imei} is already registered.")
                    return

            try:
                if editing:
                    self.db.execute(
                        "UPDATE mobile_units SET imei=?, imei2=?, serial_no=?, "
                        " color=?, storage=?, ram=?, condition=?, cost_price=?, "
                        " sell_price=?, notes=? WHERE id=?",
                        (imeis[0], e_imei2.get().strip(), e_serial.get().strip(),
                         colour, c_storage.get(), c_ram.get(), c_cond.get(),
                         cost, price, e_note.get().strip(), row["id"]))
                else:
                    with self.db.transaction() as cur:
                        for imei in imeis:
                            cur.execute(
                                "INSERT INTO mobile_units (product_id, imei, "
                                " imei2, serial_no, color, storage, ram, "
                                " condition, cost_price, sell_price, status, "
                                " notes) VALUES (?,?,?,?,?,?,?,?,?,?, "
                                " 'in_stock', ?)",
                                (product["id"], imei,
                                 e_imei2.get().strip() if len(imeis) == 1 else "",
                                 e_serial.get().strip() if len(imeis) == 1 else "",
                                 colour, c_storage.get(), c_ram.get(),
                                 c_cond.get(), cost, price,
                                 e_note.get().strip()))
                        # keep the parent product's quantity in step
                        cur.execute(
                            "UPDATE products SET stock_quantity = "
                            " stock_quantity + ?, is_serialized = 1, "
                            " updated_at = CURRENT_TIMESTAMP WHERE id=?",
                            (len(imeis), product["id"]))
                        new_qty = cur.execute(
                            "SELECT stock_quantity FROM products WHERE id=?",
                            (product["id"],)).fetchone()
                        log_stock(cur, product["id"], "imei_intake",
                                  len(imeis), new_qty[0] if new_qty else 0,
                                  f"{len(imeis)} handset(s) registered",
                                  self.staff_id())
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return

            d.destroy()
            self.refresh()
            self.toast(f"{len(imeis)} handset(s) saved."
                       if not editing else "Handset updated.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💾  Save", save, "ok", 150, side="right")

    def _delete(self):
        if self.deny_staff("delete handsets"):
            return
        row = self._selected()
        if not row:
            return
        if row["status"] == "sold":
            self.warn("Already sold",
                      "This handset has been sold and is part of a bill.\n\n"
                      "Delete the bill instead if it was a mistake.")
            return
        if not self.confirm("Delete handset",
                            f"Permanently delete IMEI {row['imei']}?",
                            danger=True):
            return
        try:
            with self.db.transaction() as cur:
                cur.execute("DELETE FROM mobile_units WHERE id=?", (row["id"],))
                cur.execute(
                    "UPDATE products SET stock_quantity = "
                    " MAX(stock_quantity - 1, 0) WHERE id=?",
                    (row["product_id"],))
                new_qty = cur.execute(
                    "SELECT stock_quantity FROM products WHERE id=?",
                    (row["product_id"],)).fetchone()
                log_stock(cur, row["product_id"], "imei_removed", -1,
                          new_qty[0] if new_qty else 0,
                          f"IMEI {row['imei']} deleted", self.staff_id())
        except Exception as exc:
            self.error("Delete failed", str(exc))
            return
        self.refresh()
        self.toast("Handset deleted.")

    def hotkey_search(self):
        self.search.focus_set()
