"""Génération des devis, factures et états annuels OpenFabLab."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, Line
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    Indenter,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BLUE = "#2e718f"
BLUE_DARK = "#1f5065"
RED = "#e30613"
LIGHT = "#eef3f4"
MID = "#d9e2e4"
TEXT = "#20282b"

# No installation-specific financial or contact fallback is distributable.
SERVICE_NAME = "Mon FabLab"
SERVICE_ADDRESS = SERVICE_PHONE = SERVICE_EMAIL = PUBLIC_ENTITY = ""
BILLING_ADDRESS = SIRET = VAT_NUMBER = IBAN = BIC = ACCOUNT_HOLDER = ""


def _document_identity(structure=None):
    """Use persisted installation settings and neutral empty fallbacks."""
    structure = structure or {}
    return {
        "name": structure.get("name", SERVICE_NAME),
        "description": structure.get("description", "Espace de fabrication numérique"),
        "address": structure.get("address", SERVICE_ADDRESS),
        "email": structure.get("email", SERVICE_EMAIL),
        "phone": structure.get("phone", SERVICE_PHONE),
        "legal_entity": structure.get("legal_entity", PUBLIC_ENTITY),
        "billing_address": structure.get("billing_address", BILLING_ADDRESS),
        "siret": structure.get("siret", SIRET),
        "vat_number": structure.get("vat_number", VAT_NUMBER),
        "vat_note": structure.get("vat_note", ""),
        "iban": structure.get("iban", IBAN),
        "bic": structure.get("bic", BIC),
        "account_holder": structure.get("account_holder", ACCOUNT_HOLDER),
        "payment_terms": structure.get("payment_terms", ""),
        "rental_terms": structure.get("rental_terms", ""),
    }

# Machine data and rental terms are provided by the installation, not this source.
RENTAL_CATALOG = {}
RENTAL_CONDITION_SECTIONS = ()


def money(cents: int | None) -> str:
    """Formate un montant entier en centimes sans approximation flottante."""
    cents = int(cents or 0)
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


def french_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def status_label(record: dict) -> str:
    if record.get("quote_cancelled_at"):
        return "Devis annulé"
    if record.get("paid_at"):
        return "Facture offerte" if int(record.get("amount_cents") or 0) == 0 else "Facture payée"
    if record.get("invoice_sent_at"):
        return "Facture envoyée"
    if record.get("invoice_number"):
        return "Facture prête"
    if record.get("quote_signed_at"):
        return "Devis signé"
    return "Devis"


def invoice_stamp(record: dict) -> tuple[str, str, str]:
    """Retourne le libellé et les couleurs du cartouche de règlement."""
    if int(record.get("amount_cents") or 0) == 0 and record.get("paid_at"):
        return "FACTURE OFFERTE", "#176a35", "#e4f5e9"
    if record.get("paid_at"):
        return (
            f"FACTURE PAYÉE LE {french_date(record['paid_at'])}",
            "#176a35",
            "#e4f5e9",
        )
    return "FACTURE À PAYER", "#9d2f2f", "#fff0ef"


def line_items(record: dict, structure: dict | None = None) -> list[dict]:
    """Calcule les lignes financières depuis les choix enregistrés."""
    if record.get("billing_type") == "rental":
        months = int(record.get("rental_months") or 1)
        monthly_cents = int(record.get("rental_monthly_cents") or 0)
        contract_fee_cents = int(
            2500 if record.get("rental_contract_fee_cents") is None
            else record.get("rental_contract_fee_cents")
        )
        delivery_fee_cents = int(
            3000 if record.get("rental_delivery_fee_cents") is None
            else record.get("rental_delivery_fee_cents")
        )
        items = [{
            "description": f"Location · {record.get('rental_machine_name') or 'Machine'}",
            "quantity": months,
            "unit_cents": monthly_cents,
            "total_cents": months * monthly_cents,
        }, {
            "description": "Frais fixes de contrat et de préparation",
            "quantity": 1,
            "unit_cents": contract_fee_cents,
            "total_cents": contract_fee_cents,
        }]
        if record.get("rental_delivery"):
            items.append({
                "description": "Livraison, installation et prise en main sur site",
                "quantity": 1,
                "unit_cents": delivery_fee_cents,
                "total_cents": delivery_fee_cents,
            })
        return items

    rate_prices = {
        ("agglo", "hourly"): ("Créneau réservable · tarif structure", 0),
        ("agglo", "half_day"): ("Créneau réservable · demi-journée structure", 0),
        ("normal", "hourly"): ("Créneau réservable · tarif horaire", 6000),
        ("normal", "half_day"): ("Créneau réservable · demi-journée", 12000),
        ("reduced", "hourly"): ("Créneau réservable · tarif réduit horaire", 3000),
        ("reduced", "half_day"): ("Créneau réservable · demi-journée réduite", 6000),
    }
    category = "agglo" if record.get("rate_is_agglo") else record["rate_category"]
    description, default_unit_cents = rate_prices[(category, record["rate_unit"])]
    if record.get("custom_tariff_key"):
        description = record.get("custom_tariff_name") or description
    unit_cents = int(
        record.get("rate_unit_cents")
        if record.get("rate_unit_cents") is not None
        else default_unit_cents
    )
    quantity = int(record.get("rate_quantity") or 0)
    items = [{
        "description": description,
        "quantity": quantity,
        "unit_cents": unit_cents,
        "total_cents": quantity * unit_cents,
    }]
    travel_quantity = int(record.get("travel_quantity") or 0)
    if travel_quantity:
        travel_unit_cents = int(
            6000 if record.get("travel_unit_cents") is None
            else record.get("travel_unit_cents")
        )
        items.append({
            "description": "Déplacement hors secteur",
            "quantity": travel_quantity,
            "unit_cents": travel_unit_cents,
            "total_cents": travel_quantity * travel_unit_cents,
        })
    consumable_mode = record.get("consumable_mode") or "included"
    consumable_quantity = int(record.get("consumable_quantity") or 0)
    if consumable_mode == "billed" and consumable_quantity:
        consumable_unit_cents = int(
            3000 if record.get("consumable_unit_cents") is None
            else record.get("consumable_unit_cents")
        )
        items.append({
            "description": "Forfait consommables",
            "quantity": consumable_quantity,
            "unit_cents": consumable_unit_cents,
            "total_cents": consumable_quantity * consumable_unit_cents,
        })
    else:
        label = (
            f"Consommables fournis gracieusement par {(structure or {}).get('name', SERVICE_NAME)}"
            if consumable_mode == "included"
            else "Consommables à apporter par le client"
        )
        items.append({
            "description": label,
            "quantity": 1,
            "unit_cents": 0,
            "total_cents": 0,
        })
    return items


def compute_total_cents(record: dict) -> int:
    return sum(item["total_cents"] for item in line_items(record))


def _set_cell_fill(cell, color: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color.lstrip("#"))
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_margins(cell, top=100, start=120, bottom=100, end=120) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for key, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{key}"))
        if node is None:
            node = OxmlElement(f"w:{key}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _docx_add_run(paragraph, text, *, size=10, bold=False, color=TEXT):
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
    return run


def _configure_docx(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(1.35)
    section.bottom_margin = Cm(1.35)
    section.left_margin = Cm(1.55)
    section.right_margin = Cm(1.55)
    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(9.5)
    styles["Normal"].paragraph_format.space_after = Pt(4)
    styles["Title"].font.name = "Arial"
    styles["Title"].font.size = Pt(25)
    styles["Title"].font.bold = True
    styles["Title"].font.color.rgb = RGBColor.from_string(BLUE_DARK.lstrip("#"))
    styles["Heading 1"].font.name = "Arial"
    styles["Heading 1"].font.size = Pt(13)
    styles["Heading 1"].font.bold = True
    styles["Heading 1"].font.color.rgb = RGBColor.from_string(BLUE_DARK.lstrip("#"))


def generate_document_docx(
    record: dict,
    document_kind: str,
    agglo_logo_path: Path | None,
    fablab_logo_path: Path | None = None,
    structure: dict | None = None,
) -> bytes:
    """Produit un DOCX éditable, institutionnel et identifiable Fablab."""
    if document_kind not in {"quote", "invoice"}:
        raise ValueError("Type de document inconnu")
    is_invoice = document_kind == "invoice"
    number = record.get("invoice_number") if is_invoice else record["quote_number"]
    date_value = record.get("invoice_date") if is_invoice else record["quote_date"]
    identity = _document_identity(structure)

    document = Document()
    _configure_docx(document)
    section = document.sections[0]

    header = document.add_table(rows=1, cols=4)
    header.alignment = WD_TABLE_ALIGNMENT.CENTER
    header.autofit = False
    header.columns[0].width = Cm(2.0)
    header.columns[1].width = Cm(2.0)
    header.columns[2].width = Cm(7.2)
    header.columns[3].width = Cm(5.8)
    agglo_cell, fablab_cell, brand_cell, title_cell = header.rows[0].cells
    agglo_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    fablab_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    brand_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    title_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    if agglo_logo_path and agglo_logo_path.exists():
        agglo_cell.paragraphs[0].add_run().add_picture(str(agglo_logo_path), width=Cm(1.55))
    if fablab_logo_path and fablab_logo_path.exists():
        fablab_cell.paragraphs[0].add_run().add_picture(str(fablab_logo_path), width=Cm(1.5))
    for cell in (agglo_cell, fablab_cell):
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = brand_cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_add_run(p, identity["name"], size=13, bold=True, color=RED)
    p = brand_cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_add_run(p, identity["description"], size=8.3, bold=True, color=BLUE_DARK)
    p = brand_cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_add_run(p, identity["address"], size=8)
    p = title_cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _docx_add_run(p, "FACTURE" if is_invoice else "DEVIS", size=26, bold=True, color=BLUE_DARK)
    p = title_cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _docx_add_run(p, f"N° {number}", size=13, bold=True, color=RED)
    if is_invoice:
        p = title_cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _docx_add_run(p, f"Devis d’origine n° {record['quote_number']}", size=8.2, color=BLUE_DARK)
    p = title_cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _docx_add_run(p, french_date(date_value), size=9)

    motif = document.add_paragraph()
    motif.alignment = WD_ALIGN_PARAGRAPH.CENTER
    motif.paragraph_format.space_before = Pt(2)
    motif.paragraph_format.space_after = Pt(6)
    _docx_add_run(motif, "● ───────────── ○ ── ⚙ ── ○ ───────────── ●", size=8, color=BLUE)

    client = document.add_table(rows=1, cols=1)
    client.alignment = WD_TABLE_ALIGNMENT.CENTER
    client.autofit = False
    destination = client.rows[0].cells[0]
    destination.width = Cm(17)
    _set_cell_fill(destination, LIGHT)
    _set_cell_margins(destination, 140, 190, 140, 190)
    p = destination.paragraphs[0]
    _docx_add_run(p, "DESTINATAIRE", size=8, bold=True, color=RED)
    p = destination.add_paragraph()
    _docx_add_run(p, record["client_structure"], size=12, bold=True, color=BLUE_DARK)
    p = destination.add_paragraph()
    _docx_add_run(
        p,
        f"{record['client_contact']} · {record['address_line']} · {record['postal_code']} {record['city']}",
        size=9,
        bold=True,
    )
    p = destination.add_paragraph()
    _docx_add_run(
        p,
        " · ".join(filter(None, [record.get("email"), record.get("phone")]))
        or "Coordonnées non renseignées",
        size=8.6,
    )

    document.add_paragraph()
    schedule = document.add_table(rows=1, cols=2)
    schedule.alignment = WD_TABLE_ALIGNMENT.CENTER
    schedule.style = "Table Grid"
    for cell, (label, value) in zip(schedule.rows[0].cells, (
        ("DATE", french_date(record["activity_date"])),
        ("HORAIRE", record.get("activity_time_details") or "À convenir"),
    )):
        _set_cell_fill(cell, LIGHT)
        _set_cell_margins(cell, 100, 130, 100, 130)
        _docx_add_run(cell.paragraphs[0], label, size=7.5, bold=True, color=RED)
        _docx_add_run(cell.add_paragraph(), value, size=9.5, bold=True, color=BLUE_DARK)

    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(2)
    heading = document.add_paragraph(style="Heading 1")
    heading.add_run("Description de l'activité")
    p = document.add_paragraph()
    _docx_add_run(p, record["title"], size=11, bold=True)
    p = document.add_paragraph()
    _docx_add_run(p, record["description"], size=9.5)

    document.add_paragraph()
    table = document.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    labels = ("Désignation", "Quantité", "Prix unitaire HT", "Total HT")
    for index, label in enumerate(labels):
        cell = table.rows[0].cells[index]
        _set_cell_fill(cell, BLUE_DARK)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if index >= 1 else WD_ALIGN_PARAGRAPH.LEFT
        _docx_add_run(p, label, size=8.5, bold=True, color="#ffffff")
    for item in line_items(record, structure):
        cells = table.add_row().cells
        values = (
            item["description"], str(item["quantity"]), money(item["unit_cents"]), money(item["total_cents"])
        )
        for index, value in enumerate(values):
            p = cells[index].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if index >= 1 else WD_ALIGN_PARAGRAPH.LEFT
            _docx_add_run(p, value, size=8.5)
    total_row = table.add_row().cells
    total_row[0].merge(total_row[2])
    _set_cell_fill(total_row[0], LIGHT)
    _set_cell_fill(total_row[3], LIGHT)
    p = total_row[0].paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _docx_add_run(p, "TOTAL HT", size=10, bold=True, color=BLUE_DARK)
    p = total_row[3].paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _docx_add_run(p, money(record["amount_cents"]), size=11, bold=True, color=BLUE_DARK)

    p = document.add_paragraph()
    _docx_add_run(p, "", size=8.5)

    if is_invoice:
        stamp_text, stamp_color, stamp_fill = invoice_stamp(record)
        stamp = document.add_table(rows=1, cols=1)
        stamp.alignment = WD_TABLE_ALIGNMENT.RIGHT
        stamp.autofit = False
        stamp.rows[0].cells[0].width = Cm(6.4)
        _set_cell_fill(stamp.rows[0].cells[0], stamp_fill)
        _set_cell_margins(stamp.rows[0].cells[0], 90, 120, 90, 120)
        p = stamp.rows[0].cells[0].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _docx_add_run(p, stamp_text, size=10.5, bold=True, color=stamp_color)

    if record.get("billing_type") == "rental":
        deposit = (
            0
            if record.get("rental_deposit_exempt")
            else int(record.get("rental_deposit_cents") or 0)
        )
        p = document.add_paragraph()
        _docx_add_run(
            p,
            f"Caution : {'dispensée' if not deposit else money(deposit)} · "
            f"Retour prévu le {french_date(record.get('rental_end_date'))}",
            size=9.2,
            bold=True,
            color=BLUE_DARK,
        )

    heading = document.add_paragraph(style="Heading 1")
    heading.add_run("Conditions et règlement")
    if is_invoice:
        paragraphs = [
            identity["payment_terms"],
            "Merci d’indiquer le numéro de facture dans le libellé du virement.",
        ]
    else:
        paragraphs = [
            "Le devis est valable 30 jours à compter de sa date d’émission.",
            (
                "La location devient ferme après réception du devis daté et signé avec la mention « Bon pour accord »."
                if record.get("billing_type") == "rental"
                else "La réservation devient ferme après réception du devis daté et signé avec la mention « Bon pour accord »."
            ),
            "Les coordonnées bancaires et les modalités de règlement seront transmises avec la facture après réalisation de l’activité.",
        ]
    for text in paragraphs:
        p = document.add_paragraph(style="List Bullet")
        _docx_add_run(p, text, size=10)
    if is_invoice:
        bank = document.add_table(rows=4, cols=2)
        bank.style = "Table Grid"
        bank.alignment = WD_TABLE_ALIGNMENT.CENTER
        bank_values = (
            ("Titulaire", identity["account_holder"]),
            ("IBAN", identity["iban"]),
            ("BIC", identity["bic"]),
            ("Référence", f"Facture {number}"),
        )
        for row, (label, value) in zip(bank.rows, bank_values):
            _set_cell_fill(row.cells[0], LIGHT)
            _docx_add_run(row.cells[0].paragraphs[0], label, size=9, bold=True, color=BLUE_DARK)
            _docx_add_run(row.cells[1].paragraphs[0], value, size=9)
    else:
        acceptance = document.add_table(rows=2, cols=2)
        acceptance.style = "Table Grid"
        acceptance.alignment = WD_TABLE_ALIGNMENT.CENTER
        acceptance.autofit = False
        acceptance.columns[0].width = Cm(8.5)
        acceptance.columns[1].width = Cm(8.5)
        for cell, label in zip(
            acceptance.rows[0].cells,
            ("DATE ET LIEU", "MENTION MANUSCRITE"),
        ):
            _set_cell_fill(cell, LIGHT)
            _set_cell_margins(cell, 90, 130, 90, 130)
            _docx_add_run(cell.paragraphs[0], label, size=8, bold=True, color=RED)
        _docx_add_run(acceptance.rows[0].cells[0].add_paragraph(), "Date :\nLieu :", size=9)
        _docx_add_run(
            acceptance.rows[0].cells[1].add_paragraph(),
            "« Bon pour Accord »",
            size=9.5,
            bold=True,
            color=BLUE_DARK,
        )
        acceptance.rows[1].cells[0].merge(acceptance.rows[1].cells[1])
        signature_cell = acceptance.rows[1].cells[0]
        _set_cell_margins(signature_cell, 90, 130, 700, 130)
        _docx_add_run(signature_cell.paragraphs[0], "SIGNATURE DU CLIENT", size=8, bold=True, color=RED)

    if record.get("billing_type") == "rental":
        document.add_page_break()
        heading = document.add_paragraph(style="Heading 1")
        heading.add_run("Conditions particulières de location")
        rental_sections = ([("Conditions de location", identity["rental_terms"].splitlines())]
                           if identity["rental_terms"] else
                           RENTAL_CONDITION_SECTIONS if identity["name"] == SERVICE_NAME else [])
        for section_title, paragraphs in rental_sections:
            p = document.add_paragraph()
            _docx_add_run(p, section_title, size=10, bold=True, color=BLUE_DARK)
            for sentence in paragraphs:
                p = document.add_paragraph(style="List Bullet")
                _docx_add_run(p, sentence, size=9.1)
        p = document.add_paragraph()
        _docx_add_run(
            p,
            f"Le matériel demeure la propriété de {identity['legal_entity'] or identity['name']}. "
            "Ce document et le devis signé constituent le dossier de location.",
            size=9.3,
            bold=True,
            color=BLUE_DARK,
        )

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_add_run(
        footer,
        f"{identity['legal_entity']} · {identity['billing_address'].replace(chr(10), ' · ')} · "
        f"SIRET {identity['siret']} · TVA {identity['vat_number']}\n"
        f"{identity['email']} · {identity['phone']}",
        size=7.5,
        color="#5f6b70",
    )

    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _pdf_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("BillingTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=colors.HexColor(BLUE_DARK), alignment=TA_RIGHT, spaceAfter=3),
        "subtitle": ParagraphStyle("BillingSubtitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(RED), alignment=TA_RIGHT),
        "h1": ParagraphStyle("BillingH1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor(BLUE_DARK), spaceBefore=8, spaceAfter=6),
        "body": ParagraphStyle("BillingBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor(TEXT)),
        "small": ParagraphStyle("BillingSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#5f6b70")),
        "small_right": ParagraphStyle("BillingSmallRight", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#5f6b70"), alignment=TA_RIGHT),
        "right": ParagraphStyle("BillingRight", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_RIGHT),
        "center": ParagraphStyle("BillingCenter", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER),
    }


def _pdf_footer(canvas, doc, identity=None):
    identity = identity or _document_identity()
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(MID))
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#5f6b70"))
    footer_line_one = (
        f"{identity['legal_entity']} · {identity['billing_address'].replace(chr(10), ' · ')} · SIRET {identity['siret']}"
    )
    footer_line_two = f"{identity['email']} · {identity['phone']}"
    canvas.drawCentredString(A4[0] / 2, 10.5 * mm, footer_line_one)
    canvas.drawCentredString(A4[0] / 2, 7.7 * mm, footer_line_two)
    canvas.restoreState()


def _pdf_image(path: Path | None, max_width: float, max_height: float):
    if not path or not path.exists():
        return None
    image = Image(str(path))
    image._restrictSize(max_width, max_height)
    return image


def _pdf_gear_motif() -> Drawing:
    """Dessine un engrenage exactement centré entre deux filets bleus."""
    width = 160 * mm
    height = 5 * mm
    center_x = width / 2
    center_y = height / 2
    drawing = Drawing(width, height)
    gear_color = colors.HexColor(BLUE)
    radius = 1.35 * mm
    drawing.add(Line(0, center_y, center_x - 7 * mm, center_y, strokeColor=gear_color, strokeWidth=0.8))
    drawing.add(Line(center_x + 7 * mm, center_y, width, center_y, strokeColor=gear_color, strokeWidth=0.8))
    drawing.add(Circle(center_x, center_y, radius, strokeColor=gear_color, fillColor=None, strokeWidth=0.8))
    drawing.add(Circle(center_x, center_y, 0.42 * mm, strokeColor=colors.HexColor(RED), fillColor=None, strokeWidth=0.7))
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (.7, .7), (.7, -.7), (-.7, -.7), (-.7, .7)):
        drawing.add(Line(
            center_x + dx * radius,
            center_y + dy * radius,
            center_x + dx * 1.75 * mm,
            center_y + dy * 1.75 * mm,
            strokeColor=gear_color,
            strokeWidth=0.75,
        ))
    return drawing


def _pdf_content_block(flowables: list, width: float = 160 * mm) -> Table:
    """Aligne un groupe de contenus sur les modules centraux du document."""
    block = Table([[flowables]], colWidths=[width], hAlign="CENTER")
    block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return block


def generate_document_pdf(
    record: dict,
    document_kind: str,
    agglo_logo_path: Path | None,
    fablab_logo_path: Path | None = None,
    structure: dict | None = None,
) -> bytes:
    """Produit le PDF officiel d'un devis ou d'une facture."""
    if document_kind not in {"quote", "invoice"}:
        raise ValueError("Type de document inconnu")
    is_invoice = document_kind == "invoice"
    number = record.get("invoice_number") if is_invoice else record["quote_number"]
    date_value = record.get("invoice_date") if is_invoice else record["quote_date"]
    identity = _document_identity(structure)
    stream = io.BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=21 * mm,
        title=f"{'Facture' if is_invoice else 'Devis'} {number}",
        author=identity["legal_entity"] or identity["name"],
    )
    styles = _pdf_styles()
    agglo_logo = _pdf_image(agglo_logo_path, 16 * mm, 16 * mm) or Paragraph(escape(identity["legal_entity"]), styles["small"])
    fablab_logo = _pdf_image(fablab_logo_path, 16 * mm, 16 * mm) or Paragraph(escape(identity["name"]), styles["small"])
    brand = Paragraph(
        f"<font color='{RED}' size='13'><b>{escape(identity['name'])}</b></font><br/>"
        f"<font color='{BLUE_DARK}' size='8'><b>{escape(identity['description'])}</b></font><br/>"
        f"<font size='7'>{escape(identity['address'])}</font>",
        ParagraphStyle("HeaderBrand", parent=styles["body"], alignment=TA_CENTER),
    )
    title = [
        Paragraph("FACTURE" if is_invoice else "DEVIS", styles["title"]),
        Paragraph(f"N° {escape(str(number))}", styles["subtitle"]),
        *([Paragraph(f"Devis d’origine n° {escape(str(record['quote_number']))}", styles["small_right"])] if is_invoice else []),
        Paragraph(french_date(date_value), styles["right"]),
    ]
    header = Table([[agglo_logo, fablab_logo, brand, title]], colWidths=[21 * mm, 21 * mm, 90 * mm, 42 * mm], hAlign="CENTER")
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (1, 0), "CENTER"),
        ("ALIGN", (3, 0), (3, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story = [header, Spacer(1, 2 * mm), _pdf_gear_motif(), Spacer(1, 5 * mm)]

    destination = (
        f"<font color='{RED}' size='7'><b>DESTINATAIRE</b></font><br/>"
        f"<font color='{BLUE_DARK}' size='11'><b>{escape(record['client_structure'])}</b></font><br/>"
        f"<b>{escape(record['client_contact'])}</b> · "
        f"{escape(record['address_line'])} · {escape(record['postal_code'])} {escape(record['city'])}<br/>"
        f"{escape(record.get('email') or 'Coordonnées non renseignées')}"
        f"{' · ' + escape(record['phone']) if record.get('phone') else ''}"
    )
    client_table = Table(
        [[Paragraph(destination, styles["body"])]],
        colWidths=[160 * mm],
        hAlign="CENTER",
    )
    client_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(MID)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([client_table, Spacer(1, 5 * mm)])
    schedule = Table([[Paragraph(
        f"<font color='{RED}' size='7'><b>DATE</b></font><br/>"
        f"<font color='{BLUE_DARK}'><b>{french_date(record['activity_date'])}</b></font>",
        styles["body"],
    ), Paragraph(
        f"<font color='{RED}' size='7'><b>HORAIRE</b></font><br/>"
        f"<font color='{BLUE_DARK}'><b>{escape(record.get('activity_time_details') or 'À convenir')}</b></font>",
        styles["body"],
    )]], colWidths=[80 * mm, 80 * mm], hAlign="CENTER")
    schedule.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(MID)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(MID)),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    description_block = _pdf_content_block([
        Paragraph("Description de l'activité", styles["h1"]),
        Paragraph(f"<b>{escape(record['title'])}</b>", styles["body"]),
        Paragraph(escape(record["description"]).replace("\n", "<br/>"), styles["body"]),
    ])
    story.extend([schedule, Spacer(1, 7 * mm), description_block, Spacer(1, 4 * mm)])
    data = [["Désignation", "Qté", "Prix unitaire HT", "Total HT"]]
    for item in line_items(record, structure):
        data.append([item["description"], str(item["quantity"]), money(item["unit_cents"]), money(item["total_cents"])])
    data.append(["", "", "TOTAL HT", money(record["amount_cents"])])
    pricing = Table(data, colWidths=[91 * mm, 14 * mm, 28 * mm, 27 * mm], repeatRows=1, hAlign="CENTER")
    pricing.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(LIGHT)),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor(MID)),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([
        pricing,
        Spacer(1, 2 * mm),
        Paragraph("", styles["small"]),
    ])
    if is_invoice:
        stamp_text, stamp_color, stamp_fill = invoice_stamp(record)
        paid_stamp = Table([[Paragraph(
            f"<b>{escape(stamp_text)}</b>",
            ParagraphStyle("PaidStamp", parent=styles["body"], textColor=colors.HexColor(stamp_color), alignment=TA_CENTER),
        )]], colWidths=[60 * mm], hAlign="RIGHT")
        paid_stamp.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(stamp_color)),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(stamp_fill)),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([Spacer(1, 2 * mm), paid_stamp])
    if record.get("billing_type") == "rental":
        deposit = 0 if record.get("rental_deposit_exempt") else int(record.get("rental_deposit_cents") or 0)
        story.append(Paragraph(
            f"<b>Caution :</b> {'dispensée' if not deposit else money(deposit)} · "
            f"<b>Retour prévu :</b> {french_date(record.get('rental_end_date'))}",
            styles["body"],
        ))
    condition_flowables = [Paragraph("Conditions et règlement", styles["h1"])]
    if is_invoice:
        condition_flowables.extend([
            Paragraph(escape(identity["payment_terms"]) + " Merci d’indiquer le numéro de facture dans le libellé du virement.", styles["body"]),
            Spacer(1, 3 * mm),
        ])
        bank = Table([
            ["Titulaire", identity["account_holder"]],
            ["IBAN", identity["iban"]],
            ["BIC", identity["bic"]],
            ["Référence", f"Facture {number}"],
        ], colWidths=[35 * mm, 125 * mm], hAlign="CENTER")
        bank.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(LIGHT)),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor(MID)),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        condition_flowables.append(bank)
    else:
        subject = "location" if record.get("billing_type") == "rental" else "réservation"
        condition_flowables.append(Paragraph(
            f"Devis valable 30 jours. La {subject} devient ferme après réception du devis daté et signé avec la mention « Bon pour accord ». Les coordonnées bancaires seront transmises avec la facture après réalisation de la prestation.",
            styles["body"],
        ))
        acceptance = Table([
            [Paragraph("<font color='%s' size='7'><b>DATE ET LIEU</b></font><br/><br/>Date :<br/>Lieu :" % RED, styles["body"]),
             Paragraph("<font color='%s' size='7'><b>MENTION MANUSCRITE</b></font><br/><br/><b>« Bon pour Accord »</b>" % RED, styles["body"])],
            [Paragraph("<font color='%s' size='7'><b>SIGNATURE DU CLIENT</b></font><br/><br/><br/><br/>" % RED, styles["body"]), ""],
        ], colWidths=[80 * mm, 80 * mm], hAlign="CENTER")
        acceptance.setStyle(TableStyle([
            ("SPAN", (0, 1), (1, 1)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(MID)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        condition_flowables.extend([Spacer(1, 4 * mm), acceptance])
    story.extend([Spacer(1, 7.5 * mm), _pdf_content_block(condition_flowables)])
    if record.get("billing_type") == "rental":
        rental_condition_flowables = [Paragraph("Conditions particulières de location", styles["h1"])]
        rental_sections = ([("Conditions de location", identity["rental_terms"].splitlines())]
                           if identity["rental_terms"] else
                           RENTAL_CONDITION_SECTIONS if identity["name"] == SERVICE_NAME else [])
        for section_title, paragraphs in rental_sections:
            rental_condition_flowables.append(Paragraph(f"<b>{escape(section_title)}</b>", styles["body"]))
            for text in paragraphs:
                rental_condition_flowables.append(Paragraph(f"• {escape(text)}", styles["body"]))
            rental_condition_flowables.append(Spacer(1, 0.5 * mm))
        rental_condition_flowables.append(Paragraph(
            f"<b>Le matériel demeure la propriété de {escape(identity['legal_entity'] or identity['name'])}. "
            "Ce document et le devis signé constituent le dossier de location.</b>",
            styles["body"],
        ))
        story.extend([
            PageBreak(),
            Indenter(left=7 * mm, right=7 * mm),
            *rental_condition_flowables,
            Indenter(left=-7 * mm, right=-7 * mm),
        ])
    footer = lambda canvas, doc: _pdf_footer(canvas, doc, identity)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def generate_client_directory_pdf(clients: list[dict], structure: dict | None = None) -> bytes:
    """Crée un annuaire clients lisible et imprimable au format PDF."""
    stream = io.BytesIO()
    identity = _document_identity(structure)
    document = SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Annuaire des clients {identity['name']}",
        author=identity["legal_entity"] or identity["name"],
    )
    styles = _pdf_styles()
    story = [
        Paragraph("Annuaire des clients", ParagraphStyle(
            "ClientDirectoryTitle", parent=styles["title"], alignment=TA_LEFT
        )),
        Paragraph(
            escape(identity["name"] + " - " + identity["description"] +
                   ""),
            styles["body"],
        ),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y')}", styles["small"]),
        Spacer(1, 5 * mm),
    ]
    headers = [
        "Contact", "Structure", "Adresse", "CP / Commune",
        "Téléphone", "E-mail", "Devis, factures et dossiers liés",
    ]
    header_style = ParagraphStyle(
        "ClientDirectoryHeader", parent=styles["small"],
        fontName="Helvetica-Bold", fontSize=7, leading=8.2, textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "ClientDirectoryCell", parent=styles["small"], fontSize=6.8, leading=8.1,
    )
    linked_style = ParagraphStyle(
        "ClientDirectoryLinked", parent=styles["small"], fontSize=6.4, leading=7.7,
    )

    def cell(value, style=cell_style):
        return Paragraph(escape("—" if value in (None, "") else str(value)), style)

    def linked_cell(client):
        linked_records = client.get("linked_records") or []
        if not linked_records:
            return Paragraph("Aucun dossier lié", linked_style)
        lines = []
        for record in linked_records:
            references = [f"Devis {record.get('quote_number')}" if record.get("quote_number") else ""]
            if record.get("invoice_number"):
                references.append(f"Facture {record['invoice_number']}")
            references = " · ".join(reference for reference in references if reference)
            title = escape(record.get("title") or "Dossier sans nom")
            detail = escape(references or "Sans numéro")
            lines.append(f"<b>{title}</b><br/><font size='6'>{detail}</font>")
        return Paragraph("<br/><br/>".join(lines), linked_style)

    data = [[cell(label, header_style) for label in headers]]
    for client in clients:
        locality = " ".join(part for part in [client.get("postal_code"), client.get("city")] if part)
        data.append([
            cell(client.get("contact_name")), cell(client.get("structure_name")),
            cell(client.get("address_line")), cell(locality), cell(client.get("phone")),
            cell(client.get("email")), linked_cell(client),
        ])
    if not clients:
        data.append([cell("Aucune fiche client"), "", "", "", "", "", ""])
    table = Table(
        data,
        colWidths=[29*mm, 31*mm, 43*mm, 31*mm, 24*mm, 42*mm, 75*mm],
        repeatRows=1,
    )
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(MID)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_number in range(1, len(data)):
        table_style.append((
            "BACKGROUND", (0, row_number), (-1, row_number),
            colors.white if row_number % 2 else colors.HexColor(LIGHT),
        ))
    table.setStyle(TableStyle(table_style))
    story.append(table)
    document.build(story)
    return stream.getvalue()


def generate_facdepot_pdf(
    records: list[dict],
    year: int,
    signature_path: Path | None = None,
    structure: dict | None = None,
) -> bytes:
    stream = io.BytesIO()
    identity = _document_identity(structure)
    document = SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Bilan de facturation {year} {identity['name']}",
        author=identity["legal_entity"] or identity["name"],
    )
    styles = _pdf_styles()
    story = [
        Paragraph(f"Bilan annuel de facturation · {year}", ParagraphStyle("FacTitle", parent=styles["title"], alignment=TA_LEFT)),
        Paragraph(
            escape(identity["name"] + " - " + identity["description"] +
                   ""),
            styles["body"],
        ),
        Paragraph(
            f"Export certifié le {datetime.now().strftime('%d/%m/%Y')}",
            styles["small"],
        ),
        Spacer(1, 5 * mm),
    ]
    headers = ["Facture", "Structure", "Contact", "Édition", "Désignation", "Montant HT", "Statut", "Date statut", "Relances"]
    table_header_style = ParagraphStyle(
        "FacHeader",
        parent=styles["small"],
        fontName="Helvetica-Bold",
        fontSize=6.6,
        leading=7.8,
        textColor=colors.white,
    )
    table_cell_style = ParagraphStyle(
        "FacCell",
        parent=styles["small"],
        fontSize=6.4,
        leading=7.6,
    )

    def fac_cell(value, style=table_cell_style):
        return Paragraph(escape("—" if value is None else str(value)), style)

    data = [[fac_cell(label, table_header_style) for label in headers]]
    for record in records:
        reminders = ", ".join(filter(None, [french_date(record.get("reminder_one_at")), french_date(record.get("reminder_two_at"))])) or "—"
        status_date = record.get("paid_at") or record.get("invoice_sent_at") or record.get("invoice_date")
        data.append([fac_cell(value) for value in [
            record.get("invoice_number") or "—",
            record.get("client_structure") or "—",
            record.get("client_contact") or "—",
            french_date(record.get("invoice_date")),
            record.get("title") or "—",
            money(record.get("amount_cents")),
            status_label(record),
            french_date(status_date),
            reminders,
        ]])
    billed = sum(int(record.get("amount_cents") or 0) for record in records)
    paid = sum(int(record.get("amount_cents") or 0) for record in records if record.get("paid_at"))
    data.append([fac_cell(value) for value in ["", "", "", "", "TOTAL FACTURÉ", money(billed), "ENCAISSÉ", money(paid), f"Reste {money(billed - paid)}"]])
    table = Table(data, colWidths=[20*mm, 34*mm, 28*mm, 20*mm, 48*mm, 24*mm, 24*mm, 22*mm, 33*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_DARK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(LIGHT)),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(MID)),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    signature = _pdf_image(signature_path, 42 * mm, 19 * mm)
    if signature:
        signature_block = Table(
            [[signature], [Paragraph(
                f"{escape((structure or {}).get('signer_name', 'Responsable'))} · Fabmanager · exporté le {datetime.now().strftime('%d/%m/%Y')}",
                styles["small"],
            )]],
            colWidths=[48 * mm],
            hAlign="RIGHT",
        )
        signature_block.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.extend([Spacer(1, 5 * mm), signature_block])
    document.build(story)
    return stream.getvalue()


def _xlsx_cell(reference: str, value, style: int = 0, formula: str | None = None, numeric=False) -> str:
    style_attr = f' s="{style}"' if style else ""
    if formula is not None:
        return f'<c r="{reference}"{style_attr}><f>{escape(formula)}</f><v>{value}</v></c>'
    if numeric:
        return f'<c r="{reference}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t>{escape(str(value))}</t></is></c>'


def generate_client_directory_xlsx(clients: list[dict], structure: dict | None = None) -> bytes:
    'Crée un classeur XLSX contenant les fiches et leurs dossiers liés.'
    headers = [
        "Contact", "Structure", "Adresse", "Code postal", "Commune",
        "Téléphone", "E-mail", "Numéros de devis/factures",
        "Noms des dossiers", "Nombre de dossiers",
    ]
    rows_xml = [
        '<row r="1" ht="28" customHeight="1">'
        + _xlsx_cell("A1", f"{_document_identity(structure)['name']} - Annuaire des clients", 1)
        + '</row>',
        '<row r="2" ht="20" customHeight="1">'
        + _xlsx_cell("A2", f"Exporté le {datetime.now().strftime('%d/%m/%Y')}")
        + '</row>',
    ]
    header_cells = "".join(
        _xlsx_cell(f"{chr(65 + index)}3", label, 2)
        for index, label in enumerate(headers)
    )
    rows_xml.append(f'<row r="3" ht="26" customHeight="1">{header_cells}</row>')
    for row_number, client in enumerate(clients, start=4):
        linked_records = client.get("linked_records") or []
        references = []
        titles = []
        for record in linked_records:
            record_references = []
            if record.get("quote_number"):
                record_references.append(f"Devis {record['quote_number']}")
            if record.get("invoice_number"):
                record_references.append(f"Facture {record['invoice_number']}")
            references.append(" · ".join(record_references) or "Sans numéro")
            titles.append(record.get("title") or "Dossier sans nom")
        values = [
            client.get("contact_name") or "", client.get("structure_name") or "",
            client.get("address_line") or "", client.get("postal_code") or "",
            client.get("city") or "", client.get("phone") or "",
            client.get("email") or "", " | ".join(references), " | ".join(titles),
            int(client.get("record_count") or len(linked_records)),
        ]
        cells = []
        for index, value in enumerate(values):
            reference = f"{chr(65 + index)}{row_number}"
            cells.append(_xlsx_cell(reference, value, 3, numeric=index == 9))
        rows_xml.append(f'<row r="{row_number}" ht="46" customHeight="1">{"".join(cells)}</row>')
    last_row = len(clients) + 3
    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols><col min="1" max="1" width="24" customWidth="1"/><col min="2" max="2" width="26" customWidth="1"/><col min="3" max="3" width="34" customWidth="1"/><col min="4" max="4" width="13" customWidth="1"/><col min="5" max="5" width="20" customWidth="1"/><col min="6" max="6" width="19" customWidth="1"/><col min="7" max="7" width="31" customWidth="1"/><col min="8" max="8" width="36" customWidth="1"/><col min="9" max="9" width="38" customWidth="1"/><col min="10" max="10" width="11" customWidth="1"/></cols>
<sheetData>{''.join(rows_xml)}</sheetData>
<autoFilter ref="A3:J{last_row if clients else 3}"/>
<mergeCells count="2"><mergeCell ref="A1:J1"/><mergeCell ref="A2:J2"/></mergeCells>
<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="18"/><color rgb="FF1F5065"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F5065"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFD9E2E4"/></left><right style="thin"><color rgb="FFD9E2E4"/></right><top style="thin"><color rgb="FFD9E2E4"/></top><bottom style="thin"><color rgb="FFD9E2E4"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets><sheet name="Annuaire clients" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr("xl/styles.xml", styles)
    return output.getvalue()


def generate_facdepot_xlsx(
    records: list[dict],
    year: int,
    signature_path: Path | None = None,
    structure: dict | None = None,
) -> bytes:
    """Crée un classeur XLSX simple, éditable et sans macro."""
    headers = ["Numéro facture", "Structure", "Contact", "Date d'édition", "Désignation", "Montant HT", "Statut", "Date du statut", "Relance 1", "Relance 2"]
    rows_xml = []
    title = _xlsx_cell(
        "A1",
        f"{_document_identity(structure)['name']} - {_document_identity(structure)['description']}"
        f" · Bilan {year}",
        1,
    )
    rows_xml.append(f'<row r="1" ht="28" customHeight="1">{title}</row>')
    rows_xml.append('<row r="2"></row>')
    header_cells = "".join(_xlsx_cell(f"{chr(65+i)}3", label, 2) for i, label in enumerate(headers))
    rows_xml.append(f'<row r="3" ht="26" customHeight="1">{header_cells}</row>')
    for row_number, record in enumerate(records, start=4):
        status_date = record.get("paid_at") or record.get("invoice_sent_at") or record.get("invoice_date")
        values = [
            record.get("invoice_number") or "",
            record.get("client_structure") or "",
            record.get("client_contact") or "",
            french_date(record.get("invoice_date")),
            record.get("title") or "",
            int(record.get("amount_cents") or 0) / 100,
            status_label(record),
            french_date(status_date),
            french_date(record.get("reminder_one_at")) if record.get("reminder_one_at") else "",
            french_date(record.get("reminder_two_at")) if record.get("reminder_two_at") else "",
        ]
        cells = []
        for index, value in enumerate(values):
            reference = f"{chr(65 + index)}{row_number}"
            cells.append(_xlsx_cell(reference, value, 3 if index == 5 else 5, numeric=index == 5))
        rows_xml.append(f'<row r="{row_number}" ht="45" customHeight="1">{"".join(cells)}</row>')
    total_row = len(records) + 4
    last_data_row = len(records) + 3
    billed = sum(int(record.get("amount_cents") or 0) for record in records) / 100
    paid = sum(int(record.get("amount_cents") or 0) for record in records if record.get("paid_at")) / 100
    totals = [
        _xlsx_cell(f"E{total_row}", "TOTAL FACTURÉ", 2),
        _xlsx_cell(
            f"F{total_row}", billed, 4,
            f"SUM(F4:F{last_data_row})" if records else None,
            numeric=True,
        ),
        _xlsx_cell(f"G{total_row}", "TOTAL ENCAISSÉ", 2),
        _xlsx_cell(
            f"H{total_row}", paid, 4,
            f'SUMIF(G4:G{last_data_row},"Facture payée",F4:F{last_data_row})' if records else None,
            numeric=True,
        ),
        _xlsx_cell(f"I{total_row}", "RESTANT DÛ", 2),
        _xlsx_cell(f"J{total_row}", billed - paid, 4, f"F{total_row}-H{total_row}", numeric=True),
    ]
    rows_xml.append(f'<row r="{total_row}" ht="25" customHeight="1">{"".join(totals)}</row>')
    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols><col min="1" max="1" width="16" customWidth="1"/><col min="2" max="3" width="24" customWidth="1"/><col min="4" max="4" width="14" customWidth="1"/><col min="5" max="5" width="40" customWidth="1"/><col min="6" max="6" width="15" customWidth="1"/><col min="7" max="7" width="18" customWidth="1"/><col min="8" max="10" width="14" customWidth="1"/></cols>
<sheetData>{''.join(rows_xml)}</sheetData>
<autoFilter ref="A3:J{last_data_row if records else 3}"/>
<mergeCells count="1"><mergeCell ref="A1:J1"/></mergeCells>
<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
{'<drawing r:id="rId1"/>' if signature_path and signature_path.exists() else ''}
</worksheet>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="# ##0,00 [$€-fr-FR]"/></numFmts>
<fonts count="3"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="18"/><color rgb="FF1F5065"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F5065"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF3F4"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFD9E2E4"/></left><right style="thin"><color rgb="FFD9E2E4"/></right><top style="thin"><color rgb="FFD9E2E4"/></top><bottom style="thin"><color rgb="FFD9E2E4"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets><sheet name="Bilan facturation" sheetId="1" r:id="rId1"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        has_signature = bool(signature_path and signature_path.exists())
        drawing_content_types = (
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/xl/drawings/drawing1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
            if has_signature else ""
        )
        archive.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>{drawing_content_types}<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr("xl/styles.xml", styles)
        if has_signature:
            signature_row = total_row + 2
            drawing = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<xdr:oneCellAnchor><xdr:from><xdr:col>7</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{signature_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="1645920" cy="685800"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="2" name="Signature du responsable"/><xdr:cNvPicPr/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>
</xdr:wsDr>'''
            archive.writestr(
                "xl/worksheets/_rels/sheet1.xml.rels",
                '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>''',
            )
            archive.writestr("xl/drawings/drawing1.xml", drawing)
            archive.writestr(
                "xl/drawings/_rels/drawing1.xml.rels",
                '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/signature.png"/></Relationships>''',
            )
            archive.write(signature_path, "xl/media/signature.png")
    return output.getvalue()
