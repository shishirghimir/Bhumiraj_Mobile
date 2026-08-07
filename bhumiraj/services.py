"""Business rules: money math, FIFO payment allocation, stock movements, auth.

Every rupee amount in the app goes through `money()` so rounding is identical
everywhere — the UI, the PDF and the reports can never disagree by a paisa.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from .config import (BILL_RETAIL, BILL_WHOLESALE, PLAN_FULL, PLAN_INSTALLMENT,
                     COUNTRY_CODE, ROLE_ADMIN)
from .security import verify_password, needs_upgrade, hash_password

# Anything below this is treated as zero — kills float dust like 1e-13.
EPS = 0.005


# ─── Money ─────────────────────────────────────────────────────────────────
def money(value) -> float:
    """Normalise any numeric-ish input to a 2-decimal rupee amount."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):   # NaN / inf guard
        return 0.0
    # round-half-up: SQLite/Python bankers-rounding surprises shopkeepers
    cents = int(v * 100 + (0.5 if v >= 0 else -0.5))
    return cents / 100.0


def parse_amount(text, default=0.0) -> float:
    """Read a rupee amount typed by a human: '1,250.50', 'Rs 900', '' → float."""
    if text is None:
        return money(default)
    if isinstance(text, (int, float)):
        return money(text)
    cleaned = re.sub(r"[^0-9.\-]", "", str(text))
    if cleaned in ("", "-", ".", "-."):
        return money(default)
    try:
        return money(float(cleaned))
    except ValueError:
        return money(default)


def parse_int(text, default=0) -> int:
    try:
        cleaned = re.sub(r"[^0-9\-]", "", str(text))
        return int(cleaned) if cleaned not in ("", "-") else int(default)
    except (TypeError, ValueError):
        return int(default)


def fmt(amount, currency="Rs.") -> str:
    return f"{currency} {money(amount):,.2f}"


def is_zero(v) -> bool:
    return abs(money(v)) < EPS


# ─── Bill totals ───────────────────────────────────────────────────────────
def line_total(quantity, unit_price) -> float:
    return money(parse_int(quantity, 0) * money(unit_price))


def compute_totals(items, discount=0.0, paid=0.0):
    """The single source of truth for bill arithmetic.

    items: iterable of dicts with 'quantity' and 'unit_price'.
    Returns dict(subtotal, discount, total, paid, due, status).

    Rules — identical to IOS Nepal so the shop's numbers stay familiar:
      subtotal = Σ(qty × unit_price)
      discount is clamped to [0, subtotal]
      total    = subtotal − discount
      paid     is clamped to [0, total]   (no overpay on a bill)
      due      = total − paid
      status   = paid / partial / unpaid
    """
    subtotal = money(sum(line_total(i.get("quantity", 0), i.get("unit_price", 0))
                         for i in items))
    disc = money(discount)
    if disc < 0:
        disc = 0.0
    if disc > subtotal:
        disc = subtotal
    total = money(subtotal - disc)

    p = money(paid)
    if p < 0:
        p = 0.0
    if p > total:
        p = total
    due = money(total - p)
    if abs(due) < EPS:
        due = 0.0

    return {
        "subtotal": subtotal,
        "discount": disc,
        "total": total,
        "paid": p,
        "due": due,
        "status": payment_status(total, p),
    }


def payment_status(total, paid) -> str:
    total, paid = money(total), money(paid)
    if paid >= total - EPS:
        return "paid"
    if paid <= EPS:
        return "unpaid"
    return "partial"


def discount_percent(subtotal, discount) -> float:
    subtotal = money(subtotal)
    if subtotal <= 0:
        return 0.0
    return round(money(discount) / subtotal * 100, 2)


def apply_percent_discount(subtotal, percent) -> float:
    pct = max(0.0, min(float(percent or 0), 100.0))
    return money(money(subtotal) * pct / 100.0)


# ─── Amount in words (Nepali/Indian numbering) ─────────────────────────────
_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety"]


def _two(n):
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + (" " + _ONES[o] if o else "")


def _three(n):
    h, r = divmod(n, 100)
    out = []
    if h:
        out.append(_ONES[h] + " Hundred")
    if r:
        out.append(_two(r))
    return " ".join(out)


def amount_in_words(amount, currency="Rupees", subunit="Paisa") -> str:
    """1,25,340.50 → 'One Lakh Twenty Five Thousand Three Hundred Forty Rupees and Fifty Paisa Only'"""
    amount = money(amount)
    neg = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paisa = int(round((amount - rupees) * 100))
    if paisa == 100:          # rounding carried over
        rupees += 1
        paisa = 0

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore, rem = divmod(rupees, 10_000_000)
        lakh, rem = divmod(rem, 100_000)
        thousand, rem = divmod(rem, 1_000)
        if crore:
            parts.append(_three(crore) + " Crore" if crore < 1000
                         else _two(crore // 100) + " Crore")
        if lakh:
            parts.append(_two(lakh) + " Lakh")
        if thousand:
            parts.append(_three(thousand) + " Thousand")
        if rem:
            parts.append(_three(rem))
        words = " ".join(p for p in parts if p)

    out = f"{words} {currency}"
    if paisa:
        out += f" and {_two(paisa)} {subunit}"
    out += " Only"
    return ("Minus " + out) if neg else out


# ─── FIFO payment allocation ───────────────────────────────────────────────
def plan_fifo_allocation(bills, amount):
    """Work out how a lump sum settles a retailer's bills, oldest first.

    bills: rows (or dicts) with id, bill_number, total_amount, paid_amount,
           bill_date — already ordered oldest → newest by the caller.
    Returns (allocations, leftover) where each allocation is:
        {bill_id, bill_number, before_due, applied, after_due, status}

    Pure function — no DB writes — so it is trivially testable and the UI can
    preview the split before the user confirms.
    """
    remaining = money(amount)
    if remaining <= EPS:
        return [], 0.0

    allocations = []
    for b in bills:
        total = money(b["total_amount"])
        paid = money(b["paid_amount"])
        due = money(total - paid)
        if due <= EPS:
            continue
        if remaining <= EPS:
            break
        applied = money(min(remaining, due))
        new_paid = money(paid + applied)
        after = money(total - new_paid)
        if abs(after) < EPS:
            after = 0.0
        allocations.append({
            "bill_id": b["id"],
            "bill_number": b["bill_number"],
            "bill_date": (b["bill_date"] if "bill_date" in b.keys()
                          else "") if hasattr(b, "keys") else b.get("bill_date", ""),
            "before_due": due,
            "applied": applied,
            "new_paid": new_paid,
            "after_due": after,
            "status": payment_status(total, new_paid),
        })
        remaining = money(remaining - applied)

    return allocations, money(max(remaining, 0.0))


def retailer_outstanding(db, retailer_id) -> float:
    """Opening balance + unpaid bill dues − unallocated advances."""
    opening = money(db.scalar(
        "SELECT opening_balance FROM retailers WHERE id=?", (retailer_id,), 0))
    bill_due = money(db.scalar(
        "SELECT COALESCE(SUM(total_amount - paid_amount), 0) FROM bills "
        "WHERE retailer_id=? AND payment_status != 'paid'", (retailer_id,), 0))
    advances = money(db.scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM payments "
        "WHERE retailer_id=? AND bill_id IS NULL", (retailer_id,), 0))
    return money(opening + bill_due - advances)


def customer_outstanding(db, phone) -> float:
    if not phone:
        return 0.0
    return money(db.scalar(
        "SELECT COALESCE(SUM(total_amount - paid_amount), 0) FROM bills "
        "WHERE customer_phone=? AND bill_type='retail' AND payment_status!='paid'",
        (phone,), 0))


def record_retailer_payment(db, retailer_id, amount, method, date_str,
                            reference="", notes="", staff_id=None):
    """Apply a payment FIFO across the retailer's open bills, atomically.

    Returns (receipt_number, allocations, leftover_advance).
    """
    amount = money(amount)
    if amount <= EPS:
        raise ValueError("Payment amount must be greater than zero.")

    open_bills = db.fetchall(
        "SELECT id, bill_number, bill_date, total_amount, paid_amount "
        "FROM bills WHERE retailer_id=? AND payment_status != 'paid' "
        "ORDER BY DATE(bill_date) ASC, id ASC", (retailer_id,))
    allocations, leftover = plan_fifo_allocation(open_bills, amount)

    receipt = db.next_receipt_number()
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")

    with db.transaction() as cur:
        for a in allocations:
            cur.execute(
                "UPDATE bills SET paid_amount=?, due_amount=?, payment_status=? "
                "WHERE id=?",
                (a["new_paid"], a["after_due"], a["status"], a["bill_id"]))
            cur.execute(
                "INSERT INTO payments (receipt_number, bill_id, retailer_id, "
                " amount, payment_method, payment_date, reference, notes, staff_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (receipt, a["bill_id"], retailer_id, a["applied"], method,
                 date_str, reference, notes, staff_id))
        if leftover > EPS:
            cur.execute(
                "INSERT INTO payments (receipt_number, bill_id, retailer_id, "
                " amount, payment_method, payment_date, reference, notes, staff_id) "
                "VALUES (?,NULL,?,?,?,?,?,?,?)",
                (receipt, retailer_id, leftover, method, date_str, reference,
                 (notes + " [advance]").strip(), staff_id))
    return receipt, allocations, leftover


def record_bill_payment(db, bill_id, amount, method, date_str,
                        reference="", notes="", staff_id=None):
    """Settle (part of) one specific bill. Used for retail walk-in dues."""
    bill = db.fetchone("SELECT * FROM bills WHERE id=?", (bill_id,))
    if not bill:
        raise ValueError("Bill not found.")
    total = money(bill["total_amount"])
    paid = money(bill["paid_amount"])
    due = money(total - paid)
    amount = money(amount)
    if amount <= EPS:
        raise ValueError("Payment amount must be greater than zero.")
    if amount > due + EPS:
        raise ValueError(f"Payment exceeds the due amount ({fmt(due)}).")

    new_paid = money(paid + amount)
    new_due = money(total - new_paid)
    if abs(new_due) < EPS:
        new_due = 0.0
    status = payment_status(total, new_paid)
    receipt = db.next_receipt_number()
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")

    with db.transaction() as cur:
        cur.execute("UPDATE bills SET paid_amount=?, due_amount=?, "
                    "payment_status=? WHERE id=?",
                    (new_paid, new_due, status, bill_id))
        cur.execute(
            "INSERT INTO payments (receipt_number, bill_id, retailer_id, "
            " customer_id, amount, payment_method, payment_date, reference, "
            " notes, staff_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (receipt, bill_id, bill["retailer_id"], bill["customer_id"], amount,
             method, date_str, reference, notes, staff_id))
    return receipt, new_paid, new_due, status


# ─── Installments (phone sold on EMI) ──────────────────────────────────────
def installment_schedule(total, down_payment, months):
    """Even monthly split; the LAST instalment absorbs the rounding remainder
    so the sum always equals the financed amount to the paisa."""
    total = money(total)
    down = money(min(max(money(down_payment), 0.0), total))
    months = max(int(months or 0), 0)
    financed = money(total - down)
    if months <= 0 or financed <= EPS:
        return down, financed, []

    base = money(financed / months)
    rows = [base] * months
    drift = money(financed - money(base * months))
    rows[-1] = money(rows[-1] + drift)
    return down, financed, rows


def installment_progress(db, register_id):
    """Return (total, paid, due, status) for a phone sold on instalments."""
    reg = db.fetchone("SELECT * FROM imei_register WHERE id=?", (register_id,))
    if not reg:
        return 0.0, 0.0, 0.0, "unknown"
    total = money(reg["total_amount"])
    paid = money(db.scalar(
        "SELECT COALESCE(SUM(amount),0) FROM imei_payments WHERE register_id=?",
        (register_id,), 0))
    paid = money(paid + money(reg["down_payment"]))
    if paid > total:
        paid = total
    due = money(total - paid)
    if abs(due) < EPS:
        due = 0.0
    return total, paid, due, payment_status(total, paid)


# ─── Stock ─────────────────────────────────────────────────────────────────
def log_stock(cur, product_id, change_type, qty_change, new_qty,
              reference="", staff_id=None, mobile_unit_id=None):
    cur.execute(
        "INSERT INTO stock_history (product_id, mobile_unit_id, change_type, "
        " quantity_change, new_quantity, reference, staff_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (product_id, mobile_unit_id, change_type, qty_change, new_qty,
         reference, staff_id))


def check_stock_available(db, items):
    """Pre-flight check before saving a bill. Returns list of problem strings."""
    problems = []
    wanted = {}
    for it in items:
        pid = it.get("product_id")
        if not pid:
            continue
        wanted[pid] = wanted.get(pid, 0) + parse_int(it.get("quantity"), 0)

    for pid, qty in wanted.items():
        row = db.fetchone(
            "SELECT name, stock_quantity, is_serialized FROM products WHERE id=?",
            (pid,))
        if not row:
            problems.append("A product on this bill no longer exists — "
                            "remove it and add it again.")
            continue
        if row["is_serialized"]:
            continue          # serialised phones are checked per IMEI unit
        if qty > row["stock_quantity"]:
            problems.append(
                f"{row['name']}: only {row['stock_quantity']} in stock, "
                f"bill needs {qty}.")

    for it in items:
        uid = it.get("mobile_unit_id")
        if not uid:
            continue
        u = db.fetchone("SELECT imei, status FROM mobile_units WHERE id=?", (uid,))
        if not u:
            problems.append("A selected handset no longer exists.")
        elif u["status"] != "in_stock":
            problems.append(f"IMEI {u['imei']} is already {u['status']}.")
    return problems


def adjust_stock(db, product_id, delta, reason, staff_id=None):
    """Manual stock correction with an audit row. Returns the new quantity."""
    row = db.fetchone("SELECT stock_quantity FROM products WHERE id=?",
                      (product_id,))
    if not row:
        raise ValueError("Product not found.")
    new_qty = int(row["stock_quantity"]) + int(delta)
    if new_qty < 0:
        raise ValueError("Stock cannot go below zero.")
    with db.transaction() as cur:
        cur.execute("UPDATE products SET stock_quantity=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_qty, product_id))
        log_stock(cur, product_id, "adjust", int(delta), new_qty, reason, staff_id)
    return new_qty


def stock_value(db, at_cost=True):
    col = "cost_price" if at_cost else "sell_price"
    return money(db.scalar(
        f"SELECT COALESCE(SUM(stock_quantity * {col}),0) FROM products "
        "WHERE is_active=1", None, 0))


# ─── Products ──────────────────────────────────────────────────────────────
def make_sku(db, category_code, name, brand=""):
    """Readable, collision-free SKU: MOB-SAM-0007"""
    code = (category_code or "GEN").upper()[:4]
    b = re.sub(r"[^A-Za-z]", "", brand or name or "X").upper()[:3] or "GEN"
    n = int(db.scalar("SELECT COUNT(*) FROM products", None, 0)) + 1
    candidate = f"{code}-{b}-{n:04d}"
    while db.fetchone("SELECT 1 FROM products WHERE sku=?", (candidate,)):
        n += 1
        candidate = f"{code}-{b}-{n:04d}"
    return candidate


def pack_attrs(d) -> str:
    clean = {k: str(v).strip() for k, v in (d or {}).items()
             if str(v).strip() not in ("", "None")}
    return json.dumps(clean, ensure_ascii=False)


def unpack_attrs(s) -> dict:
    if not s:
        return {}
    try:
        val = json.loads(s)
        return val if isinstance(val, dict) else {}
    except (ValueError, TypeError):
        return {}


def attrs_summary(attrs, limit=3) -> str:
    """'Black · 128GB · 5G' for table rows and bill lines."""
    d = attrs if isinstance(attrs, dict) else unpack_attrs(attrs)
    order = ["color", "storage", "ram", "network", "condition", "movement",
             "strap", "dial_size", "water", "connector", "wattage", "compat",
             "quality", "lens", "frame", "power", "gender"]
    vals = [d[k] for k in order if d.get(k)]
    vals += [v for k, v in d.items() if k not in order and v]
    return "  ·  ".join(vals[:limit])


def product_display(row, with_attrs=True) -> str:
    """Full human label: 'Samsung Galaxy A15 — Black · 128GB'"""
    brand = (row["brand"] or "").strip()
    name = (row["name"] or "").strip()
    model = (row["model"] or "").strip()
    head = " ".join(p for p in (brand, name) if p)
    if model and model.lower() not in head.lower():
        head = f"{head} {model}".strip()
    if with_attrs:
        try:
            extra = attrs_summary(row["attrs"])
        except (IndexError, KeyError):
            extra = ""
        if extra:
            return f"{head} — {extra}"
    return head


def price_for(row, bill_type):
    """Wholesale bills use wholesale_price when it is set, else retail."""
    if bill_type == BILL_WHOLESALE:
        wp = money(row["wholesale_price"])
        if wp > 0:
            return wp
    return money(row["sell_price"])


def delete_product(db, product_id, staff_id=None):
    """HARD delete — the product and its handsets are gone for good.

    Bill history is untouched because bill_items keeps its own snapshot of the
    name/brand/model/price, so old bills still print correctly.
    """
    with db.transaction() as cur:
        cur.execute("UPDATE bill_items SET product_id=NULL WHERE product_id=?",
                    (product_id,))
        cur.execute("UPDATE returns SET product_id=NULL WHERE product_id=?",
                    (product_id,))
        cur.execute("UPDATE imei_register SET product_id=NULL WHERE product_id=?",
                    (product_id,))
        cur.execute("DELETE FROM stock_history WHERE product_id=?", (product_id,))
        cur.execute("DELETE FROM mobile_units WHERE product_id=?", (product_id,))
        cur.execute("DELETE FROM products WHERE id=?", (product_id,))
    return True


# ─── Auth ──────────────────────────────────────────────────────────────────
def authenticate(db, username, password):
    """Return (user_row_dict, error_message). Logs every attempt."""
    username = (username or "").strip()
    row = db.fetchone("SELECT * FROM users WHERE username=? COLLATE NOCASE",
                      (username,))
    if not row:
        db.execute("INSERT INTO login_audit (username, success, note) "
                   "VALUES (?,0,'no such user')", (username,))
        return None, "Invalid username or password."
    if not row["is_active"]:
        db.execute("INSERT INTO login_audit (username, success, note) "
                   "VALUES (?,0,'disabled account')", (username,))
        return None, "This account has been disabled. Contact the owner."
    if not verify_password(password, row["password_hash"]):
        db.execute("INSERT INTO login_audit (username, success, note) "
                   "VALUES (?,0,'bad password')", (username,))
        return None, "Invalid username or password."

    # Transparently upgrade legacy SHA-256 hashes on successful login
    if needs_upgrade(row["password_hash"]):
        db.execute("UPDATE users SET password_hash=? WHERE id=?",
                   (hash_password(password), row["id"]))

    db.execute("UPDATE users SET last_login=? WHERE id=?",
               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
    db.execute("INSERT INTO login_audit (username, success, note) "
               "VALUES (?,1,'ok')", (username,))
    return dict(row), None


def is_admin(user) -> bool:
    return bool(user) and str(user.get("role", "")).lower() == ROLE_ADMIN


def normalise_phone(phone, country=COUNTRY_CODE) -> str:
    """977-prefixed digits for WhatsApp links."""
    digits = re.sub(r"[^0-9]", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits.startswith(country):
        digits = country + digits.lstrip("0")
    return digits


def clean_phone(phone) -> str:
    """Digits as the shopkeeper typed them, for storing/displaying."""
    return re.sub(r"[^0-9+]", "", str(phone or "")).strip()


def warranty_expiry(sold_date, months):
    months = int(months or 0)
    if months <= 0:
        return ""
    try:
        d = datetime.strptime(str(sold_date)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        d = datetime.now()
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = d.day
    while True:
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            day -= 1          # 31st → 30th/28th
            if day < 28:
                return d.strftime("%Y-%m-%d")


def warranty_state(expiry):
    """('Active', days_left) / ('Expired', -days) / ('None', 0)"""
    if not expiry:
        return "None", 0
    try:
        d = datetime.strptime(str(expiry)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return "None", 0
    days = (d - datetime.now()).days
    return ("Active" if days >= 0 else "Expired"), days
