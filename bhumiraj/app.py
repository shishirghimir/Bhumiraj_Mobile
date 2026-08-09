"""Main window: login, sidebar, routing, and the close → logout → quit flow.

One window for the whole app. Logging out swaps the main view back to the
login card rather than destroying the window, which is what makes the
requested close behaviour work:

    X while logged in  →  "Log out?"  →  back to the login screen
    X on the login screen →  "Quit Bhumiraj?"  →  application exits
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

import customtkinter as ctk

from .config import (APP_NAME, APP_SHORT, APP_TAGLINE, APP_VERSION, ERROR_LOG,
                     F_BODY, F_LBL, F_SEC, F_SM, F_TN, LOGO_ICO, LOGO_PATH,
                     ROLE_ADMIN, SHOP_ADDRESS, SHOP_PHONE, TH, VENDOR,
                     VENDOR_SITE)
from .database import DatabaseManager
from .pdf import DocumentGenerator
from .security import (hash_password, password_strength, staff_password_strength,
                       strength_score, verify_answer, verify_pin)
from .services import authenticate, is_admin
from .settings import BackupManager, SettingsManager
from . import ui_helpers as ui

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ─── Navigation ────────────────────────────────────────────────────────────
# (key, label, icon, admin_only)
NAV_ITEMS = [
    ("dashboard",  "Dashboard",        "📊", False),
    ("billing",    "New Bill",         "🧾", False),
    ("bills",      "Bills History",    "📋", False),
    ("products",   "Products / Stock", "📦", False),
    ("mobiles",    "Mobiles (IMEI)",   "📱", False),
    ("imei",       "Warranty / EMI",   "🛡", False),
    ("returns",    "Returns",          "↩️", False),
    ("retailers",  "Retailers",        "🏪", True),
    ("customers",  "Customers",        "👤", True),
    ("payments",   "Payments",         "💰", True),
    ("categories", "Categories",       "🏷️", True),
    ("catalog",    "Product Catalog",  "📖", True),
    ("staff",      "Staff",            "👥", True),
    ("expenses",   "Expenses",         "💸", True),
    ("reports",    "Reports",          "📈", True),
    ("settings",   "Settings",         "⚙️", True),
]


class BhumirajApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(fg_color=TH.BG)

        self.db = DatabaseManager()
        self.settings = SettingsManager()
        self.backup = BackupManager(self.db, self.settings)
        self.docs = DocumentGenerator(self.settings, self.db)

        self.user = None
        self.page_key = None
        self.nav_buttons = {}
        self._page_cache = {}
        self.last_pdf = None          # for the Ctrl+P "print last" hotkey

        self.geometry(self.settings.get("window_geometry", "1360x820+30+24"))
        self.minsize(1180, 700)
        try:
            if os.path.exists(LOGO_ICO):
                self.iconbitmap(LOGO_ICO)
        except Exception:
            pass

        ui.style_trees()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_login()
        self.after(900, self._auto_backup)

    # ── Crash guard ─────────────────────────────────────────────────
    def report_callback_exception(self, exc, val, tb):
        """Never let a stray exception kill the till mid-sale.

        In a windowed PyInstaller build sys.stderr is None, so writing to it
        raised inside the handler itself and turned a recoverable error into a
        hard "Failed to execute script main" crash. Everything here is guarded
        and the trace goes to a log file the shop can send us.
        """
        try:
            detail = "".join(traceback.format_exception(exc, val, tb))
        except Exception:
            detail = f"{exc}: {val}"

        # stderr may be None (windowed build) — never assume it exists
        try:
            if sys.stderr is not None:
                sys.stderr.write(detail)
                sys.stderr.flush()
        except Exception:
            pass

        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
                fh.write(detail)
        except Exception:
            pass

        try:
            ui.error(self, "Something went wrong",
                     f"{val}\n\nThe app is still running and your data is "
                     f"safe — you can carry on.\n\n"
                     f"If it keeps happening, send this file to support:\n"
                     f"{ERROR_LOG}")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════════════════
    def show_login(self):
        self.user = None
        self.page_key = None
        self.nav_buttons.clear()
        self._page_cache.clear()
        for w in self.winfo_children():
            w.destroy()

        shell = ctk.CTkFrame(self, fg_color=TH.BG)
        shell.pack(fill="both", expand=True)

        # Left brand panel
        left = ctk.CTkFrame(shell, fg_color=TH.SIDEBAR, corner_radius=0,
                            width=470)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        badge = ui.load_ctk_image(LOGO_PATH, (168, 168))
        if badge:
            ctk.CTkLabel(left, image=badge, text="").pack(pady=(74, 18))
        else:
            ctk.CTkLabel(left, text="📱", font=ctk.CTkFont(size=76)).pack(
                pady=(74, 18))

        ctk.CTkLabel(left, text=APP_SHORT,
                     font=ctk.CTkFont(size=32, weight="bold"),
                     text_color=TH.ACCENT).pack()
        ctk.CTkLabel(left, text=APP_TAGLINE,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#c8d4f0").pack(pady=(2, 0))
        ctk.CTkFrame(left, height=2, fg_color=TH.ACCENT_DIM).pack(
            fill="x", padx=110, pady=18)
        ctk.CTkLabel(left, text=self.settings.get("shop_address", SHOP_ADDRESS),
                     font=ctk.CTkFont(size=F_SM),
                     text_color="#a9bce4").pack()
        ctk.CTkLabel(left, text=self.settings.get("shop_phone", SHOP_PHONE),
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color="#a9bce4").pack(pady=(2, 0))

        ctk.CTkFrame(left, fg_color="transparent").pack(expand=True, fill="both")
        ctk.CTkLabel(left, text="Retail  ·  Wholesale  ·  Warranty",
                     font=ctk.CTkFont(size=F_TN),
                     text_color="#7f93c4").pack(pady=(0, 6))
        ctk.CTkLabel(left, text=f"v{APP_VERSION}   by {VENDOR}",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color=TH.ACCENT_DIM).pack()
        ctk.CTkLabel(left, text=f"visit {VENDOR_SITE}",
                     font=ctk.CTkFont(size=F_TN),
                     text_color="#7f93c4").pack(pady=(0, 26))

        # Right login card
        right = ctk.CTkFrame(shell, fg_color=TH.BG)
        right.pack(side="right", fill="both", expand=True)

        card = ctk.CTkFrame(right, fg_color=TH.PANEL, corner_radius=16,
                            border_width=1, border_color=TH.BORDER,
                            width=420)
        card.place(relx=0.5, rely=0.5, anchor="center")

        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=42, pady=40)

        ctk.CTkLabel(pad, text="Welcome back",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=TH.TEXT).pack(anchor="w")
        ctk.CTkLabel(pad, text="Sign in to open the shop",
                     font=ctk.CTkFont(size=F_BODY),
                     text_color=TH.TEXT_DIM).pack(anchor="w", pady=(2, 22))

        self.login_user = ui.labelled_entry(pad, "Username", width=316,
                                            placeholder="admin")
        self.login_pass = ui.labelled_entry(pad, "Password", width=316,
                                            show="•", placeholder="••••••••")

        self.login_msg = ctk.CTkLabel(pad, text="", font=ctk.CTkFont(size=F_SM),
                                      text_color=TH.DANGER, wraplength=316,
                                      justify="left")
        self.login_msg.pack(anchor="w", pady=(8, 0))

        ui.button(pad, "SIGN IN", self._do_login, "ok", 316, 44,
                  font_size=F_LBL).pack(pady=(14, 6))
        ctk.CTkButton(pad, text="Forgot password?", command=self._forgot,
                      fg_color="transparent", hover_color=TH.PANEL_ALT,
                      text_color=TH.TEXT_DIM,
                      font=ctk.CTkFont(size=F_SM), height=28).pack()

        self.login_user.bind("<Return>", lambda _e: self.login_pass.focus_set())
        self.login_pass.bind("<Return>", lambda _e: self._do_login())
        self.login_user.focus_set()
        self.bind("<Escape>", lambda _e: self._on_close())

    def _do_login(self):
        username = self.login_user.get().strip()
        password = self.login_pass.get()
        if not username or not password:
            self.login_msg.configure(text="Enter both username and password.")
            return
        user, err = authenticate(self.db, username, password)
        if err:
            self.login_msg.configure(text=err)
            self.login_pass.delete(0, "end")
            return
        self.user = user
        if user.get("must_change_password"):
            if not self._force_password_change():
                self.user = None
                self.login_msg.configure(
                    text="You must set a new password before continuing.")
                return
        self.build_main()

    def _force_password_change(self):
        """Blocking dialog on first login. Returns True when changed."""
        done = {"ok": False}
        d = ui.modal(self, "Set a new password", 520, 420, resizable=False)
        ui.modal_header(d, "Set a new password",
                        "Required before you can use the app")
        body = ui.modal_body(d, scroll=False)
        ctk.CTkLabel(body,
                     text="For security, choose your own password now.\n"
                          "Minimum 8 characters with an uppercase letter, a "
                          "lowercase letter and a number.",
                     font=ctk.CTkFont(size=F_SM), text_color=TH.TEXT_DIM,
                     justify="left", wraplength=440).pack(anchor="w", pady=(0, 8))
        e1 = ui.labelled_entry(body, "New password", show="•", required=True)
        e2 = ui.labelled_entry(body, "Confirm password", show="•", required=True)
        meter = ctk.CTkProgressBar(body, height=8)
        meter.pack(fill="x", pady=(8, 2))
        meter.set(0)
        hint = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=F_TN),
                            text_color=TH.TEXT_DIM)
        hint.pack(anchor="w")

        def on_type(_e=None):
            score = strength_score(e1.get())
            meter.set(score / 4)
            meter.configure(progress_color=[TH.DANGER, TH.DANGER, TH.WARN,
                                            TH.OK, TH.OK][score])
            hint.configure(text=["Too weak", "Weak", "Fair", "Good",
                                 "Strong"][score])
        e1.bind("<KeyRelease>", on_type)

        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def save():
            pw, pw2 = e1.get(), e2.get()
            if pw != pw2:
                msg.configure(text="The two passwords do not match.")
                return
            checker = (password_strength if is_admin(self.user)
                       else staff_password_strength)
            ok, why = checker(pw)
            if not ok:
                msg.configure(text=why)
                return
            self.db.execute("UPDATE users SET password_hash=?, "
                            "must_change_password=0 WHERE id=?",
                            (hash_password(pw), self.user["id"]))
            self.user["must_change_password"] = 0
            done["ok"] = True
            d.destroy()

        foot = ui.modal_footer(d)
        ui.button(foot, "Save & Continue", save, "ok", 170, side="right")
        d.protocol("WM_DELETE_WINDOW", lambda: None)   # cannot be dismissed
        self.wait_window(d)
        return done["ok"]

    def _forgot(self):
        """Recovery: admin PIN or the security question."""
        d = ui.modal(self, "Reset password", 520, 470, resizable=False)
        ui.modal_header(d, "Reset password",
                        "Verify with the recovery PIN or security answer")
        body = ui.modal_body(d, scroll=False)

        user_e = ui.labelled_entry(body, "Username", required=True)
        pin_e = ui.labelled_entry(body, "Recovery PIN", show="•",
                                  placeholder="4-digit PIN")
        ctk.CTkLabel(body, text="— or —", font=ctk.CTkFont(size=F_SM),
                     text_color=TH.TEXT_DIM).pack(pady=4)
        q = self.db.fetchone("SELECT security_question FROM admin_pin WHERE id=1")
        question = (q["security_question"] if q else "What is the shop location?")
        ans_e = ui.labelled_entry(body, question)
        new_e = ui.labelled_entry(body, "New password", show="•", required=True)
        msg = ctk.CTkLabel(body, text="", text_color=TH.DANGER,
                           font=ctk.CTkFont(size=F_SM), wraplength=440,
                           justify="left")
        msg.pack(anchor="w", pady=(6, 0))

        def reset():
            uname = user_e.get().strip()
            row = self.db.fetchone(
                "SELECT * FROM users WHERE username=? COLLATE NOCASE", (uname,))
            if not row:
                msg.configure(text="No such user.")
                return
            pin_row = self.db.fetchone("SELECT * FROM admin_pin WHERE id=1")
            ok = False
            if pin_e.get().strip() and pin_row:
                ok = verify_pin(pin_e.get().strip(), pin_row["pin_hash"])
            if not ok and ans_e.get().strip() and pin_row:
                ok = verify_answer(ans_e.get().strip(),
                                   pin_row["security_answer_hash"])
            if not ok:
                msg.configure(text="PIN or security answer is incorrect.")
                return
            checker = (password_strength
                       if str(row["role"]).lower() == ROLE_ADMIN
                       else staff_password_strength)
            good, why = checker(new_e.get())
            if not good:
                msg.configure(text=why)
                return
            self.db.execute("UPDATE users SET password_hash=?, "
                            "must_change_password=0 WHERE id=?",
                            (hash_password(new_e.get()), row["id"]))
            self.db.execute("INSERT INTO login_audit (username, success, note) "
                            "VALUES (?,1,'password reset')", (uname,))
            d.destroy()
            ui.info(self, "Password reset",
                    "Password updated. You can sign in now.")

        foot = ui.modal_footer(d)
        ui.button(foot, "Cancel", d.destroy, "muted", 110, side="right")
        ui.button(foot, "Reset", reset, "ok", 140, side="right")

    # ══════════════════════════════════════════════════════════════
    # MAIN SHELL
    # ══════════════════════════════════════════════════════════════
    def build_main(self):
        for w in self.winfo_children():
            w.destroy()
        self.unbind("<Escape>")
        self.nav_buttons.clear()
        self._page_cache.clear()

        admin = is_admin(self.user)

        # ── Sidebar ─────────────────────────────────────────────────
        side = ctk.CTkFrame(self, width=232, corner_radius=0,
                            fg_color=TH.SIDEBAR)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(pady=(16, 6), padx=12, fill="x")
        badge = ui.load_ctk_image(LOGO_PATH, (62, 62))
        if badge:
            ctk.CTkLabel(head, image=badge, text="").pack()
        ctk.CTkLabel(head, text=APP_SHORT,
                     font=ctk.CTkFont(size=19, weight="bold"),
                     text_color=TH.ACCENT).pack(pady=(6, 0))
        ctk.CTkLabel(head, text=APP_TAGLINE,
                     font=ctk.CTkFont(size=8, weight="bold"),
                     text_color="#8fa3d0").pack()
        ctk.CTkFrame(side, height=1, fg_color=TH.ACCENT_DIM).pack(
            fill="x", padx=18, pady=(10, 8))

        nav_scroll = ctk.CTkScrollableFrame(side, fg_color="transparent",
                                            width=210)
        nav_scroll.pack(fill="both", expand=True, padx=2)

        for key, label, icon, admin_only in NAV_ITEMS:
            if admin_only and not admin:
                continue
            b = ctk.CTkButton(
                nav_scroll, text=f"  {icon}   {label}",
                command=lambda k=key: self.go(k),
                font=ctk.CTkFont(size=F_BODY), anchor="w",
                fg_color="transparent", text_color=TH.TEXT,
                hover_color=TH.SIDEBAR_HV, height=38, corner_radius=8)
            b.pack(fill="x", padx=6, pady=1)
            self.nav_buttons[key] = b

        if not admin:
            b = ctk.CTkButton(
                nav_scroll, text="  🙍   My Profile",
                command=lambda: self.go("profile"),
                font=ctk.CTkFont(size=F_BODY), anchor="w",
                fg_color="transparent", text_color=TH.TEXT,
                hover_color=TH.SIDEBAR_HV, height=38, corner_radius=8)
            b.pack(fill="x", padx=6, pady=1)
            self.nav_buttons["profile"] = b

        # ── Sidebar footer ──────────────────────────────────────────
        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(fill="x", side="bottom", pady=(4, 10))
        ctk.CTkFrame(foot, height=1, fg_color=TH.BORDER).pack(fill="x",
                                                              padx=16, pady=6)
        ctk.CTkLabel(foot, text=f"👤  {self.user['full_name']}",
                     font=ctk.CTkFont(size=F_SM, weight="bold"),
                     text_color=TH.ACCENT).pack()
        ctk.CTkLabel(foot, text=("OWNER / ADMIN" if admin else "COUNTER STAFF"),
                     font=ctk.CTkFont(size=8, weight="bold"),
                     text_color="#8fa3d0").pack(pady=(0, 6))
        ui.button(foot, "🔓  Logout", self.logout, "danger", 190, 34).pack(
            padx=18)
        ctk.CTkLabel(foot, text=f"v{APP_VERSION}  ·  by {VENDOR}",
                     font=ctk.CTkFont(size=F_TN, weight="bold"),
                     text_color="#7f93c4").pack(pady=(8, 0))
        ctk.CTkLabel(foot, text=f"visit {VENDOR_SITE}",
                     font=ctk.CTkFont(size=F_TN),
                     text_color=TH.ACCENT_DIM).pack()

        # ── Content area ────────────────────────────────────────────
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=TH.BG)
        self.content.pack(side="right", fill="both", expand=True)

        self._bind_hotkeys()
        self.go("dashboard")

    def _bind_hotkeys(self):
        self.bind("<F1>", lambda _e: self.go("billing"))
        self.bind("<F2>", lambda _e: self._hotkey("save"))
        self.bind("<F3>", lambda _e: self._hotkey("search"))
        self.bind("<F5>", lambda _e: self.go(self.page_key, force=True))
        self.bind("<Control-n>", lambda _e: self.go("billing"))
        self.bind("<Control-p>", lambda _e: self._print_last())
        self.bind("<Control-b>", lambda _e: self.go("bills"))

    def _hotkey(self, action):
        page = self._page_cache.get(self.page_key)
        handler = getattr(page, f"hotkey_{action}", None) if page else None
        if callable(handler):
            handler()

    def _print_last(self):
        if self.last_pdf and os.path.exists(self.last_pdf):
            ui.print_file(self.last_pdf)
        else:
            ui.toast(self, "Nothing printed yet in this session.", "warn")

    # ── Routing ─────────────────────────────────────────────────────
    def go(self, key, force=False):
        if not key:
            return
        admin_only = {k for k, _l, _i, a in NAV_ITEMS if a}
        if key in admin_only and not is_admin(self.user):
            ui.warn(self, "Not allowed",
                    "Only the shop owner can open that section.")
            return

        for w in self.content.winfo_children():
            w.destroy()
        self.page_key = key
        for k, b in self.nav_buttons.items():
            b.configure(fg_color=TH.SIDEBAR_HL if k == key else "transparent")

        page = self._make_page(key)
        self._page_cache[key] = page
        if page is None:
            ctk.CTkLabel(self.content, text="Coming soon",
                         font=ctk.CTkFont(size=F_SEC),
                         text_color=TH.TEXT_DIM).pack(pady=60)

    def _make_page(self, key):
        from .pages import (billing, bills, catalog, categories, customers,
                            dashboard, expenses, imei, mobiles, payments,
                            products, profile, reports, retailers, returns,
                            settings_page, staff)
        registry = {
            "dashboard": dashboard.DashboardPage,
            "billing": billing.BillingPage,
            "bills": bills.BillsPage,
            "products": products.ProductsPage,
            "mobiles": mobiles.MobilesPage,
            "imei": imei.WarrantyPage,
            "returns": returns.ReturnsPage,
            "retailers": retailers.RetailersPage,
            "customers": customers.CustomersPage,
            "payments": payments.PaymentsPage,
            "categories": categories.CategoriesPage,
            "catalog": catalog.CatalogPage,
            "staff": staff.StaffPage,
            "expenses": expenses.ExpensesPage,
            "reports": reports.ReportsPage,
            "settings": settings_page.SettingsPage,
            "profile": profile.ProfilePage,
        }
        cls = registry.get(key)
        if not cls:
            return None
        try:
            return cls(self.content, self)
        except Exception as exc:
            traceback.print_exc()
            ctk.CTkLabel(self.content,
                         text=f"Could not open this page:\n{exc}",
                         font=ctk.CTkFont(size=F_BODY),
                         text_color=TH.DANGER, justify="left").pack(pady=50)
            return None

    # ── Shared helpers used by pages ────────────────────────────────
    def is_admin(self):
        return is_admin(self.user)

    def staff_id(self):
        return self.user["id"] if self.user else None

    def currency(self):
        return self.settings.get("currency", "Rs.")

    def remember_pdf(self, path):
        self.last_pdf = path

    # ── Backup ──────────────────────────────────────────────────────
    def _auto_backup(self):
        """Nightly backup at the scheduled time (default 23:55).

        Checked on startup so a missed night is caught up, then re-armed to
        fire exactly on the next slot (capped at 30 min so the timer stays
        accurate if the PC sleeps).
        """
        try:
            if self.backup.due():
                ok, msg, _path = self.backup.run()
                if ok:
                    ui.toast(self, f"Nightly backup done — {msg}", "ok", 4000)
                else:
                    ui.toast(self, msg, "warn", 5000)
        except Exception:
            pass
        try:
            wait = min(self.backup.seconds_until_next() + 5, 30 * 60)
        except Exception:
            wait = 30 * 60
        self.after(max(wait, 30) * 1000, self._auto_backup)

    # ── Logout / close ──────────────────────────────────────────────
    def logout(self, ask=True):
        if ask and not ui.confirm(self, "Log out",
                                  "Log out of Bhumiraj?\n\n"
                                  "Any unsaved bill will be discarded."):
            return
        self._save_geometry()
        self.show_login()

    def _on_close(self):
        """X button. Logged in → offer logout. On login screen → offer quit."""
        if self.user:
            if ui.confirm(self, "Log out",
                          "Do you want to log out?\n\n"
                          "You will return to the login screen."):
                self.logout(ask=False)
            return
        if ui.confirm(self, "Quit Bhumiraj",
                      "Close Bhumiraj Mobile & Watch House?", danger=True):
            self.quit_app()

    def quit_app(self):
        self._save_geometry()
        try:
            if self.settings.get("auto_backup", True) and self.backup.due():
                self.backup.run()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        self.destroy()

    def _save_geometry(self):
        try:
            self.settings.set("window_geometry", self.winfo_geometry())
        except Exception:
            pass


def run():
    app = BhumirajApp()
    app.mainloop()
