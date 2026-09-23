#!/usr/bin/env python3
"""Phase 7 descriptive concordance evaluation for the 218-case experiment."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data/evaluation"
AREAS = [f"A{i}" for i in range(1, 13)]


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(data[0]) if data else ["status"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=fields)
        out.writeheader()
        out.writerows(data)


def ranking(values):
    return [a for a, _ in sorted(values.items(), key=lambda item: (-item[1], AREAS.index(item[0])))]


def spearman(left, right):
    n = len(left)
    if n < 2:
        return None
    d2 = sum((left[a] - right[a]) ** 2 for a in AREAS)
    return 1 - (6 * d2) / (n * (n * n - 1))


def minmax(values):
    low, high = min(values), max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(x - low) / (high - low) for x in values]


def main():
    EVAL.mkdir(parents=True, exist_ok=True)
    refs = rows(ROOT / "data/reference_model/reference_profiles_A1_A12.csv")
    results = rows(ROOT / "data/experiment/results.csv")
    if len(refs) != 218 or len(results) != 218:
        raise RuntimeError(f"Expected 218 reference/results rows, got {len(refs)}/{len(results)}")
    ref_by_id = {r["case_id"]: r for r in refs}
    result_by_id = {r["participant_id"]: r for r in results}
    participant_rows, discrepancy_rows, rank_rows = [], [], []
    vectors = []
    for pid in sorted(ref_by_id):
        ref = ref_by_id[pid]
        reference_raw = {a: float(ref[f"{a}_raw"]) for a in AREAS}
        reference_norm = {a: float(ref[f"{a}_normalized"]) for a in AREAS}
        ref_rank = ranking(reference_norm)
        run = json.loads((ROOT / "data/experiment/runs" / f"{pid}.json").read_text(encoding="utf-8"))
        final = run["final_result"] or {}
        orient_rank_items = final.get("final_ranking") or []
        orient_scores = {item["area"]: float(item.get("score", 0.0)) for item in orient_rank_items if item.get("area") in AREAS}
        orient_scores = {a: orient_scores.get(a, 0.0) for a in AREAS}
        orient_rank = ranking(orient_scores)
        final_area = final.get("final_area") or result_by_id[pid].get("final_area")
        top1 = int(final_area == ref_rank[0])
        top3 = int(final_area in ref_rank[:3])
        overlap = len(set(ref_rank[:3]) & set(orient_rank[:3])) / 3
        ref_rank_pos = {a: i + 1 for i, a in enumerate(ref_rank)}
        orient_rank_pos = {a: i + 1 for i, a in enumerate(orient_rank)}
        rank_similarity = spearman(ref_rank_pos, orient_rank_pos)
        ref_scaled = minmax([reference_norm[a] for a in AREAS])
        orient_scaled = minmax([orient_scores[a] for a in AREAS])
        profile_distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(ref_scaled, orient_scaled))) / math.sqrt(len(AREAS))
        participant_rows.append({"participant_id": pid, "execution_id": run["execution_id"], "reference_model_version": "REFERENCE_MODEL_V1", "orientaai_version": "frontend/vocational engine 1.0.0", "simulator_version": "SIMULATOR_V1_VALIDATED", "reference_raw_scores": json.dumps(reference_raw), "reference_normalized_scores": json.dumps(reference_norm), "reference_ranking": json.dumps(ref_rank), "orientaai_final_area": final_area, "orientaai_final_scores": json.dumps(orient_scores), "orientaai_ranking": json.dumps(orient_rank), "top1_match": top1, "top3_match": top3, "top3_overlap": overlap, "ranking_similarity_spearman": rank_similarity, "profile_distance_minmax_euclidean": profile_distance, "seed": run["seed"]})
        vectors.append(participant_rows[-1])
        if not top1:
            discrepancy_rows.append({"participant_id": pid, "execution_id": run["execution_id"], "reference_top1": ref_rank[0], "reference_top3": json.dumps(ref_rank[:3]), "orientaai_final_area": final_area, "orientaai_top3": json.dumps(orient_rank[:3]), "top3_overlap": overlap, "ranking_similarity_spearman": rank_similarity, "profile_distance": profile_distance, "observed_pattern": "Top-1 discrepancy", "possible_explanations": "Instrument/model differences, profile ambiguity, simulator realization, or OrientaAI sensitivity; not an automatic error."})
        for area in AREAS:
            rank_rows.append({"participant_id": pid, "area": area, "reference_rank": ref_rank_pos[area], "orientaai_rank": orient_rank_pos[area], "reference_score_normalized": reference_norm[area], "orientaai_score": orient_scores[area], "reference_top1": int(area == ref_rank[0]), "reference_top3": int(area in ref_rank[:3]), "orientaai_final_area": int(area == final_area)})
    write_csv(EVAL / "participant_concordance.csv", participant_rows)
    write_csv(EVAL / "rank_position_distribution.csv", rank_rows)
    write_csv(EVAL / "discrepancy_cases.csv", discrepancy_rows)
    rep_rows = rows(ROOT / "data/replications/replication_results.csv")
    replication_concordance = []
    for r in rep_rows:
        ref = ref_by_id[r["participant_id"]]; ref_rank = ranking({a: float(ref[f"{a}_normalized"]) for a in AREAS}); final_area = r["final_area"]
        replication_concordance.append({"participant_id": r["participant_id"], "execution_id": r["execution_id"], "condition_id": "BASE", "seed": r["seed"], "reference_top1": ref_rank[0], "reference_top3": json.dumps(ref_rank[:3]), "orientaai_final_area": final_area, "top1_match": int(final_area == ref_rank[0]), "top3_match": int(final_area in ref_rank[:3]), "execution_status": r["execution_status"]})
    write_csv(EVAL / "replication_concordance.csv", replication_concordance)
    total = len(participant_rows); top1_n = sum(int(r["top1_match"]) for r in participant_rows); top3_n = sum(int(r["top3_match"]) for r in participant_rows)
    area_stats=[]
    for a in AREAS:
        ref_top1=sum(int(r["reference_top1"]) for r in rank_rows if r["area"]==a); out_final=sum(int(r["orientaai_final_area"]) for r in rank_rows if r["area"]==a); agree=sum(1 for r in participant_rows if int(r["top1_match"]) and r["orientaai_final_area"]==a)
        area_stats.append({"area":a,"reference_top1_count":ref_top1,"orientaai_final_count":out_final,"top1_agreement_count":agree,"reference_top3_count":sum(int(r["reference_top3"]) for r in rank_rows if r["area"]==a),"final_in_reference_top3_count":sum(1 for r in participant_rows if r["orientaai_final_area"]==a and a in json.loads(r["reference_ranking"])[:3]),"final_area_rate":out_final/total})
    write_csv(EVAL / "area_concordance_matrix.csv", area_stats)
    rep_top1=sum(int(r["top1_match"]) for r in replication_concordance); rep_top3=sum(int(r["top3_match"]) for r in replication_concordance)
    summary={"phase":7,"status":"COMPLETED_WITH_WARNINGS","participants_evaluated":total,"executions_evaluated":total,"replication_executions_evaluated":len(replication_concordance),"top1_matches":top1_n,"top1_rate":top1_n/total,"top3_matches":top3_n,"top3_rate":top3_n/total,"mean_top3_overlap":sum(float(r["top3_overlap"]) for r in participant_rows)/total,"mean_ranking_similarity_spearman":sum(float(r["ranking_similarity_spearman"]) for r in participant_rows)/total,"mean_profile_distance_minmax_euclidean":sum(float(r["profile_distance_minmax_euclidean"]) for r in participant_rows)/total,"replication_top1_rate":rep_top1/len(replication_concordance),"replication_top3_rate":rep_top3/len(replication_concordance),"high_concordance_cases":sum(1 for r in participant_rows if int(r["top1_match"]) and float(r["top3_overlap"])>=2/3),"discrepancy_cases":total-top1_n,"reference_model_intact":True,"ranking_metric":"Spearman correlation over deterministic A1-A12 rank order; ties resolved by A1-A12 order.","profile_metric":"Euclidean distance after independent min-max normalization of reference and OrientaAI A1-A12 scores; descriptive only.","next_phase":"PHASE_8"}
    (EVAL / "concordance_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (EVAL / "evaluation_manifest.json").write_text(json.dumps({"phase":7,"status":summary["status"],"reference_model_version":"REFERENCE_MODEL_V1","participants":total,"executions":total,"replication_executions":len(replication_concordance),"created_at":datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report=f"""# Fase 7 — Concordancia entre referencia y OrientaAI

Estado: **{summary['status']}**

Se evaluaron {total} participantes y {len(replication_concordance)} ejecuciones adaptativas replicadas. La referencia fue el perfil normalizado A1–A12 de `REFERENCE_MODEL_V1`; OrientaAI aportó área final, ranking y scores finales registrados en los recorridos.

## Métricas principales

- Top-1: {top1_n}/{total} ({summary['top1_rate']:.4f}).
- Top-3: {top3_n}/{total} ({summary['top3_rate']:.4f}).
- Solapamiento medio Top-3: {summary['mean_top3_overlap']:.4f}.
- Similitud media de ranking Spearman: {summary['mean_ranking_similarity_spearman']:.4f}.
- Distancia media de perfiles min-max: {summary['mean_profile_distance_minmax_euclidean']:.4f}.
- Replicaciones: Top-1 {summary['replication_top1_rate']:.4f}; Top-3 {summary['replication_top3_rate']:.4f}.

## Interpretación descriptiva

Se identificaron {summary['high_concordance_cases']} casos de alta concordancia y {summary['discrepancy_cases']} discrepancias Top-1. Una discrepancia no demuestra que OrientaAI sea incorrecto: puede reflejar diferencias entre instrumentos, el modelo CHASIDE→A1–A12, ambigüedad, aleatoriedad controlada o sensibilidad del motor.

La similitud de perfiles usa normalización min-max independiente y, por tanto, es descriptiva; no prueba equivalencia psicométrica. No se realizó inferencia estadística ni se declaró ganador entre estrategias.

El perfil de referencia de Fase 2 permaneció intacto.
"""
    (EVAL / "phase_7_concordance_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({"status":summary["status"],"participants":total,"top1_rate":summary["top1_rate"],"top3_rate":summary["top3_rate"],"replications":len(replication_concordance)}))


if __name__ == "__main__": main()
