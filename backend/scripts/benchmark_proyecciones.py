#!/usr/bin/env python
"""Mide la latencia del endpoint de proyecciones.

Ejemplo::

    python scripts/benchmark_proyecciones.py --requests 100 --anio 2021

El script inicia sesión con el usuario ejecutivo de prueba, consulta
``/api/v1/proyecciones`` y reporta el percentil 95 del tiempo de cliente y del
encabezado ``X-Process-Time`` del backend.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark del endpoint /api/v1/proyecciones.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="URL base del backend.",
    )
    parser.add_argument(
        "--email",
        default="ejecutivo@covid.com",
        help="Correo del usuario de prueba.",
    )
    parser.add_argument(
        "--password",
        default="EjecutivoSeguro2026*",
        help="Contraseña del usuario de prueba.",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Número de consultas a medir.",
    )
    parser.add_argument(
        "--anio",
        default="acumulado",
        help="Período a consultar: acumulado o 2020–2024.",
    )
    parser.add_argument(
        "--departamento",
        default=None,
        help="Código DIVIPOLA opcional, por ejemplo 05.",
    )
    parser.add_argument(
        "--horizonte",
        type=int,
        default=60,
        help="Horizonte de proyección: 30, 60 o 90 días.",
    )
    parser.add_argument(
        "--r",
        type=float,
        default=None,
        help="R base opcional para la simulación personalizada.",
    )
    parser.add_argument(
        "--medidas",
        type=float,
        default=40,
        help="Rigor de las medidas sanitarias (0-100).",
    )
    return parser.parse_args()


def _request_json(
    request: urllib.request.Request,
    timeout: float = 10.0,
) -> tuple[dict[str, Any], dict[str, str]]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
        headers = dict(response.headers.items())
        return body, headers


def _login(base_url: str, email: str, password: str) -> str:
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    body, _headers = _request_json(request)
    return str(body["access_token"])


def _parse_server_ms(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.removesuffix("ms"))
    except ValueError:
        return None


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


def main() -> int:
    args = parse_args()
    if args.requests < 1:
        print("Error: --requests debe ser mayor que cero.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    try:
        token = _login(base_url, args.email, args.password)
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        print(f"Error de autenticación: {exc}", file=sys.stderr)
        return 1

    params = {
        "anio": args.anio,
        "horizonte": args.horizonte,
        "medidas": args.medidas,
    }
    if args.departamento:
        params["departamento"] = args.departamento
    if args.r is not None:
        params["r"] = args.r
    url = f"{base_url}/api/v1/proyecciones?{urllib.parse.urlencode(params)}"

    client_ms: list[float] = []
    server_ms: list[float] = []
    last_body: dict[str, Any] | None = None

    for _ in range(args.requests):
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        started = time.perf_counter()
        try:
            last_body, headers = _request_json(request)
        except urllib.error.HTTPError as exc:
            print(
                f"Error HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}",
                file=sys.stderr,
            )
            return 1
        except urllib.error.URLError as exc:
            print(f"Error de conexión: {exc}", file=sys.stderr)
            return 1
        elapsed_ms = (time.perf_counter() - started) * 1_000
        client_ms.append(elapsed_ms)
        server_header = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == "x-process-time"
            ),
            None,
        )
        parsed_server = _parse_server_ms(server_header)
        if parsed_server is not None:
            server_ms.append(parsed_server)

    print(f"URL: {url}")
    print(f"Consultas: {len(client_ms)}")
    print(
        "Cliente  ms: "
        f"min={min(client_ms):.2f} "
        f"mediana={statistics.median(client_ms):.2f} "
        f"p95={_percentile(client_ms, 0.95):.2f} "
        f"max={max(client_ms):.2f}"
    )
    if server_ms:
        print(
            "Servidor ms: "
            f"min={min(server_ms):.2f} "
            f"mediana={statistics.median(server_ms):.2f} "
            f"p95={_percentile(server_ms, 0.95):.2f} "
            f"max={max(server_ms):.2f}"
        )
    if last_body is not None:
        print(
            "Última respuesta: "
            f"periodo={last_body.get('periodo')} "
            f"fecha_corte={last_body.get('fecha_corte')} "
            f"escenarios={len(last_body.get('escenarios', []))} "
            f"calidad={last_body.get('calidad', {}).get('nivel')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
