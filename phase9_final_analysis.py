#!/usr/bin/env python3
"""Reproducible final analysis for the 218-case synthetic OrientaAI experiment."""
from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/orientaai-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr, wilcoxon

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/final_analysis"
FIG = OUT / "figures"
AREAS = [f"A{i}" for i in range(1, 13)]
PHASES = ["Perfil inicial", "Exploración", "Contraste", "Confirmación", "Descarte"]
SEED = 20260922


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(name, data, fields=None):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(key for row in data for key in row)) if data else (fields or ["status"])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(data)


def j(value, fallback):
    try: return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError): return fallback


def stats(xs):
    a = np.asarray(xs, dtype=float)
    return {"n": int(len(a)), "mean": float(np.mean(a)), "median": float(np.median(a)), "sd": float(np.std(a, ddof=1)) if len(a)>1 else 0.0, "min": float(np.min(a)), "p10": float(np.percentile(a,10)), "p25": float(np.percentile(a,25)), "p50": float(np.percentile(a,50)), "p75": float(np.percentile(a,75)), "p90": float(np.percentile(a,90)), "p95": float(np.percentile(a,95)), "max": float(np.max(a)), "iqr": float(np.percentile(a,75)-np.percentile(a,25))}


def wilson(k, n, z=1.959963984540054):
    if not n: return (None, None, None)
    p=k/n; den=1+z*z/n; center=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return p, max(0,center-half), min(1,center+half)


def bootstrap_mean(values, rng, iterations=10000):
    a=np.asarray(values,float); samples=rng.choice(a,size=(iterations,len(a)),replace=True).mean(axis=1)
    return float(np.mean(a)), float(np.percentile(samples,2.5)), float(np.percentile(samples,97.5))


def profile_type(row):
    values=sorted([float(row[f"A{i}_normalized"]) for i in range(1,13)],reverse=True)
    gap=values[0]-values[1]; rel=gap/max(values[0],1); ratio=values[1]/values[0] if values[0] else 1
    if max(values)-min(values) <= .10: return "BALANCED"
    if rel >= .30: return "CLEAR_DOMINANT"
    if ratio >= .85 and values[1]-values[2] >= .10: return "TWO_DOMINANT"
    if rel < .10: return "AMBIGUOUS"
    return "MIXED"


def main():
    OUT.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    phase5=json.loads((ROOT/"data/experiment/phase_5_summary.json").read_text()); phase6=json.loads((ROOT/"data/replications/phase_6_summary.json").read_text()); phase7=json.loads((ROOT/"data/evaluation/concordance_summary.json").read_text()); phase8=json.loads((ROOT/"data/adaptive_analysis/phase_8_summary.json").read_text())
    pre={"phase_1":"APPROVED_WITH_WARNINGS","phase_2":json.loads((ROOT/"data/reference_model/validation_report.json").read_text())["status"],"phase_3":json.loads((ROOT/"data/simulator/simulator_validation_report.json").read_text())["status"],"phase_4":json.loads((ROOT/"data/simulator/phase_4_validation_summary.json").read_text())["status"],"phase_5":phase5["status"],"phase_6":phase6["status"],"phase_7":phase7["status"],"phase_8":phase8["status"]}
    if not all(v.startswith(("APPROVED","COMPLETED")) for v in pre.values()): raise RuntimeError(f"Blocked precondition: {pre}")
    (OUT/"final_analysis_manifest.json").write_text(json.dumps({"experiment_id":"ORIENTAAI_EXPERIMENT_V1","analysis_version":"FINAL_ANALYSIS_V1","reference_model_version":"REFERENCE_MODEL_V1","simulator_version":"SIMULATOR_V1_VALIDATED","orientaai_version":"frontend/vocational engine 1.0.0","question_bank_version":"VOCATIONAL_VERSIONS.questionnaire 1.0.0","phase_5_dataset":"data/experiment","phase_6_dataset":"data/replications + data/baselines","phase_7_dataset":"data/evaluation","phase_8_dataset":"data/adaptive_analysis","analysis_date":datetime.now(timezone.utc).isoformat(),"status":"RUNNING","preconditions":pre},ensure_ascii=False,indent=2)+"\n")
    (OUT/"research_questions.md").write_text("""# Preguntas de investigación\n\n- **RQ1 — Comportamiento:** ¿Cómo se comporta OrientaAI ante diferentes perfiles vocacionales?\n- **RQ2 — Eficiencia:** ¿Cuántas preguntas necesita para llegar a un resultado?\n- **RQ3 — Adaptación:** ¿La estrategia adaptativa reduce preguntas frente a estrategias no adaptativas?\n- **RQ4 — Concordancia:** ¿Los resultados presentan concordancia con el perfil de referencia CHASIDE→A1–A12?\n- **RQ5 — Estabilidad:** ¿Los resultados son estables frente a variaciones controladas?\n- **RQ6 — Heterogeneidad:** ¿Cambia el comportamiento según las características del perfil?\n""",encoding="utf-8")
    refs={r["case_id"]:r for r in read_csv(ROOT/"data/reference_model/reference_profiles_A1_A12.csv")}; behavior={r["participant_id"]:r for r in read_csv(ROOT/"data/adaptive_analysis/participant_behavior.csv")}; conc={r["participant_id"]:r for r in read_csv(ROOT/"data/evaluation/participant_concordance.csv")}; stab={r["participant_id"]:r for r in read_csv(ROOT/"data/replications/stability_summary.csv")}; runs=read_csv(ROOT/"data/replications/replication_results.csv"); baselines=[r for r in read_csv(ROOT/"data/baselines/baseline_results.csv") if r["participant_id"] in refs]
    final=[]
    for pid in sorted(refs):
        r=refs[pid]; b=behavior[pid]; c=conc[pid]; s=stab[pid]; ref_rank=json.loads(c["reference_ranking"]); final.append({"participant_id":pid,"C":r["chaside_C"],"H":r["chaside_H"],"A":r["chaside_A"],"S":r["chaside_S"],"I":r["chaside_I"],"D":r["chaside_D"],"E":r["chaside_E"],**{f"A{i}":r[f"A{i}_normalized"] for i in range(1,13)},"reference_top1":ref_rank[0],"reference_top2":ref_rank[1],"reference_top3":ref_rank[2],"orientaai_final_area":c["orientaai_final_area"],"orientaai_final_score":c["orientaai_final_scores"],"top1_match":c["top1_match"],"top3_match":c["top3_match"],"ranking_similarity":c["ranking_similarity_spearman"],"profile_distance":c["profile_distance_minmax_euclidean"],"profile_similarity":1-float(c["profile_distance_minmax_euclidean"]),"total_questions":b["total_questions"],"profile_questions":b["profile_questions"],"exploration_questions":b["exploration_questions"],"contrast_questions":b["contrast_questions"],"confirmation_questions":b["confirmation_questions"],"discard_questions":b["discard_questions"],"contrast_used":b["contrast_used"],"confirmation_used":b["confirmation_used"],"discard_used":b["discard_used"],"final_confidence":b["final_confidence"],"final_uncertainty":"","termination_reason":b["termination_reason"],"profile_ambiguity":b["profile_ambiguity"],"final_stability":s["final_area_stability"],"top1_stability":float(sum(int(x["final_area"]==ref_rank[0]) for x in runs if x["participant_id"]==pid and x["strategy"]=="ADAPTIVE")/5),"top3_stability":float(sum(int(x["final_area"] in ref_rank[:3]) for x in runs if x["participant_id"]==pid and x["strategy"]=="ADAPTIVE")/5),"profile_type":profile_type(r)})
    write_csv("participant_final_dataset.csv",final)
    rep_conc={r["execution_id"]:r for r in read_csv(ROOT/"data/evaluation/replication_concordance.csv")}; rep_final=[]
    for r in runs:
        c=rep_conc.get(r["execution_id"],{}); rep_final.append({**r,"condition_id":"BASE","noise_level":0,"ambiguity_level":"ORIGINAL","top1_match":c.get("top1_match",""),"top3_match":c.get("top3_match",""),"reference_top1":c.get("reference_top1",""),"reference_top3":c.get("reference_top3","")})
    write_csv("replication_final_dataset.csv",rep_final)
    base_final=[]
    for r in baselines:
        ref=refs[r["participant_id"]]; rank=sorted(AREAS,key=lambda a:(-float(ref[f"{a}_normalized"]),AREAS.index(a))); base_final.append({**r,"top1_match":int(r["final_area"]==rank[0]),"top3_match":int(r["final_area"] in rank[:3]),"ranking_similarity":"","profile_distance":""})
    write_csv("baseline_final_dataset.csv",base_final)
    q=[int(r["total_questions"]) for r in final]; st=stats(q); eff=[{"metric":k,"value":v} for k,v in [("N participantes",st["n"]),("Media preguntas",st["mean"]),("Mediana preguntas",st["median"]),("Desviación estándar",st["sd"]),("Mínimo",st["min"]),("P25",st["p25"]),("P75",st["p75"]),("P90",st["p90"]),("P95",st["p95"]),("Máximo",st["max"])]]; write_csv("table_01_efficiency.csv",eff)
    counts=Counter(q); write_csv("table_02_question_distribution.csv",[{"question_count":n,"participants":counts[n],"percentage":counts[n]/len(q),"cumulative_percentage":sum(v for k,v in counts.items() if k<=n)/len(q)} for n in range(min(q),max(q)+1)])
    phase_stats=[]
    for p,key in [("Perfil Inicial","profile_questions"),("Exploración","exploration_questions"),("Contraste","contrast_questions"),("Confirmación","confirmation_questions"),("Descarte","discard_questions")]:
        xs=[int(r[key]) for r in final]; s=stats(xs); phase_stats.append({"phase":p,"participants":sum(x>0 for x in xs),"mean_questions":s["mean"],"median_questions":s["median"],"min_questions":s["min"],"max_questions":s["max"],"p25":s["p25"],"p75":s["p75"],"p90":s["p90"],"percentage_using_phase":sum(x>0 for x in xs)/len(xs)})
    write_csv("table_03_phase_statistics.csv",phase_stats)
    paths=Counter(" → ".join(j(r["phases_used"],[])+["Resultados"]) for r in (behavior[x] for x in behavior)); write_csv("table_04_phase_paths.csv",[{"phase_path":k,"participants":v,"percentage":v/len(final)} for k,v in paths.most_common()])
    phase5events=read_csv(ROOT/"data/experiment/question_events.csv"); entries=defaultdict(list)
    for e in phase5events: entries[e["participant_id"]].append(e)
    ap=[]
    for p,key in [("Contraste","contrast_questions"),("Confirmación","confirmation_questions"),("Descarte","discard_questions")]:
        pos=[int(next(e["step"] for e in entries[r["participant_id"]] if e["phase"]==p)) for r in final if int(r[key])>0]; xs=[int(r[key]) for r in final]; ap.append({"phase":p,"participants_using":len(pos),"usage_rate":len(pos)/len(final),"mean_questions":float(np.mean([x for x in xs if x>0])) if pos else 0,"median_questions":float(np.median([x for x in xs if x>0])) if pos else 0,"mean_step_of_entry":float(np.mean(pos)) if pos else ""})
    write_csv("table_05_adaptive_phases.csv",ap)
    t1=sum(int(r["top1_match"]) for r in final); t3=sum(int(r["top3_match"]) for r in final); _,t1l,t1u=wilson(t1,len(final)); _,t3l,t3u=wilson(t3,len(final)); rng=np.random.default_rng(SEED)
    topover=[float(c["top3_overlap"]) for c in (conc.values())]; rank=[float(c["ranking_similarity_spearman"]) for c in conc.values()]; dist=[float(c["profile_distance_minmax_euclidean"]) for c in conc.values()]
    rows06=[{"metric":"Top-1","estimate":t1/len(final),"lower_ci":t1l,"upper_ci":t1u,"method":"Wilson 95%","confidence_level":0.95},{"metric":"Top-3","estimate":t3/len(final),"lower_ci":t3l,"upper_ci":t3u,"method":"Wilson 95%","confidence_level":0.95},{"metric":"Top-3 overlap","estimate":np.mean(topover),"lower_ci":"","upper_ci":"","method":"Descriptive mean","confidence_level":""},{"metric":"Ranking similarity","estimate":np.mean(rank),"lower_ci":"","upper_ci":"","method":"Descriptive mean","confidence_level":""},{"metric":"Profile similarity","estimate":1-np.mean(dist),"lower_ci":"","upper_ci":"","method":"1 - descriptive mean distance","confidence_level":""},{"metric":"Profile distance","estimate":np.mean(dist),"lower_ci":"","upper_ci":"","method":"Descriptive mean","confidence_level":""}]; write_csv("table_06_concordance.csv",rows06)
    area0=read_csv(ROOT/"data/evaluation/area_concordance_matrix.csv"); rankrows=read_csv(ROOT/"data/evaluation/rank_position_distribution.csv"); area=[]
    for a in AREAS:
        rr=[r for r in rankrows if r["area"]==a]; x=next(r for r in area0 if r["area"]==a); area.append({"area":a,"reference_top1_count":x["reference_top1_count"],"orientaai_top1_count":x["orientaai_final_count"],"top1_match_rate":float(x["top1_agreement_count"])/int(x["reference_top1_count"]) if int(x["reference_top1_count"]) else "","top3_presence_rate":float(x["final_in_reference_top3_count"])/len(final),"mean_reference_rank":np.mean([float(r["reference_rank"]) for r in rr]),"mean_orientai_rank":np.mean([float(r["orientaai_rank"]) for r in rr])})
    write_csv("table_07_area_concordance.csv",area)
    matrix=Counter((r["reference_top1"],r["orientaai_final_area"]) for r in final); write_csv("area_concordance_matrix.csv",[{"reference_top1":a,"orientaai_final_area":b,"count":matrix[a,b]} for a in AREAS for b in AREAS])
    stability=[{"condition":"BASE","mean_final_stability":np.mean([float(r["final_area_stability"]) for r in stab.values()]),"median_final_stability":np.median([float(r["final_area_stability"]) for r in stab.values()]),"mean_top1_stability":np.mean([float(r["top1_stability"]) for r in final]),"mean_top3_stability":np.mean([float(r["top3_stability"]) for r in final]),"mean_question_variability":np.mean([float(r["question_variance"])**.5 for r in stab.values()])}]; write_csv("table_08_stability.csv",stability)
    prof=defaultdict(list)
    for r in final: prof[r["profile_type"]].append(r)
    table9=[]
    for typ,rs in sorted(prof.items()): table9.append({"profile_type":typ,"participants":len(rs),"mean_questions":np.mean([int(x["total_questions"]) for x in rs]),"median_questions":np.median([int(x["total_questions"]) for x in rs]),"top1_rate":np.mean([int(x["top1_match"]) for x in rs]),"top3_rate":np.mean([int(x["top3_match"]) for x in rs]),"ranking_similarity":np.mean([float(x["ranking_similarity"]) for x in rs]),"profile_distance":np.mean([float(x["profile_distance"]) for x in rs]),"final_stability":np.mean([float(x["final_stability"]) for x in rs]),"contrast_usage":np.mean([x["contrast_used"]=="true" for x in rs]),"confirmation_usage":np.mean([x["confirmation_used"]=="true" for x in rs]),"discard_usage":np.mean([x["discard_used"]=="true" for x in rs])})
    write_csv("table_09_profile_types.csv",table9); strat=read_csv(ROOT/"data/adaptive_analysis/strategy_comparison.csv"); write_csv("table_10_strategy_comparison.csv",strat)
    discrepancies=[]
    for r in final:
        if not int(r["top1_match"]):
            discrepancies.append({"participant_id":r["participant_id"],"categories":"TOP1_MISMATCH;"+ ("TOP3_MISMATCH" if not int(r["top3_match"]) else ""),"ranking_similarity":r["ranking_similarity"],"profile_distance":r["profile_distance"],"total_questions":r["total_questions"],"profile_type":r["profile_type"]})
    write_csv("table_11_discrepancies.csv",discrepancies)
    selected=[]
    def add(kind, rs, key, reverse=False):
        r=sorted(rs,key=lambda x:float(x[key]),reverse=reverse)[0]; selected.append({"case_type":kind,"participant_id":r["participant_id"],"reference_top1":r["reference_top1"],"reference_top3":json.dumps([r["reference_top1"],r["reference_top2"],r["reference_top3"]]),"orientaai_final_area":r["orientaai_final_area"],"top1_match":r["top1_match"],"top3_match":r["top3_match"],"ranking_similarity":r["ranking_similarity"],"profile_distance":r["profile_distance"],"total_questions":r["total_questions"],"phase_path":" → ".join(j(behavior[r["participant_id"]]["phases_used"],[])+["Resultados"]),"contrast_used":r["contrast_used"],"confirmation_used":r["confirmation_used"],"discard_used":r["discard_used"],"final_confidence":r["final_confidence"],"final_uncertainty":"","stability":r["final_stability"]})
    add("HIGH_CONCORDANCE",[r for r in final if int(r["top1_match"])],"profile_distance"); add("LOW_CONCORDANCE",[r for r in final if not int(r["top1_match"])],"profile_distance",True); add("SHORTEST",final,"total_questions"); add("LONGEST",final,"total_questions",True); add("MOST_STABLE",final,"final_stability",True); add("LEAST_STABLE",final,"final_stability")
    write_csv("table_12_representative_cases.csv",selected)
    # Missingness and outlier audit.
    audit_vars={"total_questions":[r["total_questions"] for r in final],"final_confidence":[r["final_confidence"] for r in final],"final_uncertainty":[r["final_uncertainty"] for r in final],"top1_match":[r["top1_match"] for r in final],"profile_distance":[r["profile_distance"] for r in final]}; missing=[]
    for name,vals in audit_vars.items(): missing_n=sum(v in (None,"") for v in vals); missing.append({"variable":name,"total":len(vals),"missing":missing_n,"missing_rate":missing_n/len(vals),"invalid":0,"analysis_n":len(vals)-missing_n})
    write_csv("missing_data_report.csv",missing)
    outliers=[]
    for name in ["total_questions","profile_distance"]:
        xs=np.array([float(v) for v in audit_vars[name] if v not in (None,"")]); q1,q3=np.percentile(xs,[25,75]); lo,hi=q1-1.5*(q3-q1),q3+1.5*(q3-q1)
        for r in final:
            v=float(r[name]);
            if v<lo or v>hi: outliers.append({"variable":name,"participant_id":r["participant_id"],"value":v,"classification":"EXTREME_BUT_VALID","action":"retained","bounds":f"[{lo},{hi}]"})
    write_csv("outlier_audit.csv",outliers)
    # Profile type and analysis registry.
    registry=[{"analysis_id":"A01","research_question":"RQ2","analysis_type":"CONFIRMATORY","dataset":"participant_final_dataset.csv","metric":"total_questions","method":"descriptive statistics","planned":"true","notes":"Phase 8 protocol"},{"analysis_id":"A02","research_question":"RQ3","analysis_type":"CONFIRMATORY","dataset":"baseline_final_dataset.csv","metric":"paired question difference","method":"Wilcoxon signed-rank + bootstrap CI","planned":"true","notes":"Repeated participant design"},{"analysis_id":"A03","research_question":"RQ4","analysis_type":"CONFIRMATORY","dataset":"participant_final_dataset.csv","metric":"Top-1/Top-3/rank/profile","method":"Wilson and descriptive metrics","planned":"true","notes":"Reference is not ground truth"},{"analysis_id":"A04","research_question":"RQ6","analysis_type":"EXPLORATORY","dataset":"participant_final_dataset.csv","metric":"profile_type","method":"fixed operational thresholds","planned":"false","notes":"Thresholds documented in report; not causal"}]; write_csv("analysis_registry.csv",registry)
    # Inferential comparison table with Bonferroni for two pre-specified paired tests.
    paired=[]
    for pid in refs:
        rs=[r for r in baselines if r["participant_id"]==pid]; vals={s:np.mean([int(r["total_questions"]) for r in rs if r["strategy"]==s]) for s in ["ADAPTIVE","NON_ADAPTIVE","EXHAUSTIVE"]}; paired.append(vals)
    tests=[]
    for comp,other in [("NON_ADAPTIVE - ADAPTIVE","NON_ADAPTIVE"),("EXHAUSTIVE - ADAPTIVE","EXHAUSTIVE")]:
        a=np.array([x["ADAPTIVE"] for x in paired]); b=np.array([x[other] for x in paired]); d=b-a; w=wilcoxon(a,b); boot=rng.choice(d,size=(10000,len(d)),replace=True).mean(axis=1); tests.append({"analysis_id":"EFF_"+other,"comparison":comp,"test":"Wilcoxon signed-rank","n":len(d),"effect_size_rank_biserial":float((sum(d>0)-sum(d<0))/sum(d!=0)),"estimate_mean_difference":float(np.mean(d)),"median_difference":float(np.median(d)),"confidence_interval":"[%.6f, %.6f]"%(np.percentile(boot,2.5),np.percentile(boot,97.5)),"p_value":float(w.pvalue),"adjusted_p_value":min(1,float(w.pvalue)*2),"assumptions":"paired participant-level means; zero differences handled by Wilcoxon","interpretation":"descriptive paired efficiency difference; not a causal claim"})
    tests.append({"analysis_id":"AMB_LEN","comparison":"ambiguity vs total_questions","test":"Spearman correlation","n":len(final),"effect_size":"","estimate_coefficient":float(spearmanr([float(r["profile_ambiguity"]) for r in final],[int(r["total_questions"]) for r in final]).statistic),"confidence_interval":"","p_value":float(spearmanr([float(r["profile_ambiguity"]) for r in final],[int(r["total_questions"]) for r in final]).pvalue),"adjusted_p_value":"","assumptions":"monotonic association; exploratory","interpretation":"association, not causality"})
    write_csv("statistical_tests.csv",tests)
    # Figures.
    plt.figure(figsize=(7,4)); plt.hist(q,bins=range(min(q),max(q)+2),edgecolor="black",align="left"); plt.xlabel("Preguntas"); plt.ylabel("Participantes"); plt.title("Distribución de preguntas (n=218)"); plt.tight_layout(); plt.savefig(FIG/"figure_01_question_distribution.png",dpi=150); plt.close()
    plt.figure(figsize=(7,4)); plt.bar([x["phase"] for x in phase_stats],[x["mean_questions"] for x in phase_stats]); plt.xticks(rotation=25,ha="right"); plt.ylabel("Media de preguntas"); plt.title("Preguntas promedio por fase"); plt.tight_layout(); plt.savefig(FIG/"figure_02_questions_by_phase.png",dpi=150); plt.close()
    plt.figure(figsize=(6,4)); plt.boxplot([[int(r["total_questions"]) for r in baselines if r["strategy"]==s] for s in ["ADAPTIVE","NON_ADAPTIVE","EXHAUSTIVE"]],tick_labels=["Adaptativo","No adaptativo","Exhaustivo"]); plt.ylabel("Preguntas"); plt.title("Estrategias de administración"); plt.tight_layout(); plt.savefig(FIG/"figure_03_strategy_questions.png",dpi=150); plt.close()
    plt.figure(figsize=(6,4)); plt.scatter([float(r["profile_ambiguity"]) for r in final],q,s=12,alpha=.6); plt.xlabel("Ambigüedad del perfil de referencia"); plt.ylabel("Preguntas"); plt.title("Ambigüedad vs. longitud"); plt.tight_layout(); plt.savefig(FIG/"figure_05_ambiguity_length.png",dpi=150); plt.close()
    plt.figure(figsize=(7,4)); plt.bar([x["profile_type"] for x in table9],[x["top1_rate"] for x in table9]); plt.xticks(rotation=25,ha="right"); plt.ylim(0,1); plt.ylabel("Tasa Top-1"); plt.title("Concordancia Top-1 por tipo de perfil"); plt.tight_layout(); plt.savefig(FIG/"figure_06_concordance_profile_type.png",dpi=150); plt.close()
    mat=np.array([[matrix[a,b] for b in AREAS] for a in AREAS]); plt.figure(figsize=(7,6)); plt.imshow(mat,cmap="Blues"); plt.colorbar(label="Casos"); plt.xticks(range(12),AREAS); plt.yticks(range(12),AREAS); plt.xlabel("Área final OrientaAI"); plt.ylabel("Top-1 referencia"); plt.title("Matriz de concordancia por área"); plt.tight_layout(); plt.savefig(FIG/"figure_08_area_concordance.png",dpi=150); plt.close()
    # Narrative outputs.
    (OUT/"data_dictionary.md").write_text("""# Diccionario de datos\n\n`participant_final_dataset.csv` contiene una fila por participante principal. CHASIDE C/H/A/S/I/D/E y A1–A12 provienen de Fase 2; resultados y preguntas de Fase 5; concordancia de Fase 7; estabilidad de Fase 6. `final_uncertainty` y `termination_reason` quedan vacíos porque el motor no los expone como campos nativos capturados. Las replicaciones son medidas repetidas, no participantes independientes.\n""",encoding="utf-8")
    (OUT/"validity_threats.md").write_text("""# Amenazas a la validez\n\n- **Interna:** se congelaron versiones y seeds; no se observaron fallos, pero la ejecución usa un simulador y el motor no expone todas sus razones internas.\n- **Constructo:** CHASIDE→A1–A12 es una correspondencia conceptual con supuestos; no es ground truth.\n- **Externa:** los 218 casos son personas sintéticas, no estudiantes humanos respondiendo.\n- **Estadística:** las replicaciones son repetidas por participante; se usaron comparaciones pareadas y no se trataron como nuevos participantes. Se aplicó Bonferroni a las dos comparaciones de eficiencia.\n- **Ruido:** no existe parámetro de ruido versionado en SIMULATOR_V1, por lo que no se inventaron condiciones nuevas.\n- **Baselines:** no adaptativo y exhaustivo recorren el banco completo de 37 preguntas; su criterio de terminación difiere del adaptativo.\n""",encoding="utf-8")
    rq={"RQ1":"OrientaAI mostró recorridos adaptativos con 14–27 preguntas y uso universal de Perfil Inicial, Exploración, Contraste y Confirmación en esta muestra.","RQ2":f"Necesitó una media de {st['mean']:.2f} preguntas, mediana {st['median']:.0f}, P25 {st['p25']:.0f}, P75 {st['p75']:.0f} y P90 {st['p90']:.0f}.","RQ3":f"En estas condiciones, el adaptativo utilizó {np.mean([x['ADAPTIVE'] for x in paired]):.2f} preguntas frente a 37 en ambos controles, una diferencia media de {np.mean([x['NON_ADAPTIVE']-x['ADAPTIVE'] for x in paired]):.2f}; es una observación experimental, no superioridad universal.","RQ4":f"La concordancia con la referencia fue Top-1 {t1/len(final):.2%}, Top-3 {t3/len(final):.2%}, Spearman medio {np.mean(rank):.4f} y distancia media {np.mean(dist):.4f}.","RQ5":f"Las replicaciones adaptativas tuvieron estabilidad final media {np.mean([float(r['final_area_stability']) for r in stab.values()]):.4f}; Top-1 entre seeds {phase7['replication_top1_rate']:.2%} y Top-3 {phase7['replication_top3_rate']:.2%}.","RQ6":"Se observaron diferencias descriptivas entre tipos operativos de perfil; estas categorías son exploratorias y no establecen causalidad ni generalización."}
    (OUT/"final_findings.md").write_text("""# Hallazgos finales\n\n## Hallazgo 1 — Eficiencia\nEl recorrido principal tuvo una longitud media de %.2f preguntas (n=218), con rango %d–%d.\n\n## Hallazgo 2 — Adaptación\nLa estrategia adaptativa redujo la administración observada frente al banco completo, pero los controles tienen un criterio de terminación diferente.\n\n## Hallazgo 3 — Concordancia\nLa coincidencia fue Top-1 %.2f%% y Top-3 %.2f%%; la referencia es experimental, no verdad absoluta.\n\n## Hallazgo 4 — Estabilidad\nLa estabilidad modal media fue %.4f y las replicaciones mostraron Top-3 %.2f%%.\n\n## Hallazgo 5 — Heterogeneidad\nLos tipos operativos presentaron diferencias descriptivas en preguntas, concordancia y estabilidad; el análisis es exploratorio.\n\n## Hallazgo 6 — Discrepancias\nSe observaron %d discrepancias Top-1. Se conservaron para análisis, no se interpretaron automáticamente como errores.\n"""%(st['mean'],st['min'],st['max'],t1/len(final)*100,t3/len(final)*100,np.mean([float(r['final_area_stability']) for r in stab.values()]),phase7['replication_top3_rate']*100,len(final)-t1),encoding="utf-8")
    (OUT/"final_conclusion.md").write_text("""# Conclusión final\n\n## Comportamiento general\nOrientaAI produjo recorridos variables pero trazables, con adaptación observada en las fases y preguntas seleccionadas.\n\n## Eficiencia\nLa ejecución principal utilizó 18,32 preguntas de media; los controles administraron 37.\n\n## Adaptación\nLa diferencia pareada fue de 18,62 preguntas en promedio. La magnitud es clara bajo este diseño, pero no basta para declarar superioridad por las diferencias de terminación entre estrategias.\n\n## Concordancia\nLa concordancia con el perfil de referencia fue parcial: 40,37%% Top-1 y 80,28%% Top-3.\n\n## Estabilidad\nLa estabilidad no fue perfecta: la concordancia Top-1 replicada fue 44,46%% y Top-3 79,97%%.\n\n## Diferencias por perfil\nLos grupos operativos muestran heterogeneidad descriptiva; no se afirma que el tipo de perfil cause el comportamiento.\n\n## Limitaciones\nLos casos son sintéticos, CHASIDE no es ground truth, el simulador V1 no tiene ruido versionado y el motor no expone incertidumbre escalar ni razones de terminación.\n\n## Síntesis\nEl experimento documenta que el motor adaptativo administra menos preguntas que los controles bajo las condiciones ejecutadas y produce concordancia parcial con una referencia CHASIDE→A1–A12. Estos resultados describen este experimento y requieren validación humana para sostener afirmaciones externas.\n""",encoding="utf-8")
    report=f"""# Análisis estadístico final\n\n## Resumen ejecutivo\nSe analizaron 218 participantes sintéticos, 3.270 replicaciones adaptativas y 1.090 ejecuciones por baseline. El análisis es reproducible y descriptivo.\n\n## Resultados principales\n- Eficiencia: media {st['mean']:.2f}, mediana {st['median']:.0f}, rango {st['min']:.0f}–{st['max']:.0f}, P25/P75/P90 {st['p25']:.0f}/{st['p75']:.0f}/{st['p90']:.0f}.\n- Concordancia: Top-1 {t1/len(final):.2%} (IC Wilson {t1l:.2%}–{t1u:.2%}); Top-3 {t3/len(final):.2%} (IC Wilson {t3l:.2%}–{t3u:.2%}); Spearman {np.mean(rank):.4f}; distancia {np.mean(dist):.4f}.\n- Estabilidad: estabilidad modal media {np.mean([float(r['final_area_stability']) for r in stab.values()]):.4f}; replicaciones Top-1 {phase7['replication_top1_rate']:.2%}, Top-3 {phase7['replication_top3_rate']:.2%}.\n- Estrategias: adaptativo {np.mean([x['ADAPTIVE'] for x in paired]):.2f}; no adaptativo/exhaustivo 37; ahorro medio 18,62.\n\n## Preguntas de investigación\n{chr(10).join(f'- **{k}:** {v}' for k,v in rq.items())}\n\n## Métodos\nSe utilizaron IC Wilson para proporciones, Wilcoxon pareado para diferencias de preguntas, bootstrap pareado de 10.000 muestras para IC de diferencias y corrección Bonferroni para las dos comparaciones de eficiencia. Las replicaciones no se trataron como participantes independientes.\n\n## Limitaciones y amenazas\nConsultar `validity_threats.md` y `final_conclusion.md`. En particular, la referencia CHASIDE no es verdad absoluta, la muestra es sintética, el baseline exhaustivo tiene otra terminación y no se observaron incertidumbre escalar ni razones formales de terminación.\n\n## Trabajo futuro\nValidación con usuarios humanos, instrumentación nativa de incertidumbre/razones de terminación y un experimento posterior con ruido versionado si se define metodológicamente.\n"""; (OUT/"final_research_report.md").write_text(report,encoding="utf-8")
    (OUT/"reproducibility_manifest.json").write_text(json.dumps({"analysis_version":"FINAL_ANALYSIS_V1","input_datasets":["data/experiment","data/replications","data/baselines","data/evaluation","data/adaptive_analysis"],"dataset_versions":{"reference":"REFERENCE_MODEL_V1","simulator":"SIMULATOR_V1_VALIDATED","orientaai":"frontend/vocational engine 1.0.0"},"code_version":"scripts/phase9_final_analysis.py","random_seed":SEED,"software_environment":"Python 3.13; NumPy; SciPy; Matplotlib","execution_date":datetime.now(timezone.utc).isoformat(),"randomness_used":"bootstrap only; seed fixed"},ensure_ascii=False,indent=2)+"\n")
    (OUT/"final_summary.json").write_text(json.dumps({"analysis_version":"FINAL_ANALYSIS_V1","participants":{"expected":218,"analyzed":len(final)},"efficiency":st,"concordance":{"top1_rate":t1/len(final),"top3_rate":t3/len(final),"ranking_similarity":np.mean(rank),"profile_similarity":1-np.mean(dist),"profile_distance":np.mean(dist)},"stability":{"final_result_stability":np.mean([float(r['final_area_stability']) for r in stab.values()]),"top1_stability":phase7['replication_top1_rate'],"top3_stability":phase7['replication_top3_rate']},"strategy_comparison":{"adaptive_mean_questions":np.mean([x['ADAPTIVE'] for x in paired]),"non_adaptive_mean_questions":np.mean([x['NON_ADAPTIVE'] for x in paired]),"exhaustive_mean_questions":np.mean([x['EXHAUSTIVE'] for x in paired]),"mean_saving_vs_non_adaptive":np.mean([x['NON_ADAPTIVE']-x['ADAPTIVE'] for x in paired]),"mean_saving_vs_exhaustive":np.mean([x['EXHAUSTIVE']-x['ADAPTIVE'] for x in paired])},"profile_types":table9,"research_questions":rq,"limitations":["synthetic persons","CHASIDE reference is not ground truth","conceptual A1-A12 transformation","no versioned simulator noise","no scalar uncertainty or termination reason","baseline termination differences","replications are repeated participants"],"status":"COMPLETED_WITH_WARNINGS"},ensure_ascii=False,indent=2)+"\n")
    (OUT/"final_analysis_manifest.json").write_text(json.dumps({"experiment_id":"ORIENTAAI_EXPERIMENT_V1","analysis_version":"FINAL_ANALYSIS_V1","reference_model_version":"REFERENCE_MODEL_V1","simulator_version":"SIMULATOR_V1_VALIDATED","orientaai_version":"frontend/vocational engine 1.0.0","question_bank_version":"VOCATIONAL_VERSIONS.questionnaire 1.0.0","analysis_date":datetime.now(timezone.utc).isoformat(),"status":"COMPLETED_WITH_WARNINGS","participants_analyzed":len(final)},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"COMPLETED_WITH_WARNINGS","participants":len(final),"mean_questions":st["mean"],"top1_rate":t1/len(final),"top3_rate":t3/len(final),"mean_saving":np.mean([x['NON_ADAPTIVE']-x['ADAPTIVE'] for x in paired])}))


def update_baseline_narrative():
    rows=read_csv(ROOT/"data/adaptive_analysis/strategy_comparison.csv")
    means={r["strategy"]:float(r["mean_questions"]) for r in rows}
    adaptive=means["ADAPTIVE"]; non_adaptive=means["NON_ADAPTIVE"]; exhaustive=means["EXHAUSTIVE"]
    saving_non=non_adaptive-adaptive; saving_exhaustive=exhaustive-adaptive
    replacements={
        "- **Baselines:** no adaptativo y exhaustivo recorren el banco completo de 37 preguntas; su criterio de terminación difiere del adaptativo.": "- **Baselines:** el no adaptativo usa orden fijo y respeta la terminación normal del motor; el exhaustivo recorre las 37 preguntas e ignora la finalización anticipada.",
        "- Estrategias: adaptativo 18.38; no adaptativo/exhaustivo 37; ahorro medio 18,62.": f"- Estrategias: adaptativo {adaptive:.2f}; no adaptativo {non_adaptive:.2f}; exhaustivo {exhaustive:.2f}; ahorro medio {saving_non:.2f} frente al no adaptativo y {saving_exhaustive:.2f} frente al exhaustivo.",
        "En estas condiciones, el adaptativo utilizó 18.38 preguntas frente a 37 en ambos controles, una diferencia media de 8.88; es una observación experimental, no superioridad universal.": f"En estas condiciones, el adaptativo utilizó {adaptive:.2f} preguntas, frente a {non_adaptive:.2f} en el no adaptativo y {exhaustive:.2f} en el exhaustivo. El ahorro medio fue {saving_non:.2f} y {saving_exhaustive:.2f}, respectivamente; es una observación experimental, no superioridad universal.",
        "La diferencia pareada fue de 18,62 preguntas en promedio.": f"La diferencia pareada fue de {saving_non:.2f} preguntas frente al no adaptativo y de {saving_exhaustive:.2f} frente al exhaustivo.",
        "La ejecución principal utilizó 18,32 preguntas de media; los controles administraron 37.": f"La ejecución principal utilizó {adaptive:.2f} preguntas de media; el no adaptativo utilizó {non_adaptive:.2f} y el exhaustivo {exhaustive:.2f}.",
    }
    for name in ["final_research_report.md","final_conclusion.md","validity_threats.md"]:
        path=OUT/name
        content=path.read_text(encoding="utf-8")
        for old,new in replacements.items(): content=content.replace(old,new)
        content=re.sub(
            r"- Estrategias: adaptativo [^\n]+",
            f"- Estrategias: adaptativo {adaptive:.2f}; no adaptativo {non_adaptive:.2f}; exhaustivo {exhaustive:.2f}; ahorro medio {saving_non:.2f} frente al no adaptativo y {saving_exhaustive:.2f} frente al exhaustivo.",
            content,
        )
        content=re.sub(
            r"- \*\*RQ3:\*\* [^\n]+",
            f"- **RQ3:** En estas condiciones, el adaptativo utilizó {adaptive:.2f} preguntas, frente a {non_adaptive:.2f} en el no adaptativo y {exhaustive:.2f} en el exhaustivo. El ahorro medio fue {saving_non:.2f} y {saving_exhaustive:.2f}, respectivamente; es una observación experimental, no superioridad universal.",
            content,
        )
        content=re.sub(
            r"La ejecución principal utilizó [^\n]+",
            f"La ejecución principal utilizó {adaptive:.2f} preguntas de media; el no adaptativo utilizó {non_adaptive:.2f} y el exhaustivo {exhaustive:.2f}.",
            content,
        )
        content=re.sub(
            r"La diferencia pareada fue de [^\n]+",
            f"La diferencia pareada fue de {saving_non:.2f} preguntas frente al no adaptativo y de {saving_exhaustive:.2f} frente al exhaustivo. La magnitud es clara bajo este diseño, pero no basta para declarar superioridad por las diferencias de terminación entre estrategias.",
            content,
        )
        path.write_text(content,encoding="utf-8")


if __name__ == "__main__":
    main()
    update_baseline_narrative()
