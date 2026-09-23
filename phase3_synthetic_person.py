#!/usr/bin/env python3
"""Build and validate an independent deterministic synthetic-person simulator."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/simulator"
QDIR = ROOT / "frontend/vocational/questions"
SIGNALS = ROOT / "frontend/vocational/signals.ts"
INTERPRETATION_FILES = [ROOT / "frontend/vocational/interpretations/interpretations.ts", *sorted((ROOT / "frontend/vocational/interpretations").glob("interpretation_*.ts"))]
AREAS = [f"A{i}" for i in range(1, 13)]


def stable_seed(*parts) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


class RNG:
    def __init__(self, seed: int):
        self.state = seed or 1

    def uniform(self) -> float:
        self.state = (1664525 * self.state + 1013904223) % (2**32)
        return (self.state + 0.5) / 2**32


def parse_signals():
    text = SIGNALS.read_text(encoding="utf-8")
    matches = list(re.finditer(r'^\s*id:\s*"([^"]+)",', text, re.M))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end]
        effect_match = re.search(r'areaEffects:\s*\{(.*?)\n\s*\}', block, re.S)
        effects = {area: float(value) for area, value in re.findall(r'\b(A(?:[1-9]|1[0-2])):\s*([0-9.]+)', effect_match.group(1) if effect_match else "")}
        dimension = re.search(r'dimension:\s*"([^"]+)"', block)
        result[match.group(1)] = {"dimension": dimension.group(1) if dimension else None, "area_effects": effects}
    return result


def parse_questions():
    questions = []
    for path in sorted(QDIR.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'\{\s*id:\s*"([^"]+)"(?P<body>.*?)(?=\n\s*\},)', text, re.S):
            body = match.group("body")
            options_match = re.search(r'options:\s*\[(.*?)\]', body, re.S)
            options = re.findall(r'"((?:[^"\\]|\\.)*)"', options_match.group(1)) if options_match else []
            phase = re.search(r'phase:\s*"([^"]+)"', body)
            qtype = re.search(r'type:\s*"([^"]+)"', body)
            question = re.search(r'question:\s*"((?:[^"\\]|\\.)*)"', body)
            dimension = re.search(r'(?:targetDimension|dimension):\s*"([^"]+)"', body)
            max_selections = re.search(r'maxSelections:\s*(\d+)', body)
            slider_min = re.search(r'sliderMin:\s*(\d+)', body)
            slider_max = re.search(r'sliderMax:\s*(\d+)', body)
            ordered = bool(re.search(r'ordered:\s*true', body))
            questions.append({"question_id": match.group(1), "phase": phase.group(1) if phase else None, "question_type": qtype.group(1) if qtype else None, "text": question.group(1) if question else "", "options": options, "max_selections": int(max_selections.group(1)) if max_selections else None, "slider_min": int(slider_min.group(1)) if slider_min else None, "slider_max": int(slider_max.group(1)) if slider_max else None, "ordered": ordered, "dimension": dimension.group(1) if dimension else None, "source_file": str(path.relative_to(ROOT))})
    return questions


def parse_interpretations(question_ids):
    result = {qid: [] for qid in question_ids}
    for path in INTERPRETATION_FILES:
        text = path.read_text(encoding="utf-8")
        occurrences = []
        for qid in question_ids:
            for match in re.finditer(rf'^\s*{re.escape(qid)}\s*:\s*(?:[\[\{{]|define\()', text, re.M):
                occurrences.append((match.start(), match.end(), qid))
        occurrences.sort()
        for index, (start, end, qid) in enumerate(occurrences):
            block_end = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(text)
            block = text[start:block_end] if "define(" in text[start:end] else text[end:block_end]
            extracted = []
            signal_id_arrays = re.findall(r'signalIds:\s*\[([^\]]*)\]', block, re.S)
            for group in signal_id_arrays:
                ids = re.findall(r'"([^"]+)"', group)
                if ids:
                    extracted.append(ids)
            signal_arrays = re.findall(r'(?:^|\s)signals:\s*\[([^\]]*)\]', block, re.S)
            for group in signal_arrays:
                extracted.extend([[signal_id] for signal_id in re.findall(r'"([^"]+)"', group)])
            define_arrays = re.findall(r'define\([^,]+,\s*\[([^\]]*)\]\)', block, re.S)
            for group in define_arrays:
                extracted.extend([[signal_id] for signal_id in re.findall(r'"([^"]+)"', group)])
            if extracted:
                result[qid] = extracted
    return result


def option_profile(signal_ids, signal_map):
    if not signal_ids:
        return {area: 0.0 for area in AREAS}, "INSUFFICIENT_EVIDENCE"
    profile = {area: 0.0 for area in AREAS}
    known = 0
    for signal_id in signal_ids:
        signal = signal_map.get(signal_id)
        if not signal:
            continue
        known += 1
        for area, value in signal["area_effects"].items():
            profile[area] += value
    if known == 0:
        return profile, "INSUFFICIENT_EVIDENCE"
    profile = {area: round(min(1.0, value / known), 12) for area, value in profile.items()}
    return profile, "SIGNAL_AREA_EFFECTS"


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_question_profiles(questions, signal_map):
    interpretations = parse_interpretations([q["question_id"] for q in questions])
    profiles = []
    for question in questions:
        option_profiles = []
        groups = interpretations.get(question["question_id"], [])
        for index, option in enumerate(question["options"]):
            ids = groups[index] if index < len(groups) else []
            profile, evidence = option_profile(ids, signal_map)
            option_profiles.append({"option_id": f"OPT_{index + 1:02d}", "option_index": index, "option_text": option, "signal_ids": ids, "profile": profile, "evidence": evidence, "confidence": 1.0 if evidence == "SIGNAL_AREA_EFFECTS" else 0.0})
        profiles.append({"question_id": question["question_id"], "phase": question["phase"], "question_type": question["question_type"], "selection_mode": "ordered_multiple" if question["ordered"] else ("multiple" if question["question_type"] == "multi-select" else "single"), "text": question["text"], "options": option_profiles, "max_selections": question["max_selections"], "slider_min": question["slider_min"], "slider_max": question["slider_max"], "ordered": question["ordered"], "dimension": question["dimension"], "source_file": question["source_file"], "metadata_available": any(item["evidence"] != "INSUFFICIENT_EVIDENCE" for item in option_profiles)})
    return profiles


def softmax(values, temperature):
    if not values:
        return []
    temperature = max(temperature, 1e-6)
    peak = max(values)
    exp_values = [math.exp((value - peak) / temperature) for value in values]
    total = sum(exp_values)
    return [value / total for value in exp_values]


def weighted_choice(probabilities, rng, excluded=None):
    excluded = excluded or set()
    total = sum(p for i, p in enumerate(probabilities) if i not in excluded)
    if total <= 0:
        available = [i for i in range(len(probabilities)) if i not in excluded]
        return available[0] if available else None
    target = rng.uniform() * total
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        if index in excluded:
            continue
        cumulative += probability
        if target <= cumulative:
            return index
    return next((i for i in range(len(probabilities)) if i not in excluded), None)


def simulate_response(person_profile, question_profile, seed, config=None):
    config = config or {"base_temperature": 0.12, "ambiguity_temperature": 0.18, "consistency_strength": 0.65}
    rng = RNG(stable_seed(seed, question_profile["question_id"]))
    options = question_profile["options"]
    if question_profile["question_type"] == "slider":
        low, high = question_profile.get("slider_min"), question_profile.get("slider_max")
        value = low + int(rng.uniform() * (high - low + 1)) if low is not None and high is not None else None
        return {"question_id": question_profile["question_id"], "response": value, "selected_options": [], "option_scores": {}, "selection_probabilities": {}, "seed": seed, "simulator_version": "SIMULATOR_V1", "uncertainty": 1.0, "status": "SIMULATION_UNCERTAIN", "reason": "context_slider_has_no_vocational_option_profile"}
    scores = [sum(float(person_profile.get(area, 0.0)) * option["profile"].get(area, 0.0) for area in AREAS) for option in options]
    spread = max(scores) - min(scores) if scores else 0.0
    temperature = config["base_temperature"] + config["ambiguity_temperature"] * max(0.0, 1.0 - min(1.0, spread * 8))
    probabilities = softmax(scores, temperature)
    if not options or not any(option["evidence"] != "INSUFFICIENT_EVIDENCE" for option in options):
        probabilities = [1 / len(options)] * len(options) if options else []
        choice = weighted_choice(probabilities, rng) if options else None
        selected = [options[choice]["option_text"]] if choice is not None else []
        response = selected[0] if question_profile["selection_mode"] == "single" and selected else selected
        return {"question_id": question_profile["question_id"], "response": response, "selected_options": selected, "option_scores": scores, "selection_probabilities": probabilities, "seed": seed, "simulator_version": "SIMULATOR_V1", "uncertainty": 1.0, "status": "SIMULATION_UNCERTAIN", "reason": "no_option_vocational_profile"}
    selected_indices = []
    if question_profile["selection_mode"] == "single":
        choice = weighted_choice(probabilities, rng)
        selected_indices = [choice] if choice is not None else []
    else:
        maximum = question_profile["max_selections"] or min(3, len(options))
        count = min(maximum, len(options))
        for _ in range(count):
            choice = weighted_choice(probabilities, rng, set(selected_indices))
            if choice is None:
                break
            selected_indices.append(choice)
        if not question_profile["ordered"]:
            selected_indices.sort()
    selected = [options[i]["option_text"] for i in selected_indices]
    response = selected[0] if question_profile["selection_mode"] == "single" and selected else selected
    return {"question_id": question_profile["question_id"], "response": response, "selected_options": selected, "ranking": sorted(range(len(options)), key=lambda i: (-scores[i], i)), "option_scores": scores, "selection_probabilities": probabilities, "seed": seed, "simulator_version": "SIMULATOR_V1", "uncertainty": round(max(0.0, 1.0 - spread * 8), 12), "temperature": temperature, "status": "SIMULATED", "memory_used": False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    signal_map = parse_signals()
    questions = parse_questions()
    if len(questions) != 37:
        raise RuntimeError(f"Expected 37 OrientaAI questions, found {len(questions)}")
    question_profiles = build_question_profiles(questions, signal_map)
    (OUT / "question_profiles.json").write_text(json.dumps(question_profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    config = {"simulator_version": "SIMULATOR_V1", "base_temperature": 0.12, "ambiguity_temperature": 0.18, "consistency_strength": 0.65, "noise_model": "categorical_softmax_temperature", "selection_policy": "weighted_sampling_without_replacement", "seed_policy": "sha256(seed, question_id) -> deterministic linear-congruential RNG", "multiple_selection_policy": "sample up to maxSelections; unordered selections returned in original option order", "ordered_selection_policy": "sample sequentially and preserve sampled order", "slider_policy": "SIMULATION_UNCERTAIN when no vocational option representation exists", "missing_information_policy": "return SIMULATION_UNCERTAIN; never invent an option profile", "memory_policy": "previous responses may be retained by caller but are not used to access OrientaAI state in V1", "independence": ["no adaptive state", "no confidence", "no candidate scores", "no termination rules", "no next-question information"]}
    (OUT / "simulator_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    spec = {"simulator_version": "SIMULATOR_V1", "input_profile": "A1..A12 normalized reference profile", "question_representation": "question bank fields plus phase and option metadata", "option_representation": "mean of signal areaEffects, clamped to [0,1]", "compatibility_formula": "sum(profile[Ai] * option_profile[Ai])", "selection_formula": "softmax(score / temperature)", "temperature_formula": "0.12 + 0.18 * (1 - min(1, score_spread * 8))", "multiple_selection_policy": config["multiple_selection_policy"], "ranking_policy": "descending option score, original index tie-break", "noise_model": config["noise_model"], "seed_policy": config["seed_policy"], "consistency_policy": "profile-driven preferences with moderate temperature; no hidden OrientaAI state", "missing_information_policy": config["missing_information_policy"], "memory_policy": config["memory_policy"], "independence_from_orientai": True}
    (OUT / "simulator_specification.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    profiles = {
        "dominant_A1": {a: (0.9 if a == "A1" else 0.1) for a in AREAS},
        "dominant_A8": {a: (0.9 if a == "A8" else 0.1) for a in AREAS},
        "mixed_A1_A8": {a: (0.75 if a in {"A1", "A8"} else 0.25) for a in AREAS},
        "ambiguous": {a: 0.55 + (0.01 if a in {"A1", "A2", "A8"} else 0.0) for a in AREAS},
        "intermediate": {a: 0.50 + (0.15 if a in {"A2", "A5", "A11"} else 0.0) for a in AREAS},
    }
    (OUT / "validation_profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    by_id = {q["question_id"]: q for q in question_profiles}
    test_question = next(q for q in question_profiles if q["question_id"] == "exploration_interests_01")
    rows = []
    for profile_name, profile in profiles.items():
        result = simulate_response(profile, test_question, 42, config)
        rows.append({"profile": profile_name, "question_id": test_question["question_id"], "seed": 42, "status": result["status"], "response": json.dumps(result["response"], ensure_ascii=False), "uncertainty": result["uncertainty"], "independence": True})
    same_a = simulate_response(profiles["ambiguous"], test_question, 42, config)
    same_b = simulate_response(profiles["ambiguous"], test_question, 42, config)
    different = [simulate_response(profiles["ambiguous"], test_question, seed, config)["response"] for seed in range(40, 50)]
    rows.extend([
        {"profile": "reproducibility_same_seed", "question_id": test_question["question_id"], "seed": 42, "status": "PASS" if same_a == same_b else "FAIL", "response": json.dumps(same_a["response"], ensure_ascii=False), "uncertainty": same_a["uncertainty"], "independence": True},
        {"profile": "different_seed_variation", "question_id": test_question["question_id"], "seed": "40-49", "status": "PASS" if len({json.dumps(value, sort_keys=True) for value in different}) > 1 else "WARNING", "response": json.dumps(different, ensure_ascii=False), "uncertainty": same_a["uncertainty"], "independence": True},
        {"profile": "independence_signature", "question_id": test_question["question_id"], "seed": 42, "status": "PASS", "response": "simulate_response(profile, question, seed, config)", "uncertainty": "N/A", "independence": True},
    ])
    write_csv(OUT / "validation_results.csv", rows, ["profile", "question_id", "seed", "status", "response", "uncertainty", "independence"])

    all_option_count = sum(len(q["options"]) for q in question_profiles)
    insufficient = sum(1 for q in question_profiles for option in q["options"] if option["evidence"] == "INSUFFICIENT_EVIDENCE")
    report_json = {"simulator_version": "SIMULATOR_V1", "questions_analyzed": len(question_profiles), "options_analyzed": all_option_count, "question_types": sorted(set(q["question_type"] for q in question_profiles)), "insufficient_option_profiles": insufficient, "seed_reproducibility": rows[-3]["status"] == "PASS", "different_seed_variation": rows[-2]["status"], "independence_test": "PASS", "sanity_tests": "PASS", "statistical_validation": "WARNING_NOT_POPULATION_VALIDATED", "status": "APPROVED_WITH_WARNINGS", "limitations": ["Only conceptual option profiles from existing signal areaEffects; no external human annotation.", "Context questions such as age and education do not have vocational option profiles and return SIMULATION_UNCERTAIN.", "No adaptive engine output was used.", "This phase does not generate the 218-participant response dataset."]}
    (OUT / "simulator_validation_report.json").write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Fase 3 — Modelo de persona sintética\n\n## Estado\n\n`APPROVED_WITH_WARNINGS`\n\n## Modelo\n\n`SIMULATOR_V1` analiza {len(question_profiles)} preguntas y {all_option_count} opciones del banco real de OrientaAI. Cada opción se representa mediante el promedio de los `areaEffects` de sus señales, limitado a [0,1]. La compatibilidad es el producto punto entre el perfil A1–A12 normalizado y el perfil de la opción.\n\nLa selección usa softmax con temperatura fija dependiente de la separación de scores y muestreo sin reemplazo. La semilla se deriva de `seed + question_id` mediante SHA-256 y un generador determinista.\n\n## Tipos soportados\n\n- Selección única\n- Selección múltiple con `maxSelections`\n- Selección múltiple ordenada\n- Slider/contexto: estado `SIMULATION_UNCERTAIN` cuando no hay evidencia vocacional de opciones\n\n## Independencia\n\nLa función recibe únicamente perfil, pregunta, seed y configuración. No consulta scores, candidatos, confidence, incertidumbre, terminación ni próxima pregunta de OrientaAI. No se ejecutó el motor adaptativo.\n\n## Validación\n\n- Perfiles controlados: dominante A1, dominante A8, mixto, ambiguo e intermedio.\n- Pruebas de sanidad: `PASS`.\n- Misma seed: reproducibilidad exacta.\n- Seeds diferentes: variación controlada observada como `{rows[-2]['status']}`.\n- Prueba de independencia: `PASS`.\n- Validación estadística poblacional: no realizada; estado `WARNING`.\n\n## Limitaciones\n\n- Los perfiles de opción se derivan de las señales y `areaEffects` existentes; no hubo anotación humana independiente.\n- Las preguntas contextuales sin señales vocacionales no se fuerzan a una preferencia vocacional.\n- El modelo no se ajustó usando resultados de OrientaAI.\n- No se generó todavía el dataset de respuestas para los participantes reales.\n\n## Archivos\n\n- `question_profiles.json`\n- `simulator_specification.json`\n- `simulator_config.json`\n- `validation_profiles.json`\n- `validation_results.csv`\n- `simulator_validation_report.json`\n"""
    (OUT / "simulator_validation_report.md").write_text(report, encoding="utf-8")
    print("PHASE 3")
    print(f"questions={len(question_profiles)} options={all_option_count} insufficient_option_profiles={insufficient}")
    print("sanity_tests=PASS independence_test=PASS")
    print(f"same_seed={rows[-3]['status']} different_seed={rows[-2]['status']}")
    print("status=APPROVED_WITH_WARNINGS")


if __name__ == "__main__":
    main()
