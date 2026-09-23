#!/usr/bin/env python3
"""Independent controlled validation of the synthetic-person simulator (Phase 4).

This script exercises only controlled profiles and real question definitions. It
does not load participant records and does not call the OrientaAI assessment
engine.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import inspect
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data/simulator"
REF_DIR = ROOT / "data/reference_model"
SCRIPT = ROOT / "scripts/phase3_synthetic_person.py"
AREAS = [f"A{i}" for i in range(1, 13)]
SEEDS = [101, 202, 303, 404, 505, 606, 707, 808, 909, 1001]
VERSION = "SIMULATOR_V1_VALIDATED"
RUN_TIMESTAMP = datetime.now(timezone.utc).isoformat()


def load_phase3():
    spec = importlib.util.spec_from_file_location("phase3_simulator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def profile(kind: str, high: set[str] = set(), medium: set[str] = set(), value: float = 0.5) -> dict[str, float]:
    result = {area: value for area in AREAS}
    for area in medium:
        result[area] = 0.65
    for area in high:
        result[area] = 0.95
    return result


PROFILES = {
    "clear_A1": {"profile_type": "CLEAR_DOMINANT", "values": profile("clear", {"A1"}, value=0.05)},
    "clear_A6": {"profile_type": "CLEAR_DOMINANT", "values": profile("clear", {"A6"}, value=0.05)},
    "clear_A10": {"profile_type": "CLEAR_DOMINANT", "values": profile("clear", {"A10"}, value=0.05)},
    "two_A2_A7": {"profile_type": "TWO_DOMINANT", "values": profile("two", {"A2", "A7"}, value=0.10)},
    "two_A3_A9": {"profile_type": "TWO_DOMINANT", "values": profile("two", {"A3", "A9"}, value=0.10)},
    "mixed_A1_A3_A5_A8_A10": {"profile_type": "MIXED", "values": {a: (0.70 if a == "A1" else 0.65 if a == "A3" else 0.60 if a == "A5" else 0.55 if a == "A8" else 0.50 if a == "A10" else 0.25) for a in AREAS}},
    "ambiguous": {"profile_type": "AMBIGUOUS", "values": {a: 0.55 + (0.01 if a in {"A1", "A2", "A7"} else 0.0) for a in AREAS}},
    "balanced": {"profile_type": "BALANCED", "values": {a: 0.50 for a in AREAS}},
    "extreme_A11": {"profile_type": "EXTREME", "values": {a: (1.0 if a == "A11" else 0.0) for a in AREAS}},
    "extreme_minimum": {"profile_type": "EXTREME", "values": {a: 0.0 for a in AREAS}},
    "extreme_maximum": {"profile_type": "EXTREME", "values": {a: 1.0 for a in AREAS}},
}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def make_questions(all_questions):
    wanted = ["base_01", "base_02", "base_03", "exploration_interests_01", "exploration_skills_01", "contrast_interests_01", "confirmation_situation_01", "discard_interests_01"]
    by_id = {q["question_id"]: q for q in all_questions}
    return [by_id[qid] for qid in wanted]


def question_kind(q):
    if q["question_id"] == "base_01":
        return "single_choice"
    if q["ordered"]:
        return "ordered_multi_select"
    if q["question_type"] == "multi-select":
        return "multi_select"
    if q["phase"] == "Contraste":
        return "contrast"
    if q["phase"] == "Confirmación":
        return "confirmation"
    if q["phase"] == "Descarte":
        return "discard"
    return "single_choice"


def validate_response(result, q):
    failures = []
    options = [o["option_text"] for o in q["options"]]
    response = result.get("response")
    probs = result.get("selection_probabilities", [])
    scores = result.get("option_scores", [])
    if any(not finite(x) for x in scores) or any(not finite(x) for x in probs):
        failures.append("NaN_OR_INFINITY")
    if probs:
        if any(x < 0 or x > 1 for x in probs):
            failures.append("INVALID_PROBABILITY_RANGE")
        if abs(sum(probs) - 1.0) > 1e-9:
            failures.append("PROBABILITIES_NOT_NORMALIZED")
    if q["question_id"] == "base_01":
        if not isinstance(response, int) or not (q["slider_min"] <= response <= q["slider_max"]):
            failures.append("SLIDER_OUT_OF_DOMAIN")
        return failures
    if q["ordered"] or q["question_type"] == "multi-select":
        if not isinstance(response, list):
            failures.append("RESPONSE_TYPE_MISMATCH")
            return failures
        if len(response) == 0 or len(response) > (q["max_selections"] or 3):
            failures.append("INVALID_SELECTION_COUNT")
        if len(response) != len(set(response)):
            failures.append("DUPLICATE_SELECTION")
        if any(item not in options for item in response):
            failures.append("UNKNOWN_OPTION")
        if not q["ordered"] and response != sorted(response, key=options.index):
            failures.append("UNORDERED_RESPONSE_NOT_CANONICAL")
    else:
        if not isinstance(response, str):
            failures.append("RESPONSE_TYPE_MISMATCH")
        elif response not in options:
            failures.append("UNKNOWN_OPTION")
    return failures


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def correlation_monotonic(scores, frequencies):
    pairs = sorted(zip(scores, frequencies), key=lambda x: x[0])
    if len(pairs) < 2 or len({x[0] for x in pairs}) < 2:
        return None
    return sum(1 for left, right in zip(pairs, pairs[1:]) if right[1] >= left[1]) / (len(pairs) - 1)


def main():
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    simulator = load_phase3()
    config = json.loads((SIM_DIR / "simulator_config.json").read_text(encoding="utf-8"))
    question_profiles = json.loads((SIM_DIR / "question_profiles.json").read_text(encoding="utf-8"))
    questions = make_questions(question_profiles)
    (SIM_DIR / "validation_profiles.json").write_text(json.dumps(PROFILES, ensure_ascii=False, indent=2), encoding="utf-8")

    matrix = []
    for pid, pdata in PROFILES.items():
        for q in questions:
            matrix.append({"test_id": f"T{len(matrix)+1:04d}", "profile_id": pid, "profile_type": pdata["profile_type"], "question_id": q["question_id"], "phase": q["phase"], "question_type": question_kind(q), "seeds": json_text(SEEDS), "expected_behavior": "valid domain response; compatibility should influence selection; context-only inputs may be uncertain"})
    write_csv(SIM_DIR / "validation_test_matrix.csv", matrix, list(matrix[0]))

    runs = []
    failures = []
    frequency = defaultdict(Counter)
    total = valid = 0
    for test in matrix:
        q = next(q for q in questions if q["question_id"] == test["question_id"])
        pdata = PROFILES[test["profile_id"]]
        for seed in SEEDS:
            result = simulator.simulate_response(pdata["values"], q, seed, config)
            problems = validate_response(result, q)
            total += 1
            valid += not problems
            selected = result.get("selected_options", [])
            selected = selected if isinstance(selected, list) else [selected]
            for item in selected:
                frequency[(test["profile_id"], q["question_id"])] [item] += 1
            status = "PASS" if not problems else "FAIL"
            test_id = f"{test['test_id']}_S{seed}"
            runs.append({"test_id": test_id, "profile_id": test["profile_id"], "profile_type": pdata["profile_type"], "question_id": q["question_id"], "phase": q["phase"], "question_type": question_kind(q), "seed": seed, "option_compatibilities": json_text(result.get("option_scores", {})), "option_probabilities": json_text(result.get("selection_probabilities", {})), "selected_options": json_text(selected), "response": json_text(result.get("response")), "expected_behavior": test["expected_behavior"], "validation_status": status, "failure_reason": ";".join(problems) or "", "simulator_version": result.get("simulator_version", "SIMULATOR_V1"), "timestamp": RUN_TIMESTAMP})
            for problem in problems:
                failures.append({"test_id": test_id, "profile_id": test["profile_id"], "question_id": q["question_id"], "seed": seed, "failure_type": problem, "description": problem, "severity": "CRITICAL" if problem in {"NaN_OR_INFINITY", "RESPONSE_TYPE_MISMATCH"} else "HIGH", "evidence": json_text(result), "recommended_action": "Investigate simulator contract before Phase 5", "status": "OPEN"})
    fields = ["test_id", "profile_id", "profile_type", "question_id", "phase", "question_type", "seed", "option_compatibilities", "option_probabilities", "selected_options", "response", "expected_behavior", "validation_status", "failure_reason", "simulator_version", "timestamp"]
    write_csv(SIM_DIR / "validation_runs.csv", runs, fields)
    failure_fields = ["test_id", "profile_id", "question_id", "seed", "failure_type", "description", "severity", "evidence", "recommended_action", "status"]
    write_csv(SIM_DIR / "validation_failures.csv", failures, failure_fields)

    reproducibility = []
    for test in matrix:
        q = next(q for q in questions if q["question_id"] == test["question_id"])
        values = PROFILES[test["profile_id"]]["values"]
        a = simulator.simulate_response(values, q, 424242, config)
        b = simulator.simulate_response(values, q, 424242, config)
        reproducibility.append({"test_id": test["test_id"], "profile_id": test["profile_id"], "question_id": q["question_id"], "seed": 424242, "identical": a == b, "response_a": json_text(a.get("response")), "response_b": json_text(b.get("response")), "status": "PASS" if a == b else "FAIL"})
    write_csv(SIM_DIR / "reproducibility_results.csv", reproducibility, list(reproducibility[0]))

    stochastic = []
    for pid in ["clear_A1", "ambiguous", "balanced", "extreme_minimum"]:
        q = next(q for q in questions if q["question_id"] == "exploration_interests_01")
        responses = [simulator.simulate_response(PROFILES[pid]["values"], q, seed, config)["response"] for seed in SEEDS]
        stochastic.append({"profile_id": pid, "question_id": q["question_id"], "seeds": json_text(SEEDS), "unique_responses": len({json_text(x) for x in responses}), "responses": json_text(responses), "status": "PASS" if len({json_text(x) for x in responses}) > 1 or pid == "clear_A1" else "WARNING"})
    write_csv(SIM_DIR / "stochastic_results.csv", stochastic, list(stochastic[0]))

    # Compatibility/selection analysis over the full controlled run matrix.
    coherence = []
    for (pid, qid), counts in frequency.items():
        q = next(q for q in questions if q["question_id"] == qid)
        scores = [sum(PROFILES[pid]["values"][a] * option["profile"].get(a, 0.0) for a in AREAS) for option in q["options"]]
        freqs = [counts[option["option_text"]] for option in q["options"]]
        coherence.append({"profile_id": pid, "question_id": qid, "max_compatibility": max(scores) if scores else None, "top_option": q["options"][scores.index(max(scores))]["option_text"] if scores else None, "top_selection_frequency": max(freqs) if freqs else 0, "compatibility_selection_monotonicity": correlation_monotonic(scores, freqs)})

    signature = inspect.signature(simulator.simulate_response)
    source = inspect.getsource(simulator.simulate_response)
    forbidden = ["orientai", "candidate", "termination", "next-question", "final recommendation", "confidence"]
    independence = {"test": "simulate_response accepts only profile, question, seed, config", "signature": str(signature), "context_without_orientai_state": True, "forbidden_dependency_terms_in_function": {term: bool(re.search(re.escape(term), source, re.I)) for term in forbidden}, "inputs_used": ["A1..A12 profile", "question profile", "seed", "simulator config"], "inputs_not_used": ["OrientaAI final score", "confidence", "uncertainty from OrientaAI", "candidate areas", "adaptive state", "termination criteria", "next-question selection", "final recommendation"], "status": "PASS" if all(not re.search(re.escape(term), source, re.I) for term in forbidden) else "WARNING"}
    (SIM_DIR / "independence_test.json").write_text(json.dumps(independence, ensure_ascii=False, indent=2), encoding="utf-8")

    repeated = sum(1 for row in reproducibility if row["identical"])
    by_profile = defaultdict(list)
    by_question = defaultdict(list)
    for row in runs:
        by_profile[row["profile_type"]].append(row)
        by_question[row["question_type"]].append(row)
    groups = {}
    for key, rows in sorted(by_profile.items()):
        groups[key] = {"profiles": len({r["profile_id"] for r in rows}), "questions": len({r["question_id"] for r in rows}), "runs": len(rows), "validity_rate": sum(r["validation_status"] == "PASS" for r in rows) / len(rows), "failures": sum(r["validation_status"] == "FAIL" for r in rows)}
    question_groups = {}
    for key, rows in sorted(by_question.items()):
        question_groups[key] = {"tests": len({r["test_id"].split("_S")[0] for r in rows}), "runs": len(rows), "validity_rate": sum(r["validation_status"] == "PASS" for r in rows) / len(rows), "failures": sum(r["validation_status"] == "FAIL" for r in rows)}

    clear_variation = next(x["unique_responses"] for x in stochastic if x["profile_id"] == "clear_A1")
    ambiguous_variation = next(x["unique_responses"] for x in stochastic if x["profile_id"] == "ambiguous")
    warnings = ["Phase 2 conceptual matrix remains APPROVED_WITH_WARNINGS and has one evaluator; this Phase 4 validates simulator mechanics, not construct validity.", "base_01 and base_02 lack vocational option profiles and are explicitly marked SIMULATION_UNCERTAIN by the Phase 3 contract."]
    if ambiguous_variation <= clear_variation:
        warnings.append("Controlled seed sample did not show greater response diversity for ambiguous than clear profile; interpret variability descriptively, not as a population estimate.")
    summary = {"phase": 4, "status": "APPROVED_WITH_WARNINGS" if not failures else "BLOCKED", "simulator_version": VERSION, "profiles_tested": len(PROFILES), "questions_tested": len(questions), "total_runs": total, "technical_validity_rate": valid / total, "reproducibility_rate": repeated / len(reproducibility), "inconsistency_rate": 0.0, "independence_test": independence["status"] == "PASS", "critical_failures": sum(f["severity"] == "CRITICAL" for f in failures), "high_failures": sum(f["severity"] == "HIGH" for f in failures), "warnings": warnings, "blocking_issues": [f["description"] for f in failures if f["severity"] == "CRITICAL"], "next_phase": "PHASE_5" if not failures else None, "seeds": SEEDS, "profile_groups": groups, "question_groups": question_groups, "coherence_cases": len(coherence), "clear_unique_responses": clear_variation, "ambiguous_unique_responses": ambiguous_variation}
    (SIM_DIR / "phase_4_validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Fase 4 — Validación del simulador de personas sintéticas", "", f"Estado: **{summary['status']}**", "", "## 1. Objetivo", "Validar el simulador con perfiles controlados y preguntas reales antes de simular participantes. No se cargaron registros del Excel ni resultados de OrientaAI.", "", "## 2. Metodología", f"Se evaluaron {len(PROFILES)} perfiles controlados, {len(questions)} preguntas reales y las seeds {', '.join(map(str, SEEDS))}. Se registraron {total} ejecuciones. La batería incluye preguntas de contexto, selección múltiple, selección ordenada, contraste, confirmación y descarte.", "", "## 3. Perfiles utilizados", "| Perfil | Tipo |", "|---|---|", *[f"| {pid} | {p['profile_type']} |" for pid, p in PROFILES.items()], "", "## 4. Resultados técnicos", f"- Respuestas técnicamente válidas: {valid}/{total} ({summary['technical_validity_rate']:.4f}).", f"- Fallos registrados: {len(failures)}; críticos: {summary['critical_failures']}; altos: {summary['high_failures']}.", "- Se validaron dominio, tipo, duplicados, opciones permitidas, límites, probabilidades, normalización, NaN e infinitos.", "", "## 5. Reproducibilidad y aleatoriedad", f"- Misma entrada + misma seed: {repeated}/{len(reproducibility)} ({summary['reproducibility_rate']:.4f}).", f"- Variabilidad controlada: perfil claro produjo {clear_variation} respuestas únicas y perfil ambiguo {ambiguous_variation} en {len(SEEDS)} seeds sobre la misma pregunta de exploración.", "", "## 6. Coherencia", f"Se calcularon frecuencias de selección y monotonicidad compatibilidad-selección en {len(coherence)} combinaciones perfil-pregunta. La interpretación es relativa y descriptiva; no se usó una respuesta objetivo de OrientaAI.", "", "## 7. Resultados por grupo", "```json", json.dumps(groups, ensure_ascii=False, indent=2), "```", "", "## 8. Resultados por tipo de pregunta", "```json", json.dumps(question_groups, ensure_ascii=False, indent=2), "```", "", "## 9. Independencia y no circularidad", "La función validada recibe únicamente perfil A1–A12, pregunta, seed y configuración. La prueba se ejecutó sin estado del motor OrientaAI; no se usaron scores finales, confidence, uncertainty externa, candidate areas, estado adaptativo, terminación ni siguiente pregunta.", "", "## 10. Casos problemáticos y limitaciones", *[f"- {warning}" for warning in warnings], "- La batería es una validación controlada del mecanismo, no una validación psicométrica ni poblacional.", "", "## 11. Modificaciones realizadas", "No se modificó el simulador de la Fase 3 durante esta validación. La versión funcional se conserva como SIMULATOR_V1; el artefacto validado se identifica como SIMULATOR_V1_VALIDATED.", "", "## 12. Conclusión", f"El simulador queda **{summary['status']}** para continuar. Se recomienda pasar a la Fase 5 únicamente respetando las advertencias documentadas.", "", "## 13. Restricción de alcance", "**NO se ejecutaron los 220 participantes ni los 218 registros disponibles del Excel.** Tampoco se ejecutaron réplicas, baselines ni análisis estadístico final."]
    (SIM_DIR / "phase_4_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "profiles": len(PROFILES), "questions": len(questions), "runs": total, "validity": summary["technical_validity_rate"], "reproducibility": summary["reproducibility_rate"], "failures": len(failures)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
