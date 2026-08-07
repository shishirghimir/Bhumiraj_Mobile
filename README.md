# Bhumiraj Mobile & Watch House — Retail + Wholesale

Complete shop management system for **Bhumiraj Mobile & Watch House**,
Chabahil-7, Kathmandu — **9808773134**.

Python + CustomTkinter (GUI) · SQLite (database) · ReportLab (PDF).
One shared database, one shareable Windows `.exe`.

*Built by **Netanix Labs** — visit **netanixctf.com***

---

## Run it (no build needed)

Double-click **`RUN_APP.bat`**, or:

```
pip install -r requirements.txt
python main.py
```

### First login

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `Admin@123` |

You are **forced to set your own password** on first login (8+ characters
with an uppercase letter, a lowercase letter and a number).
Recovery PIN is `1234` and the security answer is `chabahil` — change both in
**Settings → Security**.

---

## The two roles

### Owner / Admin — sees and does everything

Dashboard (revenue, COGS, profit, dues, stock value) · New Bill · Bills History ·
Products & Stock · Mobiles (IMEI) · Warranty & Instalments · Returns ·
Retailers · Customers · Payments · Categories · Product Catalog · Staff ·
Expenses · Reports · Settings.

### Counter Staff — sells, never manages

| Staff CAN | Staff CANNOT |
|-----------|--------------|
| Create retail **and** wholesale bills | See any **cost price (CP)** |
| Print / WhatsApp a bill | See revenue, profit or margin |
| Look up products and stock | Add, edit, delete or adjust stock |
| Register handset IMEIs and warranties | Delete a bill |
| Process returns | Record retailer payments |
| See their own sales count | See a retailer's dues, history or statement |

Staff see **Wholesale price and Retail price only** — the cost price never
appears on their screen, not even in the product table columns.

---

## Pricing — three prices per product

| Price | Who sees it | Used for |
|-------|-------------|----------|
| **Cost Price (CP)** | Owner only | Profit and margin reporting |
| **Wholesale Price** | Owner + Staff | Wholesale bills to retailers |
| **Retail Price** | Owner + Staff | Retail bills to walk-in customers |

Switching a bill between Retail and Wholesale automatically re-prices every
line.

---

## Billing

* **Retail** — walk-in customer name + phone.
* **Wholesale** — pick a retailer; their credit ledger is updated.
* **Search that actually finds things** — type any words in any order; it
  matches name, brand, model, SKU, barcode, variant, details and category.
  **No result limit** — every match is listed and the table scrolls.
* **Category filter chips** — All · 📱 Mobiles · ⌚ Watches · 🔌 Chargers &
  Cables · 🕶 Sunglasses · 🎧 Accessories · 🔧 Services · 📦 Others.
* Each result row shows **Product · Brand · Model · Details · Stock · Price**.
* **Selling a phone** opens a handset picker: choose the exact IMEI, set the
  warranty, then choose **Full payment** or **Instalment / EMI** (with a live
  preview of the monthly amount).
* Money math: `total = subtotal − discount`, `due = total − paid`,
  status **PAID / PARTIAL / UNPAID**.

## Sending a bill on WhatsApp

Click **📲 SAVE & WHATSAPP** (or WhatsApp from Bills History):

1. the PDF is placed on the Windows clipboard
2. the customer's WhatsApp chat opens with the message already typed
3. **you press Ctrl+V** in the chat and the PDF attaches

Nothing is sent automatically — you always press send yourself.

## Retailers and FIFO

Outstanding = opening balance + unpaid bill dues − unallocated advances.

**Record Payment** applies the money to the **oldest unpaid bills first**, and
shows a preview of exactly which bills get how much *before* you confirm.
Anything left over is kept as an advance credit. The receipt PDF prints the
full breakdown.

**Statement of Account** — a date-range ledger PDF (debit / credit / running
balance) you can print or send on WhatsApp.

## Products

The product form asks **different questions per category type**:

| Category type | Asks for |
|---|---|
| Mobile Phone | Colour, Storage, RAM, Network, Condition, Battery, Box contents |
| Watch | Dial colour, Movement, Strap, Dial size, Water resistance, For |
| Accessory | Colour, Connector, Wattage, Compatibility, Quality grade |
| Glasses | Frame colour, Frame material, Lens type, Power, For |
| Service | Duration, Default technician |

**Brand and Model are mandatory** — the form refuses to save without them, so
they always print correctly on the bill.
Products also take a **photo**, used in the catalog PDF.

**Deleting a product removes it completely.** Old bills still print correctly
because every bill line keeps its own snapshot of the name, brand, model, SKU
and price.

## Mobiles (IMEI)

One row per physical handset — IMEI, IMEI2, serial, colour, storage, RAM,
condition, cost and price. Paste a list of IMEIs to register a whole box at
once. A handset can only be sold once; the app blocks a second attempt.

## Warranty & Instalments

Every handset sold is registered with its warranty expiry. Phones sold on EMI
show the balance owed; **Collect Instalment** records a payment and prints a
receipt showing the full payment history and remaining balance.

## Product Catalog

Build a price-list PDF: choose categories, choose **retail / wholesale / both /
no prices**, include photos, in-stock only. Print it or send it on WhatsApp.
**Cost price is never printed on a catalog.**

## Backup — automatic, to Google Drive

**Settings → Automatic Backup:**

* choose a folder (a **Google Drive Desktop** folder → it syncs to the cloud)
* the database is copied there **automatically once a day**
* copies older than **3 days** are deleted so the folder never fills up
* **Backup Now**, **Export Database** and **Import Database** are always
  available

Import is safe: the incoming file is integrity- and schema-checked, a safety
copy of the current database is taken first, and if anything is wrong **nothing
is changed**.

## Security

* Passwords: **PBKDF2-HMAC-SHA256**, per-user random salt, 200,000 iterations
* All SQL is parameterised — no injection
* Staff restrictions are enforced in the data layer, not just hidden in the UI
* Every login attempt is recorded (**Settings → Login History**)
* Owner creates every staff account; staff must change their password on first
  login

## Closing the app

Clicking **X** while logged in asks **"Do you want to log out?"** and returns
you to the login screen. Clicking **X** on the login screen asks
**"Close Bhumiraj Mobile & Watch House?"** before quitting.

## Keyboard shortcuts

`F1` new bill · `F2` save · `F3` jump to search · `F5` refresh ·
`Ctrl+N` new bill · `Ctrl+B` bills history · `Ctrl+P` reprint last document

---

## Testing

```
python run_tests.py     # 250+ headless checks: money, FIFO, stock, PDFs, backup
python gui_smoke.py     # builds every page for both roles against real data
```

`run_tests.py` includes a geometric check that opens the generated PDFs and
verifies **no two pieces of text overlap** and nothing runs off the page.

`BUILD_EXE.bat` runs the test suite first and refuses to build if anything
fails.

---

## Build the shareable EXE

```
BUILD_EXE.bat
```

Output: `dist\Bhumiraj\Bhumiraj.exe`.
Give the shop the **whole `dist\Bhumiraj` folder**. Data lives in a `data\`
folder next to the exe, so it travels with the app.

---

## Project layout

```
bhumiraj_mobile_watch/
├─ main.py                 entry point
├─ RUN_APP.bat             run with Python
├─ BUILD_EXE.bat           test + build the exe
├─ Bhumiraj.spec           PyInstaller config
├─ run_tests.py            headless test suite
├─ gui_smoke.py            builds every page for both roles
├─ requirements.txt
├─ logo.png / logo_bill.png / logo_trans.png / logo.ico
├─ data/                   database, bills, receipts, catalogs, backups, photos
└─ bhumiraj/
   ├─ config.py            paths, theme, category field schemas
   ├─ security.py          PBKDF2 hashing + password rules
   ├─ database.py          schema, transactions, backup/restore
   ├─ settings.py          settings + daily backup manager
   ├─ services.py          money math, FIFO, stock, auth
   ├─ pdf.py               bill / receipt / statement / catalog PDFs
   ├─ whatsapp.py          clipboard PDF + open chat
   ├─ ui_helpers.py        widgets, tables, filter chips, dialogs
   ├─ app.py               window, login, sidebar, routing
   └─ pages/               one module per screen (18 of them)
```

`legacy_v1_main.py.bak` is the previous single-file version, kept for
reference only — it is not used by the app.
