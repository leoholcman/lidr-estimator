"""Corre el dataset golden contra el estimador y aplica las métricas.

    uv run python -m evals.run                               # en proceso
    uv run python -m evals.run --http http://localhost:8000  # contra un servicio levantado
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from evals.metrics import run_all_metrics

DATASET = Path(__file__).parent / "golden_dataset.json"


def make_client(http: str | None) -> httpx.AsyncClient:
    if http:
        return httpx.AsyncClient(base_url=http, timeout=180)
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eval", timeout=180)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", help="URL del servicio; si falta se usa la app en proceso")
    args = parser.parse_args()

    cases = json.loads(DATASET.read_text())
    failed = 0
    async with make_client(args.http) as client:
        for case in cases:
            response = await client.post("/api/v1/estimate", json={
                "description": case["description"],
                "project_type": case["project_type"],
                "detail_level": "medium",
                "output_format": "line_items",
            })
            response.raise_for_status()
            results = run_all_metrics(case, response.json()["text"])
            failed += sum(not r.passed for r in results)
            summary = "  ".join(f"{r.name}={'ok' if r.passed else 'FALLA'} ({r.details})" for r in results)
            print(f"{case['id']:<18} {summary}")
    print(f"\n{len(cases)} casos, {failed} métricas en rojo")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
