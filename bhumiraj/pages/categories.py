"""Categories — each carries a `kind` that decides which fields the product
form asks for (a Mobile category asks for IMEI/storage/colour, a Watch
category asks for movement/strap, and so on)."""
from __future__ import annotations

import customtkinter as ctk

from ..config import F_BODY, F_SM, F_TN, KIND_LABELS, TH
from .. import ui_helpers as ui
from .base import Page


class CategoriesPage(Page):
    title = "Categories"
    subtitle = "Each category's TYPE decides which details the product form asks for"

    def build(self):
        outer = self.body()
        bar = ui.toolbar(outer)
        ui.button(bar, "➕  Add Category", lambda: self._form(None), "ok",
                  156, 36, side="left")
        ui.button(bar, "✏️  Edit", self._edit, "primary", 100, 36,
                  side="left", padx=(6, 0))
        ui.button(bar, "🗑  Delete", self._delete, "danger", 108, 36,
                  side="left", padx=(6, 0))
        ctk.CTkLabel(bar,
                     text="Deleting is blocked while products still use the "
                          "category.",
                     font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(side="left", padx=14)

        self.tree, _ = ui.make_table(
            outer, ("Category", "Code", "Type", "Products", "Stock Units",
                    "Description"),
            widths=[210, 84, 150, 92, 100, 300],
            anchors=["w", "center", "w", "center", "center", "w"],
            height=17, on_double=self._edit)
        self.refresh()

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        rows = self.db.fetchall(
            "SELECT c.*, "
            " (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id "
            "  AND p.is_active=1) AS n_prod, "
            " (SELECT COALESCE(SUM(p.stock_quantity),0) FROM products p "
            "  WHERE p.category_id=c.id AND p.is_active=1) AS n_stock "
            "FROM categories c ORDER BY c.name")
        self._rows = {}
        for c in rows:
            iid = self.tree.insert("", "end", values=(
                c["name"], c["code"] or "—",
                KIND_LABELS.get(c["kind"], c["kind"]),
                c["n_prod"], c["n_stock"], c["description"] or "—"),
                tags=("muted",) if not c["n_prod"] else ())
            self._rows[iid] = c

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.toast("Select a category first.", "warn")
            return None
        return self._rows.get(sel[0])

    def _edit(self):
        row = self._selected()
        if row:
            self._form(row)

    def _form(self, row):
        editing = row is not None
        d = ui.modal(self.app, "Edit category" if editing else "Add category",
                     520, 470, resizable=False)
        ui.modal_header(d, "Edit category" if editing else "Add category",
                        "The type controls the product form")
        body = ui.modal_body(d)

        e_name = ui.labelled_entry(body, "Category Name",
                                   row["name"] if editing else "",
                                   required=True)
        e_code = ui.labelled_entry(body, "Short Code (used in SKUs)",
                                   row["code"] if editing else "",
                                   placeholder="e.g. MOB")
        kinds = list(KIND_LABELS.values())
        kind_by_label = {v: k for k, v in KIND_LABELS.items()}
        c_kind = ui.labelled_combo(
            body, "Category Type", kinds,
            KIND_LABELS.get(row["kind"], "General") if editing else "General",
            required=True)
        hint = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=F_TN),
                            text_color=TH.ACCENT, justify="left",
                            wraplength=440)
        hint.pack(anchor="w", pady=(2, 0))

        def on_kind(_v=None):
            from ..config import KIND_FIELDS
            kind = kind_by_label.get(c_kind.get(), "general")
            fields = ", ".join(lbl for _k, lbl, _w, _o
                               in KIND_FIELDS.get(kind, []))
            hint.configure(text=f"Products in this category will be asked for: "
                                f"{fields or 'the basic fields only'}.")
        c_kind.configure(command=on_kind)
        on_kind()

        e_desc = ui.labelled_entry(body, "Description",
                                   row["description"] if editing else "")
        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            name = e_name.get().strip()
            if not name:
                msg.configure(text="Category name is required.")
                return
            clash = self.db.fetchone(
                "SELECT id FROM categories WHERE name=? COLLATE NOCASE "
                "AND id != ?", (name, row["id"] if editing else -1))
            if clash:
                msg.configure(text="A category with that name already exists.")
                return
            kind = kind_by_label.get(c_kind.get(), "general")
            code = e_code.get().strip().upper()[:6]
            try:
                if editing:
                    self.db.execute(
                        "UPDATE categories SET name=?, code=?, kind=?, "
                        "description=? WHERE id=?",
                        (name, code, kind, e_desc.get().strip(), row["id"]))
                else:
                    self.db.execute(
                        "INSERT INTO categories (name, code, kind, description) "
                        "VALUES (?,?,?,?)",
                        (name, code, kind, e_desc.get().strip()))
            except Exception as exc:
                msg.configure(text=f"Could not save: {exc}")
                return
            d.destroy()
            self.refresh()
            self.toast("Category saved.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Save", save, "ok", 130, side="right")

    def _delete(self):
        row = self._selected()
        if not row:
            return
        n = int(self.db.scalar(
            "SELECT COUNT(*) FROM products WHERE category_id=?",
            (row["id"],), 0))
        if n:
            self.warn("Category in use",
                      f"{n} product(s) still use '{row['name']}'.\n\n"
                      "Move or delete those products first.")
            return
        if not self.confirm("Delete category",
                            f"Delete the category '{row['name']}'?",
                            danger=True):
            return
        self.db.execute("DELETE FROM categories WHERE id=?", (row["id"],))
        self.refresh()
        self.toast("Category deleted.")
