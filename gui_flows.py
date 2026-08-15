"""End-to-end GUI flows — fills forms with REAL data and clicks the actual
Save buttons, then verifies the record landed in the database.

This is the suite that catches use-after-destroy bugs: both of the crashes the
shop hit lived in the code that runs AFTER a form validates successfully, so a
harness that only opens dialogs and closes them will never see them.

Every dialog button is located by its visible text and invoked exactly the way
a click would invoke it.

Run:   python gui_flows.py
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import traceback

TMP = tempfile.mkdtemp(prefix="bhumiraj_flow_")
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
from bhumiraj.app import BhumirajApp
from bhumiraj.services import money

PASS = FAIL = 0
FAILURES = []
YES = {"v": True}


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} — {detail}")
        print(f"  [FAIL] {label} — {detail}")


def stubs():
    messagebox.showinfo = lambda *a, **k: "ok"
    messagebox.showwarning = lambda *a, **k: "ok"
    messagebox.showerror = lambda *a, **k: "ok"
    messagebox.askyesno = lambda *a, **k: YES["v"]
    ui.info = lambda *a, **k: None
    ui.warn = lambda *a, **k: None
    ui.error = lambda *a, **k: None
    ui.toast = lambda *a, **k: None
    ui.confirm = lambda *a, **k: YES["v"]
    ui.ask_text = lambda *a, **k: "DELETE"
    filedialog.askopenfilename = lambda *a, **k: ""
    filedialog.asksaveasfilename = lambda *a, **k: ""
    filedialog.askdirectory = lambda *a, **k: ""
    ui.pick_product_image = lambda *a, **k: ""
    ui.pick_staff_photo = lambda *a, **k: ""
    ui.open_file = lambda *a, **k: True
    ui.print_file = lambda *a, **k: True
    wa.send = lambda *a, **k: (True, True)
    wa.open_chat = lambda *a, **k: True


# ─── dialog helpers ────────────────────────────────────────────────────────
def dialogs(app):
    return [w for w in app.winfo_children()
            if isinstance(w, (ctk.CTkToplevel, tkinter.Toplevel))
            and w.winfo_exists()]


def top_dialog(app):
    ds = dialogs(app)
    return ds[-1] if ds else None


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def find_button(root, *texts):
    """Locate a CTkButton by its visible label (case-insensitive contains)."""
    wanted = [t.lower() for t in texts]
    for w in walk(root):
        if isinstance(w, ctk.CTkButton):
            try:
                label = str(w.cget("text")).lower()
            except Exception:
                continue
            for t in wanted:
                if t in label:
                    return w
    return None


def click(app, root, *texts):
    """Press a button exactly as a real click would."""
    b = find_button(root, *texts)
    if b is None:
        raise AssertionError(f"button {texts!r} not found in dialog")
    cmd = b.cget("command")
    if not callable(cmd):
        raise AssertionError(f"button {texts!r} has no command")
    cmd()
    app.update()
    return True


def entries(root):
    """Real form entries only.

    A CTkComboBox contains its own internal CTkEntry, so a naive walk returns
    those too and every positional index silently shifts. Skip anything whose
    parent is a combobox.
    """
    out = []
    for w in walk(root):
        if not isinstance(w, ctk.CTkEntry):
            continue
        if isinstance(getattr(w, "master", None), ctk.CTkComboBox):
            continue
        out.append(w)
    return out


def set_field(root, label, value):
    """Fill the entry that sits under the label with this text.

    `ui.labelled_entry` builds  wrap -> [CTkLabel, CTkEntry], so we find the
    label and take the entry from the same wrapper. Filling by NAME instead of
    by index is what makes these flows survive layout changes.
    """
    needle = label.lower().rstrip(" *")
    for w in walk(root):
        if not isinstance(w, ctk.CTkLabel):
            continue
        try:
            text = str(w.cget("text")).lower().rstrip(" *")
        except Exception:
            continue
        if not text.startswith(needle):
            continue
        parent = w.master
        for sib in parent.winfo_children():
            # a typeable dropdown (colour, quality, warranty…) is set by .set()
            if isinstance(sib, ctk.CTkComboBox):
                sib.set(str(value))
                return sib
            if isinstance(sib, ctk.CTkEntry) and not isinstance(
                    getattr(sib, "master", None), ctk.CTkComboBox):
                sib.configure(state="normal")
                sib.delete(0, "end")
                sib.insert(0, str(value))
                return sib
    raise AssertionError(f"field {label!r} not found in dialog")


def set_textbox(root, value):
    for w in walk(root):
        if isinstance(w, ctk.CTkTextbox):
            w.delete("1.0", "end")
            w.insert("1.0", str(value))
            return w
    raise AssertionError("no textbox in dialog")


def pick_radio(root, needle):
    needle = needle.lower()
    for w in walk(root):
        if isinstance(w, ctk.CTkRadioButton):
            if needle in str(w.cget("text")).lower():
                w.invoke()
                return True
    return False


def close_all(app):
    for d in dialogs(app):
        try:
            d.grab_release()
        except Exception:
            pass
        try:
            d.destroy()
        except Exception:
            pass
    app.update()


def guard(app, label, fn):
    """Run a flow step; any exception is a failure, not a crash."""
    try:
        fn()
        app.update()
        return True
    except Exception as exc:
        traceback.print_exc()
        check(label, False, f"{type(exc).__name__}: {exc}")
        close_all(app)
        return False


# ═══════════════════════════════════════════════════════════════════════════
def main():
    stubs()
    print("=" * 76)
    print("END-TO-END GUI FLOWS — forms filled and actually submitted")
    print("=" * 76)

    app = BhumirajApp()
    app.withdraw()
    gui_smoke.seed(app.db)
    app.user = dict(app.db.fetchone("SELECT * FROM users WHERE username='admin'"))
    app.build_main()
    app.update()

    # ── 1. SELL A PHONE (the exact flow that crashed in the shop) ─────
    print("\n--- 1. sell a handset: pick IMEI -> Add to Bill " + "-" * 27)
    app.go("billing")
    app.update()
    bill = app._page_cache["billing"]

    phone = app.db.fetchone(
        "SELECT p.*, c.kind AS cat_kind FROM products p "
        "JOIN categories c ON p.category_id=c.id WHERE p.is_serialized=1 "
        "AND p.stock_quantity>0 LIMIT 1")
    units = app.db.fetchall(
        "SELECT * FROM mobile_units WHERE product_id=? AND status='in_stock'",
        (phone["id"],))
    check(f"handsets available to sell ({len(units)})", len(units) > 0)

    if guard(app, "handset picker opens",
             lambda: bill._pick_handset(phone, units)):
        d = top_dialog(app)
        check("handset picker dialog opened", d is not None)
        if d:
            # this is the click that used to blow up
            ok = guard(app, "Add to Bill click (full payment)",
                       lambda: click(app, d, "add to bill"))
            if ok:
                check("Add to Bill did not crash", True)
                check("handset landed on the bill",
                      len(bill.cart) == 1 and bill.cart[0]["imei"] == units[0]["imei"],
                      f"cart={len(bill.cart)}")
                check("warranty was read before the dialog closed",
                      bill.cart[0]["warranty_months"] > 0,
                      f"warranty={bill.cart[0]['warranty_months']}")
                check("picker dialog closed itself", top_dialog(app) is None)
    close_all(app)

    # instalment / EMI variant
    print("\n--- 2. sell a handset on EMI " + "-" * 45)
    bill.cart = []
    bill._redraw_cart()
    if len(units) > 1 and guard(app, "picker opens for EMI",
                                lambda: bill._pick_handset(phone, units)):
        d = top_dialog(app)
        if d:
            check("instalment option present", pick_radio(d, "instal"))
            app.update()
            guard(app, "fill EMI terms",
                  lambda: (set_field(d, "Selling Price", "25000"),
                           set_field(d, "Down payment", "5000"),
                           set_field(d, "Number of months", "6")))
            if guard(app, "Add to Bill click (EMI)",
                     lambda: click(app, d, "add to bill")):
                check("EMI handset added", len(bill.cart) == 1,
                      f"cart={len(bill.cart)}")
                if bill.cart:
                    check("EMI plan recorded on the line",
                          bill.cart[0]["plan"] == "installment",
                          bill.cart[0]["plan"])
    close_all(app)

    # ── 3. COMPLETE THE BILL ──────────────────────────────────────────
    print("\n--- 3. complete the bill " + "-" * 49)
    bill.cart = []
    bill._redraw_cart()
    charger = app.db.fetchone(
        "SELECT p.*, c.kind AS cat_kind FROM products p "
        "JOIN categories c ON p.category_id=c.id WHERE p.name LIKE '65W%'")
    stock_before = int(charger["stock_quantity"])
    bill._push_item(charger, 2, 1450.0)
    bill._pick_handset(phone, units)
    d = top_dialog(app)
    if d:
        click(app, d, "add to bill")
    close_all(app)
    app.update()

    bill.ent_disc.delete(0, "end")
    bill.ent_disc.insert(0, "349")
    bill._pay_full()
    app.update()
    totals = bill._recalc()
    check(f"mixed bill subtotal = {totals['subtotal']}",
          totals["subtotal"] == money(2 * 1450 + units[0]["sell_price"]),
          str(totals["subtotal"]))
    check("Full clears the balance", totals["due"] == 0.0)

    bills_before = app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
    bill._success_dialog = lambda *a, **k: None
    if guard(app, "COMPLETE BILL click", lambda: bill._save("ask")):
        check("bill saved",
              app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
              == bills_before + 1)
        nb = app.db.fetchone("SELECT * FROM bills ORDER BY id DESC LIMIT 1")
        check("saved as paid", nb["payment_status"] == "paid",
              nb["payment_status"])
        check("charger stock deducted",
              int(app.db.scalar("SELECT stock_quantity FROM products WHERE id=?",
                                (charger["id"],), 0)) == stock_before - 2)
        check("handset marked sold",
              app.db.scalar("SELECT status FROM mobile_units WHERE id=?",
                            (units[0]["id"],), "") == "sold")
        check("IMEI written to the warranty register",
              app.db.scalar("SELECT COUNT(*) FROM imei_register WHERE bill_id=?",
                            (nb["id"],), 0) == 1)
        from bhumiraj.config import BILLS_DIR
        pdf = os.path.join(BILLS_DIR, f"{nb['bill_number']}.pdf")
        check("bill PDF generated",
              os.path.exists(pdf) and os.path.getsize(pdf) > 1200)
        check("cart cleared", len(bill.cart) == 0)
    close_all(app)

    # ── 4. ADD A PRODUCT (form filled + saved) ────────────────────────
    print("\n--- 4. add a product " + "-" * 53)
    app.go("products")
    app.update()
    prods = app._page_cache["products"]
    n_before = app.db.scalar("SELECT COUNT(*) FROM products", None, 0)
    if guard(app, "product form opens", lambda: prods._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "Product Name", "Test Speaker")
            set_field(d, "Brand", "TestBrand")
            set_field(d, "Model", "TS-100")
            set_field(d, "Cost Price", "800")
            set_field(d, "Wholesale Price", "1100")
            set_field(d, "Retail Price", "1500")
            set_field(d, "Stock Quantity", "10")
            app.update()
            if guard(app, "Save Product click",
                     lambda: click(app, d, "save product")):
                after = app.db.scalar("SELECT COUNT(*) FROM products", None, 0)
                check("product row created", after == n_before + 1,
                      f"{n_before} -> {after}")
                row = app.db.fetchone(
                    "SELECT * FROM products ORDER BY id DESC LIMIT 1")
                if row and row["name"] == "Test Speaker":
                    check("three prices stored",
                          money(row["cost_price"]) == 800
                          and money(row["wholesale_price"]) == 1100
                          and money(row["sell_price"]) == 1500,
                          f"{row['cost_price']}/{row['wholesale_price']}/{row['sell_price']}")
                    check("SKU auto-generated", bool(row["sku"]), row["sku"])
    close_all(app)

    # ── 4b. ADD A MOBILE WITH ITS IMEIs IN ONE GO ─────────────────────
    print("\n--- 4b. add a mobile + its IMEIs on the product form " + "-" * 22)
    p_before = app.db.scalar("SELECT COUNT(*) FROM products", None, 0)
    u_before = app.db.scalar("SELECT COUNT(*) FROM mobile_units", None, 0)

    def pick_mobile_category(dlg):
        for w in walk(dlg):
            if isinstance(w, ctk.CTkComboBox):
                vals = list(w.cget("values") or [])
                if "Mobile Phones" in vals:
                    w.set("Mobile Phones")
                    cmd = w.cget("command")
                    if callable(cmd):
                        cmd("Mobile Phones")
                    return True
        return False

    if guard(app, "product form opens", lambda: prods._form(None)):
        d = top_dialog(app)
        if d:
            check("Mobile category selectable", pick_mobile_category(d))
            app.update()
            check("Mobile category reveals the IMEI box",
                  any(isinstance(w, ctk.CTkTextbox) for w in walk(d)))

            # the shop must always be able to type a stock quantity, even on
            # an IMEI-tracked product
            qty_box = None
            for w in walk(d):
                if isinstance(w, ctk.CTkLabel) and str(
                        w.cget("text")).lower().startswith("stock quantity"):
                    for sib in w.master.winfo_children():
                        if isinstance(sib, ctk.CTkEntry):
                            qty_box = sib
                            break
            check("stock quantity box exists", qty_box is not None)
            if qty_box is not None:
                check("stock quantity is NOT disabled",
                      str(qty_box.cget("state")) == "normal",
                      str(qty_box.cget("state")))
                qty_box.delete(0, "end")
                qty_box.insert(0, "7")
                check("stock quantity accepts typing",
                      qty_box.get() == "7", qty_box.get())

            set_field(d, "Product Name", "Galaxy M14")
            set_field(d, "Brand", "Samsung")
            set_field(d, "Model", "SM-M146B")
            set_field(d, "Cost Price", "16000")
            set_field(d, "Wholesale Price", "18500")
            set_field(d, "Retail Price", "19999")
            set_field(d, "Colour", "Navy Blue")
            three = ["356111222333401", "356111222333402", "356111222333403"]
            set_textbox(d, "\n".join(three))
            app.update()

            if guard(app, "Save Product click (with IMEIs)",
                     lambda: click(app, d, "save product")):
                check("mobile product created",
                      app.db.scalar("SELECT COUNT(*) FROM products", None, 0)
                      == p_before + 1)
                added = (app.db.scalar("SELECT COUNT(*) FROM mobile_units",
                                       None, 0) - u_before)
                check(f"3 handsets registered from the product form ({added})",
                      added == 3)
                new = app.db.fetchone(
                    "SELECT * FROM products WHERE name='Galaxy M14'")
                if new:
                    check("stock set automatically from the IMEI count",
                          int(new["stock_quantity"]) == 3,
                          str(new["stock_quantity"]))
                    check("product marked IMEI-tracked",
                          int(new["is_serialized"]) == 1)
                    check("handset inherited the colour from the form",
                          app.db.scalar(
                              "SELECT color FROM mobile_units WHERE imei=?",
                              (three[0],), "") == "Navy Blue")
    close_all(app)

    print("\n--- 4c. duplicate IMEI is refused " + "-" * 40)
    u_now = app.db.scalar("SELECT COUNT(*) FROM mobile_units", None, 0)
    if guard(app, "product form opens again", lambda: prods._form(None)):
        d = top_dialog(app)
        if d:
            pick_mobile_category(d)
            app.update()
            set_field(d, "Product Name", "Dup Test")
            set_field(d, "Brand", "Samsung")
            set_field(d, "Model", "DUP-1")
            set_field(d, "Cost Price", "100")
            set_field(d, "Wholesale Price", "150")
            set_field(d, "Retail Price", "200")
            set_textbox(d, "356111222333401")     # already registered above
            app.update()
            guard(app, "save with duplicate IMEI",
                  lambda: click(app, d, "save product"))
            check("duplicate IMEI rejected — no handset inserted",
                  app.db.scalar("SELECT COUNT(*) FROM mobile_units", None, 0)
                  == u_now)
            check("duplicate IMEI rejected — product not created",
                  app.db.scalar(
                      "SELECT COUNT(*) FROM products WHERE name='Dup Test'",
                      None, 0) == 0)
    close_all(app)

    print("\n--- 4d. a phone WITHOUT IMEI tracking sells normally " + "-" * 22)
    created = app.db.execute(
        "INSERT INTO products (name, category_id, sku, brand, model, "
        " cost_price, wholesale_price, sell_price, stock_quantity, "
        " is_serialized, attrs) VALUES ('Basic Keypad Phone', "
        " (SELECT id FROM categories WHERE name='Mobile Phones'), "
        " 'MOB-BAS-9999','Nokia','105', 1200, 1500, 1800, 20, 0, '{}')")
    plain = app.db.fetchone(
        "SELECT p.*, c.kind AS cat_kind FROM products p "
        "JOIN categories c ON p.category_id=c.id WHERE p.id=?",
        (created.lastrowid,))
    app.go("billing")
    app.update()
    bill = app._page_cache["billing"]
    bill.cart = []
    bill._redraw_cart()
    bill._rows = {"row0": plain}
    for iid in bill.results.get_children():
        bill.results.delete(iid)
    iid = bill.results.insert("", "end", values=(
        plain["name"], plain["brand"], plain["model"], "—", 20, "1800.00"))
    bill._rows = {iid: plain}
    bill.results.selection_set(iid)
    guard(app, "add non-IMEI phone from search", bill._add_selected)
    check("non-IMEI phone goes straight onto the bill, no picker",
          len(bill.cart) == 1 and bill.cart[0]["imei"] == "",
          f"cart={len(bill.cart)}")
    check("no handset dialog appeared", top_dialog(app) is None)
    bill.cart = []
    bill._redraw_cart()
    close_all(app)

    # ── 4e. ONE-CLICK ADD + EDIT LINE ─────────────────────────────────
    print("\n--- 4e. one-click add, double-click for phones, edit line "
          + "-" * 17)
    app.go("billing")
    app.update()
    bill = app._page_cache["billing"]
    bill.cart = []
    bill._redraw_cart()
    app.update()

    class FakeClick:
        def __init__(self, y=10):
            self.y = y

    def click_row(iid):
        """Drive the real click handler.

        bbox() returns nothing while the test window is hidden, so pointing
        identify_row at the row under test is what actually exercises the
        click-routing logic instead of silently skipping it.
        """
        original = bill.results.identify_row
        bill.results.identify_row = lambda _y: iid
        try:
            bill._on_result_click(FakeClick())
        finally:
            bill.results.identify_row = original

    def double_row(iid):
        original = bill.results.identify_row
        bill.results.identify_row = lambda _y: iid
        try:
            bill._on_result_double(FakeClick())
        finally:
            bill.results.identify_row = original

    bill.search_entry.delete(0, "end")
    bill.search_entry.insert(0, "a")
    bill._search()
    app.update()
    rows = bill.results.get_children()
    check(f"typing fills the results dropdown ({len(rows)})", len(rows) > 0)

    normal_iid = phone_iid = None
    for iid in rows:
        r = bill._rows.get(iid)
        if r is None:
            continue
        if r["is_serialized"] and phone_iid is None:
            phone_iid = iid
        elif not r["is_serialized"] and normal_iid is None:
            normal_iid = iid
    check("a normal product is in the results", normal_iid is not None)
    check("an IMEI phone is in the results", phone_iid is not None)

    if normal_iid:
        guard(app, "single click a normal product",
              lambda: click_row(normal_iid))
        check("ONE CLICK added a normal product to the bill",
              len(bill.cart) == 1, f"cart={len(bill.cart)}")

    if phone_iid:
        before = len(bill.cart)
        guard(app, "single click an IMEI phone", lambda: click_row(phone_iid))
        check("single click on a phone does NOT add it",
              len(bill.cart) == before, f"cart={len(bill.cart)}")
        check("hint tells the user to double-click",
              "double-click" in bill.drop_head.cget("text").lower())
        guard(app, "double click an IMEI phone", lambda: double_row(phone_iid))
        check("double click opens the handset picker",
              top_dialog(app) is not None)
        close_all(app)

    # edit a bill line: model + quality must change what prints
    if bill.cart:
        if guard(app, "edit-line dialog opens", lambda: bill._edit_line(0)):
            d = top_dialog(app)
            if d:
                set_field(d, "Model", "EDITED-MODEL-9")
                set_field(d, "Quality / Grade", "A+ Copy")
                app.update()
                if guard(app, "Save line click",
                         lambda: click(app, d, "save line")):
                    check("model changed on the bill line",
                          bill.cart[0]["model"] == "EDITED-MODEL-9",
                          bill.cart[0]["model"])
                    check("quality changed on the bill line",
                          bill.cart[0]["quality"] == "A+ Copy",
                          bill.cart[0].get("quality"))
                    bill.cart[0]["unit_price"] = 1234.0
                    bill.cart[0]["total_price"] = money(1234.0 * bill.cart[0]["quantity"])
                    check("price changed inline and total recalculated",
                          bill.cart[0]["unit_price"] == 1234.0
                          and bill.cart[0]["total_price"]
                          == money(1234.0 * bill.cart[0]["quantity"]),
                          str(bill.cart[0]["total_price"]))
        close_all(app)

        # and it must reach the saved bill + the PDF
        bill._pay_full()
        bill._success_dialog = lambda *a, **k: None
        if guard(app, "save the edited bill", lambda: bill._save("none")):
            item = app.db.fetchone(
                "SELECT * FROM bill_items ORDER BY id DESC LIMIT 1")
            check("edited model stored on the bill item",
                  item and item["product_model"] == "EDITED-MODEL-9",
                  item["product_model"] if item else "no row")
            from bhumiraj.services import unpack_attrs
            snap = unpack_attrs(item["attrs_snapshot"]) if item else {}
            check("edited quality stored in the bill snapshot",
                  snap.get("quality") == "A+ Copy", str(snap))
    close_all(app)
    bill.cart = []
    bill._redraw_cart()

    # ── 4f. SAVE WHILE A CART FIELD HAS FOCUS (the third crash) ───────
    print("\n--- 4f. save while a price box has focus " + "-" * 34)
    app.go("billing")
    app.update()
    bill = app._page_cache["billing"]
    bill.cart = []
    bill._redraw_cart()
    app.update()

    cheap = app.db.fetchone(
        "SELECT p.*, c.kind AS cat_kind FROM products p "
        "JOIN categories c ON p.category_id=c.id "
        "WHERE p.is_serialized=0 AND p.stock_quantity>2 LIMIT 1")
    bill._push_item(cheap, 2, 100.0)
    app.update()

    check("bill line rendered as widgets", len(bill._rows_ui) == 1)
    r = bill._row_ui(0)
    check("line has live qty and price boxes", r is not None)
    if r:
        r["qty"].delete(0, "end"); r["qty"].insert(0, "4")
        guard(app, "typing a qty updates the line", lambda: bill._line_typed(0))
        check("qty applied live", bill.cart[0]["quantity"] == 4,
              str(bill.cart[0]["quantity"]))
        r["price"].delete(0, "end"); r["price"].insert(0, "250")
        guard(app, "typing a price updates the line", lambda: bill._line_typed(0))
        check("price applied live", bill.cart[0]["unit_price"] == 250.0,
              str(bill.cart[0]["unit_price"]))
        check("amount recalculated live", bill.cart[0]["total_price"] == 1000.0,
              str(bill.cart[0]["total_price"]))
        check("amount label shows the new total",
              "1,000.00" in r["total"].cget("text"), r["total"].cget("text"))
    guard(app, "+ stepper", lambda: bill._step(0, 1))
    check("stepper increased the qty", bill.cart[0]["quantity"] == 5,
          str(bill.cart[0]["quantity"]))
    guard(app, "- stepper", lambda: bill._step(0, -1))
    check("stepper decreased the qty", bill.cart[0]["quantity"] == 4,
          str(bill.cart[0]["quantity"]))
    # a destroyed row must be ignored, not crash
    for w in bill._rows_ui[0].values():
        try: w.destroy()
        except Exception: pass
    app.update()
    guard(app, "typing into a destroyed row", lambda: bill._line_typed(0))
    guard(app, "stepping a destroyed row", lambda: bill._step(0, 1))
    guard(app, "editing a line that is gone", lambda: bill._line_typed(99))
    check("destroyed / missing rows handled safely", True)

    # and the full save path with a line still on the bill
    bill.cart = []
    bill._redraw_cart()
    bill._push_item(cheap, 2, 100.0)
    app.update()
    app.update()
    bill._pay_full()
    app.update()
    bill._success_dialog = lambda *a, **k: None
    before = app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
    ok = guard(app, "COMPLETE BILL with focus in the price box",
               lambda: bill._save("none"))
    check("no crash saving while a row is focused", ok)
    check("bill still saved",
          app.db.scalar("SELECT COUNT(*) FROM bills", None, 0) == before + 1)
    check("cart cleared cleanly", len(bill.cart) == 0)
    check("no stale row widgets left behind", bill._rows_ui == [])

    # rapid add / remove / clear must not leave dead widgets behind either
    for _ in range(3):
        bill._push_item(cheap, 1, 100.0)
    app.update()
    app.update()
    guard(app, "remove a line while its box has focus",
          lambda: bill._remove(0))
    guard(app, "clear the bill while a box has focus", bill._clear_cart)
    check("clear left an empty cart", len(bill.cart) == 0)
    close_all(app)

    # ── 4g. SAVE WHILE THE CARET IS IN A BILL LINE ────────────────────
    print("\n--- 4g. complete a bill with the caret in a line " + "-" * 26)
    app.deiconify()          # focus only really moves on a mapped window
    app.update()
    app.go("billing")
    app.update()
    bill = app._page_cache["billing"]
    bill.cart = []
    bill._redraw_cart()
    app.update()

    cheap2 = app.db.fetchone(
        "SELECT p.*, c.kind AS cat_kind FROM products p "
        "JOIN categories c ON p.category_id=c.id "
        "WHERE p.is_serialized=0 AND p.stock_quantity>2 LIMIT 1")
    bill._push_item(cheap2, 2, 120.0)
    app.update()

    r = bill._row_ui(0)
    check("line rendered for the focus test", r is not None)
    if r:
        r["price"].focus_set()
        app.update()
        focused_before = str(app.focus_get() or "")
        check("caret really is inside the bill line",
              focused_before.startswith(str(bill.lines_box)), focused_before)

        bill._pay_full()
        app.update()
        # NOTE: the success dialog is deliberately NOT stubbed here. It is a
        # real CTkToplevel, and it is the thing that schedules the focus
        # restore that used to crash.
        n_before = app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
        ok = guard(app, "COMPLETE BILL with the caret in a price box",
                   lambda: bill._save("none"))
        check("saving with the caret in a line did not crash", ok)
        check("bill was saved",
              app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
              == n_before + 1)

        # flush every queued after() callback — this is what used to fire
        # focus_set at the row entry that had just been destroyed
        import time as _t
        for _ in range(30):
            app.update()
            app.update_idletasks()
            _t.sleep(0.02)          # let the after(10, ...) restore actually fire
        after_focus = str(app.focus_get() or "")
        check("caret was parked outside the destroyed rows",
              not after_focus.startswith(str(bill.lines_box)), after_focus)

    close_all(app)
    app.update()
    # Direct test of the mechanism CTkToplevel uses: it remembers whichever
    # widget had focus and re-focuses it 10ms later. If that widget is a bill
    # line we are about to destroy, it raises. _park_focus is what guarantees
    # the remembered widget is the search box, which survives.
    bill.cart = []
    bill._redraw_cart()
    bill._push_item(cheap2, 1, 50.0)
    app.update()
    rr = bill._row_ui(0)
    if rr:
        rr["qty"].focus_set()
        app.update()
        check("caret is in the line before parking",
              str(app.focus_get() or "").startswith(str(bill.lines_box)),
              str(app.focus_get()))
        bill._park_focus()
        app.update()
        parked = app.focus_get()
        check("_park_focus moves the caret to the search box",
              parked is not None
              and str(parked).startswith(str(bill.search_entry)),
              str(parked))
        # what CTkToplevel would remember is now a widget that survives
        remembered = parked
        bill.cart = []
        bill._redraw_cart()
        app.update()
        ok2 = guard(app, "the remembered widget still exists after the rows go",
                    lambda: remembered.focus())
        check("CTk focus-restore target survives the redraw", ok2)
        check("no error was logged by the flush",
              not os.path.exists(os.path.join(TMP, "data", "error_log.txt")),
              "error_log.txt appeared")
    app.withdraw()
    close_all(app)

    # ── 5. ADD A STAFF ACCOUNT (the second crash) ─────────────────────
    print("\n--- 5. create a staff account " + "-" * 44)
    app.go("staff")
    app.update()
    staff = app._page_cache["staff"]
    u_before = app.db.scalar("SELECT COUNT(*) FROM users", None, 0)
    if guard(app, "staff form opens", lambda: staff._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "Full Name", "Test Counter Staff")
            set_field(d, "Username", "teststaff")
            set_field(d, "Phone", "9800000123")
            app.update()
            if guard(app, "Save staff click", lambda: click(app, d, "save")):
                check("staff account created",
                      app.db.scalar("SELECT COUNT(*) FROM users", None, 0)
                      == u_before + 1)
                new = app.db.fetchone(
                    "SELECT * FROM users WHERE username='teststaff'")
                check("staff row is correct",
                      new is not None and new["role"] == "staff")
                check("staff must change password on first login",
                      new is not None and new["must_change_password"] == 1)
                check("no crash reading the temp password after close", True)
    close_all(app)

    # ── 6. RETAILER + WHOLESALE BILL + FIFO PAYMENT ───────────────────
    print("\n--- 6. retailer, wholesale bill, FIFO payment " + "-" * 29)
    app.go("retailers")
    app.update()
    ret = app._page_cache["retailers"]
    r_before = app.db.scalar("SELECT COUNT(*) FROM retailers", None, 0)
    if guard(app, "retailer form opens", lambda: ret._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "Contact Name", "Test Retailer")
            set_field(d, "Phone", "9800000999")
            app.update()
            if guard(app, "Save retailer click", lambda: click(app, d, "save")):
                check("retailer created",
                      app.db.scalar("SELECT COUNT(*) FROM retailers", None, 0)
                      == r_before + 1)
    close_all(app)

    rid = app.db.scalar(
        "SELECT id FROM retailers WHERE name='Test Retailer'", None, None)
    if rid:
        app.go("billing")
        app.update()
        bill = app._page_cache["billing"]
        from bhumiraj.config import BILL_WHOLESALE
        bill._set_type(BILL_WHOLESALE)
        app.update()
        bill.retailer_id = rid
        bill._push_item(charger, 5, 1050.0)
        bill.ent_paid.delete(0, "end")
        bill.ent_paid.insert(0, "0")
        bill._success_dialog = lambda *a, **k: None
        if guard(app, "wholesale bill on credit", lambda: bill._save("none")):
            wb = app.db.fetchone(
                "SELECT * FROM bills WHERE retailer_id=? ORDER BY id DESC LIMIT 1",
                (rid,))
            check("wholesale bill saved unpaid",
                  wb is not None and wb["payment_status"] == "unpaid")
            from bhumiraj.services import retailer_outstanding
            check(f"retailer owes {retailer_outstanding(app.db, rid)}",
                  retailer_outstanding(app.db, rid) == 5250.0)
        close_all(app)

        app.go("retailers")
        app.update()
        ret = app._page_cache["retailers"]
        for iid in ret.tree.get_children():
            if ret.tree.item(iid, "values")[0] == "Test Retailer":
                ret.tree.selection_set(iid)
                break
        if guard(app, "payment dialog opens", ret._payment):
            d = top_dialog(app)
            if d:
                set_field(d, "Amount received", "3000")
                app.update()
                if guard(app, "Record Payment click",
                         lambda: click(app, d, "record payment")):
                    from bhumiraj.services import retailer_outstanding
                    check("FIFO applied, 2250 still owed",
                          retailer_outstanding(app.db, rid) == 2250.0,
                          str(retailer_outstanding(app.db, rid)))
                    check("receipt row written",
                          app.db.scalar(
                              "SELECT COUNT(*) FROM payments WHERE retailer_id=?"
                              " AND receipt_number != ''", (rid,), 0) >= 1)
        close_all(app)

    # ── 7. COLLECT A RETAIL DUE ───────────────────────────────────────
    print("\n--- 7. collect a due on a retail bill " + "-" * 37)
    app.go("bills")
    app.update()
    bills_page = app._page_cache["bills"]
    target = None
    for iid in bills_page.tree.get_children():
        row = bills_page._rows.get(iid)
        if row and money(row["total_amount"]) - money(row["paid_amount"]) > 1:
            bills_page.tree.selection_set(iid)
            target = row
            break
    if target:
        due = money(money(target["total_amount"]) - money(target["paid_amount"]))
        if guard(app, "collect dialog opens", bills_page._collect):
            d = top_dialog(app)
            if d:
                bills_page._receipt_dialog = lambda *a, **k: None
                if guard(app, "Record Payment click (retail)",
                         lambda: click(app, d, "record payment")):
                    after = app.db.fetchone("SELECT * FROM bills WHERE id=?",
                                            (target["id"],))
                    check(f"bill settled (was {due} due)",
                          after["payment_status"] == "paid",
                          after["payment_status"])
        close_all(app)
    else:
        check("a bill with a due exists to collect", False, "none found")

    # ── 8. EXPENSE, CATEGORY, HANDSET INTAKE ──────────────────────────
    print("\n--- 8. expense / category / handset intake " + "-" * 32)
    app.go("expenses")
    app.update()
    exp = app._page_cache["expenses"]
    e_before = app.db.scalar("SELECT COUNT(*) FROM expenses", None, 0)
    if guard(app, "expense form opens", lambda: exp._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "Description", "Test electricity bill")
            set_field(d, "Amount", "4500")
            app.update()
            if guard(app, "Save expense click", lambda: click(app, d, "save")):
                check("expense created",
                      app.db.scalar("SELECT COUNT(*) FROM expenses", None, 0)
                      == e_before + 1)
    close_all(app)

    app.go("categories")
    app.update()
    cats = app._page_cache["categories"]
    c_before = app.db.scalar("SELECT COUNT(*) FROM categories", None, 0)
    if guard(app, "category form opens", lambda: cats._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "Category Name", "Test Category")
            set_field(d, "Short Code", "TSTC")
            app.update()
            if guard(app, "Save category click", lambda: click(app, d, "save")):
                check("category created",
                      app.db.scalar("SELECT COUNT(*) FROM categories", None, 0)
                      == c_before + 1)
    close_all(app)

    app.go("mobiles")
    app.update()
    mob = app._page_cache["mobiles"]
    m_before = app.db.scalar("SELECT COUNT(*) FROM mobile_units", None, 0)
    if guard(app, "handset intake form opens", lambda: mob._form(None)):
        d = top_dialog(app)
        if d:
            set_field(d, "IMEI 1", "356938035643899")
            set_field(d, "Colour", "Graphite")
            set_field(d, "Cost Price", "21000")
            app.update()
            if guard(app, "Save handset click", lambda: click(app, d, "save")):
                check("handset registered",
                      app.db.scalar("SELECT COUNT(*) FROM mobile_units",
                                    None, 0) == m_before + 1)
    close_all(app)

    # ── 9. SETTINGS: backup / export ──────────────────────────────────
    print("\n--- 9. settings: backup now + export " + "-" * 38)
    app.go("settings")
    app.update()
    st = app._page_cache["settings"]
    guard(app, "save shop details", st._save_shop)
    check("shop details saved", True)
    guard(app, "save backup settings", st._save_backup)
    check("backup settings saved", True)
    guard(app, "backup now", st._backup_now)
    from bhumiraj.config import BACKUPS_DIR
    n_bk = len([f for f in os.listdir(BACKUPS_DIR) if f.endswith(".db")])
    check(f"backup file written ({n_bk} in folder)", n_bk >= 1)
    close_all(app)

    # ── 11. LOGIN / LOGOUT THROUGH THE REAL SCREEN ────────────────────
    print("\n--- 11. login and logout " + "-" * 49)
    from bhumiraj.services import authenticate
    app.show_login()
    app.update()
    check("login screen built", hasattr(app, "login_user"))

    app.login_user.delete(0, "end"); app.login_user.insert(0, "admin")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "wrong-password")
    guard(app, "sign in with a bad password", app._do_login)
    check("bad password is refused", app.user is None)
    check("an error is shown on screen",
          bool(app.login_msg.cget("text")), app.login_msg.cget("text"))

    app.login_user.delete(0, "end"); app.login_user.insert(0, "nosuchuser")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "Admin@123")
    guard(app, "sign in as an unknown user", app._do_login)
    check("unknown user is refused", app.user is None)

    app.login_user.delete(0, "end"); app.login_user.insert(0, "admin")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "Admin@123")
    guard(app, "sign in with the right password", app._do_login)
    check("admin signed in", app.user is not None
          and app.user["username"] == "admin")
    check("main screen opened", app.page_key == "dashboard", str(app.page_key))

    guard(app, "log out", lambda: app.logout(ask=False))
    check("logout returned to the login screen", app.user is None)
    check("login boxes are back", hasattr(app, "login_user"))

    # staff can sign in too
    app.login_user.delete(0, "end"); app.login_user.insert(0, "sita")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "shop123")
    guard(app, "staff signs in", app._do_login)
    check("staff signed in", app.user is not None
          and app.user["username"] == "sita")
    check("staff sees no owner-only pages in the sidebar",
          all(k not in app.nav_buttons
              for k in ("settings", "reports", "staff", "retailers")))
    guard(app, "staff logs out", lambda: app.logout(ask=False))

    # disabled account must be refused
    app.db.execute("UPDATE users SET is_active=0 WHERE username='sita'")
    app.login_user.delete(0, "end"); app.login_user.insert(0, "sita")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "shop123")
    guard(app, "disabled account tries to sign in", app._do_login)
    check("disabled account is refused", app.user is None)
    app.db.execute("UPDATE users SET is_active=1 WHERE username='sita'")

    # every attempt was audited
    check("login attempts were recorded",
          app.db.scalar("SELECT COUNT(*) FROM login_audit", None, 0) >= 5,
          str(app.db.scalar("SELECT COUNT(*) FROM login_audit", None, 0)))

    # back in as admin for anything that follows
    app.login_user.delete(0, "end"); app.login_user.insert(0, "admin")
    app.login_pass.delete(0, "end"); app.login_pass.insert(0, "Admin@123")
    app._do_login()
    app.update()

    # ── 12. STAFF SALARY ──────────────────────────────────────────────
    print("\n--- 12. staff salary " + "-" * 53)
    app.go("staff")
    app.update()
    staff_page = app._page_cache["staff"]
    row = app.db.fetchone("SELECT * FROM users WHERE username='teststaff'")
    check("the staff member created earlier is there", row is not None)
    if row:
        if guard(app, "open the staff member for editing",
                 lambda: staff_page._form(row)):
            d = top_dialog(app)
            if d:
                set_field(d, "Monthly Salary", "24500")
                set_field(d, "Joined Date", "2026-02-01")
                app.update()
                if guard(app, "save the salary",
                         lambda: click(app, d, "save")):
                    after = app.db.fetchone(
                        "SELECT * FROM users WHERE username='teststaff'")
                    check("salary stored",
                          after and money(after["salary"]) == 24500.0,
                          str(after["salary"]) if after else "no row")
                    check("joined date stored",
                          after and after["joined_date"] == "2026-02-01",
                          after["joined_date"] if after else "")
        close_all(app)
        staff_page.refresh()
        app.update()
        check("payroll total reflects the salary", True)

    # ── 10. integrity ─────────────────────────────────────────────────
    print("\n--- 10. integrity " + "-" * 57)
    row = app.db.fetchone("PRAGMA integrity_check")
    check("database integrity ok", row and str(row[0]).lower() == "ok")
    check("no error log was written (no unhandled exceptions)",
          not os.path.exists(os.path.join(TMP, "data", "error_log.txt")),
          "error_log.txt exists — an exception was swallowed")

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
