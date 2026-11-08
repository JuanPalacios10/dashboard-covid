from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
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


def _moving_average(values: list[Any], window: int = 7) -> list[float | None]:
    return [
        round(sum(_to_float(value) for value in values[index - window + 1 : index + 1]) / window, 2)
        if index >= window - 1
        else None
        for index in range(len(values))
    ]


def _build_trend_drawing(series_data: dict[str, Any] | None) -> Drawing:
    drawing = Drawing(width=520, height=190)
    dates = (series_data or {}).get('fechas', [])
    source_series = (series_data or {}).get('series', [])
    if not dates or not source_series:
        drawing.add(String(40, 90, 'No hay datos de tendencia para los filtros seleccionados.', fontName='Helvetica', fontSize=9, fillColor=colors.HexColor('#4b5563')))
        return drawing

    palette = ['#2563eb', '#0f766e', '#dc2626', '#d97706', '#7c3aed', '#475569', '#059669']
    daily = (series_data or {}).get('granularidad') == 'diaria'
    nacional = (series_data or {}).get('tipo') == 'nacional'
    chart_series: list[dict[str, Any]] = []
    if daily and nacional:
        values = source_series[0].get('valores', [])
        chart_series = [
            {'name': 'Casos diarios', 'values': values, 'color': '#2563eb', 'width': 1.2},
            {'name': 'Promedio 7 días', 'values': _moving_average(values), 'color': '#0f766e', 'width': 2.2},
        ]
    else:
        for index, item in enumerate(source_series):
            values = item.get('valores', [])
            chart_series.append({
                'name': item.get('nombre', f'Serie {index + 1}'),
                'values': _moving_average(values) if daily else values,
                'color': palette[index % len(palette)],
                'width': 2,
            })

    max_value = max(
        (_to_float(value) for item in chart_series for value in item['values'] if value is not None),
        default=0.0,
    )
    if max_value <= 0:
        drawing.add(String(40, 90, 'Sin casos reportados para este período.', fontName='Helvetica', fontSize=9, fillColor=colors.HexColor('#4b5563')))
        return drawing

    left, right, bottom, top = 42, 368, 32, 158
    drawing.add(Line(left, bottom, right, bottom, strokeColor=colors.HexColor('#9ca3af'), strokeWidth=0.8))
    drawing.add(Line(left, bottom, left, top, strokeColor=colors.HexColor('#9ca3af'), strokeWidth=0.8))
    for grid_index in range(1, 4):
        y = bottom + (top - bottom) * grid_index / 4
        drawing.add(Line(left, y, right, y, strokeColor=colors.HexColor('#e5e7eb'), strokeWidth=0.5))
        drawing.add(String(2, y - 3, f'{max_value * grid_index / 4:,.0f}', fontName='Helvetica', fontSize=6, fillColor=colors.HexColor('#6b7280')))

    point_count = len(dates)
    for item in chart_series:
        previous = None
        values = item['values']
        for index, value in enumerate(values[:point_count]):
            if value is None:
                previous = None
                continue
            x = left + (right - left) * index / max(point_count - 1, 1)
            y = bottom + (top - bottom) * _to_float(value) / max_value
            if previous is not None:
                drawing.add(Line(previous[0], previous[1], x, y, strokeColor=colors.HexColor(item['color']), strokeWidth=item['width']))
            previous = (x, y)

    tick_count = min(7, point_count)
    for tick in range(tick_count):
        index = round(tick * (point_count - 1) / max(tick_count - 1, 1))
        value = str(dates[index])
        label = f'{value[8:10]}/{value[5:7]}' if daily and len(value) >= 10 else value[:7]
        x = left + (right - left) * index / max(point_count - 1, 1)
        drawing.add(String(x - 12, 17, label, fontName='Helvetica', fontSize=6, fillColor=colors.HexColor('#4b5563')))

    for index, item in enumerate(chart_series):
        y = top - index * 16
        drawing.add(Line(390, y, 408, y, strokeColor=colors.HexColor(item['color']), strokeWidth=item['width']))
        drawing.add(String(414, y - 3, item['name'][:22], fontName='Helvetica', fontSize=7, fillColor=colors.HexColor('#374151')))
    return drawing


def _build_projection_table(projection_data: dict[str, Any]) -> Table:
    headings = [
        'Escenario', 'R efectivo', 'Nuevos 30 d', 'Nuevos 60 d', 'Nuevos 90 d',
        'Nuevos 180 d', 'Nuevos 365 d', 'Pico activos', 'Fecha pico',
    ]
    rows = [headings]
    for scenario in projection_data.get('escenarios', []):
        summary = scenario.get('resumen', {})
        rows.append([
            scenario.get('nombre', scenario.get('id', '')),
            f"{_to_float(scenario.get('r_efectivo')):.2f}",
            _format_number(_to_int(summary.get('nuevos_30d'))),
            _format_number(_to_int(summary.get('nuevos_60d'))),
            _format_number(_to_int(summary.get('nuevos_90d'))),
            _format_number(_to_int(summary.get('nuevos_180d'))),
            _format_number(_to_int(summary.get('nuevos_365d'))),
            _format_number(_to_int(summary.get('pico_activos'))),
            str(summary.get('fecha_pico', '')),
        ])
    table = Table(
        rows,
        colWidths=[38 * mm, 20 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 34 * mm],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def build_informe_pdf_bytes(
    payload: dict[str, Any],
    dashboard: dict[str, Any] | None = None,
    report_date: datetime | None = None,
    projection_data: dict[str, Any] | None = None,
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
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    portrait_width, portrait_height = A4
    portrait_frame = Frame(
        20 * mm,
        18 * mm,
        portrait_width - 40 * mm,
        portrait_height - 36 * mm,
        id='portrait-frame',
    )
    page_templates = [PageTemplate(id='portrait', frames=[portrait_frame], pagesize=A4)]
    if include_projection:
        landscape_width, landscape_height = landscape(A4)
        landscape_frame = Frame(
            20 * mm,
            18 * mm,
            landscape_width - 40 * mm,
            landscape_height - 36 * mm,
            id='landscape-frame',
        )
        page_templates.append(
            PageTemplate(
                id='landscape', frames=[landscape_frame], pagesize=landscape(A4)
            )
        )
    doc.addPageTemplates(page_templates)

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

    story.append(KeepTogether([
        Paragraph('Tendencia de contagios', style=header_style),
        _build_trend_drawing(dashboard.get('series')),
    ]))
    story.append(Spacer(1, 6 * mm))

    if include_projection:
        story.append(NextPageTemplate('landscape'))
        story.append(PageBreak())
        story.append(Paragraph('Comparación de escenarios · Valores proyectados', style=header_style))
        if projection_data and projection_data.get('escenarios'):
            story.append(_build_projection_table(projection_data))
        else:
            story.append(Paragraph('No hay escenarios disponibles para los filtros seleccionados.', style=body_style))
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
