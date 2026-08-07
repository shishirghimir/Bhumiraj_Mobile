"""Headless test suite for Bhumiraj — runs with no GUI.

Covers the things that must never be wrong in a shop:
  money rounding · bill totals · FIFO payment allocation · instalments ·
  stock movement · returns · deletes · password security · backup/restore ·
  and that every PDF actually builds.

Run:   python run_tests.py
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import traceback

# Point the app at a throwaway folder BEFORE anything imports config.
TMP = tempfile.mkdtemp(prefix="bhumiraj_test_")
os.environ["BHUMIRAJ_HOME"] = TMP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
except Exception:
    pass

from bhumiraj import config                                   # noqa: E402
from bhumiraj.database import DatabaseManager                 # noqa: E402
from bhumiraj.pdf import DocumentGenerator                    # noqa: E402
from bhumiraj.security import (hash_password, needs_upgrade,  # noqa: E402
                               password_strength, random_password,
                               staff_password_strength, verify_password)
from bhumiraj.services import (amount_in_words, authenticate, # noqa: E402
                               check_stock_available, compute_totals,
                               delete_product, installment_progress,
                               installment_schedule, log_stock, money,
                               normalise_phone, parse_amount, parse_int,
                               payment_status, plan_fifo_allocation,
                               record_bill_payment, record_retailer_payment,
                               retailer_outstanding, warranty_expiry,
                               warranty_state)
from bhumiraj.settings import BackupManager, SettingsManager   # noqa: E402

PASS = FAIL = 0
FAILURES = []


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}{(' — ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}{(' — ' + detail) if detail else ''}")


def eq(label, got, want, tol=0.0):
    ok = (abs(float(got) - float(want)) <= tol
          if isinstance(want, (int, float)) and not isinstance(want, bool)
          else got == want)
    check(label, ok, f"got {got!r}, expected {want!r}")


def head(title):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# ═══════════════════════════════════════════════════════════════════════
head("1. MONEY ROUNDING — the paisa must never drift")

eq("money(10.005) rounds half-up", money(10.005), 10.01)
eq("money(2.675) rounds half-up", money(2.675), 2.68)
eq("money(0.1+0.2) kills float dust", money(0.1 + 0.2), 0.30)
eq("money('') is zero", money(""), 0.0)
eq("money(None) is zero", money(None), 0.0)
eq("money('abc') is zero", money("abc"), 0.0)
eq("money(-5.555) rounds away from zero", money(-5.555), -5.56)
eq("money of huge value", money(99999999.999), 100000000.0)
eq("parse_amount('Rs 1,250.50')", parse_amount("Rs 1,250.50"), 1250.50)
eq("parse_amount('  ')", parse_amount("  "), 0.0)
eq("parse_amount('12.3.4') is safe", parse_amount("12.3.4"), 0.0)
eq("parse_int('7 pcs')", parse_int("7 pcs"), 7)
eq("parse_int('-3')", parse_int("-3"), -3)
eq("parse_int('abc', 5)", parse_int("abc", 5), 5)

# 1000 additions of 0.01 must land exactly on 10.00
acc = 0.0
for _ in range(1000):
    acc = money(acc + 0.01)
eq("1000 x 0.01 accumulates to exactly 10.00", acc, 10.00)

head("2. BILL TOTALS — subtotal, discount, paid, due, status")

t = compute_totals([{"quantity": 3, "unit_price": 1250.50}], 0, 0)
eq("3 x 1250.50 subtotal", t["subtotal"], 3751.50)
eq("no discount -> total = subtotal", t["total"], 3751.50)
eq("nothing paid -> due = total", t["due"], 3751.50)
eq("status unpaid", t["status"], "unpaid")

t = compute_totals([{"quantity": 2, "unit_price": 999.99},
                    {"quantity": 1, "unit_price": 0.02}], 100, 500)
eq("multi-line subtotal", t["subtotal"], 2000.00)
eq("discount applied", t["total"], 1900.00)
eq("partial paid", t["paid"], 500.00)
eq("due after partial", t["due"], 1400.00)
eq("status partial", t["status"], "partial")

t = compute_totals([{"quantity": 1, "unit_price": 500}], 600, 0)
eq("discount clamped to subtotal", t["discount"], 500.00)
eq("total floors at zero", t["total"], 0.00)
eq("zero total counts as paid", t["status"], "paid")

t = compute_totals([{"quantity": 1, "unit_price": 100}], -50, -20)
eq("negative discount ignored", t["discount"], 0.00)
eq("negative paid ignored", t["paid"], 0.00)

t = compute_totals([{"quantity": 1, "unit_price": 100}], 0, 5000)
eq("overpay clamped to total", t["paid"], 100.00)
eq("no negative due", t["due"], 0.00)
eq("status paid", t["status"], "paid")

t = compute_totals([], 0, 0)
eq("empty bill subtotal", t["subtotal"], 0.0)
eq("empty bill status", t["status"], "paid")

t = compute_totals([{"quantity": 1, "unit_price": 100.00}], 0, 99.999)
eq("paid within a paisa counts as paid", t["status"], "paid")

# The unit price is rounded to paisa FIRST, because that is what prints on the
# bill. 7 x 142.857 must therefore be 7 x 142.86 = 1000.02 — if it came to
# 1000.00 the customer adding up the printed line would disagree with the total.
t = compute_totals([{"quantity": 7, "unit_price": 142.857}], 0, 0)
eq("line total matches the printed unit price", t["subtotal"], 1000.02)
eq("printed unit price is what is multiplied", money(142.857), 142.86)

# discount of exactly the total leaves nothing due
t = compute_totals([{"quantity": 4, "unit_price": 250}], 1000, 0)
eq("full discount -> total 0", t["total"], 0.0)
eq("full discount -> due 0", t["due"], 0.0)

eq("payment_status boundary (paid)", payment_status(100, 100), "paid")
eq("payment_status boundary (partial)", payment_status(100, 99.99), "partial")
eq("payment_status boundary (unpaid)", payment_status(100, 0.001), "unpaid")

head("3. AMOUNT IN WORDS")

eq("zero", amount_in_words(0), "Zero Rupees Only")
eq("simple", amount_in_words(1), "One Rupees Only")
eq("with paisa", amount_in_words(1250.50),
   "One Thousand Two Hundred Fifty Rupees and Fifty Paisa Only")
eq("lakh", amount_in_words(125340),
   "One Lakh Twenty Five Thousand Three Hundred Forty Rupees Only")
eq("crore", amount_in_words(12345678),
   "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred "
   "Seventy Eight Rupees Only")
eq("teens", amount_in_words(19), "Nineteen Rupees Only")
eq("rounding carry", amount_in_words(9.999), "Ten Rupees Only")
check("negative handled", amount_in_words(-50).startswith("Minus"))

head("4. FIFO ALLOCATION — pure function")


def fake_bills(rows):
    return [{"id": i + 1, "bill_number": f"BW-{i + 1:04d}",
             "bill_date": f"2026-0{i + 1}-01",
             "total_amount": t, "paid_amount": p}
            for i, (t, p) in enumerate(rows)]


allocs, left = plan_fifo_allocation(fake_bills([(1000, 0), (2000, 0)]), 1000)
eq("exact settle of first bill: 1 allocation", len(allocs), 1)
eq("first bill fully applied", allocs[0]["applied"], 1000.00)
eq("first bill now clear", allocs[0]["after_due"], 0.00)
eq("first bill status paid", allocs[0]["status"], "paid")
eq("nothing left over", left, 0.00)

allocs, left = plan_fifo_allocation(fake_bills([(1000, 0), (2000, 0)]), 1500)
eq("spills into second bill", len(allocs), 2)
eq("second bill part-paid", allocs[1]["applied"], 500.00)
eq("second bill still owes", allocs[1]["after_due"], 1500.00)
eq("second bill partial", allocs[1]["status"], "partial")

allocs, left = plan_fifo_allocation(fake_bills([(1000, 0), (2000, 0)]), 5000)
eq("all bills cleared", len(allocs), 2)
eq("advance kept", left, 2000.00)
check("every bill ends at zero due",
      all(a["after_due"] == 0 for a in allocs))

allocs, left = plan_fifo_allocation(
    fake_bills([(1000, 1000), (500, 200), (300, 0)]), 600)
eq("already-paid bill skipped", allocs[0]["bill_number"], "BW-0002")
eq("partial bill topped up first", allocs[0]["applied"], 300.00)
eq("then next bill", allocs[1]["applied"], 300.00)
eq("nothing left", left, 0.00)

allocs, left = plan_fifo_allocation(fake_bills([(1000, 0)]), 0)
eq("zero payment allocates nothing", len(allocs), 0)
allocs, left = plan_fifo_allocation([], 500)
eq("no bills -> all advance", left, 500.00)

# awkward thirds must still sum exactly
allocs, left = plan_fifo_allocation(
    fake_bills([(333.33, 0), (333.33, 0), (333.34, 0)]), 1000)
total_applied = money(sum(a["applied"] for a in allocs))
eq("thirds sum exactly to the payment", total_applied, 1000.00)
eq("no drift left over", left, 0.00)

head("5. INSTALMENT SCHEDULE")

down, financed, rows = installment_schedule(10000, 2500, 6)
eq("down payment", down, 2500.00)
eq("financed amount", financed, 7500.00)
eq("six instalments", len(rows), 6)
eq("instalments sum to financed", money(sum(rows)), 7500.00)

down, financed, rows = installment_schedule(10000, 0, 3)
eq("awkward split sums exactly", money(sum(rows)), 10000.00)
down, financed, rows = installment_schedule(1000, 0, 7)
eq("1000 over 7 months sums exactly", money(sum(rows)), 1000.00)
check("last instalment absorbs the remainder", rows[-1] != rows[0]
      or money(sum(rows)) == 1000.00)

down, financed, rows = installment_schedule(5000, 9000, 6)
eq("down capped at total", down, 5000.00)
eq("nothing left to finance", financed, 0.00)
eq("no instalments needed", len(rows), 0)

down, financed, rows = installment_schedule(5000, 1000, 0)
eq("zero months -> no schedule", len(rows), 0)

head("6. SECURITY")

h = hash_password("Admin@123")
check("hash is PBKDF2 format", h.startswith("pbkdf2_sha256$200000$"))
check("correct password verifies", verify_password("Admin@123", h))
check("wrong password rejected", not verify_password("admin@123", h))
check("empty password rejected", not verify_password("", h))
check("two hashes of same password differ (salted)",
      hash_password("same") != hash_password("same"))
check("new hash needs no upgrade", not needs_upgrade(h))

import hashlib                                                # noqa: E402
legacy = hashlib.sha256(b"admin").hexdigest()
check("legacy sha256 still verifies", verify_password("admin", legacy))
check("legacy flagged for upgrade", needs_upgrade(legacy))
check("garbage hash rejected safely", not verify_password("x", "not-a-hash"))
check("empty stored hash rejected", not verify_password("x", ""))

check("weak password rejected", not password_strength("abc")[0])
check("no-digit password rejected", not password_strength("Abcdefgh")[0])
check("no-upper password rejected", not password_strength("abcdefg1")[0])
check("common password rejected", not password_strength("Password")[0])
check("strong password accepted", password_strength("Bhumiraj@2026")[0])
check("staff rule is 6+ with letter+digit",
      staff_password_strength("shop12")[0])
check("staff rule rejects 5 chars", not staff_password_strength("sho1")[0])
check("random password passes staff rule",
      staff_password_strength(random_password())[0])

eq("phone normalises for WhatsApp", normalise_phone("9808773134"),
   "9779808773134")
eq("phone already prefixed", normalise_phone("977-9808-773134"),
   "9779808773134")
eq("phone with leading zero", normalise_phone("09808773134"),
   "9779808773134")
eq("empty phone", normalise_phone(""), "")

head("7. WARRANTY DATES")

eq("12 month warranty", warranty_expiry("2026-08-04", 12), "2027-08-04")
eq("6 month warranty", warranty_expiry("2026-08-04", 6), "2027-02-04")
eq("month-end rollover", warranty_expiry("2026-01-31", 1), "2026-02-28")
eq("zero warranty", warranty_expiry("2026-08-04", 0), "")
state, _days = warranty_state("2020-01-01")
eq("old warranty expired", state, "Expired")
state, _days = warranty_state("2099-01-01")
eq("future warranty active", state, "Active")
eq("no expiry -> None", warranty_state("")[0], "None")

# ═══════════════════════════════════════════════════════════════════════
head("8. DATABASE — schema, seed, document numbers")

db = DatabaseManager(config.DB_PATH)
settings = SettingsManager()
docs = DocumentGenerator(settings, db)

tables = {r[0] for r in db.fetchall(
    "SELECT name FROM sqlite_master WHERE type='table'")}
for needed in ("users", "categories", "products", "mobile_units", "retailers",
               "customers", "bills", "bill_items", "payments",
               "imei_register", "imei_payments", "returns", "expenses",
               "stock_history", "counters", "login_audit", "admin_pin"):
    check(f"table '{needed}' exists", needed in tables)

eq("admin seeded", db.scalar("SELECT COUNT(*) FROM users", None, 0), 1)
eq("categories seeded",
   db.scalar("SELECT COUNT(*) FROM categories", None, 0),
   len(config.SEED_CATEGORIES))
check("admin must change password on first login",
      db.scalar("SELECT must_change_password FROM users WHERE username='admin'",
                None, 0) == 1)

n1 = db.next_bill_number("retail")
n2 = db.next_bill_number("retail")
n3 = db.next_bill_number("wholesale")
check("retail numbers increment", n1 != n2 and n1.startswith("BR-"))
check("wholesale uses its own series", n3.startswith("BW-"))
numbers = {db.next_bill_number("retail") for _ in range(200)}
eq("200 bill numbers are all unique", len(numbers), 200)

head("9. AUTHENTICATION")

user, err = authenticate(db, "admin", "Admin@123")
check("admin logs in with seeded password", user is not None and err is None)
user_bad, err_bad = authenticate(db, "admin", "wrong")
check("wrong password refused", user_bad is None and err_bad)
user_no, err_no = authenticate(db, "ghost", "x")
check("unknown user refused", user_no is None)
db.execute("INSERT INTO users (username, password_hash, role, full_name, "
           "is_active) VALUES ('offstaff', ?, 'staff', 'Off Staff', 0)",
           (hash_password("shop123"),))
u_off, e_off = authenticate(db, "offstaff", "shop123")
check("disabled account refused", u_off is None and "disabled" in e_off.lower())
check("login attempts are audited",
      db.scalar("SELECT COUNT(*) FROM login_audit", None, 0) >= 4)

# legacy hash upgrade on login
db.execute("INSERT INTO users (username, password_hash, role, full_name) "
           "VALUES ('oldstaff', ?, 'staff', 'Old Staff')", (legacy,))
u_old, _ = authenticate(db, "oldstaff", "admin")
check("legacy-hash user can log in", u_old is not None)
check("legacy hash upgraded to PBKDF2",
      not needs_upgrade(db.scalar(
          "SELECT password_hash FROM users WHERE username='oldstaff'",
          None, "")))

admin_id = db.scalar("SELECT id FROM users WHERE username='admin'", None, 1)

head("10. PRODUCTS, STOCK AND A REAL BILL")

mob_cat = db.scalar("SELECT id FROM categories WHERE name='Mobile Phones'",
                    None, 1)
acc_cat = db.scalar("SELECT id FROM categories WHERE name='Chargers'", None, 2)
watch_cat = db.scalar("SELECT id FROM categories WHERE name='Wrist Watches'",
                      None, 3)

cur = db.execute(
    "INSERT INTO products (name, category_id, sku, brand, model, cost_price, "
    " wholesale_price, sell_price, stock_quantity, min_stock_level, "
    " warranty_months, is_serialized, attrs) "
    "VALUES ('Galaxy A15', ?, 'MOB-SAM-0001', 'Samsung', 'SM-A155F', "
    " 22000, 25500, 27999, 0, 2, 12, 1, "
    " '{\"color\":\"Blue Black\",\"storage\":\"128GB\",\"ram\":\"6GB\"}')",
    (mob_cat,))
phone_id = cur.lastrowid

cur = db.execute(
    "INSERT INTO products (name, category_id, sku, brand, model, cost_price, "
    " wholesale_price, sell_price, stock_quantity, min_stock_level, attrs) "
    "VALUES ('65W Fast Charger', ?, 'CHR-SAM-0002', 'Samsung', 'EP-TA800', "
    " 850, 1050, 1450, 50, 5, '{\"connector\":\"Type-C\",\"wattage\":\"65W\"}')",
    (acc_cat,))
charger_id = cur.lastrowid

cur = db.execute(
    "INSERT INTO products (name, category_id, sku, brand, model, cost_price, "
    " wholesale_price, sell_price, stock_quantity, warranty_months, attrs) "
    "VALUES ('Classic Automatic', ?, 'WAT-TIT-0003', 'Titan', 'NH1825SL01', "
    " 4200, 5200, 6999, 8, 24, "
    " '{\"movement\":\"Automatic\",\"strap\":\"Leather\"}')",
    (watch_cat,))
watch_id = cur.lastrowid

eq("three products created",
   db.scalar("SELECT COUNT(*) FROM products", None, 0), 3)

# register three handsets
with db.transaction() as c:
    for imei in ("356938035643809", "356938035643810", "356938035643811"):
        c.execute(
            "INSERT INTO mobile_units (product_id, imei, color, storage, ram, "
            " condition, cost_price, sell_price, status) "
            "VALUES (?,?,'Blue Black','128GB','6GB','New',22000,27999,"
            " 'in_stock')", (phone_id, imei))
    c.execute("UPDATE products SET stock_quantity = stock_quantity + 3 "
              "WHERE id=?", (phone_id,))
eq("three handsets in stock",
   db.scalar("SELECT COUNT(*) FROM mobile_units WHERE status='in_stock'",
             None, 0), 3)

unit = db.fetchone("SELECT * FROM mobile_units WHERE status='in_stock' "
                   "ORDER BY id LIMIT 1")

# stock pre-flight
problems = check_stock_available(db, [
    {"product_id": charger_id, "quantity": 999}])
check("over-ordering is caught", bool(problems))
problems = check_stock_available(db, [
    {"product_id": charger_id, "quantity": 2},
    {"product_id": unit["product_id"], "quantity": 1,
     "mobile_unit_id": unit["id"]}])
check("valid order passes pre-flight", not problems)

# ── build a retail bill: 1 phone + 2 chargers, 500 discount, 20000 paid
items = [
    {"quantity": 1, "unit_price": 27999.00},
    {"quantity": 2, "unit_price": 1450.00},
]
totals = compute_totals(items, 500, 20000)
eq("bill subtotal", totals["subtotal"], 30899.00)
eq("bill total after discount", totals["total"], 30399.00)
eq("bill due", totals["due"], 10399.00)
eq("bill status", totals["status"], "partial")

bill_no = db.next_bill_number("retail")
with db.transaction() as c:
    c.execute(
        "INSERT INTO bills (bill_number, bill_type, customer_name, "
        " customer_phone, staff_id, bill_date, subtotal, discount_amount, "
        " total_amount, paid_amount, due_amount, payment_status, "
        " payment_method, plan_type) "
        "VALUES (?,'retail','Ram Bahadur','9841000001',?, '2026-08-04 10:00:00',"
        " ?,?,?,?,?,?, 'Cash','installment')",
        (bill_no, admin_id, totals["subtotal"], totals["discount"],
         totals["total"], totals["paid"], totals["due"], totals["status"]))
    bill_id = c.lastrowid
    c.execute(
        "INSERT INTO bill_items (bill_id, product_id, mobile_unit_id, "
        " product_name, product_brand, product_model, product_sku, imei, "
        " attrs_snapshot, quantity, unit_price, total_price, cogs_price, "
        " warranty_months) VALUES (?,?,?,'Galaxy A15','Samsung','SM-A155F',"
        " 'MOB-SAM-0001',?,'{\"color\":\"Blue Black\",\"storage\":\"128GB\"}',"
        " 1, 27999, 27999, 22000, 12)",
        (bill_id, phone_id, unit["id"], unit["imei"]))
    c.execute(
        "INSERT INTO bill_items (bill_id, product_id, product_name, "
        " product_brand, product_model, product_sku, quantity, unit_price, "
        " total_price, cogs_price) VALUES (?,?,'65W Fast Charger','Samsung',"
        " 'EP-TA800','CHR-SAM-0002',2,1450,2900,850)",
        (bill_id, charger_id))
    c.execute("UPDATE mobile_units SET status='sold', bill_id=?, "
              "sold_date='2026-08-04' WHERE id=?", (bill_id, unit["id"]))
    c.execute("UPDATE products SET stock_quantity=stock_quantity-1 WHERE id=?",
              (phone_id,))
    c.execute("UPDATE products SET stock_quantity=stock_quantity-2 WHERE id=?",
              (charger_id,))
    log_stock(c, charger_id, "sale", -2, 48, bill_no, admin_id)
    c.execute(
        "INSERT INTO imei_register (imei, product_id, mobile_unit_id, "
        " product_name, brand, model, color, storage, bill_id, bill_number, "
        " customer_name, customer_phone, sold_date, warranty_months, "
        " warranty_expiry, plan_type, total_amount, down_payment, "
        " installment_amount, installment_months, status) "
        "VALUES (?,?,?,'Galaxy A15','Samsung','SM-A155F','Blue Black','128GB',"
        " ?,?,'Ram Bahadur','9841000001','2026-08-04',12,?,'installment',"
        " 27999, 8000, 3333.17, 6, 'active')",
        (unit["imei"], phone_id, unit["id"], bill_id, bill_no,
         warranty_expiry("2026-08-04", 12)))
    reg_id = c.lastrowid

eq("charger stock deducted",
   db.scalar("SELECT stock_quantity FROM products WHERE id=?",
             (charger_id,), 0), 48)
eq("phone stock deducted",
   db.scalar("SELECT stock_quantity FROM products WHERE id=?",
             (phone_id,), 0), 2)
eq("handset marked sold",
   db.scalar("SELECT status FROM mobile_units WHERE id=?", (unit["id"],), ""),
   "sold")
eq("stock movement logged",
   db.scalar("SELECT COUNT(*) FROM stock_history", None, 0), 1)
eq("bill items stored",
   db.scalar("SELECT COUNT(*) FROM bill_items WHERE bill_id=?", (bill_id,), 0),
   2)
eq("warranty expiry recorded",
   db.scalar("SELECT warranty_expiry FROM imei_register WHERE id=?",
             (reg_id,), ""), "2027-08-04")

# selling the same handset again must be refused
problems = check_stock_available(db, [
    {"product_id": phone_id, "quantity": 1, "mobile_unit_id": unit["id"]}])
check("already-sold handset cannot be sold twice", bool(problems))

head("11. COLLECTING A RETAIL DUE")

receipt, new_paid, new_due, status = record_bill_payment(
    db, bill_id, 5000, "eSewa", "2026-08-10", "TXN-99", "part payment",
    admin_id)
eq("paid rises", new_paid, 25000.00)
eq("due falls", new_due, 5399.00)
eq("still partial", status, "partial")
check("receipt number issued", receipt.startswith("RC-"))

try:
    record_bill_payment(db, bill_id, 999999, "Cash", "2026-08-11", "", "",
                        admin_id)
    check("overpaying a bill is refused", False)
except ValueError:
    check("overpaying a bill is refused", True)

try:
    record_bill_payment(db, bill_id, 0, "Cash", "2026-08-11", "", "", admin_id)
    check("zero payment is refused", False)
except ValueError:
    check("zero payment is refused", True)

receipt2, new_paid2, new_due2, status2 = record_bill_payment(
    db, bill_id, 5399, "Cash", "2026-08-12", "", "final", admin_id)
eq("bill fully settled", new_due2, 0.00)
eq("status now paid", status2, "paid")
eq("db agrees the bill is paid",
   db.scalar("SELECT payment_status FROM bills WHERE id=?", (bill_id,), ""),
   "paid")

head("12. WHOLESALE — retailer, invoices, FIFO settlement")

cur = db.execute(
    "INSERT INTO retailers (name, shop_name, phone, city, opening_balance) "
    "VALUES ('Hari Sharma','Hari Mobile Center','9851000002','Bhaktapur',2500)")
ret_id = cur.lastrowid
eq("opening balance is the starting due",
   retailer_outstanding(db, ret_id), 2500.00)

ws_bills = []
for idx, amount in enumerate(((10000, "2026-05-01"), (7500, "2026-06-01"),
                              (12500, "2026-07-01")), start=1):
    value, date = amount
    number = db.next_bill_number("wholesale")
    c = db.execute(
        "INSERT INTO bills (bill_number, bill_type, retailer_id, "
        " customer_name, staff_id, bill_date, subtotal, total_amount, "
        " paid_amount, due_amount, payment_status, payment_method) "
        "VALUES (?,'wholesale',?, 'Hari Sharma', ?, ?, ?, ?, 0, ?, 'unpaid', "
        " 'Credit')",
        (number, ret_id, admin_id, date + " 09:00:00", value, value, value))
    ws_bills.append((c.lastrowid, number, value))

eq("outstanding = opening + three invoices",
   retailer_outstanding(db, ret_id), 32500.00)

# Pay 15,000 — should clear invoice 1 (10,000) and part-pay invoice 2
receipt, allocs, leftover = record_retailer_payment(
    db, ret_id, 15000, "Bank Transfer", "2026-07-15", "CHQ-4411", "",
    admin_id)
eq("two invoices touched", len(allocs), 2)
eq("oldest invoice first", allocs[0]["bill_number"], ws_bills[0][1])
eq("oldest invoice cleared", allocs[0]["after_due"], 0.00)
eq("second invoice part-paid", allocs[1]["applied"], 5000.00)
eq("second invoice still owes", allocs[1]["after_due"], 2500.00)
eq("no advance yet", leftover, 0.00)
eq("outstanding drops correctly", retailer_outstanding(db, ret_id), 17500.00)
eq("invoice 1 marked paid in db",
   db.scalar("SELECT payment_status FROM bills WHERE id=?",
             (ws_bills[0][0],), ""), "paid")
eq("invoice 2 marked partial in db",
   db.scalar("SELECT payment_status FROM bills WHERE id=?",
             (ws_bills[1][0],), ""), "partial")
eq("payment rows written per bill",
   db.scalar("SELECT COUNT(*) FROM payments WHERE receipt_number=?",
             (receipt,), 0), 2)

# Overpay: 20,000 against 15,000 of remaining invoice due
receipt_b, allocs_b, leftover_b = record_retailer_payment(
    db, ret_id, 20000, "Cash", "2026-07-20", "", "", admin_id)
eq("remaining invoices cleared", len(allocs_b), 2)
eq("advance retained", leftover_b, 5000.00)
check("all invoices now paid",
      db.scalar("SELECT COUNT(*) FROM bills WHERE retailer_id=? "
                "AND payment_status != 'paid'", (ret_id,), 0) == 0)
eq("opening balance minus advance is what remains",
   retailer_outstanding(db, ret_id), -2500.00)

try:
    record_retailer_payment(db, ret_id, 0, "Cash", "2026-07-21", "", "",
                            admin_id)
    check("zero retailer payment refused", False)
except ValueError:
    check("zero retailer payment refused", True)

# the money must balance: sum of payments == sum applied + advances
paid_sum = money(db.scalar(
    "SELECT COALESCE(SUM(amount),0) FROM payments WHERE retailer_id=?",
    (ret_id,), 0))
eq("every rupee is accounted for", paid_sum, 35000.00)

head("13. INSTALMENTS ON A HANDSET")

total, paid, due, status = installment_progress(db, reg_id)
eq("instalment total", total, 27999.00)
eq("down payment counted", paid, 8000.00)
eq("balance owed", due, 19999.00)
eq("status partial", status, "partial")

for amount in (3333.17, 3333.17, 3333.17):
    rc = db.next_installment_receipt()
    db.execute(
        "INSERT INTO imei_payments (register_id, receipt_number, "
        " payment_date, amount, payment_method, staff_id) "
        "VALUES (?,?,?,?,'Cash',?)",
        (reg_id, rc, "2026-09-04", amount, admin_id))
total, paid, due, status = installment_progress(db, reg_id)
eq("three instalments recorded", paid, 17999.51)
eq("balance after three", due, 9999.49)

db.execute("INSERT INTO imei_payments (register_id, receipt_number, "
           "payment_date, amount, payment_method, staff_id) "
           "VALUES (?,?,?,?,'Cash',?)",
           (reg_id, db.next_installment_receipt(), "2026-12-04", 9999.49,
            admin_id))
total, paid, due, status = installment_progress(db, reg_id)
eq("handset fully paid off", due, 0.00)
eq("status paid", status, "paid")
last_pay_id = db.scalar("SELECT MAX(id) FROM imei_payments", None, 0)

head("14. RETURNS")

before = db.scalar("SELECT stock_quantity FROM products WHERE id=?",
                   (charger_id,), 0)
with db.transaction() as c:
    c.execute(
        "INSERT INTO returns (bill_id, bill_number, product_id, product_name, "
        " quantity, refund_amount, restocked, reason, staff_id, return_date) "
        "VALUES (?,?,?,'65W Fast Charger',1,1450,1,'Defective',?, "
        " '2026-08-15 12:00:00')", (bill_id, bill_no, charger_id, admin_id))
    c.execute("UPDATE products SET stock_quantity=stock_quantity+1 WHERE id=?",
              (charger_id,))
    c.execute("UPDATE bills SET total_amount=total_amount-1450, "
              " paid_amount=MIN(paid_amount, total_amount-1450) WHERE id=?",
              (bill_id,))
after = db.scalar("SELECT stock_quantity FROM products WHERE id=?",
                  (charger_id,), 0)
eq("returned item is back in stock", after, before + 1)
eq("bill total reduced by the refund",
   money(db.scalar("SELECT total_amount FROM bills WHERE id=?", (bill_id,), 0)),
   28949.00)
eq("paid never exceeds the reduced total",
   money(db.scalar("SELECT paid_amount FROM bills WHERE id=?", (bill_id,), 0)),
   28949.00)

head("15. PDF GENERATION — every document must build")

pdf_dir = os.path.join(TMP, "pdf_out")
os.makedirs(pdf_dir, exist_ok=True)


def build(label, fn, name):
    path = os.path.join(pdf_dir, name)
    try:
        fn(path)
        size = os.path.getsize(path)
        check(f"{label} builds ({size:,} bytes)", size > 1200)
    except Exception as exc:
        traceback.print_exc()
        check(f"{label} builds", False, str(exc))


build("retail bill PDF", lambda p: docs.generate_bill(bill_id, p), "bill.pdf")
build("wholesale invoice PDF",
      lambda p: docs.generate_bill(ws_bills[2][0], p), "ws_bill.pdf")
build("payment receipt PDF (FIFO split)",
      lambda p: docs.generate_receipt(receipt, p), "receipt.pdf")
build("retail receipt PDF",
      lambda p: docs.generate_receipt(receipt2, p), "receipt2.pdf")
build("instalment receipt PDF",
      lambda p: docs.generate_installment_receipt(last_pay_id, p), "emi.pdf")
build("statement of account PDF",
      lambda p: docs.generate_statement(ret_id, "2026-01-01", "2026-12-31", p),
      "statement.pdf")
build("catalog PDF (retail prices)",
      lambda p: docs.generate_catalog(p, None, "retail", False, False),
      "catalog.pdf")
build("catalog PDF (both prices + images)",
      lambda p: docs.generate_catalog(p, None, "both", True, False),
      "catalog2.pdf")
build("catalog PDF (no prices)",
      lambda p: docs.generate_catalog(p, None, "none", False, True),
      "catalog3.pdf")

# a bill with a very long product name must not overflow the page
db.execute(
    "INSERT INTO bill_items (bill_id, product_name, product_brand, "
    " product_model, product_sku, quantity, unit_price, total_price) "
    "VALUES (?,?,?,?,?,1,10,10)",
    (bill_id, "Extra Long Product Name " * 6, "SomeVeryLongBrandName",
     "MODEL-NUMBER-THAT-IS-VERY-LONG-INDEED-2026", "SKU-LONG-0001"))
build("bill PDF with very long text wraps",
      lambda p: docs.generate_bill(bill_id, p), "bill_long.pdf")

head("15b. NO TEXT OVERLAP — long values must wrap, never collide")

# Regression guard: a long customer name / handset name used to run out of its
# info card and print on top of the card next to it.
db.execute("UPDATE bills SET customer_name=?, customer_phone='9841000001' "
           "WHERE id=?",
           ("Ram Bahadur Shrestha Chaudhary Tamang Magar", bill_id))
db.execute("UPDATE retailers SET name=?, shop_name=?, address=? WHERE id=?",
           ("Hari Prasad Sharma Adhikari",
            "Hari Mobile Center & Electronics Emporium Pvt. Ltd.",
            "Suryabinayak Municipality Ward No 7, Near Big Mart", ret_id))
db.execute("UPDATE imei_register SET product_name=?, brand=?, model=? "
           "WHERE id=?", ("Galaxy A15 5G Ultra Max Edition",
                          "Samsung Electronics", "SM-A155F/DSN", reg_id))

long_docs = {
    "long_bill.pdf": lambda p: docs.generate_bill(bill_id, p),
    "long_receipt.pdf": lambda p: docs.generate_receipt(receipt, p),
    "long_emi.pdf": lambda p: docs.generate_installment_receipt(last_pay_id, p),
    "long_statement.pdf": lambda p: docs.generate_statement(
        ret_id, "2026-01-01", "2026-12-31", p),
}
for fname, fn in long_docs.items():
    build(f"{fname} builds with long text", fn, fname)

try:
    import fitz                                               # noqa: E402

    PAGE_WIDTH = 595.28
    RIGHT_EDGE = PAGE_WIDTH - 14 * 2.834645 + 1.0   # page width - margin

    for fname in long_docs:
        path = os.path.join(pdf_dir, fname)
        doc = fitz.open(path)
        overflow = []
        overlaps = []
        for page in doc:
            spans = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span["text"].strip()
                        if not text:
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        if x1 > RIGHT_EDGE or x0 < 0:
                            overflow.append(text)
                        spans.append((x0, y0, x1, y1, text))
            # any two spans sharing a line that horizontally intersect
            for i, a in enumerate(spans):
                for b in spans[i + 1:]:
                    same_line = abs(a[1] - b[1]) < 2.0 and abs(a[3] - b[3]) < 2.0
                    if not same_line:
                        continue
                    if a[0] < b[2] - 0.6 and b[0] < a[2] - 0.6:
                        overlaps.append(f"{a[4]!r} / {b[4]!r}")
        doc.close()
        check(f"{fname}: nothing runs off the page",
              not overflow, "; ".join(overflow[:3]))
        check(f"{fname}: no two texts overlap",
              not overlaps, "; ".join(overlaps[:3]))
except ImportError:
    print("  [skip] PyMuPDF not installed — geometric overlap check skipped")

head("16. HARD DELETE — product goes, bill history survives")

items_before = db.scalar(
    "SELECT COUNT(*) FROM bill_items WHERE product_id=?", (charger_id,), 0)
check("charger is on a bill before delete", items_before > 0)
delete_product(db, charger_id, admin_id)
eq("product row is gone",
   db.scalar("SELECT COUNT(*) FROM products WHERE id=?", (charger_id,), 0), 0)
eq("bill line survives the delete",
   db.scalar("SELECT COUNT(*) FROM bill_items WHERE bill_id=? "
             "AND product_name='65W Fast Charger'", (bill_id,), 0), 1)
eq("bill line name snapshot intact",
   db.scalar("SELECT product_name FROM bill_items WHERE bill_id=? "
             "AND product_sku='CHR-SAM-0002' LIMIT 1", (bill_id,), ""),
   "65W Fast Charger")
build("bill PDF still prints after the product was deleted",
      lambda p: docs.generate_bill(bill_id, p), "bill_after_delete.pdf")

delete_product(db, phone_id, admin_id)
eq("handsets of a deleted phone are removed too",
   db.scalar("SELECT COUNT(*) FROM mobile_units WHERE product_id=?",
             (phone_id,), 0), 0)

head("17. BACKUP — daily schedule, retention, export, import")

backup_dir = os.path.join(TMP, "gdrive")
settings.set("backup_folder", backup_dir)
settings.set("backup_retention_days", 3)
settings.set("auto_backup", True)
settings.set("last_backup", "")
bm = BackupManager(db, settings)

settings.set("backup_time", "23:55")
eq("scheduled time parsed", bm.scheduled_time(), (23, 55))
settings.set("backup_time", "9:5")
eq("loose time still parsed", bm.scheduled_time(), (9, 5))
settings.set("backup_time", "nonsense")
eq("bad time falls back to the default", bm.scheduled_time(), (23, 55))
settings.set("backup_time", "23:55")

from datetime import datetime as _dt                          # noqa: E402
before = _dt(2026, 8, 4, 23, 50)      # 5 minutes before tonight's run
after = _dt(2026, 8, 4, 23, 56)       # just after it
eq("last slot before 23:55 is yesterday's run",
   bm.last_slot(before), _dt(2026, 8, 3, 23, 55))
eq("last slot after 23:55 is tonight's run",
   bm.last_slot(after), _dt(2026, 8, 4, 23, 55))
eq("next slot before 23:55 is tonight",
   bm.next_slot(before), _dt(2026, 8, 4, 23, 55))
eq("next slot after 23:55 is tomorrow",
   bm.next_slot(after), _dt(2026, 8, 5, 23, 55))

settings.set("last_backup", "2026-08-04 23:55:10")
check("not due again the same night", not bm.due(_dt(2026, 8, 5, 9, 0)))
check("due again the next night", bm.due(_dt(2026, 8, 5, 23, 56)))
settings.set("last_backup", "2026-08-01 23:55:00")
check("a missed night is caught up on next open",
      bm.due(_dt(2026, 8, 4, 10, 0)))
settings.set("auto_backup", False)
check("switching auto backup off stops it", not bm.due(_dt(2026, 8, 9, 23, 59)))
settings.set("auto_backup", True)
settings.set("last_backup", "")

check("a backup is due when none was ever taken", bm.due())
ok, msg, path = bm.run()
check("backup runs", ok, msg)
check("backup file exists", path and os.path.exists(path))
check("backup landed in the chosen folder",
      path and os.path.dirname(path) == backup_dir)
check("backup is not due again immediately", not bm.due())

# a backup file older than the window is pruned; a fresh one is kept
old_name = "bhumiraj_backup_2020-01-01_010101.db"
shutil.copy2(path, os.path.join(backup_dir, old_name))
kept_before = len(bm.list_backups())
removed = bm.prune()
eq("one stale backup removed", removed, 1)
check("fresh backup kept", len(bm.list_backups()) == kept_before - 1)
check("stale file really gone",
      not os.path.exists(os.path.join(backup_dir, old_name)))

# unrelated files in that folder must never be touched
other = os.path.join(backup_dir, "my_family_photos.db")
with open(other, "w") as fh:
    fh.write("not ours")
os.utime(other, (0, 0))
bm.prune()
check("unrelated files in the Drive folder are left alone",
      os.path.exists(other))

export_path = os.path.join(TMP, "exported")
saved = bm.export_to(export_path)
check("export adds the .db extension", saved.endswith(".db"))
check("exported file exists", os.path.exists(saved))

bills_before = db.scalar("SELECT COUNT(*) FROM bills", None, 0)
db.execute("INSERT INTO expenses (expense_date, category, description, amount) "
           "VALUES ('2026-08-04','Rent','Shop rent August', 25000)")
eq("expense added after the export",
   db.scalar("SELECT COUNT(*) FROM expenses", None, 0), 1)

safety = bm.import_from(saved)
eq("import restored the earlier snapshot",
   db.scalar("SELECT COUNT(*) FROM expenses", None, 0), 0)
eq("bills survived the import",
   db.scalar("SELECT COUNT(*) FROM bills", None, 0), bills_before)
check("a safety copy of the replaced db was kept",
      safety and os.path.exists(safety))

bad = os.path.join(TMP, "not_a_database.db")
with open(bad, "w") as fh:
    fh.write("this is definitely not sqlite")
try:
    bm.import_from(bad)
    check("importing a junk file is refused", False)
except Exception:
    check("importing a junk file is refused", True)
check("database still usable after a refused import",
      db.scalar("SELECT COUNT(*) FROM bills", None, 0) == bills_before)

empty = os.path.join(TMP, "empty_schema.db")
import sqlite3                                                # noqa: E402
con = sqlite3.connect(empty)
con.execute("CREATE TABLE unrelated_stuff (id INTEGER)")
con.commit()
con.close()
try:
    bm.import_from(empty)
    check("importing a non-Bhumiraj database is refused", False)
except ValueError:
    check("importing a non-Bhumiraj database is refused", True)

head("18. EDGE CASES")

t = compute_totals([{"quantity": 0, "unit_price": 500}], 0, 0)
eq("zero-quantity line contributes nothing", t["subtotal"], 0.0)
t = compute_totals([{"quantity": 1000000, "unit_price": 99999.99}], 0, 0)
check("very large bill computes", t["subtotal"] > 0)
t = compute_totals([{"quantity": 1, "unit_price": "not a number"}], 0, 0)
eq("garbage price treated as zero", t["subtotal"], 0.0)

alloc, left = plan_fifo_allocation(fake_bills([(0.01, 0)]), 0.01)
eq("one-paisa bill settles exactly", alloc[0]["after_due"], 0.00)

db.execute("INSERT INTO retailers (name, phone) VALUES ('Empty Retailer','1')")
empty_ret = db.scalar("SELECT id FROM retailers WHERE name='Empty Retailer'",
                      None, 0)
eq("retailer with no bills owes nothing",
   retailer_outstanding(db, empty_ret), 0.00)
_r, allocs_e, left_e = record_retailer_payment(
    db, empty_ret, 1000, "Cash", "2026-08-04", "", "", admin_id)
eq("payment with no bills becomes advance", left_e, 1000.00)
eq("advance shows as negative balance",
   retailer_outstanding(db, empty_ret), -1000.00)

check("concurrent-safe numbering under load",
      len({db.next_bill_number("wholesale") for _ in range(50)}) == 50)

db.close()

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 74}")
print(f"RESULT:  {PASS} passed,  {FAIL} failed")
print("=" * 74)
if FAILURES:
    print("\nFailures:")
    for f in FAILURES:
        print(f"  - {f}")
try:
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass
sys.exit(1 if FAIL else 0)
