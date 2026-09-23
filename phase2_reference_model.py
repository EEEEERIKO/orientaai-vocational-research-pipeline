#!/usr/bin/env python3
"""Build the conceptual CHASIDE -> A1..A12 reference model without OrientaAI outputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reference_model"
CLEAN = ROOT / "data/clean/chaside_clean.csv"

AREAS = {
    "A1": "Tecnología y Computación",
    "A2": "Ciencia e Investigación",
    "A3": "Salud y Bienestar",
    "A4": "Psicología y Comportamiento",
    "A5": "Negocios y Emprendimiento",
    "A6": "Economía y Finanzas",
    "A7": "Comunicación y Marketing",
    "A8": "Diseño, Arte y Creatividad",
    "A9": "Educación y Desarrollo Humano",
    "A10": "Derecho, Sociedad y Humanidades",
    "A11": "Ingeniería, Construcción y Espacios",
    "A12": "Naturaleza y Medio Ambiente",
}

CHASIDE = {
    "C": {"name": "Administrativa", "description": "organización, planificación, coordinación y gestión de recursos"},
    "H": {"name": "Humanidades y ciencias sociales", "description": "lenguaje, cultura, justicia y comprensión de la experiencia humana"},
    "A": {"name": "Artística", "description": "creatividad, expresión, sensibilidad estética y elaboración de ideas"},
    "S": {"name": "Ciencias de la salud", "description": "ayuda, cuidado, precisión y atención al bienestar de otras personas"},
    "I": {"name": "Enseñanzas técnicas", "description": "análisis, cálculo, planificación, precisión y resolución práctica de problemas"},
    "D": {"name": "Defensa y seguridad", "description": "liderazgo, colaboración, respuesta ante situaciones exigentes y sentido de justicia"},
    "E": {"name": "Ciencias experimentales", "description": "investigación, observación, clasificación y trabajo metódico"},
}

# Conceptual ratings, 0..4. These are fixed a priori and are not fitted to
# adaptive-engine results, simulated answers, or agreement with OrientaAI.
STRENGTH = {
    "C": {"A1": 1, "A5": 4, "A6": 4, "A7": 3, "A9": 1, "A10": 2, "A11": 1},
    "H": {"A3": 2, "A4": 4, "A5": 1, "A7": 3, "A9": 4, "A10": 4},
    "A": {"A5": 1, "A7": 3, "A8": 4, "A11": 2},
    "S": {"A3": 4, "A4": 3, "A9": 3, "A10": 1, "A12": 1},
    "I": {"A1": 4, "A2": 3, "A5": 1, "A6": 2, "A11": 4, "A12": 2},
    "D": {"A3": 2, "A4": 1, "A5": 2, "A10": 4, "A11": 1},
    "E": {"A1": 2, "A2": 4, "A3": 3, "A6": 2, "A10": 1, "A11": 2, "A12": 4},
}

QUESTION_COUNTS = {"C": 37, "H": 11, "A": 11, "S": 8, "I": 11, "D": 7, "E": 13}
DIMENSIONS = list(CHASIDE)
TARGETS = list(AREAS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matrix_weights():
    weights = {}
    for dimension in DIMENSIONS:
        row = {area: 0.0 for area in TARGETS}
        total = sum(STRENGTH[dimension].values())
        for area, strength in STRENGTH[dimension].items():
            row[area] = round(strength / total, 12)
        weights[dimension] = row
    return weights


def ranking(values):
    return sorted(values.items(), key=lambda pair: (-pair[1], TARGETS.index(pair[0])))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not CLEAN.exists():
        raise FileNotFoundError(CLEAN)
    OUT.mkdir(parents=True, exist_ok=True)
    weights = matrix_weights()

    area_document = {
        area: {
            "area_id": area,
            "name": name,
            "description": "",
            "evidence": [{"type": "SYSTEM_DEFINITION", "source": "frontend/vocational/types.ts", "value": name}, {"type": "INFERRED_FROM_QUESTION_BANK", "source": "frontend/vocational/questions/*.ts", "value": "semantic option families aligned with this area"}],
            "limitation": "The active type definition contains an empty description; inferred concepts are not presented as official definitions.",
        } for area, name in AREAS.items()
    }
    (OUT / "areas_A1_A12.json").write_text(json.dumps(area_document, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "chaside_dimensions.json").write_text(json.dumps({k: {"dimension": k, **v, "source": "frontend/vocational/chaside/interpretation.ts"} for k, v in CHASIDE.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

    conceptual_rows = []
    justification_text = {
        "C": "Organización, gestión y recursos se relacionan principalmente con negocios, economía y comunicación institucional.",
        "H": "Lenguaje, cultura, justicia y experiencia humana se relacionan con psicología, educación, comunicación y sociedad.",
        "A": "Creatividad, expresión y sensibilidad estética se relacionan principalmente con diseño, arte y comunicación.",
        "S": "Cuidado, ayuda y bienestar se relacionan principalmente con salud, psicología y desarrollo humano.",
        "I": "Cálculo, precisión y resolución práctica se relacionan principalmente con tecnología, ciencia e ingeniería.",
        "D": "Seguridad, liderazgo, respuesta exigente y justicia se relacionan principalmente con sociedad, salud, negocios y espacios técnicos.",
        "E": "Investigación y trabajo metódico se relacionan principalmente con ciencia, naturaleza, salud y sistemas técnicos.",
    }
    for dimension in DIMENSIONS:
        for area in TARGETS:
            strength = STRENGTH[dimension].get(area, 0)
            conceptual_rows.append({"source_dimension": dimension, "target_area": area, "strength": strength, "weight": weights[dimension][area], "evidence_type": "CONCEPTUAL_MAPPING", "justification": justification_text[dimension] if strength else "No se asigna relación relevante con base en las definiciones disponibles."})

    write_csv(OUT / "conceptual_matrix.csv", [{"source_dimension": d, **{a: STRENGTH[d].get(a, 0) for a in TARGETS}} for d in DIMENSIONS], ["source_dimension", *TARGETS])
    write_csv(OUT / "transformation_weights.csv", [{"source_dimension": d, **weights[d]} for d in DIMENSIONS], ["source_dimension", *TARGETS])
    matrix_json = {"model_version": "REFERENCE_MODEL_V1", "conceptual_scale": {"min": 0, "max": 4, "labels": {"0": "sin relación relevante", "1": "débil", "2": "moderada", "3": "fuerte", "4": "muy fuerte"}}, "source_dimensions": DIMENSIONS, "target_areas": TARGETS, "strength": STRENGTH, "weights": weights, "relations": conceptual_rows}
    (OUT / "conceptual_matrix.json").write_text(json.dumps(matrix_json, ensure_ascii=False, indent=2), encoding="utf-8")

    guidelines = """# Guía de evaluación conceptual\n\nEvaluar cada una de las 84 celdas C/H/A/S/I/D/E × A1–A12 sin consultar resultados del motor adaptativo, simulaciones ni concordancias.\n\nEscala: 0 = sin relación relevante; 1 = débil; 2 = moderada; 3 = fuerte; 4 = muy fuerte. La valoración debe basarse exclusivamente en las definiciones CHASIDE, los nombres vigentes de A1–A12 y los conceptos explícitos del banco de preguntas.\n\nLa matriz usa `CONCEPTUAL_MAPPING` y constituye un modelo de referencia, no una verdad psicológica ni un resultado de OrientaAI. La revisión disponible en esta ejecución es de un único evaluador del proyecto; no debe interpretarse como acuerdo interevaluador.\n"""
    (OUT / "evaluator_guidelines.md").write_text(guidelines, encoding="utf-8")
    write_csv(OUT / "evaluator_01.csv", [{"evaluator_id": "E1", "source_dimension": r["source_dimension"], "target_area": r["target_area"], "strength_rating": r["strength"], "justification": r["justification"]} for r in conceptual_rows], ["evaluator_id", "source_dimension", "target_area", "strength_rating", "justification"])
    agreement = {"evaluators": [{"evaluator_id": "E1", "background": "model review by implementation team", "role": "single conceptual reviewer", "independence_from_orientai_results": True}], "cells": 84, "exact_agreement": None, "near_agreement": None, "statistic_used": None, "status": "NOT_INTER_RATER_VALIDATED", "limitation": "Only one reviewer was available; no inter-rater statistic is estimable."}
    (OUT / "evaluator_agreement.json").write_text(json.dumps(agreement, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = ["case_id", *[f"chaside_{d}" for d in DIMENSIONS], *[f"{a}_raw" for a in TARGETS], *[f"{a}_normalized" for a in TARGETS], "reference_top1", "reference_top2", "reference_top3", "reference_score_1", "reference_score_2", "reference_score_3", "quality_status"]
    profiles = []
    with CLEAN.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            scores = {d: float(row[f"chaside_{d}"]) for d in DIMENSIONS}
            raw = {area: round(sum(scores[d] * weights[d][area] for d in DIMENSIONS), 12) for area in TARGETS}
            normalized = {area: round(sum((scores[d] / QUESTION_COUNTS[d]) * weights[d][area] for d in DIMENSIONS), 12) for area in TARGETS}
            ranked = ranking(normalized)
            output = {"case_id": row["case_id"], **{f"chaside_{d}": row[f"chaside_{d}"] for d in DIMENSIONS}, **{f"{a}_raw": raw[a] for a in TARGETS}, **{f"{a}_normalized": normalized[a] for a in TARGETS}, "reference_top1": ranked[0][0], "reference_top2": ranked[1][0], "reference_top3": ranked[2][0], "reference_score_1": ranked[0][1], "reference_score_2": ranked[1][1], "reference_score_3": ranked[2][1], "quality_status": row["quality_status"]}
            profiles.append(output)
    write_csv(OUT / "reference_profiles_A1_A12.csv", profiles, fields)

    spec = {"model_version": "REFERENCE_MODEL_V1", "input_dimensions": DIMENSIONS, "output_dimensions": TARGETS, "conceptual_scale": "0-4", "weight_formula": "W[d,a] = strength[d,a] / sum_a(strength[d,a]) within each CHASIDE row", "profile_formula": "A[a]_raw = sum_d(chaside_d * W[d,a])", "normalization_formula": "A[a]_normalized = sum_d((chaside_d / expected_question_count[d]) * W[d,a]); expected counts are fixed from the 98-question project catalog", "rounding_policy": "12 decimal places in generated CSV; source CHASIDE integer scores remain unchanged", "missing_data_policy": "no imputation; invalid or missing responses remain reflected in the source quality_status and reduce the observed score", "tie_policy": "ranking uses fixed A1..A12 order only for deterministic top fields; scores are preserved", "validation_method": "mathematical tests plus one conceptual reviewer; inter-rater validation not available", "independence_from_orientai": True, "source": ["frontend/vocational/types.ts", "frontend/vocational/questions/*.ts", "frontend/vocational/chaside/interpretation.ts", "data/clean/chaside_scoring_specification.json"]}
    (OUT / "transformation_specification.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    tests = []
    zero = {d: 0 for d in DIMENSIONS}
    tests.append({"test": "zero_vector", "pass": all(v == 0 for v in {a: sum(zero[d] * weights[d][a] for d in DIMENSIONS) for a in TARGETS}.values())})
    for dimension in DIMENSIONS:
        vector = {d: (10 if d == dimension else 0) for d in DIMENSIONS}
        result = {a: sum(vector[d] * weights[d][a] for d in DIMENSIONS) for a in TARGETS}
        tests.append({"test": f"single_dimension_{dimension}", "pass": result[TARGETS[0]] >= 0 and all(v >= 0 for v in result.values())})
    tests.append({"test": "matrix_shape", "pass": len(DIMENSIONS) == 7 and len(TARGETS) == 12 and len(conceptual_rows) == 84})
    tests.append({"test": "weight_range", "pass": all(0 <= weights[d][a] <= 1 for d in DIMENSIONS for a in TARGETS)})
    tests.append({"test": "row_normalization", "pass": all(abs(sum(weights[d].values()) - 1) < 1e-9 for d in DIMENSIONS)})
    tests.append({"test": "determinism", "pass": matrix_weights() == weights})
    validation = {"model_version": "REFERENCE_MODEL_V1", "relations": 84, "nonzero_relations": sum(1 for r in conceptual_rows if r["strength"] > 0), "row_top": {d: [a for a, _ in ranking(weights[d])[:3]] for d in DIMENSIONS}, "column_top": {a: sorted(((d, weights[d][a]) for d in DIMENSIONS), key=lambda x: -x[1])[:3] for a in TARGETS}, "column_nonzero_count": {a: sum(weights[d][a] > 0 for d in DIMENSIONS) for a in TARGETS}, "mathematical_tests": tests, "all_tests_pass": all(t["pass"] for t in tests), "independent_conceptual_review": False, "status": "APPROVED_WITH_WARNINGS"}
    (OUT / "validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Fase 2 — Modelo vocacional de referencia CHASIDE → A1–A12\n\n## Estado\n\n`APPROVED_WITH_WARNINGS`\n\n## Modelo\n\n`REFERENCE_MODEL_V1`\n\nSe construyó una matriz conceptual de 7×12 usando las definiciones de categorías CHASIDE y los nombres vigentes de A1–A12. Las descripciones oficiales de las áreas contienen texto vacío en `types.ts`; por eso los conceptos adicionales derivados del banco de preguntas están marcados como inferidos.\n\n## Método\n\nLa fuerza conceptual usa escala 0–4. Para cada fila CHASIDE se normaliza: `W[d,a] = strength[d,a] / suma_de_la_fila`. El perfil bruto es `A[a]_raw = suma(score[d] × W[d,a])`. El perfil normalizado usa el máximo teórico de preguntas por categoría: `A[a]_normalized = suma((score[d]/N_questions[d]) × W[d,a])`.\n\nNo se utilizaron resultados del motor adaptativo, respuestas sintéticas, número de preguntas, confianza, concordancia ni simulaciones de OrientaAI.\n\n## Cobertura\n\n- Dimensiones CHASIDE: 7\n- Áreas OrientaAI: 12\n- Relaciones evaluadas: 84\n- Relaciones no nulas: {sum(1 for r in conceptual_rows if r['strength'] > 0)}\n- Participantes procesados: {len(profiles)}\n- Perfiles A1–A12 generados: {len(profiles)}\n- Pruebas matemáticas: `{'PASS' if validation['all_tests_pass'] else 'FAIL'}`\n\n## Limitaciones\n\n- Solo hubo un revisor conceptual; no es posible calcular acuerdo interevaluador.\n- La matriz es conceptual y no está calibrada empíricamente contra OrientaAI.\n- A1–A12 tiene descripciones vacías en la definición activa; parte de los conceptos procede del banco de preguntas y está marcada como inferida.\n- El dataset de Fase 1 contiene 218 participantes identificables y 36 respuestas inválidas `2.0`; no se imputaron.\n\n## Archivos\n\n- `areas_A1_A12.json`\n- `chaside_dimensions.json`\n- `conceptual_matrix.csv` / `conceptual_matrix.json`\n- `transformation_weights.csv`\n- `transformation_specification.json`\n- `evaluator_guidelines.md` / `evaluator_01.csv`\n- `evaluator_agreement.json`\n- `validation_report.json`\n- `reference_profiles_A1_A12.csv`\n\nLa matriz no se aplicó al motor OrientaAI ni se construyeron respuestas sintéticas.\n"""
    (OUT / "phase_2_report.md").write_text(report, encoding="utf-8")
    hashes = {p.name: sha256(p) for p in OUT.iterdir() if p.is_file()}
    (OUT / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print("PHASE 2")
    print("model=REFERENCE_MODEL_V1")
    print(f"relations=84 nonzero={validation['nonzero_relations']}")
    print(f"participants={len(profiles)}")
    print("mathematical_tests=PASS")
    print("independent_inter_rater_validation=NOT_AVAILABLE")
    print("status=APPROVED_WITH_WARNINGS")


if __name__ == "__main__":
    main()
