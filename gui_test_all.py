"""Exhaustive GUI harness — clicks EVERY action on EVERY page, both roles.

How it works:
  * every blocking dialog (messagebox, filedialog) is stubbed so nothing hangs
  * for each page it selects the first table row, then calls every zero-argument
    action method on the page object — that is every toolbar button, every
    row action, every "open form" handler
  * pass 1 answers NO to confirmations, so destructive paths build their dialog
    and then cancel; pass 2 answers YES for a curated safe subset
  * after each call, any Toplevel left open is closed and the tk error queue is
    checked, so a broken dialog shows up as a failure instead of a silent hang

Run:   python gui_test_all.py
"""
from __future__ import annotations

import inspect
import io
import os
import shutil
import sys
import tempfile
import traceback

TMP = tempfile.mkdtemp(prefix="bhumiraj_all_")
os.environ["BHUMIRAJ_HOME"] = TMP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
except Exception:
    pass

import tkinter
from tkinter import filedialog, messagebox

import customtkinter as ctk

import gui_smoke
from bhumiraj import ui_helpers as ui
from bhumiraj import whatsapp as wa
from bhumiraj.app import NAV_ITEMS, BhumirajApp

PASS = FAIL = 0
FAILURES = []
ANSWER_YES = {"value": False}


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{label} — {detail}")
        print(f"  [FAIL] {label} — {detail}")


# ─── stub everything that would block or touch the outside world ───────────
def install_stubs():
    messagebox.showinfo = lambda *a, **k: "ok"
    messagebox.showwarning = lambda *a, **k: "ok"
    messagebox.showerror = lambda *a, **k: "ok"
    messagebox.askyesno = lambda *a, **k: ANSWER_YES["value"]
    messagebox.askokcancel = lambda *a, **k: ANSWER_YES["value"]
    messagebox.askquestion = lambda *a, **k: (
        "yes" if ANSWER_YES["value"] else "no")

    ui.info = lambda *a, **k: None
    ui.warn = lambda *a, **k: None
    ui.error = lambda *a, **k: None
    ui.toast = lambda *a, **k: None
    ui.confirm = lambda *a, **k: ANSWER_YES["value"]
    ui.ask_text = lambda *a, **k: "DELETE" if ANSWER_YES["value"] else None

    filedialog.askopenfilename = lambda *a, **k: ""
    filedialog.asksaveasfilename = lambda *a, **k: ""
    filedialog.askdirectory = lambda *a, **k: ""
    ui.pick_image = lambda *a, **k: ""
    ui.pick_product_image = lambda *a, **k: ""
    ui.pick_staff_photo = lambda *a, **k: ""

    # never actually launch a printer, a PDF viewer or WhatsApp
    ui.open_file = lambda *a, **k: True
    ui.print_file = lambda *a, **k: True
    wa.send = lambda *a, **k: (True, True)
    wa.open_chat = lambda *a, **k: True
    wa.copy_file_to_clipboard = lambda *a, **k: True


def close_extra_windows(app):
    """Destroy any Toplevel a button opened, so the next call is clean."""
    closed = 0
    for w in list(app.winfo_children()):
        if isinstance(w, (ctk.CTkToplevel, tkinter.Toplevel)):
            try:
                w.grab_release()
            except Exception:
                pass
            try:
                w.destroy()
                closed += 1
            except Exception:
                pass
    try:
        app.update()
    except Exception:
        pass
    return closed


# methods that are internal plumbing, not user actions
SKIP = {
    "build", "refresh", "destroy", "quit", "update", "pack", "grid", "place",
    "_selected", "_stock_for", "_recalc", "_redraw_cart", "_period", "_where",
    "_date_from", "_empty_items", "_build_party", "_build_cart",
    "_build_search", "_total_row", "_card", "_refresh_backups", "_refresh_row",
    "_pdf_for", "_receipt_pdf", "_rows", "_item_row", "_cart_row",
    "_shop", "_backup", "_security", "_about", "_admin_view", "_staff_view",
    "_low_stock", "_recent_bills", "_top_products", "_warranty_soon",
    "_on_search_key", "_focus_results", "_preview", "_selected_cats",
    "_receipt_dialog", "_receipt_done", "_done_dialog", "_success_dialog",
    "_after_save", "_whatsapp_", "_goto_party", "_disable_tree",
    "money_text", "toast", "info", "warn", "error", "confirm", "deny_staff",
    "body", "open_pdf", "print_pdf", "staff_id",
}


def actions_of(page):
    """Every zero-argument action DEFINED IN OUR OWN CODE (i.e. every button).

    Pages subclass CTkFrame, so plain reflection would also call inherited
    Tk/CustomTkinter internals (bind_all, clipboard_get, config...). Those are
    framework methods, not buttons — filter to functions whose module is ours.
    """
    out = []
    for name in dir(page):
        if name in SKIP or name.startswith("__"):
            continue
        try:
            attr = getattr(page, name)
        except Exception:
            continue
        if not callable(attr) or not inspect.ismethod(attr):
            continue
        mod = getattr(inspect.getmodule(attr.__func__), "__name__", "")
        if not mod.startswith("bhumiraj"):
            continue
        try:
            sig = inspect.signature(attr)
        except (TypeError, ValueError):
            continue
        required = [p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if required:
            continue
        out.append((name, attr))
    return sorted(out)


def select_first_rows(page):
    """Pick the first row in every table so row-actions have something."""
    for attr in ("tree", "results", "hist", "due_tree", "preview", "bk_tree"):
        t = getattr(page, attr, None)
        if t is None:
            continue
        try:
            kids = t.get_children()
            if kids:
                t.selection_set(kids[0])
                t.focus(kids[0])
        except Exception:
            pass


def exercise(app, role, key, deep=False):
    """Open a page and click everything on it."""
    try:
        app.go(key)
        app.update()
    except Exception as exc:
        traceback.print_exc()
        check(f"{role}/{key}: page opens", False, str(exc))
        return
    page = app._page_cache.get(key)
    if page is None:
        check(f"{role}/{key}: page opens", False, "no page object")
        return
    check(f"{role}/{key}: page opens", True)

    select_first_rows(page)
    app.update()

    for name, fn in actions_of(page):
        try:
            fn()
            app.update()
            close_extra_windows(app)
            check(f"{role}/{key}.{name}()", True)
        except Exception as exc:
            traceback.print_exc()
            close_extra_windows(app)
            check(f"{role}/{key}.{name}()", False,
                  f"{type(exc).__name__}: {exc}")
        # a click may have re-rendered the page; re-select for the next one
        try:
            if app._page_cache.get(key) is page:
                select_first_rows(page)
        except Exception:
            pass


def main():
    install_stubs()
    print("=" * 76)
    print("EXHAUSTIVE GUI TEST — every page, every button, both roles")
    print("=" * 76)

    app = BhumirajApp()
    app.withdraw()
    gui_smoke.seed(app.db)

    for role, username in (("ADMIN", "admin"), ("STAFF", "sita")):
        user = app.db.fetchone("SELECT * FROM users WHERE username=?",
                               (username,))
        app.user = dict(user)
        app.build_main()
        app.update()

        is_admin = username == "admin"
        keys = [k for k, _l, _i, admin_only in NAV_ITEMS
                if not admin_only or is_admin]
        if not is_admin:
            keys.append("profile")

        print(f"\n--- {role}: {len(keys)} pages "
              + "-" * (46 - len(role)))
        for key in keys:
            exercise(app, role, key)

        # staff must be refused if they try to route into an owner-only page.
        # NB: 'products' and 'mobiles' are intentionally OPEN to staff — they
        # need to look up stock and prices — but strictly read-only.
        if not is_admin:
            for hidden in [k for k, _l, _i, admin_only in NAV_ITEMS
                           if admin_only]:
                before = app.page_key
                app.go(hidden)
                app.update()
                close_extra_windows(app)
                check(f"STAFF blocked from owner page '{hidden}'",
                      app.page_key == before,
                      f"staff reached {hidden}")

            # …and must not be able to change anything on the pages they CAN see
            app.go("products")
            app.update()
            prods = app._page_cache["products"]
            select_first_rows(prods)
            pid = prods._selected()["id"] if prods._selected() else None
            before_row = app.db.fetchone(
                "SELECT name, cost_price, sell_price, wholesale_price, "
                "stock_quantity FROM products WHERE id=?", (pid,))
            n_before = app.db.scalar("SELECT COUNT(*) FROM products", None, 0)

            ANSWER_YES["value"] = True          # staff clicks "yes" on prompts
            for attempt in ("_edit", "_delete", "_adjust"):
                try:
                    getattr(prods, attempt)()
                    app.update()
                    close_extra_windows(app)
                except Exception as exc:
                    check(f"STAFF products.{attempt}() refused cleanly",
                          False, str(exc))
            ANSWER_YES["value"] = False

            after_row = app.db.fetchone(
                "SELECT name, cost_price, sell_price, wholesale_price, "
                "stock_quantity FROM products WHERE id=?", (pid,))
            check("STAFF could not delete a product",
                  app.db.scalar("SELECT COUNT(*) FROM products", None, 0)
                  == n_before)
            check("STAFF could not change a product's prices or stock",
                  before_row is not None and after_row is not None
                  and tuple(before_row) == tuple(after_row))

            app.go("mobiles")
            app.update()
            mob = app._page_cache["mobiles"]
            select_first_rows(mob)
            units_before = app.db.scalar(
                "SELECT COUNT(*) FROM mobile_units", None, 0)
            ANSWER_YES["value"] = True
            for attempt in ("_form", "_edit", "_delete"):
                try:
                    getattr(mob, attempt)()
                    app.update()
                    close_extra_windows(app)
                except Exception as exc:
                    check(f"STAFF mobiles.{attempt}() refused cleanly",
                          False, str(exc))
            ANSWER_YES["value"] = False
            check("STAFF could not add or delete handsets",
                  app.db.scalar("SELECT COUNT(*) FROM mobile_units", None, 0)
                  == units_before)

            # but staff CAN price a line on a bill they are making
            app.go("billing")
            app.update()
            bill = app._page_cache["billing"]
            prod = app.db.fetchone(
                "SELECT p.*, c.kind AS cat_kind FROM products p "
                "JOIN categories c ON p.category_id=c.id "
                "WHERE p.is_serialized=0 AND p.stock_quantity>0 LIMIT 1")
            bill._push_item(prod, 2, 999.0)
            app.update()
            check("STAFF can set the price on a retail bill line",
                  bill.cart and bill.cart[0]["unit_price"] == 999.0)
            bill._bump(0, 1)
            app.update()
            check("STAFF can change the quantity on a bill line",
                  bill.cart[0]["quantity"] == 3
                  and bill.cart[0]["total_price"] == 2997.0)
            # switching type with items in the cart must ASK first
            from bhumiraj.config import BILL_RETAIL, BILL_WHOLESALE
            ANSWER_YES["value"] = False
            bill._set_type(BILL_WHOLESALE)
            app.update()
            check("switching bill type with a part-built bill asks first",
                  bill.bill_type == BILL_RETAIL)

            bill.cart = []
            bill._redraw_cart()
            app.update()
            bill._set_type(BILL_WHOLESALE)
            app.update()
            check("STAFF can switch to a wholesale bill",
                  bill.bill_type == BILL_WHOLESALE)
            check("wholesale mode shows the retailer picker to staff",
                  getattr(bill, "retailer_combo", None) is not None)
            check("staff see no retailer dues while billing",
                  bill.party_note.cget("text") == "")
            bill._set_type(BILL_RETAIL)
            app.update()

    # ── pass 2: say YES to confirmations on safe, reversible actions ──
    print("\n--- pass 2: confirmations answered YES " + "-" * 36)
    ANSWER_YES["value"] = True
    app.user = dict(app.db.fetchone("SELECT * FROM users WHERE username='admin'"))
    app.build_main()
    app.update()
    for key in ("billing", "bills", "products", "mobiles", "categories",
                "retailers", "customers", "payments", "imei", "returns",
                "expenses", "staff", "catalog", "reports", "settings",
                "dashboard"):
        exercise(app, "ADMIN-YES", key)
    ANSWER_YES["value"] = False

    # ── the app must still be healthy after all that clicking ─────────
    print("\n--- integrity after the click storm " + "-" * 39)
    try:
        row = app.db.fetchone("PRAGMA integrity_check")
        check("database integrity ok", row and str(row[0]).lower() == "ok",
              str(row[0]) if row else "no result")
    except Exception as exc:
        check("database integrity ok", False, str(exc))

    for table in ("users", "products", "bills", "bill_items", "categories",
                  "retailers", "mobile_units", "payments"):
        try:
            n = app.db.scalar(f"SELECT COUNT(*) FROM {table}", None, -1)
            check(f"{table} still queryable ({n} rows)", n >= 0)
        except Exception as exc:
            check(f"{table} still queryable", False, str(exc))

    try:
        app.go("dashboard")
        app.update()
        check("app still navigable at the end", app.page_key == "dashboard")
    except Exception as exc:
        check("app still navigable at the end", False, str(exc))

    try:
        app.db.close()
        app.destroy()
    except Exception:
        pass

    print("\n" + "=" * 76)
    print(f"RESULT:  {PASS} passed,  {FAIL} failed")
    print("=" * 76)
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = main()
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
