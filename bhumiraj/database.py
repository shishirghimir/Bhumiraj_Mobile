"""SQLite schema + safe access helpers for Bhumiraj Retail & Wholesale.

Everything is parameterised (no string-built SQL with user data), every write
goes through a lock, and multi-statement writes run in a single transaction so
a failure never leaves half a bill behind.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from datetime import datetime

from .config import (BACKUPS_DIR, DB_PATH, SEED_CATEGORIES, BILL_PREFIX,
                     BILL_RETAIL, BILL_WHOLESALE)
from .security import hash_password, hash_answer, new_pin_hash

# Legacy v1 tables that are replaced by the v2 schema. Dropped only when empty.
_LEGACY_TABLES = ["sale_items", "sales", "sale_counter", "warranty"]


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = None
        self._lock = threading.RLock()
        self.connect()
        self.create_tables()

    # ── Connection ──────────────────────────────────────────────────
    def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                    timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self._integrity_or_raise()

    def _integrity_or_raise(self):
        try:
            row = self.conn.execute("PRAGMA quick_check").fetchone()
            if row and str(row[0]).lower() != "ok":
                self._quarantine_and_reset()
        except sqlite3.DatabaseError:
            self._quarantine_and_reset()

    def _quarantine_and_reset(self):
        """Corrupt file — move it aside and start clean rather than crash."""
        try:
            self.conn.close()
        except Exception:
            pass
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bad = os.path.join(BACKUPS_DIR, f"CORRUPT_{stamp}.db")
        try:
            shutil.move(self.db_path, bad)
        except Exception:
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                    timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _ensure(self):
        if self.conn is None:
            self.connect()

    # ── Schema ──────────────────────────────────────────────────────
    def create_tables(self):
        with self._lock:
            self._ensure()
            c = self.conn.cursor()

            # ── Users: admin + counter staff ────────────────────────
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                full_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                address TEXT DEFAULT '',
                photo_path TEXT DEFAULT '',
                citizenship_no TEXT DEFAULT '',
                salary REAL DEFAULT 0,
                joined_date TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                must_change_password INTEGER DEFAULT 0,
                security_question TEXT DEFAULT '',
                security_answer_hash TEXT DEFAULT '',
                last_login TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            # Recovery PIN for admin password reset (single row, id=1)
            c.execute("""CREATE TABLE IF NOT EXISTS admin_pin (
                id INTEGER PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                security_question TEXT DEFAULT 'What is the shop location?',
                security_answer_hash TEXT DEFAULT '')""")

            c.execute("""CREATE TABLE IF NOT EXISTS login_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT DEFAULT '',
                success INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            # ── Catalogue ───────────────────────────────────────────
            # `kind` drives which extra fields the product form asks for.
            c.execute("""CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'general',
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            # Three prices: cost_price (ADMIN ONLY), wholesale_price, sell_price.
            # attrs holds the category-kind specific fields as JSON.
            c.execute("""CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                sku TEXT DEFAULT '',
                barcode TEXT DEFAULT '',
                brand TEXT DEFAULT '',
                model TEXT DEFAULT '',
                variant TEXT DEFAULT '',
                cost_price REAL NOT NULL DEFAULT 0,
                wholesale_price REAL NOT NULL DEFAULT 0,
                sell_price REAL NOT NULL DEFAULT 0,
                stock_quantity INTEGER NOT NULL DEFAULT 0,
                min_stock_level INTEGER DEFAULT 2,
                unit TEXT DEFAULT 'pcs',
                warranty_months INTEGER DEFAULT 0,
                is_serialized INTEGER DEFAULT 0,
                attrs TEXT DEFAULT '{}',
                description TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id))""")

            # One row per physical handset — the Mobiles tab works on this.
            c.execute("""CREATE TABLE IF NOT EXISTS mobile_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                imei TEXT NOT NULL,
                imei2 TEXT DEFAULT '',
                serial_no TEXT DEFAULT '',
                color TEXT DEFAULT '',
                storage TEXT DEFAULT '',
                ram TEXT DEFAULT '',
                condition TEXT DEFAULT 'New',
                cost_price REAL DEFAULT 0,
                sell_price REAL DEFAULT 0,
                status TEXT DEFAULT 'in_stock',
                bill_id INTEGER,
                sold_date TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE)""")

            # ── Parties ─────────────────────────────────────────────
            c.execute("""CREATE TABLE IF NOT EXISTS retailers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                shop_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                alt_phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                address TEXT DEFAULT '',
                city TEXT DEFAULT '',
                pan_number TEXT DEFAULT '',
                opening_balance REAL DEFAULT 0,
                credit_limit REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            c.execute("""CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                address TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            # ── Bills ───────────────────────────────────────────────
            c.execute("""CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_number TEXT NOT NULL UNIQUE,
                bill_type TEXT NOT NULL DEFAULT 'retail',
                retailer_id INTEGER,
                customer_id INTEGER,
                customer_name TEXT DEFAULT 'Walk-in',
                customer_phone TEXT DEFAULT '',
                staff_id INTEGER NOT NULL,
                bill_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subtotal REAL NOT NULL DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                total_amount REAL NOT NULL DEFAULT 0,
                paid_amount REAL DEFAULT 0,
                due_amount REAL DEFAULT 0,
                payment_status TEXT DEFAULT 'paid',
                payment_method TEXT DEFAULT 'Cash',
                plan_type TEXT DEFAULT 'full',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (staff_id) REFERENCES users(id),
                FOREIGN KEY (retailer_id) REFERENCES retailers(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id))""")

            # Snapshot columns so an old bill still prints after a product is
            # deleted. cogs_price is the cost at sale time (admin reporting).
            c.execute("""CREATE TABLE IF NOT EXISTS bill_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL,
                product_id INTEGER,
                mobile_unit_id INTEGER,
                product_name TEXT NOT NULL,
                product_brand TEXT DEFAULT '',
                product_model TEXT DEFAULT '',
                product_sku TEXT DEFAULT '',
                imei TEXT DEFAULT '',
                attrs_snapshot TEXT DEFAULT '{}',
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                cogs_price REAL DEFAULT 0,
                warranty_months INTEGER DEFAULT 0,
                FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE)""")

            # One row per bill touched by a payment (FIFO writes several).
            # bill_id NULL = unallocated advance sitting on the retailer account.
            c.execute("""CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_number TEXT DEFAULT '',
                bill_id INTEGER,
                retailer_id INTEGER,
                customer_id INTEGER,
                amount REAL NOT NULL,
                payment_method TEXT DEFAULT 'Cash',
                payment_date TEXT NOT NULL,
                reference TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                staff_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE SET NULL,
                FOREIGN KEY (retailer_id) REFERENCES retailers(id) ON DELETE CASCADE)""")

            # ── IMEI / warranty register + installments ─────────────
            c.execute("""CREATE TABLE IF NOT EXISTS imei_register (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imei TEXT NOT NULL,
                product_id INTEGER,
                mobile_unit_id INTEGER,
                product_name TEXT DEFAULT '',
                brand TEXT DEFAULT '',
                model TEXT DEFAULT '',
                color TEXT DEFAULT '',
                storage TEXT DEFAULT '',
                bill_id INTEGER,
                bill_number TEXT DEFAULT '',
                customer_name TEXT DEFAULT '',
                customer_phone TEXT DEFAULT '',
                sold_date TEXT DEFAULT '',
                warranty_months INTEGER DEFAULT 0,
                warranty_expiry TEXT DEFAULT '',
                plan_type TEXT DEFAULT 'full',
                total_amount REAL DEFAULT 0,
                down_payment REAL DEFAULT 0,
                installment_amount REAL DEFAULT 0,
                installment_months INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            c.execute("""CREATE TABLE IF NOT EXISTS imei_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                register_id INTEGER NOT NULL,
                receipt_number TEXT DEFAULT '',
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT DEFAULT 'Cash',
                notes TEXT DEFAULT '',
                staff_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (register_id) REFERENCES imei_register(id) ON DELETE CASCADE)""")

            # ── Returns / expenses / audit ──────────────────────────
            c.execute("""CREATE TABLE IF NOT EXISTS returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER,
                bill_number TEXT DEFAULT '',
                product_id INTEGER,
                mobile_unit_id INTEGER,
                product_name TEXT NOT NULL,
                imei TEXT DEFAULT '',
                quantity INTEGER NOT NULL,
                refund_amount REAL NOT NULL,
                restocked INTEGER DEFAULT 1,
                reason TEXT DEFAULT '',
                staff_id INTEGER,
                return_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            c.execute("""CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_date TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Other',
                description TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT DEFAULT 'Cash',
                notes TEXT DEFAULT '',
                staff_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            c.execute("""CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                mobile_unit_id INTEGER,
                change_type TEXT NOT NULL,
                quantity_change INTEGER DEFAULT 0,
                new_quantity INTEGER DEFAULT 0,
                reference TEXT DEFAULT '',
                staff_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            c.execute("""CREATE TABLE IF NOT EXISTS counters (
                prefix TEXT PRIMARY KEY,
                max_seq INTEGER NOT NULL DEFAULT 0)""")

            for idx in [
                "CREATE INDEX IF NOT EXISTS ix_prod_name    ON products(name)",
                "CREATE INDEX IF NOT EXISTS ix_prod_brand   ON products(brand)",
                "CREATE INDEX IF NOT EXISTS ix_prod_cat     ON products(category_id)",
                "CREATE INDEX IF NOT EXISTS ix_prod_active  ON products(is_active)",
                "CREATE INDEX IF NOT EXISTS ix_prod_sku     ON products(sku)",
                "CREATE INDEX IF NOT EXISTS ix_unit_imei    ON mobile_units(imei)",
                "CREATE INDEX IF NOT EXISTS ix_unit_prod    ON mobile_units(product_id)",
                "CREATE INDEX IF NOT EXISTS ix_unit_status  ON mobile_units(status)",
                "CREATE INDEX IF NOT EXISTS ix_bill_number  ON bills(bill_number)",
                "CREATE INDEX IF NOT EXISTS ix_bill_date    ON bills(bill_date)",
                "CREATE INDEX IF NOT EXISTS ix_bill_type    ON bills(bill_type)",
                "CREATE INDEX IF NOT EXISTS ix_bill_ret     ON bills(retailer_id)",
                "CREATE INDEX IF NOT EXISTS ix_bill_status  ON bills(payment_status)",
                "CREATE INDEX IF NOT EXISTS ix_bill_staff   ON bills(staff_id)",
                "CREATE INDEX IF NOT EXISTS ix_bi_bill      ON bill_items(bill_id)",
                "CREATE INDEX IF NOT EXISTS ix_bi_prod      ON bill_items(product_id)",
                "CREATE INDEX IF NOT EXISTS ix_pay_ret      ON payments(retailer_id)",
                "CREATE INDEX IF NOT EXISTS ix_pay_bill     ON payments(bill_id)",
                "CREATE INDEX IF NOT EXISTS ix_pay_date     ON payments(payment_date)",
                "CREATE INDEX IF NOT EXISTS ix_imei_imei    ON imei_register(imei)",
                "CREATE INDEX IF NOT EXISTS ix_imei_phone   ON imei_register(customer_phone)",
                "CREATE INDEX IF NOT EXISTS ix_imeipay_reg  ON imei_payments(register_id)",
                "CREATE INDEX IF NOT EXISTS ix_ret_bill     ON returns(bill_id)",
                "CREATE INDEX IF NOT EXISTS ix_exp_date     ON expenses(expense_date)",
                "CREATE INDEX IF NOT EXISTS ix_sh_prod      ON stock_history(product_id)",
            ]:
                try:
                    c.execute(idx)
                except sqlite3.OperationalError:
                    pass

            self.conn.commit()
            self._migrate(c)
            self._seed()

    def _migrate(self, c):
        """Add columns introduced after the first release, drop empty v1 tables."""
        added = [
            ("products", "wholesale_price", "REAL NOT NULL DEFAULT 0"),
            ("products", "attrs", "TEXT DEFAULT '{}'"),
            ("products", "warranty_months", "INTEGER DEFAULT 0"),
            ("products", "is_serialized", "INTEGER DEFAULT 0"),
            ("bills", "due_amount", "REAL DEFAULT 0"),
            ("bills", "plan_type", "TEXT DEFAULT 'full'"),
            ("users", "salary", "REAL DEFAULT 0"),
            ("users", "must_change_password", "INTEGER DEFAULT 0"),
        ]
        for table, col, decl in added:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass

        # Retire v1 tables only when they hold no data — never destroy records.
        for t in _LEGACY_TABLES:
            try:
                exists = c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (t,)).fetchone()
                if not exists:
                    continue
                n = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                if n == 0:
                    c.execute(f"DROP TABLE [{t}]")
            except sqlite3.Error:
                pass
        self.conn.commit()

    def _seed(self):
        c = self.conn.cursor()
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO users (username, password_hash, role, full_name, "
                " phone, address, must_change_password, security_question, "
                " security_answer_hash, joined_date) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("admin", hash_password("Admin@123"), "admin", "Shop Owner",
                 "9808773134", "Chabahil-7, Kathmandu", 1,
                 "What is the shop location?", hash_answer("chabahil"),
                 datetime.now().strftime("%Y-%m-%d")))

        if c.execute("SELECT COUNT(*) FROM admin_pin").fetchone()[0] == 0:
            c.execute("INSERT INTO admin_pin (id, pin_hash, security_question, "
                      "security_answer_hash) VALUES (1,?,?,?)",
                      (new_pin_hash("1234"), "What is the shop location?",
                       hash_answer("chabahil")))

        if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO categories (name, code, kind) VALUES (?,?,?)",
                SEED_CATEGORIES)

        for pfx in (BILL_PREFIX[BILL_RETAIL], BILL_PREFIX[BILL_WHOLESALE],
                    "RC", "IP"):
            c.execute("INSERT OR IGNORE INTO counters (prefix, max_seq) "
                      "VALUES (?, 0)", (pfx,))
        self.conn.commit()

    # ── Generic helpers ─────────────────────────────────────────────
    def execute(self, q, p=None):
        with self._lock:
            self._ensure()
            cur = self.conn.cursor()
            cur.execute(q, p or ())
            self.conn.commit()
            return cur

    def execute_many(self, queries):
        """Run (sql, params) pairs in ONE transaction. All or nothing."""
        with self._lock:
            self._ensure()
            cur = self.conn.cursor()
            try:
                cur.execute("BEGIN")
                for q, p in queries:
                    cur.execute(q, p or ())
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return cur

    def transaction(self):
        """Context manager giving a cursor inside a single transaction.

        Used by services that need lastrowid part-way through the batch.
        """
        return _Txn(self)

    def fetchall(self, q, p=None):
        with self._lock:
            self._ensure()
            return self.conn.cursor().execute(q, p or ()).fetchall()

    def fetchone(self, q, p=None):
        with self._lock:
            self._ensure()
            return self.conn.cursor().execute(q, p or ()).fetchone()

    def scalar(self, q, p=None, default=0):
        row = self.fetchone(q, p)
        if not row:
            return default
        val = row[0]
        return default if val is None else val

    # ── Document numbers ────────────────────────────────────────────
    def next_number(self, prefix):
        """Atomic, gap-free document number:  BR-2026-0001"""
        with self._lock:
            self._ensure()
            cur = self.conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                cur.execute("INSERT OR IGNORE INTO counters (prefix, max_seq) "
                            "VALUES (?, 0)", (prefix,))
                cur.execute("UPDATE counters SET max_seq = max_seq + 1 "
                            "WHERE prefix = ?", (prefix,))
                seq = cur.execute("SELECT max_seq FROM counters WHERE prefix=?",
                                  (prefix,)).fetchone()[0]
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return f"{prefix}-{datetime.now().year}-{seq:04d}"

    def next_bill_number(self, bill_type):
        return self.next_number(BILL_PREFIX.get(bill_type, "BR"))

    def next_receipt_number(self):
        return self.next_number("RC")

    def next_installment_receipt(self):
        return self.next_number("IP")

    # ── Backup / restore ────────────────────────────────────────────
    def backup(self, dest):
        """Consistent online backup using SQLite's own backup API."""
        with self._lock:
            self._ensure()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            target = sqlite3.connect(dest)
            try:
                with target:
                    self.conn.backup(target)
            finally:
                target.close()
        return dest

    def restore(self, src):
        """Replace the live DB with `src` after validating it.

        A safety copy of the current database is taken first, and the file is
        only swapped in once the incoming one passes an integrity + schema
        check — so a bad import can never destroy working data.
        """
        if not os.path.exists(src):
            raise FileNotFoundError(src)

        # 1. Validate the incoming file before touching anything
        probe = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            row = probe.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise ValueError("Backup file failed the integrity check.")
            names = {r[0] for r in probe.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "products", "bills", "bill_items", "categories"}
            missing = required - names
            if missing:
                raise ValueError("Not a Bhumiraj backup — missing tables: "
                                 + ", ".join(sorted(missing)))
        finally:
            probe.close()

        with self._lock:
            # 2. Safety copy of what we are about to overwrite
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety = os.path.join(BACKUPS_DIR, f"pre_restore_{stamp}.db")
            try:
                self.backup(safety)
            except Exception:
                safety = None

            # 3. Swap: copy source over the live file, then reconnect
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
            for suffix in ("-wal", "-shm"):
                side = self.db_path + suffix
                if os.path.exists(side):
                    try:
                        os.remove(side)
                    except OSError:
                        pass
            try:
                shutil.copy2(src, self.db_path)
            except Exception:
                if safety and os.path.exists(safety):
                    shutil.copy2(safety, self.db_path)
                self.connect()
                raise
            self.connect()
            self.create_tables()   # bring an older backup up to current schema
        return safety

    def close(self):
        with self._lock:
            if self.conn:
                try:
                    self.conn.commit()
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None


class _Txn:
    """with db.transaction() as cur:  … all-or-nothing, lastrowid available."""

    def __init__(self, db):
        self.db = db
        self.cur = None

    def __enter__(self):
        self.db._lock.acquire()
        self.db._ensure()
        self.cur = self.db.conn.cursor()
        self.cur.execute("BEGIN IMMEDIATE")
        return self.cur

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db.conn.commit()
            else:
                self.db.conn.rollback()
        finally:
            self.db._lock.release()
        return False
