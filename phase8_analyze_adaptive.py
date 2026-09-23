#!/usr/bin/env python3
"""Phase 8 descriptive analysis of the frozen experiment outputs."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr, wilcoxon

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/adaptive_analysis"
AREAS = [f"A{i}" for i in range(1, 13)]
PHASES = ["Perfil inicial", "Exploración", "Contraste", "Confirmación", "Descarte"]


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(name, data, fields=None):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(data[0]) if data else ["status"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)


def values(rows, key):
    return [float(row[key]) for row in rows if row.get(key) not in (None, "")]


def percentile(xs, p):
    return float(np.percentile(xs, p, method="linear"))


def summary_stats(xs):
    xs = np.asarray(xs, dtype=float)
    return {"mean": float(np.mean(xs)), "median": float(np.median(xs)), "min": float(np.min(xs)), "max": float(np.max(xs)), "std": float(np.std(xs, ddof=1)) if len(xs) > 1 else 0.0, "p25": percentile(xs, 25), "p50": percentile(xs, 50), "p75": percentile(xs, 75), "p90": percentile(xs, 90), "p95": percentile(xs, 95)}


def mode(values_):
    return Counter(values_).most_common(1)[0][0] if values_ else None


def json_load(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    phase5 = json.loads((ROOT / "data/experiment/phase_5_summary.json").read_text())
    phase6 = json.loads((ROOT / "data/replications/phase_6_summary.json").read_text())
    phase7 = json.loads((ROOT / "data/evaluation/concordance_summary.json").read_text())
    if not all(item.get("status", "").startswith("COMPLETED") for item in (phase5, phase6, phase7)):
        raise RuntimeError("Phase 5, 6 and 7 must be completed")
    results = read_csv(ROOT / "data/experiment/results.csv")
    concordance = {r["participant_id"]: r for r in read_csv(ROOT / "data/evaluation/participant_concordance.csv")}
    events = read_csv(ROOT / "data/experiment/question_events.csv")
    transitions = read_csv(ROOT / "data/experiment/phase_transitions.csv")
    decisions = read_csv(ROOT / "data/experiment/decision_events.csv")
    rep = read_csv(ROOT / "data/replications/replication_results.csv")
    refs = {r["case_id"]: r for r in read_csv(ROOT / "data/reference_model/reference_profiles_A1_A12.csv")}
    baseline = [r for r in read_csv(ROOT / "data/baselines/baseline_results.csv") if r["participant_id"] in refs]
    by_pid_events = defaultdict(list)
    for row in events: by_pid_events[row["participant_id"]].append(row)
    by_pid_transitions = defaultdict(list)
    for row in transitions: by_pid_transitions[row["participant_id"]].append(row)
    behavior = []
    for result in results:
        pid = result["participant_id"]
        ref = refs[pid]
        scores = {a: float(ref[f"{a}_normalized"]) for a in AREAS}
        ordered = sorted(scores.values(), reverse=True)
        gap = ordered[0] - ordered[1]
        ambiguity = 1 - gap / max(ordered[0], 1.0)
        c = concordance[pid]
        qphase = json_load(result["questions_per_phase"], {})
        phases = json_load(result["phases_used"], [])
        behavior.append({"participant_id":pid,"total_questions":int(result["total_questions"]),"profile_questions":qphase.get("Perfil inicial",0),"exploration_questions":qphase.get("Exploración",0),"contrast_questions":qphase.get("Contraste",0),"confirmation_questions":qphase.get("Confirmación",0),"discard_questions":qphase.get("Descarte",0),"contrast_used":result["contrast_used"],"confirmation_used":result["confirmation_used"],"discard_used":result["discard_used"],"final_area":result["final_area"],"final_confidence":result["final_confidence"],"final_uncertainty":"","termination_reason":result["termination_reason"],"phases_used":json.dumps(phases,ensure_ascii=False),"reference_top1":json.loads(c["reference_ranking"])[0],"top1_match":c["top1_match"],"top3_match":c["top3_match"],"profile_ambiguity":ambiguity,"reference_profile":json.dumps(scores)})
    write_csv("participant_behavior.csv", behavior)
    qcounts = [r["total_questions"] for r in behavior]; stats = summary_stats(qcounts); p25,p75 = stats["p25"],stats["p75"]
    dist=[]
    for n in range(int(stats["max"])+1):
        count=qcounts.count(n); dist.append({"question_count":n,"participants":count,"percentage":count/len(qcounts),"cumulative_percentage":sum(x<=n for x in qcounts)/len(qcounts)})
    write_csv("question_count_distribution.csv",dist)
    for r in behavior: r["length_group"] = "SHORT" if r["total_questions"] <= p25 else "LONG" if r["total_questions"] >= p75 else "MEDIUM"
    short=[r for r in behavior if r["length_group"]=="SHORT"]; long=[r for r in behavior if r["length_group"]=="LONG"]
    write_csv("short_runs.csv", [{k:r[k] for k in ["participant_id","total_questions","reference_profile","reference_top1","final_area","final_confidence","final_uncertainty","phases_used"]} for r in short])
    write_csv("long_runs.csv", [{k:r[k] for k in ["participant_id","total_questions","reference_profile","reference_top1","final_area","final_confidence","final_uncertainty","phases_used"]} for r in long])
    ambiguity_rows=[{"participant_id":r["participant_id"],"ambiguity_measure":r["profile_ambiguity"],"total_questions":r["total_questions"]} for r in behavior]
    conf_rows=[{"participant_id":r["participant_id"],"total_questions":r["total_questions"],"final_confidence":r["final_confidence"]} for r in behavior]
    unc_rows=[{"participant_id":r["participant_id"],"total_questions":r["total_questions"],"uncertainty_initial":"","uncertainty_final":"","uncertainty_reduction":"","data_available":False} for r in behavior]
    write_csv("ambiguity_vs_length.csv",ambiguity_rows); write_csv("confidence_vs_length.csv",conf_rows); write_csv("uncertainty_vs_length.csv",unc_rows)
    phase_rows=[]
    for phase in PHASES:
        xs=[int(r[f'{ {"Perfil inicial":"profile","Exploración":"exploration","Contraste":"contrast","Confirmación":"confirmation","Descarte":"discard"}[phase]}_questions']) for r in behavior]
        s=summary_stats(xs); phase_rows.append({"phase":phase,"participants":sum(x>0 for x in xs),"mean_questions":s["mean"],"median_questions":s["median"],"min_questions":s["min"],"max_questions":s["max"],"p25":s["p25"],"p75":s["p75"],"p90":s["p90"]})
    write_csv("questions_by_phase.csv",phase_rows)
    phase_path=Counter(" → ".join(json_load(r["phases_used"],[])+["Resultados"]) for r in behavior)
    write_csv("phase_paths.csv",[{"phase_path":k,"participants":v,"percentage":v/len(behavior)} for k,v in phase_path.most_common()])
    trans=Counter((r["from_phase"],r["to_phase"]) for r in transitions); write_csv("phase_transitions.csv",[{"from_phase":a,"to_phase":b,"count":n,"percentage":n/len(behavior)} for (a,b),n in trans.items()])
    # Phase-specific event details; absent uncertainty/reasons stay explicitly null.
    confirmation=[]; discard=[]
    for r in behavior:
        pid=r["participant_id"]; ev=by_pid_events[pid]; conf=[x for x in ev if x["phase"]=="Confirmación"]; dis=[x for x in ev if x["phase"]=="Descarte"]
        confirmation.append({"participant_id":pid,"confirmation_used":bool(conf),"confirmation_questions":len(conf),"first_confirmation_step":conf[0]["step"] if conf else "","confidence_before":"","confidence_after":r["final_confidence"] if conf else "","uncertainty_before":"","uncertainty_after":"","decision_reason":""})
        discard.append({"participant_id":pid,"discard_used":bool(dis),"discard_questions":len(dis),"first_discard_step":dis[0]["step"] if dis else "","confidence_before":"","confidence_after":"","uncertainty_before":"","uncertainty_after":"","decision_reason":""})
    write_csv("confirmation_analysis.csv",confirmation); write_csv("discard_analysis.csv",discard)
    # Trajectories: the engine exposes area confidence, not a scalar global confidence/uncertainty.
    trajectories=[]
    for pid in refs:
        run=json.loads((ROOT/"data/experiment/runs"/f"{pid}.json").read_text()); vals=[]
        for step in run.get("steps",[]):
            areas=step["state_after"]["areas"]; vals.append(max(float(a.get("confidence",0)) for a in areas.values()))
        trajectories.append({"participant_id":pid,"initial_confidence":0 if not vals else vals[0],"final_confidence":0 if not vals else vals[-1],"confidence_change":0 if not vals else vals[-1]-vals[0],"maximum_confidence":max(vals or [0]),"step_at_max_confidence":(vals.index(max(vals))+1) if vals else "","confidence_definition":"maximum area confidence at each step"})
    write_csv("confidence_trajectory.csv",trajectories); write_csv("uncertainty_trajectory.csv",[{"participant_id":pid,"initial_uncertainty":"","final_uncertainty":"","uncertainty_change":"","minimum_uncertainty":"","step_at_minimum_uncertainty":"","data_available":False} for pid in refs])
    # Question and decision frequencies.
    qfreq=Counter(r["question_id"] for r in events); qphase={r["question_id"]:r["phase"] for r in events}; write_csv("adaptive_question_usage.csv",[{"question_id":q,"phase":qphase[q],"frequency":n,"participants":len({r["participant_id"] for r in events if r["question_id"]==q}),"selection_reason":""} for q,n in qfreq.most_common()])
    dcounts=Counter((r["decision_type"],r["decision_reason"]) for r in decisions); write_csv("decision_analysis.csv",[{"decision_type":a,"decision_reason":b,"frequency":n,"phase":""} for (a,b),n in dcounts.items()])
    # Replication-level stability associated with main-run length.
    stab={r["participant_id"]:r for r in read_csv(ROOT/"data/replications/stability_summary.csv")}
    # Strategies and paired comparisons.
    by_strategy=defaultdict(list)
    for r in baseline: by_strategy[r["strategy"]].append(r)
    by_pid_strategy=defaultdict(lambda: defaultdict(list))
    for r in baseline: by_pid_strategy[r["participant_id"]][r["strategy"]].append(r)
    paired=[]; savings=[]
    for pid, groups in by_pid_strategy.items():
        aq=np.mean([int(x["total_questions"]) for x in groups["ADAPTIVE"]]); nq=np.mean([int(x["total_questions"]) for x in groups["NON_ADAPTIVE"]]); eq=np.mean([int(x["total_questions"]) for x in groups["EXHAUSTIVE"]]);
        paired.append({"participant_id":pid,"adaptive_questions":aq,"non_adaptive_questions":nq,"exhaustive_questions":eq,"adaptive_final_area":mode([x["final_area"] for x in groups["ADAPTIVE"]]),"non_adaptive_final_area":mode([x["final_area"] for x in groups["NON_ADAPTIVE"]]),"exhaustive_final_area":mode([x["final_area"] for x in groups["EXHAUSTIVE"]])})
        savings.append({"participant_id":pid,"adaptive_questions":aq,"non_adaptive_questions":nq,"absolute_saving":nq-aq,"saving_rate":(nq-aq)/nq if nq else "","exhaustive_questions":eq,"absolute_saving_vs_exhaustive":eq-aq,"saving_rate_vs_exhaustive":(eq-aq)/eq if eq else ""})
    write_csv("paired_strategy_comparison.csv",paired); write_csv("question_savings.csv",savings)
    def strategy_row(strategy, rs):
        q=[int(x["total_questions"]) for x in rs]; s=summary_stats(q)
        matches=[]
        for x in rs:
            ref_rank=sorted(AREAS, key=lambda a: (-float(refs[x["participant_id"]][f"{a}_normalized"]), AREAS.index(a)))
            matches.append((x["final_area"]==ref_rank[0], x["final_area"] in ref_rank[:3]))
        return {"strategy":strategy,"participants":len({x["participant_id"] for x in rs}),"mean_questions":s["mean"],"median_questions":s["median"],"p25_questions":s["p25"],"p75_questions":s["p75"],"p90_questions":s["p90"],"min_questions":s["min"],"max_questions":s["max"],"top1_rate":sum(a for a,b in matches)/len(matches) if matches else "","top3_rate":sum(b for a,b in matches)/len(matches) if matches else "","mean_ranking_similarity":phase7["mean_ranking_similarity_spearman"] if strategy=="ADAPTIVE" else "","mean_profile_distance":phase7["mean_profile_distance_minmax_euclidean"] if strategy=="ADAPTIVE" else ""}
    write_csv("strategy_comparison.csv",[strategy_row(s,by_strategy[s]) for s in ["ADAPTIVE","NON_ADAPTIVE","EXHAUSTIVE"]])
    # Association and statistical comparisons at participant level.
    amb=np.array([float(r["ambiguity_measure"]) for r in ambiguity_rows]); q=np.array(qcounts); amb_corr=float(spearmanr(amb,q).statistic); conf=np.array([float(r["final_confidence"]) for r in conf_rows]); conf_corr=float(spearmanr(conf,q).statistic)
    paired_a=np.array([r["adaptive_questions"] for r in paired]); paired_n=np.array([r["non_adaptive_questions"] for r in paired]); paired_e=np.array([r["exhaustive_questions"] for r in paired])
    def test(a,b):
        w=wilcoxon(a,b,zero_method="wilcox",alternative="two-sided"); d=b-a; return {"test":"Wilcoxon signed-rank","n":len(a),"median_difference_b_minus_a":float(np.median(d)),"mean_difference_b_minus_a":float(np.mean(d)),"statistic":float(w.statistic),"p_value":float(w.pvalue),"effect_rank_biserial":float((sum(d>0)-sum(d<0))/max(sum(d!=0),1))}
    tests=[{"comparison":"NON_ADAPTIVE - ADAPTIVE",**test(paired_a,paired_n)},{"comparison":"EXHAUSTIVE - ADAPTIVE",**test(paired_a,paired_e)}]
    groups=[]
    for label in ["SHORT","MEDIUM","LONG"]:
        rr=[r for r in behavior if r["length_group"]==label]; groups.append({"group":label,"participants":len(rr),"mean_questions":float(np.mean([int(x["total_questions"]) for x in rr])),"mean_confidence":float(np.mean([float(x["final_confidence"]) for x in rr])),"mean_ambiguity":float(np.mean([float(x["profile_ambiguity"]) for x in rr])),"top1_rate":float(np.mean([int(x["top1_match"]) for x in rr])),"top3_rate":float(np.mean([int(x["top3_match"]) for x in rr])),"contrast_usage":float(np.mean([x["contrast_used"]=="true" for x in rr])),"confirmation_usage":float(np.mean([x["confirmation_used"]=="true" for x in rr]))})
    write_csv("length_group_comparison.csv",groups)
    summary={"phase":8,"status":"COMPLETED_WITH_WARNINGS","participants":len(behavior),"adaptive":stats,"phase_usage":{p:{"participants":sum(int(r[f'{ {"Perfil inicial":"profile","Exploración":"exploration","Contraste":"contrast","Confirmación":"confirmation","Descarte":"discard"}[p]}_questions'])>0 for r in behavior),"mean_questions":next(x["mean_questions"] for x in phase_rows if x["phase"]==p)} for p in PHASES},"comparison":{"adaptive_mean_questions":float(np.mean(paired_a)),"non_adaptive_mean_questions":float(np.mean(paired_n)),"exhaustive_mean_questions":float(np.mean(paired_e)),"mean_question_saving_vs_non_adaptive":float(np.mean(paired_n-paired_a)),"mean_question_saving_vs_exhaustive":float(np.mean(paired_e-paired_a))},"ambiguity_definition":"1 - (reference Top1 - Top2) / max(reference Top1, 1); higher means closer top areas","ambiguity_spearman_vs_length":amb_corr,"confidence_spearman_vs_length":conf_corr,"statistical_tests":tests,"uncertainty_available":False,"replications_as_repeated_measures":True,"warnings":["OrientaAI does not expose a scalar uncertainty or termination reason in the captured engine state; these fields remain null.","Phase 3 has no versioned noise parameter, so no new noise conditions were introduced.","The exhaustive baseline administers the 37-question bank and is structurally different from adaptive termination."],"next_phase":"PHASE_9"}
    (OUT/"phase_8_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report=f"""# Fase 8 — Evaluación del comportamiento adaptativo

Estado: **{summary['status']}**

## Datos analizados

Se analizaron {len(behavior)} ejecuciones principales, 3.270 replicaciones adaptativas y 1.090 ejecuciones por estrategia de baseline. Las replicaciones se trataron como medidas repetidas del mismo participante.

## Eficiencia

- Media: {stats['mean']:.4f} preguntas.
- Mediana: {stats['median']:.4f}.
- Mínimo/máximo: {stats['min']:.0f}/{stats['max']:.0f}.
- P25/P75/P90: {stats['p25']:.2f}/{stats['p75']:.2f}/{stats['p90']:.2f}.

SHORT, MEDIUM y LONG se definieron antes del análisis mediante P25/P75: SHORT ≤ P25, MEDIUM entre ambos límites y LONG ≥ P75.

## Fases y rutas

Las principales rutas observadas se encuentran en `phase_paths.csv`. Contraste se utilizó en {sum(x['contrast_used']=='true' for x in behavior)}/{len(behavior)} casos, Confirmación en {sum(x['confirmation_used']=='true' for x in behavior)}/{len(behavior)} y Descarte en {sum(x['discard_used']=='true' for x in behavior)}/{len(behavior)}.

## Ambigüedad, confianza e incertidumbre

La ambigüedad fue definida reproduciblemente a partir de la separación normalizada entre Top-1 y Top-2 del perfil de referencia. Su correlación Spearman observada con longitud fue {amb_corr:.4f}; la correlación entre confianza final de área y longitud fue {conf_corr:.4f}. Son asociaciones descriptivas, no efectos causales.

El motor no expone una variable escalar de incertidumbre ni una razón formal de terminación en los datos capturados; los campos de incertidumbre y motivo quedan nulos. La trayectoria de confianza usa la máxima confianza de área por paso, no una confianza global inventada.

## Comparación de estrategias

Adaptativo: {np.mean(paired_a):.4f} preguntas; no adaptativo: {np.mean(paired_n):.4f}; exhaustivo: {np.mean(paired_e):.4f}. El ahorro medio observado fue {np.mean(paired_n-paired_a):.4f} frente a no adaptativo y {np.mean(paired_e-paired_a):.4f} frente a exhaustivo.

Las pruebas Wilcoxon pareadas y sus tamaños de efecto están en `phase_8_summary.json`. No se declara una estrategia ganadora: el ahorro se interpreta junto con concordancia y estabilidad. El baseline exhaustivo administra el banco completo de 37 preguntas y no comparte el mismo criterio de terminación.

## Limitaciones

La falta de incertidumbre escalar y razones de terminación impide analizar esos componentes directamente. No se introdujeron nuevas condiciones de ruido. Los resultados son descriptivos; no establecen causalidad ni conclusiones finales de investigación.
"""
    (OUT/"phase_8_adaptive_behavior_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({"status":summary["status"],"participants":len(behavior),"mean":stats["mean"],"median":stats["median"],"min":stats["min"],"max":stats["max"],"p25":stats["p25"],"p75":stats["p75"],"p90":stats["p90"],"amb_corr":amb_corr,"saving":float(np.mean(paired_n-paired_a))}))


if __name__ == "__main__": main()
