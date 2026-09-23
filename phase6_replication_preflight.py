#!/usr/bin/env python3
"""Phase 6 preflight gate; never starts replications while Phase 5 is blocked."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/replications"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    phase5 = read_json(ROOT / "data/experiment/phase_5_summary.json")
    phase5_status = phase5.get("status", "MISSING")
    phases = {
        "phase_1": "APPROVED_WITH_WARNINGS",
        "phase_2": read_json(ROOT / "data/reference_model/validation_report.json").get("status", "MISSING"),
        "phase_3": read_json(ROOT / "data/simulator/simulator_validation_report.json").get("status", "MISSING"),
        "phase_4": read_json(ROOT / "data/simulator/phase_4_validation_summary.json").get("status", "MISSING"),
        "phase_5": phase5_status,
    }
    manifest = {
        "experiment_id": "ORIENTAAI_EXPERIMENT_V1",
        "phase": 6,
        "reference_model_version": "REFERENCE_MODEL_V1",
        "simulator_version": read_json(ROOT / "data/simulator/phase_4_validation_summary.json").get("simulator_version", "UNKNOWN"),
        "orientaai_version": "frontend/vocational engine 1.0.0",
        "question_bank_version": "VOCATIONAL_VERSIONS.questionnaire 1.0.0",
        "configuration_version": "SIMULATOR_V1 config + frozen frontend engine configuration",
        "base_experiment_version": "ORIENTAAI_EXPERIMENT_V1 / PHASE_5",
        "replication_policy_version": "PHASE_6_POLICY_NOT_STARTED",
        "baseline_policy_version": "PHASE_6_POLICY_NOT_STARTED",
        "status": "BLOCKED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preconditions": phases,
        "blocking_issue": "Phase 5 status is BLOCKED; Phase 6 requires COMPLETED or COMPLETED_WITH_WARNINGS.",
        "replications_started": False,
        "baselines_started": False,
    }
    (OUT / "replication_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "experimental_conditions.json").write_text(json.dumps({"status": "NOT_DEFINED_PRECONDITION_BLOCKED", "conditions": [], "reason": manifest["blocking_issue"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = """# Fase 6 — Replicaciones y escenarios de control

Estado: **BLOCKED**

## Precondición

La Fase 6 requiere que la Fase 5 esté `COMPLETED` o `COMPLETED_WITH_WARNINGS`. El estado real de la Fase 5 es `BLOCKED` porque el dataset validado contiene 218 participantes identificables frente a los 220 exigidos por el protocolo.

## Ejecución

No se iniciaron replicaciones, condiciones de ruido, condiciones de ambigüedad ni escenarios controlados. Tampoco se ejecutaron los baselines adaptativo, no adaptativo o exhaustivo.

No se definieron condiciones experimentales ejecutables ni seeds de replicación, para evitar generar un diseño que no puede aplicarse comparativamente al experimento principal.

## Integridad

Los resultados de la Fase 5 permanecieron intactos. No se creó ni sobrescribió `data/experiment/runs/` y no se generaron resultados de replicación o baseline.

## Decisión

La Fase 6 queda bloqueada hasta resolver el tamaño del dataset y completar la Fase 5 con el protocolo aprobado.
"""
    (OUT / "phase_6_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "BLOCKED", "phase5_status": phase5_status, "replications": 0, "baselines": 0}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
