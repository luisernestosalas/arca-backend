"""
Generador de PDFs de certificados ARCA.
Produce un documento PDF profesional con:
  - Nivel de certificación y score
  - Radar de dimensiones
  - Stress tests
  - QR de verificación
  - Hash SHA-256
"""
from __future__ import annotations

import io
import qrcode
from datetime import date
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as rl_canvas


# Paleta de colores ARCA
COLORS = {
    "PLATINUM": colors.HexColor("#1D9E75"),
    "GOLD":     colors.HexColor("#EF9F27"),
    "SILVER":   colors.HexColor("#888780"),
    "BRONZE":   colors.HexColor("#BA7517"),
    "NO_CERT":  colors.HexColor("#E24B4A"),
    "dark":     colors.HexColor("#1a1a1a"),
    "muted":    colors.HexColor("#6b7280"),
    "border":   colors.HexColor("#e5e7eb"),
    "bg":       colors.HexColor("#f9fafb"),
}

DIM_LABELS = {
    "D1": "Liquidez estructural",
    "D2": "Concentración de ingresos",
    "D3": "Dependencia operacional",
    "D4": "Exposición macro",
    "D5": "Resiliencia legal",
    "D6": "Capacidad adaptativa",
    "D7": "Gobernanza",
}


def generate_certificate_pdf(
    cert_id: str,
    subject_name: str,
    cert_level: str,
    global_score: float,
    p_survival: float,
    ife_score: float,
    dim_scores: dict[str, float],
    stress_results: list[dict],
    valid_from: date,
    valid_until: Optional[date],
    cert_hash: str,
    verify_url: str,
) -> bytes:
    """
    Genera el PDF del certificado ARCA y retorna bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )

    level_color = COLORS.get(cert_level, COLORS["SILVER"])
    styles = _build_styles(level_color)
    story = []

    # --- Encabezado ---
    story.append(_header_section(subject_name, cert_level, global_score,
                                  p_survival, ife_score, valid_from,
                                  valid_until, level_color, styles))
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=0.5,
                              color=COLORS["border"], spaceAfter=6*mm))

    # --- Scores por dimensión ---
    story.append(Paragraph("Score por dimensión", styles["section_title"]))
    story.append(Spacer(1, 3*mm))
    story.append(_dimension_table(dim_scores, styles))
    story.append(Spacer(1, 6*mm))

    # --- Stress tests ---
    story.append(Paragraph("Resultados stress tests", styles["section_title"]))
    story.append(Spacer(1, 3*mm))
    story.append(_stress_table(stress_results, styles))
    story.append(Spacer(1, 8*mm))

    # --- Footer con QR y hash ---
    story.append(HRFlowable(width="100%", thickness=0.5,
                              color=COLORS["border"], spaceBefore=4*mm, spaceAfter=4*mm))
    story.append(_footer_section(cert_id, cert_hash, verify_url, styles))

    doc.build(story, onFirstPage=_page_background, onLaterPages=_page_background)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Secciones del documento
# ---------------------------------------------------------------------------

def _header_section(subject_name, cert_level, score, p_survival, ife,
                     valid_from, valid_until, level_color, styles):
    """Encabezado con logo textual, nivel, score y métricas clave."""
    from reportlab.platypus import KeepTogether

    elements = []

    # Logo + nombre sistema
    elements.append(Paragraph("ARCA", styles["logo"]))
    elements.append(Paragraph(
        "ARQUITECTURA DE RIESGO Y CERTIFICACIÓN ANTICIPATORIA",
        styles["logo_sub"]
    ))
    elements.append(Spacer(1, 5*mm))

    # Nombre del sujeto
    elements.append(Paragraph(subject_name, styles["subject_name"]))
    elements.append(Spacer(1, 3*mm))

    # Badge de nivel
    badge_text = f"● {cert_level}"
    elements.append(Paragraph(badge_text, styles["level_badge"]))
    elements.append(Spacer(1, 5*mm))

    # Métricas en tabla horizontal
    validity_str = (
        f"{valid_from.strftime('%d %b %Y')} → {valid_until.strftime('%d %b %Y')}"
        if valid_until else "No aplica"
    )
    metrics_data = [
        ["Score global", "P(supervivencia)", "Índice IFE", "Vigencia"],
        [
            f"{score:.1f}/100",
            f"{p_survival*100:.1f}%",
            f"{ife:.1f}",
            validity_str,
        ],
    ]
    t = Table(metrics_data, colWidths=[42*mm, 42*mm, 38*mm, 48*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), COLORS["bg"]),
        ("TEXTCOLOR",   (0,0), (-1,0), COLORS["muted"]),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,0), 8),
        ("FONTNAME",    (0,1), (-1,1), "Helvetica-Bold"),
        ("FONTSIZE",    (0,1), (-1,1), 13),
        ("TEXTCOLOR",   (0,1), (-1,1), COLORS["dark"]),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [COLORS["bg"], colors.white]),
        ("BOX",         (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
    ]))
    elements.append(t)

    return KeepTogether(elements)


def _dimension_table(dim_scores: dict, styles) -> Table:
    """Tabla de scores por dimensión con barra visual."""
    data = [["Dimensión", "Score", "Nivel"]]
    for dim_id, label in DIM_LABELS.items():
        score = dim_scores.get(dim_id, 0)
        bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
        level = "Alto" if score >= 70 else "Medio" if score >= 50 else "Bajo"
        data.append([f"{dim_id} · {label}", f"{score:.0f}/100", f"{bar}  {level}"])

    t = Table(data, colWidths=[90*mm, 25*mm, 55*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), COLORS["bg"]),
        ("TEXTCOLOR",   (0,0), (-1,0), COLORS["muted"]),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, COLORS["bg"]]),
        ("BOX",         (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("ALIGN",       (1,0), (1,-1), "CENTER"),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    return t


def _stress_table(stress_results: list, styles) -> Table:
    """Tabla de resultados de stress tests."""
    data = [["Escenario", "Score bajo stress", "Resultado"]]
    for s in stress_results:
        result_text = "✓ Supera" if s.get("survived") else "✗ Falla"
        data.append([
            f"{s['id']} · {s['name']}",
            f"{s['score_under_stress']:.1f}/100",
            result_text,
        ])

    t = Table(data, colWidths=[95*mm, 40*mm, 35*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), COLORS["bg"]),
        ("TEXTCOLOR",   (0,0), (-1,0), COLORS["muted"]),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, COLORS["bg"]]),
        ("BOX",         (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("ALIGN",       (1,0), (-1,-1), "CENTER"),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING", (0,0), (0,-1), 8),
    ]))
    return t


def _footer_section(cert_id: str, cert_hash: str, verify_url: str, styles):
    """Footer con QR de verificación y hash SHA-256."""
    from reportlab.platypus import KeepTogether

    # Generar QR
    qr = qrcode.QRCode(version=2, box_size=3, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_flowable = Image(qr_buffer, width=25*mm, height=25*mm)

    # Tabla footer: QR | datos
    footer_data = [[
        qr_flowable,
        Paragraph(
            f"<b>ID:</b> ARCA-{cert_id[:8].upper()}<br/>"
            f"<b>Hash SHA-256:</b> {cert_hash[:32]}...<br/>"
            f"<b>Verificar:</b> {verify_url}<br/>"
            f"<font size='7' color='#9ca3af'>Motor v1.0.0 · "
            f"Este certificado certifica resiliencia estructural, no predice éxito.</font>",
            styles["footer_text"]
        ),
    ]]
    t = Table(footer_data, colWidths=[30*mm, 140*mm])
    t.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (1,0), (1,0), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    return KeepTogether([t])


# ---------------------------------------------------------------------------
# Helpers de estilo y página
# ---------------------------------------------------------------------------

def _build_styles(level_color) -> dict:
    base = getSampleStyleSheet()
    return {
        "logo": ParagraphStyle("logo", fontSize=22, fontName="Helvetica-Bold",
                                textColor=level_color, alignment=TA_CENTER),
        "logo_sub": ParagraphStyle("logo_sub", fontSize=8, fontName="Helvetica",
                                    textColor=COLORS["muted"], alignment=TA_CENTER,
                                    spaceAfter=2),
        "subject_name": ParagraphStyle("subject_name", fontSize=16,
                                        fontName="Helvetica-Bold",
                                        textColor=COLORS["dark"], alignment=TA_CENTER),
        "level_badge": ParagraphStyle("level_badge", fontSize=13,
                                       fontName="Helvetica-Bold",
                                       textColor=level_color, alignment=TA_CENTER),
        "section_title": ParagraphStyle("section_title", fontSize=11,
                                         fontName="Helvetica-Bold",
                                         textColor=COLORS["dark"], spaceAfter=2),
        "footer_text": ParagraphStyle("footer_text", fontSize=8,
                                       fontName="Helvetica",
                                       textColor=COLORS["muted"],
                                       leading=13),
    }


def _page_background(canvas, doc):
    """Añade borde sutil a cada página."""
    canvas.saveState()
    canvas.setStrokeColor(COLORS["border"])
    canvas.setLineWidth(0.5)
    canvas.rect(10*mm, 10*mm, A4[0]-20*mm, A4[1]-20*mm)
    canvas.restoreState()
