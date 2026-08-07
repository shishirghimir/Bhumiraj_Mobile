"""Returns — take goods back against a bill, refund and restock."""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..config import F_BODY, F_LBL, F_SM, F_TN, RETURN_REASONS, TH
from ..services import log_stock, money, parse_amount, parse_int, payment_status
from .. import ui_helpers as ui
from .base import Page


class ReturnsPage(Page):
    title = "Returns"
    subtitle = "Take items back against a bill — refund and put stock back"

    def build(self):
        outer = self.body()

        finder = ctk.CTkFrame(outer, fg_color=TH.PANEL, corner_radius=10,
                              border_width=1, border_color=TH.BORDER)
        finder.pack(fill="x", pady=(0, 8))
        pad = ctk.CTkFrame(finder, fg_color="transparent")
        pad.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(pad, text="FIND THE BILL",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.TEXT_DIM).pack(anchor="w")
        row = ctk.CTkFrame(pad, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.find = ctk.CTkEntry(
            row, height=38, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="Bill number, customer name or phone…",
            fg_color=TH.PANEL_ALT, border_color=TH.NAVY, border_width=2)
        self.find.pack(side="left", fill="x", expand=True)
        self.find.bind("<Return>", lambda _e: self._search())
        ui.button(row, "🔍  Find Bill", self._search, "primary", 130, 38,
                  side="left", padx=(6, 0))

        split = ctk.CTkFrame(outer, fg_color="transparent")
        split.pack(fill="both", expand=True)
        left = ctk.CTkFrame(split, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ctk.CTkFrame(split, fg_color="transparent", width=430)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)

        ui.section(left, "ITEMS ON THIS BILL")
        self.items_box = ctk.CTkScrollableFrame(left, fg_color=TH.PANEL,
                                                corner_radius=10)
        self.items_box.pack(fill="both", expand=True)
        self._empty_items()

        ui.section(right, "RETURN HISTORY")
        self.hist, _ = ui.make_table(
            right, ("Date", "Bill No", "Product", "Qty", "Refund"),
            widths=[100, 116, 152, 50, 96],
            anchors=["w", "w", "w", "center", "e"], height=18)
        self.refresh()

        self.bill = None
        self.rows = []

    def _empty_items(self):
        for w in self.items_box.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.items_box,
                     text="Search for a bill above to start a return.",
                     font=ctk.CTkFont(size=F_BODY),
                     text_color=TH.TEXT_DIM).pack(pady=40)

    def refresh(self):
        for r in self.hist.get_children():
            self.hist.delete(r)
        for r in self.db.fetchall(
                "SELECT * FROM returns ORDER BY id DESC LIMIT 200"):
            self.hist.insert("", "end", values=(
                str(r["return_date"])[:10], r["bill_number"] or "—",
                (r["product_name"] or "")[:26], r["quantity"],
                f"{money(r['refund_amount']):,.2f}"), tags=("low",))

    # ── find ────────────────────────────────────────────────────────
    def _search(self):
        text = self.find.get().strip()
        if not text:
            self.warn("Search", "Type a bill number, name or phone.")
            return
        like = f"%{text}%"
        bills = self.db.fetchall(
            "SELECT * FROM bills WHERE bill_number LIKE ? "
            " OR customer_name LIKE ? OR customer_phone LIKE ? "
            "ORDER BY id DESC LIMIT 40", (like, like, like))
        if not bills:
            self.warn("Not found", "No bill matches that search.")
            return
        if len(bills) == 1:
            self._load(bills[0])
            return

        d = ui.modal(self.app, "Choose the bill", 720, 460)
        ui.modal_header(d, "Several bills matched", "Pick the right one")
        body = ui.modal_body(d, scroll=False)
        tree, _ = ui.make_table(
            body, ("Bill No", "Date", "Customer", "Total", "Status"),
            widths=[128, 140, 200, 116, 96],
            anchors=["w", "w", "w", "e", "center"], height=12)
        bmap = {}
        for b in bills:
            iid = tree.insert("", "end", values=(
                b["bill_number"], str(b["bill_date"])[:16],
                b["customer_name"] or "Walk-in",
                f"{money(b['total_amount']):,.2f}",
                (b["payment_status"] or "paid").upper()))
            bmap[iid] = b

        def choose():
            sel = tree.selection()
            if not sel:
                return
            d.destroy()
            self._load(bmap[sel[0]])
        tree.bind("<Double-1>", lambda _e: choose())
        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Select", choose, "ok", 130, side="right")

    def _load(self, bill):
        self.bill = bill
        self.rows = []
        for w in self.items_box.winfo_children():
            w.destroy()

        head = ctk.CTkFrame(self.items_box, fg_color=TH.PANEL_ALT,
                            corner_radius=8)
        head.pack(fill="x", padx=6, pady=(6, 8))
        info = ctk.CTkFrame(head, fg_color="transparent")
        info.pack(fill="x", padx=12, pady=9)
        ctk.CTkLabel(info, text=f"Bill {bill['bill_number']}",
                     font=ctk.CTkFont(size=F_LBL, weight="bold"),
                     text_color=TH.ACCENT).pack(anchor="w")
        ctk.CTkLabel(
            info,
            text=f"{bill['customer_name'] or 'Walk-in'}  ·  "
                 f"{str(bill['bill_date'])[:16]}  ·  "
                 f"Total {self.money_text(bill['total_amount'])}  ·  "
                 f"Paid {self.money_text(bill['paid_amount'])}",
            font=ctk.CTkFont(size=F_SM),
            text_color=TH.TEXT_DIM).pack(anchor="w")

        items = self.db.fetchall(
            "SELECT * FROM bill_items WHERE bill_id=? ORDER BY id",
            (bill["id"],))
        if not items:
            ctk.CTkLabel(self.items_box, text="This bill has no items.",
                         text_color=TH.WARN).pack(pady=20)
            return

        for it in items:
            already = int(self.db.scalar(
                "SELECT COALESCE(SUM(quantity),0) FROM returns "
                "WHERE bill_id=? AND product_name=? AND IFNULL(imei,'')=?",
                (bill["id"], it["product_name"], it["imei"] or ""), 0))
            remaining = int(it["quantity"]) - already
            self.rows.append(self._item_row(it, remaining))

        totals = ctk.CTkFrame(self.items_box, fg_color="transparent")
        totals.pack(fill="x", padx=6, pady=(10, 6))
        self.refund_lbl = ctk.CTkLabel(
            totals, text=f"Refund total: {self.cur} 0.00",
            font=ctk.CTkFont(size=F_LBL, weight="bold"),
            text_color=TH.ACCENT)
        self.refund_lbl.pack(side="left")

        opts = ctk.CTkFrame(self.items_box, fg_color="transparent")
        opts.pack(fill="x", padx=6, pady=(0, 6))
        self.c_reason = ui.labelled_combo(opts, "Reason", RETURN_REASONS,
                                          "Defective")
        self.restock_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="Put the returned items back into stock",
                        variable=self.restock_var,
                        font=ctk.CTkFont(size=F_SM),
                        fg_color=TH.NAVY).pack(anchor="w", pady=6)
        ui.button(opts, "↩️  Process Return", self._process, "danger", 200, 42
                  ).pack(anchor="w", pady=4)
        self._recalc()

    def _item_row(self, item, remaining):
        card = ctk.CTkFrame(self.items_box, fg_color=TH.PANEL_ALT,
                            corner_radius=8)
        card.pack(fill="x", padx=6, pady=3)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(7, 2))

        head = " ".join(x for x in (item["product_brand"],
                                    item["product_name"]) if x)
        if item["product_model"]:
            head += f" — {item['product_model']}"
        var = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(top, text=head[:44], variable=var,
                              font=ctk.CTkFont(size=F_BODY, weight="bold"),
                              fg_color=TH.NAVY, command=self._recalc)
        chk.pack(side="left")
        if remaining <= 0:
            chk.configure(state="disabled", text=head[:38] + "  (returned)")

        meta = []
        if item["imei"]:
            meta.append(f"IMEI {item['imei']}")
        meta.append(f"sold {item['quantity']}  ·  returnable {max(remaining,0)}")
        meta.append(f"@ {self.cur} {money(item['unit_price']):,.2f}")
        ctk.CTkLabel(card, text="  ·  ".join(meta),
                     font=ctk.CTkFont(size=F_TN),
                     text_color=TH.TEXT_DIM).pack(anchor="w", padx=32)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=32, pady=(2, 8))
        ctk.CTkLabel(row, text="Qty to return:",
                     font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(side="left")
        qty = ctk.CTkEntry(row, width=56, height=26, justify="center",
                           font=ctk.CTkFont(size=F_SM),
                           fg_color=TH.PANEL, border_color=TH.BORDER)
        qty.pack(side="left", padx=6)
        qty.insert(0, str(max(remaining, 0)))
        qty.bind("<KeyRelease>", lambda _e: self._recalc())
        if remaining <= 0:
            qty.configure(state="disabled")

        ctk.CTkLabel(row, text="Refund each:", font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(side="left", padx=(12, 0))
        refund = ctk.CTkEntry(row, width=82, height=26, justify="right",
                              font=ctk.CTkFont(size=F_SM),
                              fg_color=TH.PANEL, border_color=TH.BORDER)
        refund.pack(side="left", padx=6)
        refund.insert(0, f"{money(item['unit_price']):.2f}")
        refund.bind("<KeyRelease>", lambda _e: self._recalc())
        if remaining <= 0:
            refund.configure(state="disabled")

        return {"item": item, "var": var, "qty": qty, "refund": refund,
                "remaining": max(remaining, 0)}

    def _recalc(self):
        total = 0.0
        for r in self.rows:
            if not r["var"].get():
                continue
            qty = min(parse_int(r["qty"].get()), r["remaining"])
            total += money(qty * parse_amount(r["refund"].get()))
        if hasattr(self, "refund_lbl"):
            self.refund_lbl.configure(
                text=f"Refund total: {self.cur} {money(total):,.2f}")
        return money(total)

    # ── process ─────────────────────────────────────────────────────
    def _process(self):
        if not self.bill:
            return
        picked = []
        for r in self.rows:
            if not r["var"].get():
                continue
            qty = parse_int(r["qty"].get())
            if qty <= 0:
                continue
            if qty > r["remaining"]:
                self.warn("Too many",
                          f"{r['item']['product_name']}: only "
                          f"{r['remaining']} can still be returned.")
                return
            picked.append((r["item"], qty, parse_amount(r["refund"].get())))

        if not picked:
            self.warn("Nothing selected",
                      "Tick the items being returned and set a quantity.")
            return

        refund_total = money(sum(money(q * p) for _it, q, p in picked))
        restock = bool(self.restock_var.get())
        reason = self.c_reason.get()

        if not self.confirm(
                "Confirm return",
                f"Return {len(picked)} item line(s) from bill "
                f"{self.bill['bill_number']}?\n\n"
                f"Refund: {self.money_text(refund_total)}\n"
                f"Restock: {'yes' if restock else 'no'}\n"
                f"Reason: {reason}"):
            return

        bill_id = self.bill["id"]
        bill_no = self.bill["bill_number"]
        try:
            with self.db.transaction() as cur:
                for item, qty, unit_refund in picked:
                    cur.execute(
                        "INSERT INTO returns (bill_id, bill_number, product_id, "
                        " mobile_unit_id, product_name, imei, quantity, "
                        " refund_amount, restocked, reason, staff_id, "
                        " return_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (bill_id, bill_no, item["product_id"],
                         item["mobile_unit_id"], item["product_name"],
                         item["imei"] or "", qty, money(qty * unit_refund),
                         1 if restock else 0, reason, self.staff_id(),
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                    if restock and item["product_id"]:
                        cur.execute(
                            "UPDATE products SET stock_quantity = "
                            " stock_quantity + ?, updated_at=CURRENT_TIMESTAMP "
                            "WHERE id=?", (qty, item["product_id"]))
                        got = cur.execute(
                            "SELECT stock_quantity FROM products WHERE id=?",
                            (item["product_id"],)).fetchone()
                        log_stock(cur, item["product_id"], "return", qty,
                                  got[0] if got else 0,
                                  f"Return on {bill_no}", self.staff_id(),
                                  item["mobile_unit_id"])
                    if item["mobile_unit_id"]:
                        cur.execute(
                            "UPDATE mobile_units SET status=?, bill_id=NULL, "
                            "sold_date='' WHERE id=?",
                            ("in_stock" if restock else "returned",
                             item["mobile_unit_id"]))
                        cur.execute(
                            "UPDATE imei_register SET status='returned' "
                            "WHERE mobile_unit_id=?", (item["mobile_unit_id"],))

                # Reduce the bill so reports and dues stay honest
                new_total = money(money(self.bill["total_amount"]) - refund_total)
                if new_total < 0:
                    new_total = 0.0
                new_paid = money(min(money(self.bill["paid_amount"]), new_total))
                new_due = money(new_total - new_paid)
                cur.execute(
                    "UPDATE bills SET total_amount=?, paid_amount=?, "
                    " due_amount=?, payment_status=?, "
                    " notes = TRIM(IFNULL(notes,'') || ?) WHERE id=?",
                    (new_total, new_paid, new_due,
                     payment_status(new_total, new_paid),
                     f" [Return {datetime.now():%Y-%m-%d}: "
                     f"-{refund_total:,.2f}]", bill_id))
        except Exception as exc:
            self.error("Return failed", str(exc))
            return

        self.refresh()
        self.info("Return processed",
                  f"Refund of {self.money_text(refund_total)} recorded.\n"
                  + ("Stock has been put back." if restock
                     else "Stock was NOT restocked."))
        refreshed = self.db.fetchone("SELECT * FROM bills WHERE id=?",
                                     (bill_id,))
        if refreshed:
            self._load(refreshed)

    def hotkey_search(self):
        self.find.focus_set()
