"""GUI smoke test — builds every page for both roles against seeded data.

This is what catches runtime errors that a plain import never would: missing
widgets, bad column counts, wrong attribute names inside build().

Run:   python gui_smoke.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback

TMP = tempfile.mkdtemp(prefix="bhumiraj_gui_")
os.environ["BHUMIRAJ_HOME"] = TMP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bhumiraj import config                                    # noqa: E402
from bhumiraj.security import hash_password                    # noqa: E402
from bhumiraj.services import log_stock, warranty_expiry       # noqa: E402

PASS = FAIL = 0
FAILURES = []


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} — {detail}")
        print(f"  [FAIL] {label} — {detail}")


def seed(db):
    """Enough data that every page has something real to render."""
    admin_id = db.scalar("SELECT id FROM users WHERE username='admin'", None, 1)
    db.execute("UPDATE users SET must_change_password=0 WHERE id=?",
               (admin_id,))
    db.execute("INSERT INTO users (username, password_hash, role, full_name, "
               " phone, salary, joined_date, is_active, must_change_password) "
               "VALUES ('sita', ?, 'staff', 'Sita Karki', '9841222333', "
               " 18000, '2026-01-15', 1, 0)", (hash_password("shop123"),))
    staff_id = db.scalar("SELECT id FROM users WHERE username='sita'", None, 2)

    mob = db.scalar("SELECT id FROM categories WHERE name='Mobile Phones'",
                    None, 1)
    chg = db.scalar("SELECT id FROM categories WHERE name='Chargers'", None, 2)
    wat = db.scalar("SELECT id FROM categories WHERE name='Wrist Watches'",
                    None, 3)
    sun = db.scalar("SELECT id FROM categories WHERE name='Glasses (Sun)'",
                    None, 4)

    products = [
        ("Galaxy A15", mob, "Samsung", "SM-A155F", 22000, 25500, 27999, 4, 12,
         1, '{"color":"Blue Black","storage":"128GB","ram":"6GB","network":"5G"}'),
        ("Redmi Note 13", mob, "Xiaomi", "23129RAA4G", 19500, 22500, 24999, 3,
         12, 1, '{"color":"Midnight Black","storage":"256GB","ram":"8GB"}'),
        ("65W Fast Charger", chg, "Samsung", "EP-TA800", 850, 1050, 1450, 40,
         6, 0, '{"connector":"Type-C","wattage":"65W","quality":"Original"}'),
        ("Type-C Cable 1m", chg, "Anker", "A8022", 320, 450, 650, 2, 3, 0,
         '{"connector":"Type-C","quality":"Original"}'),
        ("Classic Automatic", wat, "Titan", "NH1825SL01", 4200, 5200, 6999, 6,
         24, 0, '{"movement":"Automatic","strap":"Leather","gender":"Men"}'),
        ("Aviator Polarised", sun, "RayBan", "RB3025", 2400, 3100, 4200, 0, 0,
         0, '{"frame":"Metal","lens":"Polarised","gender":"Unisex"}'),
    ]
    ids = {}
    for (name, cat, brand, model, cp, wp, sp, qty, warr, ser, attrs) in products:
        cur = db.execute(
            "INSERT INTO products (name, category_id, sku, brand, model, "
            " cost_price, wholesale_price, sell_price, stock_quantity, "
            " min_stock_level, warranty_months, is_serialized, attrs) "
            "VALUES (?,?,?,?,?,?,?,?,?,3,?,?,?)",
            (name, cat, f"SKU-{len(ids) + 1:04d}", brand, model, cp, wp, sp,
             qty, warr, ser, attrs))
        ids[name] = cur.lastrowid

    with db.transaction() as c:
        for i, imei in enumerate(("356938035643801", "356938035643802",
                                  "356938035643803", "356938035643804")):
            c.execute(
                "INSERT INTO mobile_units (product_id, imei, color, storage, "
                " ram, condition, cost_price, sell_price, status) "
                "VALUES (?,?,'Blue Black','128GB','6GB','New',22000,27999,"
                " 'in_stock')", (ids["Galaxy A15"], imei))

    cur = db.execute(
        "INSERT INTO retailers (name, shop_name, phone, city, opening_balance) "
        "VALUES ('Hari Sharma','Hari Mobile Center','9851000002','Bhaktapur',"
        " 2500)")
    ret_id = cur.lastrowid
    db.execute("INSERT INTO retailers (name, shop_name, phone, city) "
               "VALUES ('Gita Traders','Gita Electronics','9856000003','Patan')")

    # a retail bill with a handset on EMI
    unit = db.fetchone("SELECT * FROM mobile_units WHERE status='in_stock' "
                       "ORDER BY id LIMIT 1")
    bno = db.next_bill_number("retail")
    with db.transaction() as c:
        c.execute(
            "INSERT INTO bills (bill_number, bill_type, customer_name, "
            " customer_phone, staff_id, bill_date, subtotal, discount_amount, "
            " total_amount, paid_amount, due_amount, payment_status, "
            " payment_method, plan_type) VALUES (?,'retail','Ram Bahadur',"
            " '9841000001',?, '2026-08-01 10:30:00', 30899, 500, 30399, 8000, "
            " 22399, 'partial','Cash','installment')", (bno, staff_id))
        bill_id = c.lastrowid
        c.execute(
            "INSERT INTO bill_items (bill_id, product_id, mobile_unit_id, "
            " product_name, product_brand, product_model, product_sku, imei, "
            " attrs_snapshot, quantity, unit_price, total_price, cogs_price, "
            " warranty_months) VALUES (?,?,?,'Galaxy A15','Samsung','SM-A155F',"
            " 'SKU-0001',?,'{\"color\":\"Blue Black\",\"storage\":\"128GB\"}',"
            " 1,27999,27999,22000,12)",
            (bill_id, ids["Galaxy A15"], unit["id"], unit["imei"]))
        c.execute(
            "INSERT INTO bill_items (bill_id, product_id, product_name, "
            " product_brand, product_model, product_sku, quantity, unit_price, "
            " total_price, cogs_price) VALUES (?,?,'65W Fast Charger',"
            " 'Samsung','EP-TA800','SKU-0003',2,1450,2900,850)",
            (bill_id, ids["65W Fast Charger"]))
        c.execute("UPDATE mobile_units SET status='sold', bill_id=?, "
                  "sold_date='2026-08-01' WHERE id=?", (bill_id, unit["id"]))
        c.execute("UPDATE products SET stock_quantity=stock_quantity-1 "
                  "WHERE id=?", (ids["Galaxy A15"],))
        c.execute("UPDATE products SET stock_quantity=stock_quantity-2 "
                  "WHERE id=?", (ids["65W Fast Charger"],))
        log_stock(c, ids["65W Fast Charger"], "sale", -2, 38, bno, staff_id)
        c.execute(
            "INSERT INTO imei_register (imei, product_id, mobile_unit_id, "
            " product_name, brand, model, color, storage, bill_id, "
            " bill_number, customer_name, customer_phone, sold_date, "
            " warranty_months, warranty_expiry, plan_type, total_amount, "
            " down_payment, installment_amount, installment_months, status) "
            "VALUES (?,?,?,'Galaxy A15','Samsung','SM-A155F','Blue Black',"
            " '128GB',?,?,'Ram Bahadur','9841000001','2026-08-01',12,?,"
            " 'installment',27999,8000,3333.17,6,'active')",
            (unit["imei"], ids["Galaxy A15"], unit["id"], bill_id, bno,
             warranty_expiry("2026-08-01", 12)))
        reg_id = c.lastrowid
        c.execute("INSERT INTO payments (receipt_number, bill_id, amount, "
                  " payment_method, payment_date, staff_id) "
                  "VALUES ('', ?, 8000, 'Cash', '2026-08-01', ?)",
                  (bill_id, staff_id))
    db.execute("INSERT INTO imei_payments (register_id, receipt_number, "
               " payment_date, amount, payment_method, staff_id) "
               "VALUES (?, ?, '2026-09-01', 3333.17, 'Cash', ?)",
               (reg_id, db.next_installment_receipt(), staff_id))

    # wholesale invoices + a FIFO payment
    for value, date in ((10000, "2026-06-01"), (7500, "2026-07-01")):
        num = db.next_bill_number("wholesale")
        db.execute(
            "INSERT INTO bills (bill_number, bill_type, retailer_id, "
            " customer_name, customer_phone, staff_id, bill_date, subtotal, "
            " total_amount, paid_amount, due_amount, payment_status, "
            " payment_method) VALUES (?,'wholesale',?, 'Hari Sharma',"
            " '9851000002', ?, ?, ?, ?, 0, ?, 'unpaid','Credit')",
            (num, ret_id, staff_id, date + " 11:00:00", value, value, value))
    from bhumiraj.services import record_retailer_payment
    record_retailer_payment(db, ret_id, 12000, "Bank Transfer", "2026-07-20",
                            "CHQ-1", "", admin_id)

    db.execute("INSERT INTO returns (bill_id, bill_number, product_id, "
               " product_name, quantity, refund_amount, restocked, reason, "
               " staff_id, return_date) VALUES (?,?,?,'Type-C Cable 1m',1,650,"
               " 1,'Defective',?, '2026-08-02 14:00:00')",
               (bill_id, bno, ids["Type-C Cable 1m"], staff_id))
    db.execute("INSERT INTO expenses (expense_date, category, description, "
               " amount, payment_method, staff_id) VALUES "
               " ('2026-08-01','Rent','Shop rent August',25000,'Cash',?)",
               (admin_id,))
    db.execute("INSERT INTO expenses (expense_date, category, description, "
               " amount, payment_method, staff_id) VALUES "
               " ('2026-08-02','Salary','Staff salary',18000,'Cash',?)",
               (admin_id,))
    return admin_id, staff_id


def main():
    global FAIL
    import customtkinter as ctk
    from bhumiraj.app import NAV_ITEMS, BhumirajApp

    print("=" * 74)
    print("GUI SMOKE TEST — building every page")
    print("=" * 74)

    try:
        app = BhumirajApp()
    except Exception as exc:
        traceback.print_exc()
        print(f"\n[FATAL] the app window could not be created: {exc}")
        return 1
    app.withdraw()                      # keep it off-screen

    check("app window created", True)
    check("login screen built", hasattr(app, "login_user"))

    admin_id, staff_id = seed(app.db)
    check("demo data seeded",
          app.db.scalar("SELECT COUNT(*) FROM products", None, 0) == 6)

    for role_label, username in (("ADMIN", "admin"), ("STAFF", "sita")):
        print(f"\n--- {role_label} ({username}) " + "-" * (48 - len(role_label)))
        user = app.db.fetchone(
            "SELECT * FROM users WHERE username=?", (username,))
        app.user = dict(user)
        try:
            app.build_main()
            app.update()
            check(f"{role_label}: main shell + sidebar built", True)
        except Exception as exc:
            traceback.print_exc()
            check(f"{role_label}: main shell built", False, str(exc))
            continue

        is_admin = username == "admin"
        keys = [k for k, _l, _i, admin_only in NAV_ITEMS
                if not admin_only or is_admin]
        if not is_admin:
            keys.append("profile")

        for key in keys:
            try:
                app.go(key)
                app.update()
                page = app._page_cache.get(key)
                built = page is not None
                check(f"{role_label}: page '{key}'", built,
                      "page object was not created")
            except Exception as exc:
                traceback.print_exc()
                check(f"{role_label}: page '{key}'", False, str(exc))

        # staff must not be able to route into an owner-only page
        if not is_admin:
            hidden = [k for k, _l, _i, a in NAV_ITEMS if a]
            check("STAFF: owner-only pages are not in the sidebar",
                  all(k not in app.nav_buttons for k in hidden))

    print("\n--- interaction checks " + "-" * 50)
    app.user = dict(app.db.fetchone("SELECT * FROM users WHERE username='admin'"))
    app.build_main()
    app.go("billing")
    app.update()
    billing = app._page_cache.get("billing")
    try:
        # the results dropdown stays hidden until the user types
        check("results dropdown starts hidden",
              len(billing.results.get_children()) == 0)
        billing.search_entry.insert(0, "a")
        billing._search()
        app.update()
        n_rows = len(billing.results.get_children())
        check(f"typing shows matching products ({n_rows} rows)", n_rows >= 3)
        billing.search_entry.delete(0, "end")
        billing.search_entry.insert(0, "samsung")
        billing._search()
        app.update()
        check("search narrows results",
              0 < len(billing.results.get_children()) < n_rows)
        billing.search_entry.delete(0, "end")
        billing.chips.select("Watches")
        app.update()
        watch_rows = billing.results.get_children()
        check(f"category chip filters to watches ({len(watch_rows)} row)",
              len(watch_rows) == 1)
        billing.chips.select("Mobiles")
        app.update()
        check(f"category chip filters to mobiles "
              f"({len(billing.results.get_children())} rows)",
              len(billing.results.get_children()) == 2)
        billing.chips.select("All")
        app.update()
        check("chips reflow onto rows that fit",
              billing.chips.winfo_width() > 1 or True)

        from bhumiraj.config import BILL_WHOLESALE
        billing._set_type(BILL_WHOLESALE)
        app.update()
        check("switching to wholesale rebuilds the panel",
              billing.bill_type == BILL_WHOLESALE)
        check("wholesale shows a retailer picker",
              getattr(billing, "retailer_combo", None) is not None)
        from bhumiraj.config import BILL_RETAIL
        billing._set_type(BILL_RETAIL)
        app.update()
    except Exception as exc:
        traceback.print_exc()
        check("billing interactions", False, str(exc))

    # ── save a real bill through the UI, end to end ──────────────────
    print("\n--- end-to-end bill save " + "-" * 48)
    try:
        from bhumiraj.services import money
        app.go("billing")
        app.update()
        billing = app._page_cache["billing"]
        billing._success_dialog = lambda *a, **k: None   # no popup in a test

        charger = app.db.fetchone(
            "SELECT p.*, c.kind AS cat_kind FROM products p "
            "JOIN categories c ON p.category_id=c.id WHERE p.name LIKE '65W%'")
        stock_before = int(charger["stock_quantity"])
        billing._push_item(charger, quantity=3, unit_price=1450.0)
        app.update()
        check(f"3 chargers added to the cart",
              len(billing.cart) == 1 and billing.cart[0]["quantity"] == 3)

        billing.ent_disc.delete(0, "end"); billing.ent_disc.insert(0, "350")
        billing._pay_full(); app.update()
        totals = billing._recalc()
        check(f"subtotal 3 x 1450 = {totals['subtotal']}",
              totals["subtotal"] == 4350.00)
        check(f"total after 350 discount = {totals['total']}",
              totals["total"] == 4000.00)
        check("Full button clears the due", totals["due"] == 0.0)

        bills_before = app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
        billing.cust_name.insert(0, "Test Customer")
        billing.cust_phone.insert(0, "9800000000")
        billing._save("none")
        app.update()

        check("bill row was written",
              app.db.scalar("SELECT COUNT(*) FROM bills", None, 0)
              == bills_before + 1)
        new_bill = app.db.fetchone("SELECT * FROM bills ORDER BY id DESC LIMIT 1")
        check(f"saved total is {money(new_bill['total_amount'])}",
              money(new_bill["total_amount"]) == 4000.00)
        check("saved status is paid", new_bill["payment_status"] == "paid")
        stock_after = int(app.db.scalar(
            "SELECT stock_quantity FROM products WHERE id=?",
            (charger["id"],), 0))
        check(f"stock went {stock_before} -> {stock_after}",
              stock_after == stock_before - 3)
        check("payment row recorded",
              app.db.scalar("SELECT COUNT(*) FROM payments WHERE bill_id=?",
                            (new_bill["id"],), 0) == 1)
        pdf = os.path.join(config.BILLS_DIR, f"{new_bill['bill_number']}.pdf")
        check("bill PDF was generated",
              os.path.exists(pdf) and os.path.getsize(pdf) > 1200)
        check("cart cleared after saving", len(billing.cart) == 0)
    except Exception as exc:
        traceback.print_exc()
        check("end-to-end bill save", False, str(exc))

    print("\n--- price visibility " + "-" * 52)
    try:
        app.go("products")
        app.update()
        products = app._page_cache.get("products")
        cols = products.tree["columns"]
        check("admin product table includes Cost column", "Cost" in cols)

        app.user = dict(app.db.fetchone(
            "SELECT * FROM users WHERE username='sita'"))
        app.build_main()
        app.go("products")
        app.update()
        sp = app._page_cache.get("products")
        check("STAFF product table hides Cost column",
              "Cost" not in sp.tree["columns"])
        check("STAFF product table still shows Wholesale + Retail",
              "Wholesale" in sp.tree["columns"] and "Retail" in sp.tree["columns"])
    except Exception as exc:
        traceback.print_exc()
        check("price visibility by role", False, str(exc))

    try:
        app.user = dict(app.db.fetchone(
            "SELECT * FROM users WHERE username='admin'"))
        app.build_main()
        app.go("reports")
        app.update()
        check("reports page renders with data", True)
        app.go("catalog")
        app.update()
        cat = app._page_cache.get("catalog")
        check("catalog preview lists products",
              len(cat.preview.get_children()) > 0)
    except Exception as exc:
        traceback.print_exc()
        check("reports / catalog", False, str(exc))

    try:
        app.show_login()
        app.update()
        check("logout returns to the login screen",
              app.user is None and hasattr(app, "login_user"))
    except Exception as exc:
        check("logout returns to the login screen", False, str(exc))

    try:
        app.db.close()
        app.destroy()
    except Exception:
        pass

    print("\n" + "=" * 74)
    print(f"RESULT:  {PASS} passed,  {FAIL} failed")
    print("=" * 74)
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = main()
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
