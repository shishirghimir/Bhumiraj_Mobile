"""Expenses — rent, salary, purchases and everything else going out."""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from ..config import (EXPENSE_CATEGORIES, F_BODY, F_SM, PAYMENT_METHODS, TH)
from ..services import money, parse_amount
from .. import ui_helpers as ui
from .base import Page


class ExpensesPage(Page):
    title = "Expenses"
    subtitle = "Everything the shop spends — feeds straight into Net Profit"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        self.search = ctk.CTkEntry(
            bar, height=36, width=290, font=ctk.CTkFont(size=F_BODY),
            placeholder_text="🔍  Description, category…",
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())

        now = datetime.now()
        self.year = ctk.CTkComboBox(
            bar, values=["All"] + [str(y) for y in range(now.year - 4,
                                                         now.year + 2)],
            width=100, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh())
        self.year.pack(side="left", padx=6)
        self.year.set(str(now.year))

        self.month = ctk.CTkComboBox(
            bar, values=["All"] + [f"{m:02d}" for m in range(1, 13)],
            width=90, height=36, font=ctk.CTkFont(size=F_BODY),
            fg_color=TH.PANEL_ALT, border_color=TH.BORDER,
            button_color=TH.NAVY, command=lambda _v: self.refresh())
        self.month.pack(side="left")
        self.month.set(f"{now.month:02d}")

        ui.button(bar, "🗑  Delete", self._delete, "danger", 100, 36,
                  side="right")
        ui.button(bar, "✏️  Edit", self._edit, "primary", 96, 36,
                  side="right", padx=(0, 6))
        ui.button(bar, "➕  Add Expense", lambda: self._form(None), "ok",
                  146, 36, side="right", padx=(0, 6))

        self.stats = ctk.CTkFrame(outer, fg_color="transparent")
        self.stats.pack(fill="x", pady=(0, 4))

        self.tree, _ = ui.make_table(
            outer, ("Date", "Category", "Description", "Amount", "Method",
                    "Note", "Added By"),
            widths=[106, 136, 280, 116, 116, 200, 130],
            anchors=["w", "w", "w", "e", "w", "w", "w"],
            height=17, on_double=self._edit)
        self.refresh()

    def _period(self):
        where, params = ["1=1"], []
        y, m = self.year.get(), self.month.get()
        if y != "All" and m != "All":
            where.append("strftime('%Y-%m', e.expense_date) = ?")
            params.append(f"{y}-{m}")
        elif y != "All":
            where.append("strftime('%Y', e.expense_date) = ?")
            params.append(y)
        for word in self.search.get().strip().split():
            like = f"%{word}%"
            where.append("(e.description LIKE ? OR e.category LIKE ? "
                         " OR e.notes LIKE ?)")
            params += [like] * 3
        return " AND ".join(where), params

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        where, params = self._period()
        rows = self.db.fetchall(
            "SELECT e.*, u.full_name FROM expenses e "
            "LEFT JOIN users u ON e.staff_id=u.id "
            f"WHERE {where} ORDER BY e.expense_date DESC, e.id DESC", params)

        self._rows = {}
        total = 0.0
        by_cat = {}
        for e in rows:
            total += money(e["amount"])
            by_cat[e["category"]] = money(by_cat.get(e["category"], 0)
                                          + money(e["amount"]))
            iid = self.tree.insert("", "end", values=(
                str(e["expense_date"])[:10], e["category"], e["description"],
                f"{money(e['amount']):,.2f}", e["payment_method"] or "Cash",
                e["notes"] or "—", e["full_name"] or "—"), tags=("low",))
            self._rows[iid] = e

        for w in self.stats.winfo_children():
            w.destroy()
        ui.stat_card(self.stats, "Entries", f"{len(rows):,}", TH.NAVY, 140)
        ui.stat_card(self.stats, "Total spent", self.money_text(total),
                     TH.DANGER, 206)
        if by_cat:
            top_cat = max(by_cat.items(), key=lambda kv: kv[1])
            ui.stat_card(self.stats, f"Biggest: {top_cat[0]}",
                         self.money_text(top_cat[1]), TH.WARN, 220)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select an expense first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _edit(self):
        row = self._selected()
        if row:
            self._form(row)

    def _form(self, row):
        editing = row is not None
        d = ui.modal(self.app, "Edit expense" if editing else "Add expense",
                     520, 480, resizable=False)
        ui.modal_header(d, "Edit expense" if editing else "Add expense",
                        "Recorded against Net Profit", TH.WARN)
        body = ui.modal_body(d)

        e_date = ui.labelled_entry(
            body, "Date",
            str(row["expense_date"])[:10] if editing
            else datetime.now().strftime("%Y-%m-%d"), required=True)
        c_cat = ui.labelled_combo(body, "Category", EXPENSE_CATEGORIES,
                                  row["category"] if editing else "Other",
                                  required=True)
        e_desc = ui.labelled_entry(body, "Description",
                                   row["description"] if editing else "",
                                   required=True)
        g = ui.form_grid(body, 2)
        e_amt = ui.labelled_entry(
            g[0], "Amount",
            f"{money(row['amount']):.2f}" if editing else "", required=True)
        c_method = ui.labelled_combo(g[1], "Paid by", PAYMENT_METHODS,
                                     row["payment_method"] if editing
                                     else "Cash")
        e_note = ui.labelled_entry(body, "Note",
                                   row["notes"] if editing else "")

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            desc = e_desc.get().strip()
            amount = parse_amount(e_amt.get())
            date = e_date.get().strip()
            if not desc:
                msg.configure(text="Description is required.")
                return
            if amount <= 0:
                msg.configure(text="Amount must be greater than zero.")
                return
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                msg.configure(text="Date must look like 2026-08-04.")
                return
            params = (date, c_cat.get(), desc, amount, c_method.get(),
                      e_note.get().strip())
            if editing:
                self.db.execute(
                    "UPDATE expenses SET expense_date=?, category=?, "
                    " description=?, amount=?, payment_method=?, notes=? "
                    "WHERE id=?", params + (row["id"],))
            else:
                self.db.execute(
                    "INSERT INTO expenses (expense_date, category, description, "
                    " amount, payment_method, notes, staff_id) "
                    "VALUES (?,?,?,?,?,?,?)", params + (self.staff_id(),))
            d.destroy()
            self.refresh()
            self.toast("Expense saved.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Save", save, "ok", 130, side="right")

    def _delete(self):
        row = self._selected()
        if not row:
            return
        if not self.confirm("Delete expense",
                            f"Delete '{row['description']}' "
                            f"({self.money_text(row['amount'])})?", danger=True):
            return
        self.db.execute("DELETE FROM expenses WHERE id=?", (row["id"],))
        self.refresh()
        self.toast("Expense deleted.")

    def hotkey_search(self):
        self.search.focus_set()
