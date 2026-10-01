"""Printable animation attendance sheet using the existing ReportLab engine."""

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reservations_sync import booking_counts, booking_presence, booking_reservation_status


STATUS_LABELS = {"confirmed": "Confirmé", "waitlisted": "Liste d'attente",
                 "offer_pending": "Place proposée", "cancelled": "Annulé", "expired": "Offre expirée"}
LINK_LABELS = {"matched": "Coordonnées concordantes", "manual": "Vérifié manuellement",
               "needs_review": "À vérifier", "candidate": "À vérifier", "visitor": "Non rattaché"}


def generate_animation_bookings_pdf(service, config, bookings, structure, category_labels,
                                    main_logo=None, institution_logo=None):
    """A4 landscape, repeated table headings and no technical booking identifiers."""
    output = io.BytesIO()
    width, height = landscape(A4)
    name = structure.get("name") or "FabLab"
    color = colors.HexColor(structure.get("color") or "#2e718f")
    document = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=12*mm,
                                 rightMargin=12*mm, topMargin=30*mm, bottomMargin=17*mm,
                                 title=f"Inscriptions - {service['title']}", author=name)
    body = ParagraphStyle("BookingCell", fontName="Helvetica", fontSize=8.5, leading=11,
                          textColor=colors.HexColor("#20282b"))
    heading = ParagraphStyle("BookingHeading", parent=body, fontName="Helvetica-Bold",
                             fontSize=17, leading=21, spaceAfter=3*mm)
    small = ParagraphStyle("BookingSmall", parent=body, fontSize=8, leading=10)
    header_style = ParagraphStyle("BookingTableHeading", parent=small,
                                   fontName="Helvetica-Bold", textColor=colors.white)

    def cell(value, style=body):
        return Paragraph(escape(str(value or "-")), style)

    local_date = date.fromisoformat(service["service_date"]).strftime("%d/%m/%Y")
    timing = f"{local_date} - {service['start_time'] or '-'} à {service['end_time'] or '-'}"
    story = [cell("Inscriptions / feuille de présence", heading),
             cell(service["title"], ParagraphStyle("BookingTitle", parent=body,
                                                  fontName="Helvetica-Bold", fontSize=12, leading=15)),
             cell(f"{timing} | Âge minimum : {service['minimum_age'] or 0} ans"), Spacer(1, 4*mm)]
    counts = booking_counts(bookings)
    metrics = [("Capacité", config["capacity"] if config else "-"),
               ("Confirmés", counts["confirmed"]), ("Liste d'attente", counts["waitlisted"]),
               ("Places proposées", counts["offer_pending"]), ("Présents", counts["present"]),
               ("Absents", counts["absent"])]
    metric_table = Table([[Paragraph(f"<b>{escape(str(value))}</b><br/>{escape(label)}", body)
                            for label, value in metrics]], colWidths=[45.5*mm]*6)
    metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3f4")),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("TOPPADDING", (0, 0), (-1, -1), 7),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([metric_table, Spacer(1, 5*mm)])
    groups = {}
    for row in bookings:
        if row["group_uuid"]:
            groups.setdefault(row["group_uuid"], []).append(row)
    slot_mode = config is not None and dict(config).get("booking_mode") == "slots"
    headings = ["Participant", "Âge / type", "Réservation", "Présence / émargement", "Rattachement", "Contact", "Réservation liée"]
    if slot_mode:
        headings.insert(1, "Créneau")
    data = [[cell(label, header_style) for label in headings]]
    for row in bookings:
        age = f"{int(service['service_date'][:4]) - row['birth_year']} ans" if row["birth_year"] else "Âge non renseigné"
        category = category_labels.get(row["category"], "Usager") if row["user_id"] else "Visiteur"
        presence = booking_presence(row)
        label = "Présent" if presence is True else "Absent" if presence is False else "Non renseignée"
        companions = [f"{other['first_name']} {other['last_name']}"
                      for other in groups.get(row["group_uuid"], []) if other["external_uuid"] != row["external_uuid"]]
        cells = [cell(f"{row['first_name']} {row['last_name']}"),
                     Paragraph(f"{escape(age)}<br/>{escape(category)}", body),
                     cell(STATUS_LABELS.get(booking_reservation_status(row), "Non renseignée")),
                     Paragraph(escape(label) + "<br/><br/>" + ("____________" if slot_mode else "________________"), small),
                     cell(LINK_LABELS.get(row["link_status"], "Non rattaché"), small),
                     Paragraph("<br/>".join(escape(str(value)) for value in (row["email"], row["phone"]) if value) or "-", small),
                     cell(", ".join(companions), small)]
        if slot_mode:
            cells.insert(1, cell(dict(row).get("slot_label", ""), small))
        data.append(cells)
    if not bookings:
        data.append([cell("Aucun participant inscrit")] + [""] * (len(headings)-1))
    widths = [36,23,25,28,29,29,61,42] if slot_mode else [41,29,35,37,37,54,40]
    table = Table(data, colWidths=[value*mm for value in widths], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), color),
                              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8f9")]),
                              ("LINEBELOW", (0, 0), (-1, 0), 0.5, color),
                              ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d9e2e4")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("TOPPADDING", (0, 0), (-1, -1), 7),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(table)

    def page_frame(canvas, doc):
        canvas.saveState()
        text_x = 12*mm
        if main_logo and main_logo.is_file():
            canvas.drawImage(ImageReader(str(main_logo)), 12*mm, height-24*mm,
                             width=34*mm, height=17*mm, preserveAspectRatio=True, mask="auto")
            text_x = 50*mm
        canvas.setFillColor(color)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(text_x, height-14*mm, name)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(text_x, height-20*mm, timing)
        if institution_logo and institution_logo.is_file():
            canvas.drawImage(ImageReader(str(institution_logo)), width-45*mm, height-24*mm,
                             width=33*mm, height=17*mm, preserveAspectRatio=True, mask="auto")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#58666b"))
        canvas.drawString(12*mm, 8*mm, "Document contenant des données personnelles : à conserver uniquement pour l'organisation de l'activité.")
        canvas.drawRightString(width-12*mm, 8*mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
