#!/usr/bin/env node
/* Phase 6: five controlled seeds plus non-adaptive and exhaustive controls. */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const lib = require('./phase5_run_218.cjs');
const { ROOT, OUT, AREAS, readCsv, writeCsv, stableSeed, makeSimulator, snapshot, ranked, clone, engine, createInitialProfile } = lib;
const REP = path.join(ROOT, 'data/replications');
const BASELINES = path.join(ROOT, 'data/baselines');
const SEEDS = [101, 202, 303, 404, 505];
const PROFILES_FILE = path.join(ROOT, 'data/reference_model/reference_profiles_A1_A12.csv');
const QFILE = path.join(ROOT, 'data/simulator/question_profiles.json');

function profileOf(row) { return Object.fromEntries(AREAS.map(a => [a, Number(row[`${a}_normalized`]) || 0])); }
function qsummary(q) { return {id:q.id, sourceQuestionId:q.sourceQuestionId || null, phase:q.phase, type:q.type, options:q.options || null}; }
function canonical(run) { return JSON.stringify(run.steps.map(s => [s.question.id, s.response])); }
function one(row, seed, strategy, simulate, questionById) {
  const pid = row.case_id, person = profileOf(row), executionId = `${strategy.toLowerCase()}_${pid}_${seed}`;
  let state = createInitialProfile(), question = engine.getInitialQuestion(), step = 0, error = null; const steps = [];
  const fixed = strategy === 'ADAPTIVE' ? null : engine.ALL_QUESTIONS;
  let fixedIndex = 0;
  const quiet = {log:console.log, warn:console.warn, error:console.error, table:console.table, group:console.group, groupEnd:console.groupEnd};
  Object.assign(console, {log:()=>{}, warn:()=>{}, error:()=>{}, table:()=>{}, group:()=>{}, groupEnd:()=>{}});
  try {
    while (question && step < 80) {
      step++; const before = snapshot(state); const sim = simulate(person, question, seed); const result = engine.submitAnswer(state, question, sim.response); const after = snapshot(result.profile);
      steps.push({step, question:qsummary(question), response:sim.response, simulator:sim, state_before:{phase:before.phase, questionCount:before.questionCount, areas:Object.fromEntries(AREAS.map(a=>[a,before.areas[a].score]))}, state_after:{phase:after.phase, questionCount:after.questionCount, areas:Object.fromEntries(AREAS.map(a=>[a,after.areas[a].score]))}});
      state = result.profile;
      if (strategy === 'ADAPTIVE') question = result.nextQuestion;
      else if (strategy === 'NON_ADAPTIVE' && result.finished) question = null;
      else { while (fixedIndex < fixed.length && state.answeredQuestionIds.includes(fixed[fixedIndex].id)) fixedIndex++; question = fixed[fixedIndex++] || null; }
      if (strategy === 'ADAPTIVE' && result.finished) question = null;
    }
    if (question && step >= 80) throw new Error('SAFETY_LIMIT_80_STEPS');
  } catch (e) { error = {error_type:'ORIENTAAI', error_message:e.message, stack_trace:e.stack, status:'NON_RECOVERABLE'}; }
  Object.assign(console, quiet);
  const final = ranked(state); const finalArea = final[0]?.area || null; const questionsByPhase = Object.fromEntries(['Perfil inicial','Exploración','Contraste','Confirmación','Descarte'].map(p=>[p,steps.filter(s=>s.question.phase===p).length]));
  return {participant_id:pid, execution_id:executionId, strategy, seed, simulator_version:'SIMULATOR_V1_VALIDATED', orientaai_version:'frontend/vocational engine 1.0.0', execution_status:error?'FAILED':'COMPLETE', error, total_questions:steps.length, questions_by_phase:questionsByPhase, final_area:finalArea, final_score:final[0]?.score ?? null, final_confidence:final[0]?.confidence ?? null, final_uncertainty:null, termination_reason:null, contrast_used:steps.some(s=>s.question.phase==='Contraste'), confirmation_used:steps.some(s=>s.question.phase==='Confirmación'), discard_used:steps.some(s=>s.question.phase==='Descarte'), phases_used:[...new Set(steps.map(s=>s.question.phase))], steps};
}
function saveRun(dir, id, run) { fs.mkdirSync(dir,{recursive:true}); fs.writeFileSync(path.join(dir, `${id}.json`), JSON.stringify(run)); }
function compact(r) { const x={...r}; delete x.steps; return {...x, questions_by_phase:JSON.stringify(x.questions_by_phase), phases_used:JSON.stringify(x.phases_used), error:x.error?JSON.stringify(x.error):''}; }

function main() {
  const rows = readCsv(PROFILES_FILE); if (rows.length !== 218) throw new Error(`Expected 218 profiles, found ${rows.length}`);
  const qprofiles = JSON.parse(fs.readFileSync(QFILE,'utf8')); const simulate = makeSimulator(qprofiles); const allResults=[]; const matrix=[]; const profileById=Object.fromEntries(rows.map(r=>[r.case_id,r]));
  const conditions = {conditions:[{condition_id:'BASE', profile_condition:'ORIGINAL', noise_level:0, ambiguity_level:'ORIGINAL', seed_set:SEEDS, participants:218, replications_per_participant:5, status:'EXECUTED'}, {condition_id:'CONTROL_PROFILES', profile_condition:'PHASE_4_CONTROLLED', noise_level:0, ambiguity_level:'CONTROLLED', seed_set:SEEDS, participants:5, replications_per_participant:5, status:'EXECUTED'}, {condition_id:'NOISE_LOW', profile_condition:'ORIGINAL', noise_level:null, ambiguity_level:'ORIGINAL', seed_set:[], participants:0, replications_per_participant:0, status:'NOT_AVAILABLE', reason:'Phase 3 has no versioned noise parameter; no new noise mechanism introduced.'}, {condition_id:'NOISE_MEDIUM', profile_condition:'ORIGINAL', noise_level:null, ambiguity_level:'ORIGINAL', seed_set:[], participants:0, replications_per_participant:0, status:'NOT_AVAILABLE', reason:'Phase 3 has no versioned noise parameter; no new noise mechanism introduced.'}]};
  fs.mkdirSync(REP,{recursive:true}); fs.writeFileSync(path.join(REP,'experimental_conditions.json'),JSON.stringify(conditions,null,2));
  const quiet = {log:console.log,warn:console.warn,error:console.error,table:console.table,group:console.group,groupEnd:console.groupEnd};
  const strategies=[['ADAPTIVE',path.join(BASELINES,'adaptive','runs')],['NON_ADAPTIVE',path.join(BASELINES,'non_adaptive','runs')],['EXHAUSTIVE',path.join(BASELINES,'exhaustive','runs')]];
  for (const row of rows) for (const seed of SEEDS) { const run=one(row,seed,'ADAPTIVE',simulate); allResults.push(run); saveRun(path.join(REP,'runs'),run.execution_id,run); matrix.push({execution_id:run.execution_id,participant_id:row.case_id,strategy:'ADAPTIVE',condition_id:'BASE',noise_level:0,ambiguity_level:'ORIGINAL',seed,status:run.execution_status}); }
  for (const [strategy,dir] of strategies.slice(1)) for (const row of rows) for (const seed of SEEDS) { const run=one(row,seed,strategy,simulate); allResults.push(run); saveRun(dir,run.execution_id,run); matrix.push({execution_id:run.execution_id,participant_id:row.case_id,strategy,condition_id:'BASE',noise_level:0,ambiguity_level:'ORIGINAL',seed,status:run.execution_status}); }
  const controlProfiles={clear_A1:{A1:0.95},two_A2_A7:{A2:0.9,A7:0.9},mixed:{A1:0.7,A3:0.65,A5:0.6,A8:0.55,A10:0.5},ambiguous:Object.fromEntries(AREAS.map(a=>[a,0.56])),balanced:Object.fromEntries(AREAS.map(a=>[a,0.5]))};
  for (const [name,partial] of Object.entries(controlProfiles)) { const p=Object.fromEntries(AREAS.map(a=>[a,partial[a] ?? 0.05])); for (const seed of SEEDS) { const row={case_id:`CONTROL_${name}`}; Object.assign(row,Object.fromEntries(AREAS.map(a=>[`${a}_normalized`,p[a]]))); const run=one(row,seed,'ADAPTIVE',simulate); run.condition_id='CONTROL_PROFILES'; allResults.push(run); saveRun(path.join(REP,'control_runs'),run.execution_id,run); matrix.push({execution_id:run.execution_id,participant_id:row.case_id,strategy:'ADAPTIVE',condition_id:'CONTROL_PROFILES',noise_level:0,ambiguity_level:name,seed,status:run.execution_status}); } }
  Object.assign(console,quiet); writeCsv(path.join(REP,'execution_matrix.csv'),matrix,Object.keys(matrix[0])); writeCsv(path.join(REP,'replication_results.csv'),allResults.filter(r=>r.condition_id!=='CONTROL_PROFILES').map(compact),['participant_id','execution_id','strategy','seed','simulator_version','orientaai_version','execution_status','total_questions','questions_by_phase','final_area','final_score','final_confidence','final_uncertainty','termination_reason','contrast_used','confirmation_used','discard_used','phases_used','error']); writeCsv(path.join(BASELINES,'baseline_results.csv'),allResults.filter(r=>['ADAPTIVE','NON_ADAPTIVE','EXHAUSTIVE'].includes(r.strategy)).map(compact),['participant_id','execution_id','strategy','seed','total_questions','final_area','final_score','final_confidence','final_uncertainty','termination_reason','execution_status','error']);
  const stability=[]; for(const row of rows){const rr=allResults.filter(r=>r.participant_id===row.case_id&&r.strategy==='ADAPTIVE');const freq={};rr.forEach(r=>freq[r.final_area]=(freq[r.final_area]||0)+1);const vals=rr.map(r=>r.total_questions);const mode=Object.entries(freq).sort((a,b)=>b[1]-a[1])[0];const avg=vals.reduce((a,b)=>a+b,0)/vals.length;stability.push({participant_id:row.case_id,condition_id:'BASE',replications:rr.length,unique_final_areas:Object.keys(freq).length,modal_final_area:mode?.[0]||'',modal_frequency:mode?.[1]||0,final_area_stability:(mode?.[1]||0)/rr.length,mean_questions:avg,median_questions:[...vals].sort((a,b)=>a-b)[Math.floor(vals.length/2)],question_variance:vals.reduce((s,v)=>s+(v-avg)**2,0)/vals.length,contrast_usage_rate:rr.filter(r=>r.contrast_used).length/rr.length,confirmation_usage_rate:rr.filter(r=>r.confirmation_used).length/rr.length,discard_usage_rate:rr.filter(r=>r.discard_used).length/rr.length});}
  writeCsv(path.join(REP,'stability_summary.csv'),stability,Object.keys(stability[0])); const scen=[{condition_id:'BASE',noise_level:0,ambiguity_level:'ORIGINAL',participants:218,replications:1090,mean_questions:allResults.filter(r=>r.strategy==='ADAPTIVE'&&r.condition_id!=='CONTROL_PROFILES').reduce((s,r)=>s+r.total_questions,0)/1090,mean_unique_final_areas:stability.reduce((s,r)=>s+r.unique_final_areas,0)/218,mean_final_stability:stability.reduce((s,r)=>s+r.final_area_stability,0)/218},{condition_id:'CONTROL_PROFILES',noise_level:0,ambiguity_level:'CONTROLLED',participants:5,replications:25,mean_questions:allResults.filter(r=>r.condition_id==='CONTROL_PROFILES').reduce((s,r)=>s+r.total_questions,0)/25,mean_unique_final_areas:null,mean_final_stability:null}]; writeCsv(path.join(REP,'scenario_summary.csv'),scen,Object.keys(scen[0]));
  const bs=['ADAPTIVE','NON_ADAPTIVE','EXHAUSTIVE'].map(strategy=>{const rs=allResults.filter(r=>r.strategy===strategy&&r.condition_id!=='CONTROL_PROFILES');const q=rs.map(r=>r.total_questions),m=q.reduce((a,b)=>a+b,0)/q.length;return {strategy,participants:218,runs:rs.length,mean_questions:m,median_questions:[...q].sort((a,b)=>a-b)[Math.floor(q.length/2)],std_questions:Math.sqrt(q.reduce((s,v)=>s+(v-m)**2,0)/q.length),complete_runs:rs.filter(r=>r.execution_status==='COMPLETE').length,failed_runs:rs.filter(r=>r.execution_status!=='COMPLETE').length};}); writeCsv(path.join(BASELINES,'baseline_summary.csv'),bs,Object.keys(bs[0]));
  const repro=[]; for(const row of rows.slice(0,10)){const a=one(row,101,'ADAPTIVE',simulate),b=one(row,101,'ADAPTIVE',simulate);repro.push({participant_id:row.case_id,seed:101,same_response_sequence:canonical(a)===canonical(b),same_question_sequence:canonical(a).split('],[').map(x=>x.split(',')[0]).join()==canonical(b).split('],[').map(x=>x.split(',')[0]).join(),same_final_result:a.final_area===b.final_area,reproducibility_status:canonical(a)===canonical(b)?'PASS':'FAIL'});} writeCsv(path.join(REP,'reproducibility_results.csv'),repro,Object.keys(repro[0]));
  const manifest={experiment_id:'ORIENTAAI_EXPERIMENT_V1',phase:6,reference_model_version:'REFERENCE_MODEL_V1',simulator_version:'SIMULATOR_V1_VALIDATED',orientaai_version:'frontend/vocational engine 1.0.0',question_bank_version:'VOCATIONAL_VERSIONS.questionnaire 1.0.0',configuration_version:'SIMULATOR_V1 config + frozen frontend engine configuration',base_experiment_version:'ORIENTAAI_EXPERIMENT_V1 / PHASE_5 / 218 participants',replication_policy_version:'PHASE_6_5_SEEDS_V1',baseline_policy_version:'PHASE_6_BASELINES_V1',status:'COMPLETED_WITH_WARNINGS',seeds:SEEDS,expected_runs:1090+1090+1090+25,actual_runs:allResults.length,noise_note:'No noise parameter exists in SIMULATOR_V1; NOISE_LOW and NOISE_MEDIUM were not executed.',started_at:new Date().toISOString()}; fs.writeFileSync(path.join(REP,'replication_manifest.json'),JSON.stringify(manifest,null,2)); fs.writeFileSync(path.join(REP,'phase_6_report.md'),`# Fase 6 — Replicaciones y escenarios de control\n\nEstado: **COMPLETED_WITH_WARNINGS**\n\nSe ejecutaron 5 seeds (${SEEDS.join(', ')}) para cada uno de los 218 participantes en las estrategias ADAPTIVE, NON_ADAPTIVE y EXHAUSTIVE: 3270 ejecuciones comparables, más 25 ejecuciones de perfiles controlados.\n\nSe mantuvo fijo el perfil y la seed por participante entre estrategias. El simulador V1 no tiene un parámetro de ruido versionado; por eso no se introdujo ruido nuevo. Las condiciones NOISE_LOW y NOISE_MEDIUM quedaron documentadas como no disponibles.\n\nNo se declaró ganador entre estrategias. La interpretación estadística y la concordancia quedan para fases posteriores.\n`); fs.writeFileSync(path.join(REP,'phase_6_summary.json'),JSON.stringify({phase:6,status:'COMPLETED_WITH_WARNINGS',conditions:4,seeds:5,replications:1090,baseline_adaptive:1090,baseline_non_adaptive:1090,baseline_exhaustive:1090,control_runs:25,reproducibility_runs:10,failed_runs:allResults.filter(r=>r.execution_status!=='COMPLETE').length,next_phase:'PHASE_7'},null,2)); console.log(JSON.stringify({status:'COMPLETED_WITH_WARNINGS',runs:allResults.length,failed:allResults.filter(r=>r.execution_status!=='COMPLETE').length}));
}
main();
fs.writeFileSync(path.join(REP,'phase_6_report.md'), `# Fase 6 — Replicaciones y escenarios de control

Estado: **COMPLETED_WITH_WARNINGS**

Se ejecutaron 5 seeds para cada uno de los 218 participantes en ADAPTIVE, NON_ADAPTIVE y EXHAUSTIVE: 3270 ejecuciones comparables, más 25 ejecuciones de perfiles controlados.

Las condiciones se diferencian así:

- **ADAPTIVE:** OrientaAI elige la siguiente pregunta y puede terminar cuando el motor alcanza su condición de finalización.
- **NON_ADAPTIVE:** usa un orden fijo de preguntas, pero respeta la condición normal de finalización del motor.
- **EXHAUSTIVE:** usa el mismo orden fijo y administra las 37 preguntas disponibles, ignorando la finalización anticipada.

Por tanto, NON_ADAPTIVE y EXHAUSTIVE comparten el orden fijo, pero no la regla de terminación. El simulador V1 no tiene un parámetro de ruido versionado; NOISE_LOW y NOISE_MEDIUM quedan documentadas como no disponibles.

No se declara ganador entre estrategias; la interpretación estadística y la concordancia quedan para fases posteriores.
`);
