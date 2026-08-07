"""Bill / receipt / statement / catalog PDFs.

Built on reportlab **platypus** (not raw canvas drawing) so every cell wraps
its own text and grows its own row — text can never overlap or run off the
page, no matter how long a product name or address is.

Page furniture (navy header band, shop details, footer) is painted by
`_PageFurniture` on every page; the flowables start below it.
"""
from __future__ import annotations

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from .config import (APP_NAME, LOGO_BILL, PDF_GOLD, PDF_GREY, PDF_LIGHT,
                     PDF_LINE, PDF_NAVY, SHOP_ADDRESS, SHOP_PHONE, VENDOR,
                     VENDOR_SITE, BILL_WHOLESALE)
from .services import (amount_in_words, attrs_summary, fmt, money,
                       unpack_attrs, warranty_state)

NAVY = colors.HexColor(PDF_NAVY)
GOLD = colors.HexColor(PDF_GOLD)
GREY = colors.HexColor(PDF_GREY)
LIGHT = colors.HexColor(PDF_LIGHT)
LINE = colors.HexColor(PDF_LINE)
WHITE = colors.white
BLACK = colors.HexColor("#1b1f2a")
RED = colors.HexColor("#b3342f")
GREEN = colors.HexColor("#1f8a55")

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
HEADER_H = 34 * mm          # navy band + shop line
FOOTER_H = 16 * mm

_styles = getSampleStyleSheet()


def _st(name, size, leading=None, color=BLACK, bold=False, align=TA_LEFT,
        space_after=0):
    return ParagraphStyle(
        name, parent=_styles["Normal"],
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading or (size + 2.4),
        textColor=color, alignment=align, spaceAfter=space_after)


S_CELL = _st("cell", 8.4)
S_CELL_B = _st("cellb", 8.4, bold=True)
S_CELL_R = _st("cellr", 8.4, align=TA_RIGHT)
S_CELL_RB = _st("cellrb", 8.4, bold=True, align=TA_RIGHT)
S_CELL_C = _st("cellc", 8.4, align=TA_CENTER)
S_SUB = _st("sub", 7.2, color=GREY)
S_TH = _st("th", 8.4, color=WHITE, bold=True)
S_TH_R = _st("thr", 8.4, color=WHITE, bold=True, align=TA_RIGHT)
S_TH_C = _st("thc", 8.4, color=WHITE, bold=True, align=TA_CENTER)
S_H2 = _st("h2", 10.5, color=NAVY, bold=True, space_after=3)
S_SMALL = _st("small", 7.6, color=GREY)
S_TERM = _st("term", 7.4, color=GREY, leading=10)


def _esc(text):
    """Make a value safe to drop into reportlab's mini-HTML."""
    txt = "" if text is None else str(text)
    return txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text, style=S_CELL, escape=True):
    """Paragraph. Set escape=False when the string already carries <b> markup
    and every piece of DATA inside it has been passed through _esc()."""
    txt = _esc(text) if escape else ("" if text is None else str(text))
    return Paragraph(txt or "&nbsp;", style)


def _label(label, value, style=S_SMALL):
    """'<b>Label:</b> value' with the value safely escaped."""
    return _p(f"<b>{_esc(label)}</b> {_esc(value)}", style, escape=False)


def _date(value, with_time=False):
    if not value:
        return ""
    raw = str(value)
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(raw[:19] if len(raw) > 10 else raw, f)
            return d.strftime("%d %b %Y, %I:%M %p" if with_time else "%d %b %Y")
        except ValueError:
            continue
    return raw[:10]


class _PageFurniture:
    """Draws the header band and footer on every page of a document."""

    def __init__(self, settings, doc_label, doc_number="", accent=NAVY):
        self.s = settings
        self.label = doc_label
        self.number = doc_number
        self.accent = accent

    def __call__(self, canvas, doc):
        canvas.saveState()
        self._header(canvas)
        self._footer(canvas, doc)
        canvas.restoreState()

    def _header(self, c):
        top = PAGE_H
        band_h = 24 * mm
        c.setFillColor(self.accent)
        c.rect(0, top - band_h, PAGE_W, band_h, stroke=0, fill=1)
        # gold rule under the band
        c.setFillColor(GOLD)
        c.rect(0, top - band_h - 1.6 * mm, PAGE_W, 1.6 * mm, stroke=0, fill=1)

        x = MARGIN
        # Logo in a white rounded chip so the navy artwork stays readable
        if LOGO_BILL and os.path.exists(LOGO_BILL):
            try:
                size = 17 * mm
                cy = top - band_h / 2 - size / 2
                c.setFillColor(WHITE)
                c.roundRect(x - 1.2 * mm, cy - 1.2 * mm, size + 2.4 * mm,
                            size + 2.4 * mm, 2.4 * mm, stroke=0, fill=1)
                c.drawImage(ImageReader(LOGO_BILL), x, cy, size, size,
                            preserveAspectRatio=True, mask="auto")
                x += size + 5 * mm
            except Exception:
                pass

        name = self.s.get("shop_name", APP_NAME)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(x, top - 10.5 * mm, name[:46])
        c.setFont("Helvetica", 8.2)
        c.setFillColor(colors.HexColor("#c8d4f0"))
        addr = self.s.get("shop_address", SHOP_ADDRESS)
        phone = self.s.get("shop_phone", SHOP_PHONE)
        alt = self.s.get("shop_phone_alt", "")
        phones = phone + (" / " + alt if alt else "")
        c.drawString(x, top - 15.2 * mm, addr[:60])
        c.drawString(x, top - 19.4 * mm, f"Phone: {phones}")

        # Document label on the right, inside the band
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 13)
        c.drawRightString(PAGE_W - MARGIN, top - 11 * mm, self.label.upper())
        if self.number:
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(PAGE_W - MARGIN, top - 16.4 * mm, self.number)
        c.setFillColor(colors.HexColor("#c8d4f0"))
        c.setFont("Helvetica", 7.4)
        c.drawRightString(PAGE_W - MARGIN, top - 20.6 * mm,
                          datetime.now().strftime("Printed %d %b %Y, %I:%M %p"))

    def _footer(self, c, doc):
        y = 11 * mm
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(MARGIN, y + 5 * mm, PAGE_W - MARGIN, y + 5 * mm)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 7)
        c.drawString(MARGIN, y + 1.5 * mm,
                     f"{self.s.get('shop_name', APP_NAME)}  ·  "
                     f"{self.s.get('shop_phone', SHOP_PHONE)}")
        c.setFont("Helvetica-Oblique", 6.6)
        c.drawCentredString(PAGE_W / 2, y + 1.5 * mm,
                            f"Software by {VENDOR} — {VENDOR_SITE}")
        c.setFont("Helvetica", 7)
        c.drawRightString(PAGE_W - MARGIN, y + 1.5 * mm, f"Page {doc.page}")


def _build_doc(path, settings, label, number, accent=NAVY, top_extra=0):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=HEADER_H + top_extra, bottomMargin=FOOTER_H,
        title=f"{label} {number}".strip(), author=settings.get("shop_name", APP_NAME))
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  PAGE_W - 2 * MARGIN,
                  PAGE_H - doc.topMargin - doc.bottomMargin,
                  id="body", showBoundary=0,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    furniture = _PageFurniture(settings, label, number, accent)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=furniture)])
    return doc


def _info_block(pairs_left, pairs_right, width):
    """Two side-by-side label/value cards that wrap instead of colliding.

    The inner tables are sized to the HALF they sit in, minus the outer cell
    padding — otherwise a long value (a handset name, a long address) runs out
    of its card and over the top of the one next to it.
    """
    gap = 6 * mm
    pad = 6                      # matches LEFTPADDING/RIGHTPADDING below
    half = (width - gap) / 2
    inner_w = half - (pad * 2)

    def mini(pairs):
        rows = [[_p(label, S_SUB), _p(value, S_CELL_B)] for label, value in pairs]
        t = Table(rows, colWidths=[inner_w * 0.34, inner_w * 0.66])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    outer = Table([[mini(pairs_left), "", mini(pairs_right)]],
                  colWidths=[half, gap, half])
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (0, 0), LIGHT),
        ("BACKGROUND", (2, 0), (2, 0), LIGHT),
        ("BOX", (0, 0), (0, 0), 0.6, LINE),
        ("BOX", (2, 0), (2, 0), 0.6, LINE),
    ]))
    return outer


def _totals_table(rows, width, currency="Rs."):
    data = []
    styles = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
    ]
    for i, (label, value, kind) in enumerate(rows):
        if kind == "grand":
            data.append([_p(label, _st("gl", 10, color=WHITE, bold=True)),
                         _p(value, _st("gv", 11, color=WHITE, bold=True,
                                       align=TA_RIGHT))])
            styles += [("BACKGROUND", (0, i), (-1, i), NAVY)]
        elif kind == "due":
            colr = RED if "0.00" not in value else GREEN
            data.append([_p(label, _st("dl", 9, color=colr, bold=True)),
                         _p(value, _st("dv", 9.6, color=colr, bold=True,
                                       align=TA_RIGHT))])
            styles += [("BACKGROUND", (0, i), (-1, i),
                        colors.HexColor("#fdf0ef") if colr == RED
                        else colors.HexColor("#eef8f2"))]
        else:
            data.append([_p(label, S_CELL), _p(value, S_CELL_RB)])
    t = Table(data, colWidths=[width * 0.52, width * 0.48])
    t.setStyle(TableStyle(styles))
    return t


# ═══════════════════════════════════════════════════════════════════════════
class DocumentGenerator:
    def __init__(self, settings, db):
        self.s = settings
        self.db = db

    def _cur(self):
        return self.s.get("currency", "Rs.")

    # ── BILL ────────────────────────────────────────────────────────
    def generate_bill(self, bill_id, output_path):
        cur = self._cur()
        bill = self.db.fetchone("SELECT * FROM bills WHERE id=?", (bill_id,))
        if not bill:
            raise ValueError("Bill not found.")
        items = self.db.fetchall(
            "SELECT * FROM bill_items WHERE bill_id=? ORDER BY id", (bill_id,))
        staff = self.db.fetchone("SELECT full_name FROM users WHERE id=?",
                                 (bill["staff_id"],))
        retailer = None
        if bill["retailer_id"]:
            retailer = self.db.fetchone("SELECT * FROM retailers WHERE id=?",
                                        (bill["retailer_id"],))

        is_ws = bill["bill_type"] == BILL_WHOLESALE
        label = "Wholesale Invoice" if is_ws else "Retail Bill"
        accent = colors.HexColor("#3b2f7a") if is_ws else NAVY

        doc = _build_doc(output_path, self.s, label, bill["bill_number"], accent)
        W = PAGE_W - 2 * MARGIN
        flow = [Spacer(1, 4 * mm)]

        # ── Party / bill info ────────────────────────────────────────
        if retailer:
            left = [("Retailer", retailer["name"] or "")]
            if retailer["shop_name"]:
                left.append(("Shop", retailer["shop_name"]))
            if retailer["phone"]:
                left.append(("Phone", retailer["phone"]))
            addr = ", ".join(p for p in (retailer["address"], retailer["city"]) if p)
            if addr:
                left.append(("Address", addr))
            if retailer["pan_number"]:
                left.append(("PAN", retailer["pan_number"]))
        else:
            left = [("Customer", bill["customer_name"] or "Walk-in")]
            if bill["customer_phone"]:
                left.append(("Phone", bill["customer_phone"]))

        right = [
            ("Bill No", bill["bill_number"]),
            ("Date", _date(bill["bill_date"], True)),
            ("Payment", bill["payment_method"] or "Cash"),
            ("Served by", (staff["full_name"] if staff else "—")),
        ]
        if bill["plan_type"] == "installment":
            right.append(("Plan", "Instalment / EMI"))
        flow.append(_info_block(left, right, W))
        flow.append(Spacer(1, 5 * mm))

        # ── Items ────────────────────────────────────────────────────
        col_no = 9 * mm
        col_qty = 14 * mm
        col_rate = 26 * mm
        col_amt = 30 * mm
        col_desc = W - (col_no + col_qty + col_rate + col_amt)

        data = [[_p("#", S_TH_C), _p("Description", S_TH),
                 _p("Qty", S_TH_C), _p(f"Rate ({cur})", S_TH_R),
                 _p(f"Amount ({cur})", S_TH_R)]]

        for idx, it in enumerate(items, 1):
            # Headline: brand + name + model  — model is always shown
            bits = [b for b in (it["product_brand"], it["product_name"]) if b]
            head = " ".join(bits) or "Item"
            model = (it["product_model"] or "").strip()
            if model and model.lower() not in head.lower():
                head = f"{head} — {model}"

            sub_lines = []
            extra = attrs_summary(unpack_attrs(it["attrs_snapshot"]), limit=6)
            if extra:
                sub_lines.append(extra)
            if it["imei"]:
                sub_lines.append(f"IMEI: {it['imei']}")
            if it["product_sku"]:
                sub_lines.append(f"SKU: {it['product_sku']}")
            if it["warranty_months"]:
                sub_lines.append(f"Warranty: {it['warranty_months']} months")

            cell = [_p(head, S_CELL_B)]
            for line in sub_lines:
                cell.append(_p(line, S_SUB))

            data.append([
                _p(str(idx), S_CELL_C),
                cell,
                _p(str(it["quantity"]), S_CELL_C),
                _p(f"{money(it['unit_price']):,.2f}", S_CELL_R),
                _p(f"{money(it['total_price']):,.2f}", S_CELL_RB),
            ])

        table = Table(data, colWidths=[col_no, col_desc, col_qty, col_rate, col_amt],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("VALIGN", (0, 1), (0, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#f7f9fd")]),
            ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
            ("BOX", (0, 0), (-1, -1), 0.7, LINE),
            ("LINEAFTER", (0, 0), (-2, -1), 0.35, LINE),
        ]))
        flow.append(table)
        flow.append(Spacer(1, 4 * mm))

        # ── Totals + words ───────────────────────────────────────────
        subtotal = money(bill["subtotal"])
        disc = money(bill["discount_amount"])
        total = money(bill["total_amount"])
        paid = money(bill["paid_amount"])
        due = money(total - paid)

        rows = [("Subtotal", f"{cur} {subtotal:,.2f}", "n")]
        if disc > 0:
            pct = (disc / subtotal * 100) if subtotal else 0
            rows.append((f"Discount ({pct:.1f}%)", f"− {cur} {disc:,.2f}", "n"))
        rows.append(("GRAND TOTAL", f"{cur} {total:,.2f}", "grand"))
        rows.append(("Paid", f"{cur} {paid:,.2f}", "n"))
        rows.append(("Balance Due", f"{cur} {due:,.2f}", "due"))

        words = _label("In words:", amount_in_words(total))
        status = (bill["payment_status"] or "paid").upper()
        badge_col = {"PAID": GREEN, "PARTIAL": GOLD}.get(status, RED)
        badge = Table([[_p(status, _st("bg", 9.5, color=WHITE, bold=True,
                                       align=TA_CENTER))]],
                      colWidths=[26 * mm], rowHeights=[7.5 * mm])
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), badge_col),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        left_stack = Table([[badge], [Spacer(1, 3 * mm)], [words]],
                           colWidths=[W * 0.54])
        left_stack.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        pair = Table([[left_stack, _totals_table(rows, W * 0.42, cur)]],
                     colWidths=[W * 0.56, W * 0.44])
        pair.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        flow.append(pair)
        flow.append(Spacer(1, 5 * mm))

        # ── IMEI / warranty note ─────────────────────────────────────
        imei_rows = [it for it in items if it["imei"]]
        if imei_rows:
            note = [_p("Handset & Warranty Details", S_H2)]
            for it in imei_rows:
                exp = ""
                reg = self.db.fetchone(
                    "SELECT warranty_expiry FROM imei_register WHERE imei=? "
                    "ORDER BY id DESC LIMIT 1", (it["imei"],))
                if reg and reg["warranty_expiry"]:
                    exp = f"  ·  Warranty valid till {_date(reg['warranty_expiry'])}"
                head_txt = _esc(" ".join(
                    x for x in (it["product_brand"], it["product_name"],
                                it["product_model"]) if x))
                note.append(_p(
                    f"{head_txt}  —  IMEI <b>{_esc(it['imei'])}</b>{_esc(exp)}",
                    S_SMALL, escape=False))
            box = Table([[note]], colWidths=[W])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf0")),
                ("BOX", (0, 0), (-1, -1), 0.6, GOLD),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            flow.append(KeepTogether(box))
            flow.append(Spacer(1, 4 * mm))

        if bill["notes"]:
            flow.append(_label("Note:", bill["notes"]))
            flow.append(Spacer(1, 3 * mm))

        flow.append(self._terms_and_signature(W))
        doc.build(flow)
        return output_path

    def _terms_and_signature(self, W):
        terms = self.s.get("bill_terms", "")
        term_cell = [_p("Terms & Conditions", _st("tt", 8.4, color=NAVY, bold=True))]
        for line in str(terms).splitlines():
            if line.strip():
                term_cell.append(_p("•  " + line.strip(), S_TERM))

        sign = [
            Spacer(1, 12 * mm),
            _p("_______________________", _st("sl", 8, color=GREY, align=TA_RIGHT)),
            _p("Authorised Signature", _st("sl2", 7.6, color=GREY, align=TA_RIGHT)),
        ]
        t = Table([[term_cell, sign]], colWidths=[W * 0.62, W * 0.38])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    # ── PAYMENT RECEIPT ─────────────────────────────────────────────
    def generate_receipt(self, receipt_number, output_path):
        """Receipt for a payment — covers FIFO splits across several bills."""
        cur = self._cur()
        rows = self.db.fetchall(
            "SELECT p.*, b.bill_number, b.total_amount, b.paid_amount, "
            "       b.bill_date, b.payment_status "
            "FROM payments p LEFT JOIN bills b ON p.bill_id = b.id "
            "WHERE p.receipt_number=? ORDER BY b.bill_date, p.id",
            (receipt_number,))
        if not rows:
            raise ValueError("Receipt not found.")

        first = rows[0]
        party_name, party_phone, party_kind = "Walk-in Customer", "", "Customer"
        remaining = 0.0
        if first["retailer_id"]:
            r = self.db.fetchone("SELECT * FROM retailers WHERE id=?",
                                 (first["retailer_id"],))
            if r:
                party_name = r["name"]
                party_phone = r["phone"] or ""
                party_kind = "Retailer"
            from .services import retailer_outstanding
            remaining = retailer_outstanding(self.db, first["retailer_id"])
        elif first["bill_id"]:
            b = self.db.fetchone("SELECT * FROM bills WHERE id=?",
                                 (first["bill_id"],))
            if b:
                party_name = b["customer_name"] or "Walk-in"
                party_phone = b["customer_phone"] or ""
                remaining = money(b["total_amount"]) - money(b["paid_amount"])

        total_received = money(sum(money(r["amount"]) for r in rows))
        staff = self.db.fetchone("SELECT full_name FROM users WHERE id=?",
                                 (first["staff_id"],))

        doc = _build_doc(output_path, self.s, "Payment Receipt", receipt_number,
                         colors.HexColor("#14663f"))
        W = PAGE_W - 2 * MARGIN
        flow = [Spacer(1, 4 * mm)]

        left = [(party_kind, party_name)]
        if party_phone:
            left.append(("Phone", party_phone))
        right = [
            ("Receipt No", receipt_number),
            ("Date", _date(first["payment_date"])),
            ("Method", first["payment_method"] or "Cash"),
            ("Received by", staff["full_name"] if staff else "—"),
        ]
        if first["reference"]:
            right.append(("Reference", first["reference"]))
        flow.append(_info_block(left, right, W))
        flow.append(Spacer(1, 5 * mm))

        # Big "received" banner
        banner = Table([[
            _p("AMOUNT RECEIVED", _st("brl", 9, color=WHITE, bold=True)),
            _p(f"{cur} {total_received:,.2f}",
               _st("brv", 17, color=WHITE, bold=True, align=TA_RIGHT)),
        ]], colWidths=[W * 0.5, W * 0.5], rowHeights=[14 * mm])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#14663f")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        flow.append(banner)
        flow.append(Spacer(1, 2.5 * mm))
        flow.append(_label("In words:", amount_in_words(total_received)))
        flow.append(Spacer(1, 5 * mm))

        # Allocation breakdown — this is what makes FIFO transparent
        allocated = [r for r in rows if r["bill_id"]]
        if allocated:
            flow.append(_p("Applied to Bills (oldest first)", S_H2))
            data = [[_p("#", S_TH_C), _p("Bill No", S_TH), _p("Bill Date", S_TH),
                     _p(f"Bill Total ({cur})", S_TH_R),
                     _p(f"Applied ({cur})", S_TH_R),
                     _p(f"Still Due ({cur})", S_TH_R)]]
            for i, r in enumerate(allocated, 1):
                still = money(money(r["total_amount"]) - money(r["paid_amount"]))
                data.append([
                    _p(str(i), S_CELL_C),
                    _p(r["bill_number"] or "—", S_CELL_B),
                    _p(_date(r["bill_date"]), S_CELL),
                    _p(f"{money(r['total_amount']):,.2f}", S_CELL_R),
                    _p(f"{money(r['amount']):,.2f}", S_CELL_RB),
                    _p(f"{still:,.2f}", S_CELL_R),
                ])
            t = Table(data, colWidths=[9 * mm, W * 0.20, W * 0.17,
                                       W * 0.19, W * 0.19, W * 0.19 - 9 * mm],
                      repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14663f")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [WHITE, colors.HexColor("#f4faf6")]),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 4 * mm))

        advance = money(sum(money(r["amount"]) for r in rows if not r["bill_id"]))
        summary = []
        if advance > 0:
            summary.append(("Kept as advance / credit", f"{cur} {advance:,.2f}", "n"))
        summary.append(("Remaining Outstanding", f"{cur} {money(remaining):,.2f}",
                        "due"))
        holder = Table([["", _totals_table(summary, W * 0.44, cur)]],
                       colWidths=[W * 0.56, W * 0.44])
        holder.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        flow.append(holder)
        flow.append(Spacer(1, 6 * mm))
        flow.append(self._terms_and_signature(W))
        doc.build(flow)
        return output_path

    # ── INSTALMENT RECEIPT (phone EMI) ──────────────────────────────
    def generate_installment_receipt(self, payment_id, output_path):
        cur = self._cur()
        pay = self.db.fetchone(
            "SELECT ip.*, r.imei, r.product_name, r.brand, r.model, r.color, "
            "       r.customer_name, r.customer_phone, r.total_amount, "
            "       r.down_payment, r.installment_amount, r.installment_months, "
            "       r.sold_date, r.bill_number, r.id AS reg_id "
            "FROM imei_payments ip JOIN imei_register r ON ip.register_id = r.id "
            "WHERE ip.id=?", (payment_id,))
        if not pay:
            raise ValueError("Instalment payment not found.")

        from .services import installment_progress
        total, paid, due, status = installment_progress(self.db, pay["reg_id"])

        doc = _build_doc(output_path, self.s, "Instalment Receipt",
                         pay["receipt_number"] or f"IP-{payment_id}",
                         colors.HexColor("#7a4a12"))
        W = PAGE_W - 2 * MARGIN
        flow = [Spacer(1, 4 * mm)]

        left = [("Customer", pay["customer_name"] or "—")]
        if pay["customer_phone"]:
            left.append(("Phone", pay["customer_phone"]))
        left.append(("Handset", " ".join(p for p in (pay["brand"],
                                                     pay["product_name"],
                                                     pay["model"]) if p)))
        left.append(("IMEI", pay["imei"]))
        right = [
            ("Receipt No", pay["receipt_number"] or f"IP-{payment_id}"),
            ("Date", _date(pay["payment_date"])),
            ("Method", pay["payment_method"] or "Cash"),
            ("Original Bill", pay["bill_number"] or "—"),
        ]
        flow.append(_info_block(left, right, W))
        flow.append(Spacer(1, 5 * mm))

        banner = Table([[
            _p("INSTALMENT RECEIVED", _st("il", 9, color=WHITE, bold=True)),
            _p(f"{cur} {money(pay['amount']):,.2f}",
               _st("iv", 17, color=WHITE, bold=True, align=TA_RIGHT)),
        ]], colWidths=[W * 0.5, W * 0.5], rowHeights=[14 * mm])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#7a4a12")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        flow.append(banner)
        flow.append(Spacer(1, 2.5 * mm))
        flow.append(_label("In words:", amount_in_words(pay["amount"])))
        flow.append(Spacer(1, 5 * mm))

        rows = [
            ("Handset Price", f"{cur} {money(total):,.2f}", "n"),
            ("Down Payment", f"{cur} {money(pay['down_payment']):,.2f}", "n"),
            ("Total Paid So Far", f"{cur} {money(paid):,.2f}", "grand"),
            ("Remaining Balance", f"{cur} {money(due):,.2f}", "due"),
        ]
        history = self.db.fetchall(
            "SELECT payment_date, amount, payment_method FROM imei_payments "
            "WHERE register_id=? ORDER BY payment_date, id", (pay["reg_id"],))
        hist_cell = [_p("Payment History", S_H2)]
        for h in history:
            hist_cell.append(_p(
                f"{_date(h['payment_date'])}  —  {cur} {money(h['amount']):,.2f} "
                f"({h['payment_method']})", S_SMALL))
        if pay["installment_amount"]:
            hist_cell.append(Spacer(1, 2 * mm))
            hist_cell.append(_p(
                f"Agreed instalment: {cur} {money(pay['installment_amount']):,.2f}"
                f" × {pay['installment_months'] or '—'} months", S_SMALL))

        pair = Table([[hist_cell, _totals_table(rows, W * 0.44, cur)]],
                     colWidths=[W * 0.56, W * 0.44])
        pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
        flow.append(pair)
        flow.append(Spacer(1, 6 * mm))
        flow.append(self._terms_and_signature(W))
        doc.build(flow)
        return output_path

    # ── STATEMENT OF ACCOUNT (retailer) ─────────────────────────────
    def generate_statement(self, retailer_id, date_from, date_to, output_path):
        cur = self._cur()
        r = self.db.fetchone("SELECT * FROM retailers WHERE id=?", (retailer_id,))
        if not r:
            raise ValueError("Retailer not found.")

        opening_bills = money(self.db.scalar(
            "SELECT COALESCE(SUM(total_amount),0) FROM bills "
            "WHERE retailer_id=? AND DATE(bill_date) < ?",
            (retailer_id, date_from), 0))
        opening_paid = money(self.db.scalar(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE retailer_id=? AND DATE(payment_date) < ?",
            (retailer_id, date_from), 0))
        opening = money(money(r["opening_balance"]) + opening_bills - opening_paid)

        bills = self.db.fetchall(
            "SELECT bill_number AS ref, bill_date AS dt, total_amount AS amt, "
            "       'bill' AS kind, payment_status AS st FROM bills "
            "WHERE retailer_id=? AND DATE(bill_date) BETWEEN ? AND ?",
            (retailer_id, date_from, date_to))
        pays = self.db.fetchall(
            "SELECT receipt_number AS ref, payment_date AS dt, amount AS amt, "
            "       'payment' AS kind, payment_method AS st FROM payments "
            "WHERE retailer_id=? AND DATE(payment_date) BETWEEN ? AND ?",
            (retailer_id, date_from, date_to))
        entries = sorted(list(bills) + list(pays),
                         key=lambda x: (str(x["dt"])[:10], x["kind"]))

        doc = _build_doc(output_path, self.s, "Statement of Account",
                         r["name"], colors.HexColor("#3b2f7a"))
        W = PAGE_W - 2 * MARGIN
        flow = [Spacer(1, 4 * mm)]

        left = [("Retailer", r["name"])]
        if r["shop_name"]:
            left.append(("Shop", r["shop_name"]))
        if r["phone"]:
            left.append(("Phone", r["phone"]))
        addr = ", ".join(p for p in (r["address"], r["city"]) if p)
        if addr:
            left.append(("Address", addr))
        right = [
            ("Period From", _date(date_from)),
            ("Period To", _date(date_to)),
            ("Opening Balance", f"{cur} {opening:,.2f}"),
            ("Generated", datetime.now().strftime("%d %b %Y")),
        ]
        flow.append(_info_block(left, right, W))
        flow.append(Spacer(1, 5 * mm))

        data = [[_p("Date", S_TH), _p("Particulars", S_TH), _p("Ref", S_TH),
                 _p(f"Debit ({cur})", S_TH_R), _p(f"Credit ({cur})", S_TH_R),
                 _p(f"Balance ({cur})", S_TH_R)]]
        running = opening
        data.append([_p(_date(date_from), S_CELL),
                     _p("Opening Balance", S_CELL_B), _p("—", S_CELL),
                     _p("—", S_CELL_R), _p("—", S_CELL_R),
                     _p(f"{running:,.2f}", S_CELL_RB)])

        total_debit = total_credit = 0.0
        for e in entries:
            amt = money(e["amt"])
            if e["kind"] == "bill":
                running = money(running + amt)
                total_debit = money(total_debit + amt)
                data.append([_p(_date(e["dt"]), S_CELL),
                             _p(f"Invoice ({e['st']})", S_CELL),
                             _p(e["ref"] or "—", S_CELL),
                             _p(f"{amt:,.2f}", S_CELL_R),
                             _p("—", S_CELL_R),
                             _p(f"{running:,.2f}", S_CELL_RB)])
            else:
                running = money(running - amt)
                total_credit = money(total_credit + amt)
                data.append([_p(_date(e["dt"]), S_CELL),
                             _p(f"Payment ({e['st']})", S_CELL),
                             _p(e["ref"] or "—", S_CELL),
                             _p("—", S_CELL_R),
                             _p(f"{amt:,.2f}", S_CELL_R),
                             _p(f"{running:,.2f}", S_CELL_RB)])

        data.append([_p("", S_CELL), _p("CLOSING BALANCE", S_CELL_B),
                     _p("", S_CELL),
                     _p(f"{total_debit:,.2f}", S_CELL_RB),
                     _p(f"{total_credit:,.2f}", S_CELL_RB),
                     _p(f"{running:,.2f}", S_CELL_RB)])

        t = Table(data, colWidths=[W * 0.13, W * 0.29, W * 0.16,
                                   W * 0.14, W * 0.14, W * 0.14], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b2f7a")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8e5f6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2),
             [WHITE, colors.HexColor("#f7f6fc")]),
            ("BOX", (0, 0), (-1, -1), 0.7, LINE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.35, LINE),
            ("LINEABOVE", (0, -1), (-1, -1), 0.9, colors.HexColor("#3b2f7a")),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 4 * mm))
        flow.append(_label("Closing balance in words:",
                           amount_in_words(running)))
        flow.append(Spacer(1, 6 * mm))
        flow.append(self._terms_and_signature(W))
        doc.build(flow)
        return output_path

    # ── PRODUCT CATALOG ─────────────────────────────────────────────
    def generate_catalog(self, output_path, category_ids=None,
                         price_mode="retail", include_images=True,
                         only_in_stock=False):
        """Printable / shareable price list, grouped by category.

        price_mode: 'retail' | 'wholesale' | 'both' | 'none'
        Cost price is NEVER printed — a catalog is a customer-facing document.
        """
        cur = self._cur()
        doc = _build_doc(output_path, self.s, "Product Catalog",
                         datetime.now().strftime("%b %Y"))
        W = PAGE_W - 2 * MARGIN
        flow = [Spacer(1, 3 * mm)]

        where = ["p.is_active = 1"]
        params = []
        if category_ids:
            where.append("p.category_id IN (%s)"
                         % ",".join("?" * len(category_ids)))
            params += list(category_ids)
        if only_in_stock:
            where.append("p.stock_quantity > 0")

        cats = self.db.fetchall(
            "SELECT DISTINCT c.id, c.name, c.kind FROM categories c "
            "JOIN products p ON p.category_id = c.id "
            "WHERE " + " AND ".join(where) + " ORDER BY c.name", params)

        if not cats:
            flow.append(_p("No products match the selected filters.", S_CELL))
            doc.build(flow)
            return output_path

        for ci, cat in enumerate(cats):
            rows = self.db.fetchall(
                "SELECT * FROM products p WHERE " + " AND ".join(where)
                + " AND p.category_id = ? ORDER BY p.brand, p.name",
                params + [cat["id"]])
            if not rows:
                continue

            title = Table([[_p(cat["name"].upper(),
                               _st("ct", 11, color=WHITE, bold=True))]],
                          colWidths=[W], rowHeights=[8.5 * mm])
            title.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]))
            flow.append(title)
            flow.append(Spacer(1, 2 * mm))

            img_w = 16 * mm if include_images else 0
            price_cols = {"both": 2, "none": 0}.get(price_mode, 1)
            col_price = 28 * mm      # wide enough that the header never wraps
            col_stock = 16 * mm
            col_desc = W - img_w - col_stock - (col_price * price_cols)

            header = ([_p("Photo", S_TH_C)] if include_images else []) \
                + [_p("Product", S_TH)]
            if price_mode in ("retail", "both"):
                header.append(_p(f"Retail ({cur})", S_TH_R))
            if price_mode in ("wholesale", "both"):
                header.append(_p(f"Wholesale ({cur})", S_TH_R))
            header.append(_p("Stock", S_TH_C))
            data = [header]

            for pr in rows:
                cells = []
                if include_images:
                    img_path = pr["image_path"]
                    if img_path and os.path.exists(img_path):
                        try:
                            cells.append(Image(img_path, width=13 * mm,
                                               height=13 * mm,
                                               kind="proportional"))
                        except Exception:
                            cells.append(_p("—", S_CELL_C))
                    else:
                        cells.append(_p("—", S_CELL_C))

                head = " ".join(p for p in (pr["brand"], pr["name"]) if p)
                model = (pr["model"] or "").strip()
                if model and model.lower() not in head.lower():
                    head = f"{head} — {model}"
                block = [_p(head, S_CELL_B)]
                extra = attrs_summary(unpack_attrs(pr["attrs"]), limit=5)
                if extra:
                    block.append(_p(extra, S_SUB))
                if pr["warranty_months"]:
                    block.append(_p(f"Warranty: {pr['warranty_months']} months",
                                    S_SUB))
                cells.append(block)

                if price_mode in ("retail", "both"):
                    cells.append(_p(f"{money(pr['sell_price']):,.2f}", S_CELL_RB))
                if price_mode in ("wholesale", "both"):
                    wp = money(pr["wholesale_price"]) or money(pr["sell_price"])
                    cells.append(_p(f"{wp:,.2f}", S_CELL_R))

                qty = int(pr["stock_quantity"])
                stock_style = S_CELL_C if qty > 0 else _st(
                    "oos", 8.4, color=RED, bold=True, align=TA_CENTER)
                cells.append(_p(str(qty) if qty > 0 else "Out", stock_style))
                data.append(cells)

            widths = ([img_w] if include_images else []) + [col_desc]
            widths += [col_price] * price_cols
            widths += [col_stock]

            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2645a0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [WHITE, colors.HexColor("#f7f9fd")]),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 6 * mm))
            if ci < len(cats) - 1 and len(rows) > 14:
                flow.append(PageBreak())

        flow.append(_p("Prices are subject to change without prior notice. "
                       "Please confirm availability before ordering.", S_TERM))
        doc.build(flow)
        return output_path
