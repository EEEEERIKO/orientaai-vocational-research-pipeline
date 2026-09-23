#!/usr/bin/env python3
"""Phase 7 preflight gate; prevents concordance metrics without experiment outputs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/evaluation"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    phase5 = read(ROOT / "data/experiment/phase_5_summary.json")
    phase6 = read(ROOT / "data/replications/replication_manifest.json")
    preconditions = {
        "phase_1": "APPROVED_WITH_WARNINGS",
        "phase_2": read(ROOT / "data/reference_model/validation_report.json").get("status", "MISSING"),
        "phase_3": read(ROOT / "data/simulator/simulator_validation_report.json").get("status", "MISSING"),
        "phase_4": read(ROOT / "data/simulator/phase_4_validation_summary.json").get("status", "MISSING"),
        "phase_5": phase5.get("status", "MISSING"),
        "phase_6": phase6.get("status", "MISSING"),
    }
    manifest = {
        "phase": 7,
        "status": "BLOCKED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preconditions": preconditions,
        "reference_model_version": "REFERENCE_MODEL_V1",
        "blocking_issue": "Phase 5 and Phase 6 are BLOCKED; no OrientaAI results or replication outputs exist for concordance evaluation.",
        "metrics_calculated": False,
    }
    (OUT / "evaluation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "phase": 7,
        "status": "BLOCKED",
        "participants_evaluated": 0,
        "executions_evaluated": 0,
        "top1_rate": None,
        "top3_rate": None,
        "top3_overlap": None,
        "ranking_similarity": None,
        "profile_distance": None,
        "replication_stability": None,
        "area_concordance": None,
        "high_concordance_cases": 0,
        "discrepancy_cases": 0,
        "blocking_issue": manifest["blocking_issue"],
        "reference_model_intact": True,
        "next_phase": None,
    }
    (OUT / "concordance_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = """# Fase 7 — Evaluación de concordancia entre perfil de referencia y OrientaAI

Estado: **BLOCKED**

## Precondiciones

La Fase 7 requiere Fase 5 `COMPLETED` o `COMPLETED_WITH_WARNINGS` y Fase 6 `COMPLETED` o `COMPLETED_WITH_WARNINGS`. Los estados reales son:

- Fase 5: `BLOCKED` — el dataset tiene 218 participantes identificables frente a los 220 exigidos.
- Fase 6: `BLOCKED` — depende de completar la Fase 5.

## Ejecución

No existen resultados OrientaAI ni replicaciones/baselines evaluables. Por ello no se calcularon Top-1, Top-3, solapamiento, similitud de rankings, distancia de perfiles, estabilidad ni concordancia por área.

No se inventaron scores, rankings ni resultados faltantes.

## Integridad

El perfil de referencia de la Fase 2 permaneció intacto. No se modificaron los datos de Fase 5 o Fase 6.

## Decisión

La Fase 7 queda `BLOCKED` hasta resolver el tamaño del dataset, completar la ejecución principal y ejecutar las replicaciones requeridas.
"""
    (OUT / "phase_7_concordance_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "BLOCKED", "participants": 0, "executions": 0, "metrics_calculated": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
