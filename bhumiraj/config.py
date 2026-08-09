"""Paths, theme, fonts and the category-driven product field schemas.

ONE source of truth — every other module imports from here.
"""
from __future__ import annotations

import os
import sys

# ─── Paths ─────────────────────────────────────────────────────────────────
def get_app_dir():
    """Folder for writable data (DB, bills, backups) — next to the EXE/script.

    BHUMIRAJ_HOME overrides it, which lets the test suite run against a
    throwaway folder and lets the shop keep its data on another drive.
    """
    override = os.environ.get("BHUMIRAJ_HOME", "").strip()
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_dir():
    """Bundled read-only resources (logo, icon).

    Deliberately NOT affected by BHUMIRAJ_HOME — the logo ships with the code,
    while BHUMIRAJ_HOME only moves the writable data folder.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    if getattr(sys, "frozen", False):
        cand = os.path.join(os.path.dirname(sys.executable), "_internal")
        if os.path.isdir(cand):
            return cand
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_resource(name):
    for root in (get_resource_dir(), get_app_dir()):
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
    return os.path.join(get_resource_dir(), name)


APP_DIR = get_app_dir()
DATA_DIR = os.path.join(APP_DIR, "data")
BILLS_DIR = os.path.join(DATA_DIR, "bills")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")
STAFF_PHOTOS_DIR = os.path.join(DATA_DIR, "staff_photos")
PRODUCT_IMG_DIR = os.path.join(DATA_DIR, "product_images")
CATALOG_DIR = os.path.join(DATA_DIR, "catalogs")

for _d in (DATA_DIR, BILLS_DIR, RECEIPTS_DIR, BACKUPS_DIR,
           STAFF_PHOTOS_DIR, PRODUCT_IMG_DIR, CATALOG_DIR):
    os.makedirs(_d, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "bhumiraj.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
ERROR_LOG = os.path.join(DATA_DIR, "error_log.txt")

LOGO_PATH = find_resource("logo.png")        # circular badge — sidebar / login
LOGO_BILL = find_resource("logo_bill.png")   # flattened RGB — PDF header
LOGO_SMALL = find_resource("logo_small.png")
LOGO_ICO = find_resource("logo.ico")

# ─── Identity ──────────────────────────────────────────────────────────────
APP_NAME = "Bhumiraj Mobile & Watch House"
APP_SHORT = "BHUMIRAJ"
APP_TAGLINE = "MOBILE & WATCH HOUSE"
APP_VERSION = "2.0"

SHOP_PHONE = "9808773134"
SHOP_ADDRESS = "Chabahil-7, Kathmandu"
SHOP_EST = "Est. 2082"

VENDOR = "Netanix Labs"
VENDOR_SITE = "netanixctf.com"
VENDOR_LINE = f"by {VENDOR}  ·  visit {VENDOR_SITE}"

CURRENCY = "Rs."
COUNTRY_CODE = "977"

# ─── Theme — navy + gold, matched to the shop logo ─────────────────────────
class TH:
    BG          = "#101828"   # main canvas
    PANEL       = "#18213a"   # card / panel
    PANEL_ALT   = "#1f2a48"   # raised card
    SIDEBAR     = "#0d1b3e"   # deep navy (logo blue)
    SIDEBAR_HV  = "#1a2c5c"   # sidebar hover
    SIDEBAR_HL  = "#2645a0"   # sidebar selected
    BORDER      = "#2a3654"
    TEXT        = "#eef2f8"
    TEXT_DIM    = "#93a2c4"
    ACCENT      = "#ffc734"   # gold
    ACCENT_DIM  = "#b8912a"
    NAVY        = "#12296b"   # brand navy for PDFs / buttons
    NAVY_HV     = "#0c1d4d"
    OK          = "#1f8a55"
    OK_HV       = "#166b41"
    WARN        = "#e08a12"
    DANGER      = "#b3342f"
    DANGER_HV   = "#8a2622"
    INFO        = "#3f6ea8"
    INFO_HV     = "#2f5586"
    MUTED       = "#3a4463"
    MUTED_HV    = "#2c3450"
    # status colours (Treeview tag foregrounds)
    OOS         = "#f26a6a"
    LOW         = "#e8a020"
    POS         = "#4fc98a"
    WHOLESALE   = "#8f7ae6"   # tag colour for wholesale bills

# PDF colours (reportlab HexColor strings)
PDF_NAVY = "#12296b"
PDF_GOLD = "#c8951a"
PDF_GREY = "#5b6478"
PDF_LIGHT = "#eef1f7"
PDF_LINE = "#c9d1e2"

# ─── Font sizes ────────────────────────────────────────────────────────────
F_TITLE = 24
F_SEC = 18
F_LBL = 14
F_BODY = 13
F_SM = 11
F_TN = 9

# ─── Roles ─────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"

# What staff may NEVER see. Enforced in the data/UI layer, not just hidden.
STAFF_FORBIDDEN = {
    "cost_price",       # CP is admin-only — staff see wholesale + retail only
    "profit",
    "margin",
    "revenue_totals",
    "retailer_ledger",  # outstanding dues / statements / sales history
    "expenses",
    "reports",
}

# ─── Bill types ────────────────────────────────────────────────────────────
BILL_RETAIL = "retail"
BILL_WHOLESALE = "wholesale"
BILL_PREFIX = {BILL_RETAIL: "BR", BILL_WHOLESALE: "BW"}

PAYMENT_METHODS = ["Cash", "eSewa", "Khalti", "Fonepay", "IME Pay",
                   "Bank Transfer", "Cheque", "Card", "Credit"]

PLAN_FULL = "full"
PLAN_INSTALLMENT = "installment"

# ─── Category kinds → which product fields to ask for ──────────────────────
# Each entry: (field_key, Label, widget, options_or_None)
#   widget: "text" | "num" | "int" | "combo"
KIND_MOBILE = "mobile"
KIND_WATCH = "watch"
KIND_ACCESSORY = "accessory"
KIND_EYEWEAR = "eyewear"
KIND_SERVICE = "service"
KIND_GENERAL = "general"

KIND_LABELS = {
    KIND_MOBILE: "Mobile Phone",
    KIND_WATCH: "Watch",
    KIND_ACCESSORY: "Accessory",
    KIND_EYEWEAR: "Glasses / Eyewear",
    KIND_SERVICE: "Service / Repair",
    KIND_GENERAL: "General",
}

STORAGE_OPTS = ["", "8GB", "16GB", "32GB", "64GB", "128GB", "256GB", "512GB", "1TB"]
RAM_OPTS = ["", "1GB", "2GB", "3GB", "4GB", "6GB", "8GB", "12GB", "16GB"]
NETWORK_OPTS = ["", "2G", "3G", "4G", "4G VoLTE", "5G"]
CONDITION_OPTS = ["New", "Used", "Refurbished", "Display Piece", "Exchange"]
MOVEMENT_OPTS = ["", "Quartz", "Automatic", "Mechanical", "Digital",
                 "Chronograph", "Smart Watch", "Solar"]
STRAP_OPTS = ["", "Leather", "Stainless Steel", "Silicone", "Rubber",
              "Nylon", "Fabric", "Ceramic", "Titanium", "Gold Plated"]
WATER_OPTS = ["", "Not Water Resistant", "Splash Proof", "3 ATM", "5 ATM",
              "10 ATM", "20 ATM", "IP67", "IP68"]
CONNECTOR_OPTS = ["", "Type-C", "Micro USB", "Lightning", "3.5mm Jack",
                  "USB-A", "Wireless", "Magnetic", "N/A"]
QUALITY_OPTS = ["", "Original", "OG Quality", "A+ Copy", "Copy", "Local",
                "Refurbished"]
COMPATIBILITY_OPTS = ["", "Android", "iPhone", "iPad", "iPhone & iPad",
                      "Universal", "Men", "Women", "Unisex", "Kids", "N/A"]
LENS_OPTS = ["", "Sun / UV", "Blue Cut", "Reading", "Prescription",
             "Photochromic", "Polarised", "Plain"]
FRAME_OPTS = ["", "Metal", "Plastic", "TR90", "Acetate", "Titanium",
              "Rimless", "Half Rim"]
WARRANTY_OPTS = ["0", "1", "3", "6", "12", "18", "24", "36"]

# Fields stored in the `attrs` JSON column, per category kind.
KIND_FIELDS = {
    KIND_MOBILE: [
        ("color",       "Colour",            "text",  None),
        ("storage",     "Storage",           "combo", STORAGE_OPTS),
        ("ram",         "RAM",               "combo", RAM_OPTS),
        ("network",     "Network",           "combo", NETWORK_OPTS),
        ("condition",   "Condition",         "combo", CONDITION_OPTS),
        ("battery",     "Battery (mAh)",     "text",  None),
        ("box_items",   "Box Contents",      "text",  None),
    ],
    KIND_WATCH: [
        ("color",       "Dial Colour",       "text",  None),
        ("movement",    "Movement",          "combo", MOVEMENT_OPTS),
        ("strap",       "Strap Material",    "combo", STRAP_OPTS),
        ("dial_size",   "Dial Size (mm)",    "text",  None),
        ("water",       "Water Resistance",  "combo", WATER_OPTS),
        ("gender",      "For",               "combo", ["", "Men", "Women", "Unisex", "Kids"]),
    ],
    KIND_ACCESSORY: [
        ("color",       "Colour",            "text",  None),
        ("connector",   "Connector Type",    "combo", CONNECTOR_OPTS),
        ("wattage",     "Wattage / Capacity", "text", None),
        ("compat",      "Compatibility",     "combo", COMPATIBILITY_OPTS),
        ("quality",     "Quality Grade",     "combo", QUALITY_OPTS),
    ],
    KIND_EYEWEAR: [
        ("color",       "Frame Colour",      "text",  None),
        ("frame",       "Frame Material",    "combo", FRAME_OPTS),
        ("lens",        "Lens Type",         "combo", LENS_OPTS),
        ("power",       "Power / Number",    "text",  None),
        ("gender",      "For",               "combo", ["", "Men", "Women", "Unisex", "Kids"]),
    ],
    KIND_SERVICE: [
        ("duration",    "Typical Duration",  "text",  None),
        ("technician",  "Default Technician", "text", None),
    ],
    KIND_GENERAL: [
        ("color",       "Colour",            "text",  None),
        ("variant_note", "Variant / Note",   "text",  None),
    ],
}

# Categories seeded on first run: (name, code, kind)
SEED_CATEGORIES = [
    ("Mobile Phones",            "MOB", KIND_MOBILE),
    ("Feature Phones",           "FTP", KIND_MOBILE),
    ("Tablets",                  "TAB", KIND_MOBILE),
    ("Smart Watches",            "SMW", KIND_WATCH),
    ("Wrist Watches",            "WAT", KIND_WATCH),
    ("Wall Clocks",              "CLK", KIND_WATCH),
    ("Glasses (Sun)",            "SUN", KIND_EYEWEAR),
    ("Glasses (Reading)",        "REA", KIND_EYEWEAR),
    ("Cases & Covers",           "CSE", KIND_ACCESSORY),
    ("Chargers",                 "CHR", KIND_ACCESSORY),
    ("Cables",                   "CBL", KIND_ACCESSORY),
    ("Earphones & Headphones",   "HDP", KIND_ACCESSORY),
    ("Bluetooth Speakers",       "SPK", KIND_ACCESSORY),
    ("Power Banks",              "PWR", KIND_ACCESSORY),
    ("Memory Cards & Drives",    "MEM", KIND_ACCESSORY),
    ("Tempered Glass",           "TEM", KIND_ACCESSORY),
    ("Selfie Sticks / Tripods",  "TRP", KIND_ACCESSORY),
    ("Watch Bands",              "BND", KIND_WATCH),
    ("Watch Batteries",          "BAT", KIND_ACCESSORY),
    ("SIM & Recharge",           "SIM", KIND_GENERAL),
    ("Repair Services",          "RPR", KIND_SERVICE),
    ("Accessories (Other)",      "ACC", KIND_ACCESSORY),
    ("Others",                   "OTH", KIND_GENERAL),
]

EXPENSE_CATEGORIES = ["Rent", "Salary", "Electricity", "Water", "Internet",
                      "Purchase", "Transport", "Repair Tools", "Marketing",
                      "Tax / VAT", "Maintenance", "Tea / Snacks", "Other"]

RETURN_REASONS = ["Defective", "Wrong Item", "Customer Changed Mind",
                  "Damaged in Transit", "Warranty Claim", "Size / Fit",
                  "Duplicate Order", "Other"]

# ─── Backup policy ─────────────────────────────────────────────────────────
BACKUP_TIME = "23:55"          # nightly backup runs at this time
BACKUP_INTERVAL_HOURS = 24     # one backup per day
BACKUP_RETENTION_DAYS = 3      # delete backups older than this

DEFAULT_SETTINGS = {
    "shop_name": APP_NAME,
    "shop_address": SHOP_ADDRESS,
    "shop_phone": SHOP_PHONE,
    "shop_phone_alt": "",
    "shop_email": "",
    "shop_pan": "",
    "currency": CURRENCY,
    "theme": "dark",
    "default_payment": "Cash",
    "low_stock_threshold": 3,
    "bill_terms": "Goods once sold will only be exchanged within 7 days with the bill.\n"
                  "Warranty covers manufacturing defects only — physical or liquid damage is void.",
    "auto_backup": True,
    "backup_folder": "",          # user picks a Google Drive folder
    "backup_time": BACKUP_TIME,   # nightly run time (24h, HH:MM)
    "backup_retention_days": BACKUP_RETENTION_DAYS,
    "last_backup": "",
    "window_geometry": "1360x820+30+24",
    "whatsapp_enabled": True,
}
