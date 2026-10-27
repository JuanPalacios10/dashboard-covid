"""Endpoints de administración protegidos por rol."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ..dependencies.auth import require_admin

router = APIRouter(prefix="/admin", tags=["administracion"])


@router.post(
    "/etl",
    status_code=status.HTTP_200_OK,
    summary="Ejecutar ETL de administración",
    description="Endpoint protegido. Solo usuarios con rol 'admin' pueden ejecutarlo.",
)
def trigger_etl(current_user: dict = Depends(require_admin)) -> dict:
    return {
        "mensaje": "ETL iniciado correctamente",
        "ejecutado_por": current_user.get("user_id"),
        "rol": current_user.get("role"),
    }
