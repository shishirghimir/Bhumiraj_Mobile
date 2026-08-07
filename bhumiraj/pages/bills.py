"""Bills History — reprint, WhatsApp, collect a due, and (admin only) delete."""
from __future__ import annotations

import os
from datetime import datetime

import customtkinter as ctk

from ..config import (BILLS_DIR, BILL_WHOLESALE, F_BODY, F_LBL, F_SM, F_TN,
                      PAYMENT_METHODS, RECEIPTS_DIR, TH)
from ..services import (money, parse_amount, record_bill_payment,
                        record_retailer_payment, retailer_outstanding)
from .. import ui_helpers as ui
from .. import whatsapp as wa
from .base import Page

PAGE_SIZE = 300


class BillsPage(Page):
    title = "Bills History"
    subtitle = "Every retail and wholesale bill — reprint, share or collect dues"

    def build(self):
        self.page = 0
        self.sort_col = "Date"
        self.sort_desc = True
        outer = self.body()

        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=320, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Bill no, customer, phone…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh(0))

        self.type_filter = ctk.CTkComboBox(
            bar, values=["All bills", "Retail only", "Wholesale only"],
            width=150, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh(0))
        self.type_filter.pack(side="left", padx=6)
        self.type_filter.set("All bills")

        self.status_filter = ctk.CTkComboBox(
            bar, values=["Any status", "Paid", "Partial", "Unpaid"],
            width=140, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh(0))
        self.status_filter.pack(side="left")
        self.status_filter.set("Any status")

        if self.admin:
            ui.button(bar, "🗑  Delete", self._delete, "danger", 104, 36,
                      side="right")
            ui.button(bar, "💰  Collect Due", self._collect, "gold", 138, 36,
                      side="right", padx=(0, 6))
        ui.button(bar, "📲  WhatsApp", self._whatsapp, "primary", 128, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "🖨  Print", self._print, "info", 96, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "📄  Open PDF", self._open, "muted", 118, 36,
                  side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        cols = ("Bill No", "Type", "Date", "Customer", "Phone", "Items",
                "Total", "Paid", "Due", "Status", "Staff")
        self.tree, _ = ui.make_table(
            outer, cols,
            widths=[118, 88, 132, 168, 106, 56, 96, 96, 96, 84, 116],
            anchors=["w", "w", "w", "w", "w", "center", "e", "e", "e",
                     "center", "w"],
            height=16, on_double=self._open)
        ui.sortable(self.tree, cols, self._on_sort)

        nav = ctk.CTkFrame(outer, fg_color="transparent")
        nav.pack(fill="x", pady=(6, 0))
        ui.button(nav, "◀  Previous", lambda: self.refresh(self.page - 1),
                  "muted", 120, 32, side="left")
        self.page_lbl = ctk.CTkLabel(nav, text="", font=ctk.CTkFont(size=F_SM),
                                     text_color=TH.TEXT_DIM)
        self.page_lbl.pack(side="left", padx=12)
        ui.button(nav, "Next  ▶", lambda: self.refresh(self.page + 1),
                  "muted", 120, 32, side="left")
        self.refresh(0)

    def _on_sort(self, col, desc):
        self.sort_col, self.sort_desc = col, desc
        self.refresh(0)

    # ── data ────────────────────────────────────────────────────────
    def _where(self):
        where = ["1=1"]
        params = []
        tf = self.type_filter.get()
        if tf == "Retail only":
            where.append("b.bill_type = 'retail'")
        elif tf == "Wholesale only":
            where.append("b.bill_type = 'wholesale'")
        sf = self.status_filter.get()
        if sf != "Any status":
            where.append("b.payment_status = ?")
            params.append(sf.lower())
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(b.bill_number LIKE ? OR b.customer_name LIKE ? "
                         " OR b.customer_phone LIKE ?)")
            params += [like] * 3
        return " AND ".join(where), params

    def refresh(self, page=None):
        if page is not None:
            self.page = max(0, page)
        for r in self.tree.get_children():
            self.tree.delete(r)

        where, params = self._where()
        total_rows = int(self.db.scalar(
            f"SELECT COUNT(*) FROM bills b WHERE {where}", params, 0))
        pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = min(self.page, pages - 1)

        order_map = {
            "Bill No": "b.bill_number", "Type": "b.bill_type",
            "Date": "b.bill_date", "Customer": "b.customer_name COLLATE NOCASE",
            "Phone": "b.customer_phone", "Total": "b.total_amount",
            "Paid": "b.paid_amount", "Due": "(b.total_amount-b.paid_amount)",
            "Status": "b.payment_status", "Items": "item_count",
            "Staff": "u.full_name COLLATE NOCASE",
        }
        order = order_map.get(self.sort_col, "b.bill_date")
        direction = "DESC" if self.sort_desc else "ASC"

        rows = self.db.fetchall(
            "SELECT b.*, u.full_name AS staff_name, "
            " (SELECT COUNT(*) FROM bill_items bi WHERE bi.bill_id=b.id) "
            "   AS item_count "
            "FROM bills b LEFT JOIN users u ON b.staff_id = u.id "
            f"WHERE {where} ORDER BY {order} {direction}, b.id DESC "
            "LIMIT ? OFFSET ?", params + [PAGE_SIZE, self.page * PAGE_SIZE])

        self._rows = {}
        for b in rows:
            due = money(money(b["total_amount"]) - money(b["paid_amount"]))
            status = (b["payment_status"] or "paid").upper()
            tag = ("due" if status == "UNPAID"
                   else "partial" if status == "PARTIAL"
                   else "wholesale" if b["bill_type"] == BILL_WHOLESALE else "")
            iid = self.tree.insert("", "end", values=(
                b["bill_number"],
                "WHOLESALE" if b["bill_type"] == BILL_WHOLESALE else "Retail",
                str(b["bill_date"])[:16],
                b["customer_name"] or "Walk-in",
                b["customer_phone"] or "—",
                b["item_count"],
                f"{money(b['total_amount']):,.2f}",
                f"{money(b['paid_amount']):,.2f}",
                f"{due:,.2f}", status,
                b["staff_name"] or "—"), tags=(tag,) if tag else ())
            self._rows[iid] = b

        self.page_lbl.configure(
            text=f"Page {self.page + 1} of {pages}   ·   {total_rows:,} bill(s)")

        for w in self.stats.winfo_children():
            w.destroy()
        # Staff never see aggregate revenue — only the owner does.
        if self.admin:
            agg = self.db.fetchone(
                "SELECT COALESCE(SUM(total_amount),0) t, "
                " COALESCE(SUM(paid_amount),0) p, COUNT(*) n "
                f"FROM bills b WHERE {where}", params)
            ui.stat_card(self.stats, "Bills", f"{agg['n']:,}", TH.NAVY, 138)
            ui.stat_card(self.stats, "Billed",
                         self.money_text(agg["t"]), TH.ACCENT_DIM, 190)
            ui.stat_card(self.stats, "Collected",
                         self.money_text(agg["p"]), TH.OK, 190)
            ui.stat_card(self.stats, "Outstanding",
                         self.money_text(money(agg["t"]) - money(agg["p"])),
                         TH.DANGER, 190)
        else:
            ui.stat_card(self.stats, "Bills listed", f"{total_rows:,}",
                         TH.NAVY, 168)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a bill first.", "warn")
            return None
        return self._rows.get(sel[0])

    # ── PDF helpers ─────────────────────────────────────────────────
    def _pdf_for(self, bill):
        path = os.path.join(BILLS_DIR, f"{bill['bill_number']}.pdf")
        if not os.path.exists(path):
            try:
                self.docs.generate_bill(bill["id"], path)
            except Exception as exc:
                self.error("PDF failed", str(exc))
                return None
        return path

    def _open(self):
        bill = self._selected()
        if bill:
            path = self._pdf_for(bill)
            if path:
                self.open_pdf(path)

    def _print(self):
        bill = self._selected()
        if bill:
            path = self._pdf_for(bill)
            if path:
                self.print_pdf(path)

    def _whatsapp(self):
        bill = self._selected()
        if not bill:
            return
        phone = bill["customer_phone"]
        if not phone and bill["retailer_id"]:
            phone = self.db.scalar(
                "SELECT phone FROM retailers WHERE id=?",
                (bill["retailer_id"],), "")
        if not phone:
            phone = ui.ask_text(self.app, "WhatsApp",
                                "Enter the WhatsApp number to send to:")
            if not phone:
                return
        path = self._pdf_for(bill)
        due = money(money(bill["total_amount"]) - money(bill["paid_amount"]))
        msg = wa.bill_message(self.settings.get("shop_name", ""),
                              self.settings.get("shop_phone", ""),
                              bill["bill_number"], money(bill["total_amount"]),
                              bill["customer_name"] or "", due, self.cur)
        wa.send(self.app, phone, msg, path)
        self.toast("WhatsApp opened — press Ctrl+V to attach the PDF.", "info")

    # ── collect a due ───────────────────────────────────────────────
    def _collect(self):
        if self.deny_staff("record payments"):
            return
        bill = self._selected()
        if not bill:
            return
        due = money(money(bill["total_amount"]) - money(bill["paid_amount"]))
        if due <= 0.005:
            self.info("Already settled", "This bill is fully paid.")
            return

        d = ui.modal(self.app, "Collect payment", 560, 560)
        ui.modal_header(d, "Collect payment", bill["bill_number"], TH.OK)
        body = ui.modal_body(d)

        card = ctk.CTkFrame(body, fg_color=TH.PANEL_ALT, corner_radius=10)
        card.pack(fill="x", pady=(0, 10))
        for label, value, color in (
                ("Customer", bill["customer_name"] or "Walk-in", None),
                ("Bill total", self.money_text(bill["total_amount"]), None),
                ("Already paid", self.money_text(bill["paid_amount"]), TH.POS),
                ("Balance due", self.money_text(due), TH.DANGER)):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(r, text=label, font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.TEXT_DIM).pack(side="left")
            ctk.CTkLabel(r, text=str(value),
                         font=ctk.CTkFont(size=F_BODY, weight="bold"),
                         text_color=color or TH.TEXT).pack(side="right")

        is_ws = bill["bill_type"] == BILL_WHOLESALE and bill["retailer_id"]
        if is_ws:
            outstanding = retailer_outstanding(self.db, bill["retailer_id"])
            ctk.CTkLabel(
                body,
                text=f"This retailer owes {self.money_text(outstanding)} in "
                     "total.\nPayments are applied to their OLDEST unpaid "
                     "bills first (FIFO).",
                font=ctk.CTkFont(size=F_SM), text_color=TH.ACCENT,
                justify="left").pack(anchor="w", pady=(0, 6))

        e_amt = ui.labelled_entry(body, "Amount received", f"{due:.2f}",
                                  required=True)
        g = ui.form_grid(body, 2)
        c_method = ui.labelled_combo(g[0], "Method", PAYMENT_METHODS,
                                     self.settings.get("default_payment", "Cash"))
        e_date = ui.labelled_entry(g[1], "Date",
                                   datetime.now().strftime("%Y-%m-%d"))
        e_ref = ui.labelled_entry(body, "Reference (cheque / txn no.)")
        e_note = ui.labelled_entry(body, "Note")

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=480,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            amount = parse_amount(e_amt.get())
            if amount <= 0.005:
                msg.configure(text="Enter an amount greater than zero.")
                return
            try:
                if is_ws:
                    receipt, allocations, leftover = record_retailer_payment(
                        self.db, bill["retailer_id"], amount, c_method.get(),
                        e_date.get().strip(), e_ref.get().strip(),
                        e_note.get().strip(), self.staff_id())
                    summary = "\n".join(
                        f"  • {a['bill_number']}: "
                        f"{self.cur} {a['applied']:,.2f} applied "
                        f"(due {self.cur} {a['after_due']:,.2f})"
                        for a in allocations) or "  • kept as advance"
                    extra = (f"\n\nUnallocated advance: "
                             f"{self.cur} {leftover:,.2f}"
                             if leftover > 0.005 else "")
                else:
                    if amount > due + 0.005:
                        msg.configure(
                            text=f"That is more than the balance due "
                                 f"({self.money_text(due)}).")
                        return
                    receipt, new_paid, new_due, _st = record_bill_payment(
                        self.db, bill["id"], amount, c_method.get(),
                        e_date.get().strip(), e_ref.get().strip(),
                        e_note.get().strip(), self.staff_id())
                    summary = (f"  • {bill['bill_number']}: "
                               f"{self.cur} {amount:,.2f} applied "
                               f"(due {self.cur} {new_due:,.2f})")
                    extra = ""
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
            self._receipt_dialog(receipt, amount, summary + extra, path,
                                 bill["customer_name"],
                                 bill["customer_phone"])

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "💰  Record Payment", save, "ok", 178, side="right")

    def _receipt_dialog(self, receipt, amount, summary, path, name, phone):
        d = ui.modal(self.app, f"Receipt {receipt}", 520, 430, resizable=False)
        ui.modal_header(d, "✅  PAYMENT RECORDED", receipt, TH.OK)
        body = ui.modal_body(d, scroll=False)
        ctk.CTkLabel(body, text=f"{self.cur} {money(amount):,.2f} received",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TH.POS).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(body, text="Applied to:", font=ctk.CTkFont(size=F_SM,
                     weight="bold"), text_color=TH.TEXT_DIM).pack(anchor="w")
        ctk.CTkLabel(body, text=summary, font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT, justify="left",
                     wraplength=440).pack(anchor="w", pady=(2, 10))

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
                target = phone or ui.ask_text(self.app, "WhatsApp",
                                              "Enter the WhatsApp number:")
                if target:
                    msg = wa.receipt_message(
                        self.settings.get("shop_name", ""),
                        self.settings.get("shop_phone", ""),
                        receipt, amount, name or "", 0, self.cur)
                    wa.send(self.app, target, msg, path)

        ui.button(btns, "🖨  PRINT", lambda: act("print"), "ok", 142, 46,
                  side="left")
        ui.button(btns, "📄  OPEN", lambda: act("open"), "info", 142, 46,
                  side="left", padx=(6, 0))
        ui.button(btns, "📲  WHATSAPP", lambda: act("wa"), "primary", 142, 46,
                  side="left", padx=(6, 0))
        ui.button(ui.modal_footer(d), "DONE", d.destroy, "muted", 120,
                  side="right")

    # ── delete (admin only) ─────────────────────────────────────────
    def _delete(self):
        if self.deny_staff("delete bills"):
            return
        bill = self._selected()
        if not bill:
            return
        items = self.db.fetchall(
            "SELECT * FROM bill_items WHERE bill_id=?", (bill["id"],))
        restock = self.confirm(
            "Return stock?",
            f"Delete bill {bill['bill_number']}?\n\n"
            "Click YES to put the items BACK into stock.\n"
            "Click NO to delete the bill without restocking.")
        if not self.confirm(
                "Confirm delete",
                f"This permanently deletes bill {bill['bill_number']} "
                f"({self.money_text(bill['total_amount'])}) and its payment "
                "records.\n\nThis cannot be undone. Continue?", danger=True):
            return

        try:
            with self.db.transaction() as cur:
                if restock:
                    from ..services import log_stock
                    for it in items:
                        if it["product_id"]:
                            cur.execute(
                                "UPDATE products SET stock_quantity = "
                                " stock_quantity + ? WHERE id=?",
                                (it["quantity"], it["product_id"]))
                            row = cur.execute(
                                "SELECT stock_quantity FROM products WHERE id=?",
                                (it["product_id"],)).fetchone()
                            log_stock(cur, it["product_id"], "bill_deleted",
                                      it["quantity"], row[0] if row else 0,
                                      bill["bill_number"], self.staff_id())
                        if it["mobile_unit_id"]:
                            cur.execute(
                                "UPDATE mobile_units SET status='in_stock', "
                                "bill_id=NULL, sold_date='' WHERE id=?",
                                (it["mobile_unit_id"],))
                cur.execute("DELETE FROM imei_register WHERE bill_id=?",
                            (bill["id"],))
                cur.execute("DELETE FROM payments WHERE bill_id=?", (bill["id"],))
                cur.execute("DELETE FROM bills WHERE id=?", (bill["id"],))
        except Exception as exc:
            self.error("Delete failed", str(exc))
            return
        self.refresh()
        self.toast("Bill deleted." + (" Stock returned." if restock else ""))

    def hotkey_search(self):
        self.search.focus_set()
