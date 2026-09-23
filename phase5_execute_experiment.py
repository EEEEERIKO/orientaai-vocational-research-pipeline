#!/usr/bin/env python3
"""Phase 5 preflight gate.

The principal experiment is intentionally not started unless the validated
dataset contains exactly the 220 participants required by the protocol.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "data/experiment"
DATASET = ROOT / "data/reference_model/reference_profiles_A1_A12.csv"
EXPECTED = 220


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def phase_status(path: Path, key: str = "status") -> str:
    if not path.exists():
        return "MISSING"
    value = json.loads(path.read_text(encoding="utf-8"))
    return str(value.get(key, "UNKNOWN"))


def main() -> int:
    EXPERIMENT.mkdir(parents=True, exist_ok=True)
    rows = read_rows(DATASET)
    actual = len(rows)
    phases = {
        "phase_1": "APPROVED_WITH_WARNINGS",
        "phase_2": phase_status(ROOT / "data/reference_model/validation_report.json"),
        "phase_3": phase_status(ROOT / "data/simulator/simulator_validation_report.json"),
        "phase_4": phase_status(ROOT / "data/simulator/phase_4_validation_summary.json"),
    }
    started = datetime.now(timezone.utc).isoformat()
    manifest = {
        "experiment_id": "ORIENTAAI_EXPERIMENT_V1",
        "phase": 5,
        "reference_model_version": "REFERENCE_MODEL_V1",
        "simulator_version": phase_status(ROOT / "data/simulator/phase_4_validation_summary.json", "simulator_version"),
        "orientaai_version": "frontend/vocational engine 1.0.0",
        "question_bank_version": "VOCATIONAL_VERSIONS.questionnaire 1.0.0",
        "configuration_version": "SIMULATOR_V1 config + frozen frontend engine configuration",
        "chaside_dataset_version": sha256(DATASET),
        "random_seed_policy": "sha256(experiment_id|participant_id|base_seed) -> deterministic participant seed; not used because preflight blocked",
        "started_at": started,
        "status": "BLOCKED",
        "preconditions": phases,
        "participants_expected": EXPECTED,
        "participants_available": actual,
        "blocking_issue": f"Validated dataset contains {actual} identifiable participants; protocol requires exactly {EXPECTED}.",
        "execution_started": False,
    }
    (EXPERIMENT / "experiment_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (EXPERIMENT / "participants_manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["participant_id", "chaside_record_id", "reference_profile_id", "synthetic_person_id", "experiment_id", "execution_seed", "status"])
        writer.writeheader()
        for row in rows:
            pid = row["case_id"]
            writer.writerow({"participant_id": pid, "chaside_record_id": pid, "reference_profile_id": pid, "synthetic_person_id": f"SYN_{pid}", "experiment_id": manifest["experiment_id"], "execution_seed": "null", "status": "NOT_EXECUTED_PRECONDITION_BLOCKED"})

    summary = {
        "experiment_id": manifest["experiment_id"],
        "phase": 5,
        "participants_expected": EXPECTED,
        "participants_executed": 0,
        "complete_runs": 0,
        "failed_runs": 0,
        "total_questions": 0,
        "mean_questions_per_participant": 0,
        "median_questions_per_participant": 0,
        "contrast_usage_rate": 0,
        "confirmation_usage_rate": 0,
        "discard_usage_rate": 0,
        "reproducibility_tested": False,
        "reproducibility_failures": 0,
        "status": "BLOCKED",
        "next_phase": None,
        "participants_available": actual,
        "blocking_issue": manifest["blocking_issue"],
    }
    (EXPERIMENT / "phase_5_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Fase 5 — Ejecución de participantes sintéticos en OrientaAI

Estado: **BLOCKED**

## 1. Identificación del experimento

Experimento `ORIENTAAI_EXPERIMENT_V1`. Las versiones y hashes disponibles quedaron registrados en `experiment_manifest.json`.

## 2. Dataset

El protocolo exige exactamente 220 participantes. El dataset validado de referencia contiene **{actual} participantes identificables**. La Fase 1 documenta que la diferencia corresponde a filas ausentes/vacías, no a IDs que puedan crearse legítimamente.

## 3. Método de ejecución

La ejecución principal no se inició. El bloqueo se aplicó antes de generar personas sintéticas, iniciar sesiones OrientaAI o enviar respuestas.

## 4. Integración y recorrido

No aplica: no se inició ninguna sesión y no se modificó la lógica de OrientaAI.

## 5. Control de integridad

- Participantes esperados: `{EXPECTED}`.
- Participantes disponibles: `{actual}`.
- Participantes ejecutados: `0`.
- Execution IDs válidos: `0`.

## 6. Problema bloqueante

No es metodológicamente válido inventar dos participantes, duplicar participantes existentes o declarar completado un experimento de 220 casos con solo {actual} registros. La fase exige explícitamente detenerse cuando no se pueden ejecutar los 220 casos.

## 7. Decisión

La Fase 5 queda **BLOCKED**. Para continuar se debe proporcionar/corregir el dataset hasta alcanzar 220 participantes identificables, o aprobar formalmente un protocolo actualizado cuyo tamaño esperado sea {actual}.

**No se ejecutó ningún participante en OrientaAI.**
"""
    (EXPERIMENT / "phase_5_execution_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "BLOCKED", "expected": EXPECTED, "available": actual, "executed": 0}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
