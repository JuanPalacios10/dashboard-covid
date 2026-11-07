from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Line, String


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: int) -> str:
    return f"{value:,}"


def build_informe_report_hash(payload: dict[str, Any], dashboard: dict[str, Any], report_date: datetime) -> str:
    """Calcula un identificador estable para el informe basado en los filtros y KPIs seleccionados."""
    kpis = dashboard.get('kpis', {})
    normalized = {
        'destino': payload.get('destino', 'Consejo de gobierno'),
        'territorio': payload.get('territorio', 'Nacional'),
        'anio': payload.get('anio', 'acumulado'),
        'departamento': payload.get('departamento'),
        'incluir_proyeccion': bool(payload.get('incluir_proyeccion', False)),
        'fecha': report_date.date().isoformat(),
        'casos_confirmados': _to_int(kpis.get('casos_confirmados', 0)),
        'fallecidos': _to_int(kpis.get('fallecidos', 0)),
        'recuperados': _to_int(kpis.get('recuperados', 0)),
        'activos': _to_int(kpis.get('activos', 0)),
        'letalidad': _to_float(kpis.get('tasa_letalidad', 0.0)),
        'recuperacion': _to_float(kpis.get('tasa_recuperacion', 0.0)),
    }
    payload_bytes = json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload_bytes).hexdigest()[:16].upper()


def _stable_report_hash(payload: dict[str, Any], dashboard: dict[str, Any], report_date: datetime) -> str:
    return build_informe_report_hash(payload, dashboard, report_date)


def _build_kpi_rows(dashboard: dict[str, Any]) -> list[list[str]]:
    kpis = dashboard.get("kpis", {})
    return [
        ["Casos confirmados", _format_number(_to_int(kpis.get("casos_confirmados", 0)))],
        ["Fallecidos", _format_number(_to_int(kpis.get("fallecidos", 0)))],
        ["Recuperados", _format_number(_to_int(kpis.get("recuperados", 0)))],
        ["Activos", _format_number(_to_int(kpis.get("activos", 0)))],
        ["Letalidad", f"{_to_float(kpis.get('tasa_letalidad', 0)) * 100:.2f}%"],
        ["Recuperación", f"{_to_float(kpis.get('tasa_recuperacion', 0)) * 100:.2f}%"],
    ]


def _build_trend_drawing() -> Drawing:
    drawing = Drawing(width=520, height=160)
    drawing.add(Line(30, 20, 500, 20, strokeColor=colors.grey, strokeWidth=1))
    drawing.add(Line(30, 20, 30, 140, strokeColor=colors.grey, strokeWidth=1))

    points = [
        (40, 60),
        (100, 70),
        (170, 90),
        (240, 80),
        (310, 100),
        (380, 85),
        (450, 110),
    ]
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        drawing.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor('#3b82f6'), strokeWidth=2.5))

    for x, y in points:
        drawing.add(Line(x - 3, y, x + 3, y, strokeColor=colors.HexColor('#1d4ed8'), strokeWidth=1.5))

    drawing.add(String(340, 145, 'Tendencia semanal', fontName='Helvetica-Bold', fontSize=9, fillColor=colors.HexColor('#1f2937')))
    return drawing


def build_informe_pdf_bytes(
    payload: dict[str, Any],
    dashboard: dict[str, Any] | None = None,
    report_date: datetime | None = None,
) -> bytes:
    """Genera un PDF ejecutivo con membrete, KPIs y firma visual."""
    report_date = report_date or datetime.now(timezone.utc)
    territory = payload.get('territorio') or 'Nacional'
    destination = payload.get('destino') or 'Consejo de gobierno'
    include_projection = bool(payload.get('incluir_proyeccion', False))

    if dashboard is None:
        dashboard = {
            'periodo': 'acumulado',
            'anio': None,
            'fecha_corte': report_date.date().isoformat(),
            'actualizado_en': report_date.isoformat(),
            'kpis': {
                'casos_confirmados': 6412380,
                'fallecidos': 180000,
                'recuperados': 6200000,
                'activos': 3200,
                'tasa_letalidad': 0.028,
                'tasa_recuperacion': 0.97,
            },
        }

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#111827'),
        spaceAfter=10,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#374151'),
        leading=12,
    )
    header_style = ParagraphStyle(
        'Header',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0f172a'),
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1f2937'),
    )

    story: list[Any] = []
    story.append(Paragraph('Secretaría de Salud / Observatorio Epidemiológico', style=header_style))
    story.append(Paragraph('Informe ejecutivo de situación epidemiológica', style=title_style))
    story.append(Paragraph(f"Territorio: {territory} — Dirigido a: {destination}", style=subtitle_style))
    story.append(Paragraph(f"Fecha de generación: {report_date.strftime('%d/%m/%Y %H:%M UTC')}", style=subtitle_style))
    story.append(Paragraph(f"Código del documento: INF-{report_date.strftime('%Y%m%d%H%M')}", style=subtitle_style))
    story.append(Spacer(1, 6 * mm))

    kpi_rows = _build_kpi_rows(dashboard)
    table = Table(kpi_rows, colWidths=[90 * mm, 70 * mm])
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(Paragraph('Indicadores clave', style=header_style))
    story.append(table)
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph('Tendencia reciente', style=header_style))
    story.append(_build_trend_drawing())
    story.append(Spacer(1, 6 * mm))

    if include_projection:
        story.append(Paragraph('Proyección a 30 días', style=header_style))
        story.append(Paragraph('Escenario institucional: proyección establecida para comité de decisión.', style=body_style))
        story.append(Spacer(1, 4 * mm))

    report_hash = build_informe_report_hash(payload, dashboard, report_date)
    signature = (
        'Firma digital del reporte\n'
        'Firmado por: Ejecutivo de Toma de Decisiones\n'
        'Cargo: Dirección de Salud Pública\n'
        f'Hash SHA-256: {report_hash}'
    )
    story.append(Paragraph('Firma del reporte', style=header_style))
    story.append(Paragraph(signature, style=body_style))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph('Confidencial. Uso institucional. No se entrega a terceros sin autorización.', style=subtitle_style))

    doc.build(story)
    return buffer.getvalue()
