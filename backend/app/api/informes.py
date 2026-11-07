from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..services.auth import UserRole
from ..services.dashboard import DashboardService, get_dashboard_service
from ..services.informes import build_informe_pdf_bytes
from .auth import require_roles

router = APIRouter(prefix="/informes", tags=["informes"])


class InformePdfRequest(BaseModel):
    destino: str = Field(default="Consejo de gobierno")
    territorio: str = Field(default="Nacional")
    anio: str | int | None = None
    departamento: str | None = None
    incluir_proyeccion: bool = False


@router.post(
    "/pdf",
    status_code=status.HTTP_200_OK,
    summary="Genera el PDF oficial del informe ejecutivo",
    description=(
        "Genera un PDF autorizado para el rol ejecutivo con membrete, fecha, "
        "resumen de KPIs y firma institucional del reporte."
    ),
)
def exportar_pdf(
    response: Response,
    _current_user: Annotated[
        dict[str, Any],
        Depends(require_roles([UserRole.EJECUTIVO])),
    ],
    dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
    payload: InformePdfRequest,
) -> Response:
    """Genera el PDF final a partir del estado actual del tablero."""
    try:
        anio = payload.anio if payload.anio not in (None, '') else 'acumulado'
        dashboard_data = dashboard_service.get(str(anio), payload.departamento)
        pdf_bytes = build_informe_pdf_bytes(payload.model_dump(), dashboard_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parámetros del informe inválidos: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - protect the route from backend data issues
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No fue posible generar el PDF porque los agregados del tablero no "
                "están disponibles o están incompletos."
            ),
        ) from exc

    filename = (
        f"informe-{payload.territorio.lower().replace(' ', '-') or 'nacional'}-"
        f"{payload.destino.lower().replace(' ', '-') or 'consejo'}.pdf"
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return Response(content=pdf_bytes, media_type="application/pdf")