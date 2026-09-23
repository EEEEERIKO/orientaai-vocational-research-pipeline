#!/usr/bin/env node
/* Execute the frozen vocational engine for the 218 validated records. */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const Module = require('module');
const ts = require(path.join(process.cwd(), 'frontend/node_modules/typescript'));

const ROOT = process.cwd();
const FRONTEND = path.join(ROOT, 'frontend');
const OUT = path.join(ROOT, 'data/experiment');
const RUNS = path.join(OUT, 'runs');
const AREAS = Array.from({length: 12}, (_, i) => `A${i + 1}`);
const BASE_SEED = 20260922;

const originalResolve = Module._resolveFilename;
Module._resolveFilename = function(request, parent, isMain, options) {
  if (request.startsWith('@/')) request = path.join(FRONTEND, request.slice(2));
  return originalResolve.call(this, request, parent, isMain, options);
};
require.extensions['.ts'] = function(module, filename) {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true, importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove } }).outputText;
  module._compile(output, filename);
};
require.extensions['.tsx'] = require.extensions['.ts'];

const { createInitialProfile } = require(path.join(FRONTEND, 'vocational/profile.ts'));
const engine = require(path.join(FRONTEND, 'vocational/engine/index.ts'));
const { SIGNALS } = require(path.join(FRONTEND, 'vocational/signals.ts'));

function readCsv(file) {
  const lines = fs.readFileSync(file, 'utf8').trimEnd().split(/\r?\n/);
  const parse = line => {
    const cells = []; let cell = ''; let quoted = false;
    for (let i = 0; i < line.length; i++) { const c = line[i]; if (c === '"') { if (quoted && line[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted; } else if (c === ',' && !quoted) { cells.push(cell); cell = ''; } else cell += c; }
    cells.push(cell); return cells;
  };
  const headers = parse(lines[0]);
  return lines.slice(1).filter(Boolean).map(line => { const cells = parse(line); return Object.fromEntries(headers.map((h, i) => [h, cells[i] ?? ''])); });
}
function csvValue(v) { return String(v ?? '').replaceAll('"', '""'); }
function writeCsv(file, rows, fields) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const out = [fields.join(',')];
  for (const row of rows) out.push(fields.map(f => { const v = row[f]; if (v === null || v === undefined) return ''; const s = typeof v === 'string' ? v : JSON.stringify(v); return /[",\n]/.test(s) ? `"${csvValue(s)}"` : s; }).join(','));
  fs.writeFileSync(file, out.join('\n') + '\n');
}
function stableSeed(...parts) { return Number.parseInt(crypto.createHash('sha256').update(parts.join('|')).digest('hex').slice(0, 8), 16) || 1; }
class RNG { constructor(seed) { this.state = seed || 1; } uniform() { this.state = (1664525 * this.state + 1013904223) >>> 0; return (this.state + 0.5) / 4294967296; } }
function weightedChoice(probabilities, rng, excluded = new Set()) { let total = probabilities.reduce((s, p, i) => excluded.has(i) ? s : s + p, 0); if (total <= 0) return [...probabilities.keys()].find(i => !excluded.has(i)); let target = rng.uniform() * total; let cumulative = 0; for (let i = 0; i < probabilities.length; i++) { if (excluded.has(i)) continue; cumulative += probabilities[i]; if (target <= cumulative) return i; } return probabilities.findIndex((_, i) => !excluded.has(i)); }
function softmax(values, temperature) { const peak = Math.max(...values); const exps = values.map(v => Math.exp((v - peak) / Math.max(temperature, 1e-6))); const total = exps.reduce((a, b) => a + b, 0); return exps.map(v => v / total); }
function clone(v) { return JSON.parse(JSON.stringify(v)); }
function makeSimulator(questionProfiles) {
  const byId = Object.fromEntries(questionProfiles.map(q => [q.question_id, q]));
  return function simulate(person, question, seed) {
    const sourceId = question.sourceQuestionId || question.id;
    const source = byId[sourceId];
    const rng = new RNG(stableSeed(seed, question.id));
    if (question.type === 'slider') { const low = question.sliderMin, high = question.sliderMax; const response = low + Math.floor(rng.uniform() * (high - low + 1)); return {response, selected_options: [], option_scores: [], selection_probabilities: [], uncertainty: 1, status: 'SIMULATION_UNCERTAIN', reason: 'context_slider_has_no_vocational_option_profile'}; }
    const options = question.options || [];
    const sourceOptions = source ? source.options : [];
    const optionProfiles = options.map((text, uiIndex) => { let sourceIndex = question.optionSourceIndices ? question.optionSourceIndices[uiIndex] : sourceOptions.findIndex(o => o.option_text === text); if (sourceIndex < 0) sourceIndex = uiIndex; return sourceOptions[sourceIndex]?.profile || Object.fromEntries(AREAS.map(a => [a, 0])); });
    const scores = optionProfiles.map(p => AREAS.reduce((sum, a) => sum + Number(person[a] || 0) * Number(p[a] || 0), 0));
    const spread = Math.max(...scores) - Math.min(...scores); const temperature = 0.12 + 0.18 * Math.max(0, 1 - Math.min(1, spread * 8));
    let probabilities = softmax(scores, temperature); if (!optionProfiles.some(p => Object.values(p).some(v => v > 0))) probabilities = options.map(() => 1 / Math.max(options.length, 1));
    const selectedIndices = [];
    if (question.type === 'multi-select') { const max = question.maxSelections || Math.min(3, options.length); for (let i = 0; i < Math.min(max, options.length); i++) { const choice = weightedChoice(probabilities, rng, new Set(selectedIndices)); if (choice === undefined || choice < 0) break; selectedIndices.push(choice); } if (!question.ordered) selectedIndices.sort((a, b) => a - b); } else { const choice = weightedChoice(probabilities, rng); if (choice !== undefined && choice >= 0) selectedIndices.push(choice); }
    const selected = selectedIndices.map(i => options[i]);
    return { response: question.type === 'multiple-choice' ? selected[0] : selected, selected_options: selected, option_scores: scores, selection_probabilities: probabilities, uncertainty: Math.max(0, 1 - spread * 8), ranking: scores.map((_, i) => i).sort((a, b) => scores[b] - scores[a] || a - b), status: 'SIMULATED' };
  };
}
function snapshot(state) { return {phase: state.phase, questionCount: state.questionCount, answeredQuestionIds: clone(state.answeredQuestionIds), dimensions: clone(state.dimensions), areas: clone(state.areas), evidenceCount: state.evidence.length, confidence: Object.fromEntries(Object.values(state.areas).map(a => [a.area, a.confidence]))}; }
function ranked(state) { return Object.values(state.areas).sort((a, b) => b.score - a.score || a.area.localeCompare(b.area)).map((a, i) => ({rank: i + 1, area: a.area, score: a.score, confidence: a.confidence})); }
function safeJson(v) { return JSON.stringify(v === undefined ? null : v); }

function main() {
  const profiles = readCsv(path.join(ROOT, 'data/reference_model/reference_profiles_A1_A12.csv'));
  const questions = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/simulator/question_profiles.json'), 'utf8'));
  const config = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/simulator/simulator_config.json'), 'utf8'));
  if (profiles.length !== 218) throw new Error(`Expected 218 validated profiles, found ${profiles.length}`);
  fs.mkdirSync(RUNS, {recursive: true});
  const simulate = makeSimulator(questions);
  const questionEvents = [], signalEvents = [], areaEvents = [], decisionEvents = [], transitions = [], results = [], participantManifest = [];
  const originalConsole = {...console};
  for (const row of profiles) {
    const pid = row.case_id; const seed = stableSeed('ORIENTAAI_EXPERIMENT_V1', pid, BASE_SEED); const person = Object.fromEntries(AREAS.map(a => [a, Number(row[`${a}_normalized`]) || 0]));
    const refRaw = Object.fromEntries(AREAS.map(a => [a, Number(row[`${a}_raw`]) || 0]));
    const run = {participant_id: pid, execution_id: `exec_${pid}`, seed, input: {chaside: {C: Number(row.chaside_C), H: Number(row.chaside_H), A: Number(row.chaside_A), S: Number(row.chaside_S), I: Number(row.chaside_I), D: Number(row.chaside_D), E: Number(row.chaside_E), record_id: pid}, reference_profile: {raw: refRaw, normalized: person, version: 'REFERENCE_MODEL_V1'}}, synthetic_person: {profile: person, simulator_version: 'SIMULATOR_V1_VALIDATED', seed}, steps: [], phase_transitions: [], signals: [], area_evolution: [], decisions: [], final_result: null};
    let state = createInitialProfile(); let question = engine.getInitialQuestion(); let step = 0; let error = null;
    console.log = () => {}; console.warn = () => {}; console.error = () => {}; console.table = () => {}; console.group = () => {}; console.groupEnd = () => {};
    try {
      while (question && step < 80) {
        step++; const before = snapshot(state); const sim = simulate(person, question, seed); const response = sim.response; const result = engine.submitAnswer(state, question, response); const after = snapshot(result.profile); const newEvidence = result.profile.evidence.slice(state.evidence.length); const sourceId = question.sourceQuestionId || question.id;
        const stateBefore = before, stateAfter = after; const selected = Array.isArray(response) ? response : [response];
        const qEvent = {participant_id: pid, execution_id: run.execution_id, step, phase: question.phase, question_id: question.id, source_question_id: question.sourceQuestionId || null, question_type: question.type, question_text: question.question, options: question.options || null, selected_options: selected, ranking: sim.ranking || null, response, raw_simulator_response: response, orientaai_formatted_response: response, response_seed: seed, confidence_before: before.areas, confidence_after: after.areas, uncertainty_before: null, uncertainty_after: null, candidate_questions: null, selection_reason: null, selection_score: null, timestamp: new Date().toISOString()};
        questionEvents.push(qEvent); run.steps.push({step, question: {id: question.id, sourceQuestionId: question.sourceQuestionId || null, phase: question.phase, type: question.type, text: question.question, options: question.options || null}, response: {raw_simulator_response: response, orientaai_formatted_response: response, seed}, simulator: sim, state_before: stateBefore, state_after: stateAfter});
        for (const ev of newEvidence) { const signal = SIGNALS.find(s => s.id === ev.signalId); const effect = signal?.areaEffects?.[ev.area] ?? 0; signalEvents.push({participant_id: pid, execution_id: run.execution_id, step, question_id: question.id, signal_id: ev.signalId, signal_type: signal?.dimension || null, signal_value: ev.strength, source: 'OrientaAI interpretation', target_area: ev.area, effect}); run.signals.push({step, ...ev, signal_type: signal?.dimension || null, effect}); }
        for (const area of AREAS) { const b = before.areas[area]?.score ?? 0, a = after.areas[area]?.score ?? 0; const delta = a - b; if (delta !== 0) { const entry = {participant_id: pid, execution_id: run.execution_id, step, area_id: area, previous_score: b, effect: delta, new_score: a}; areaEvents.push(entry); run.area_evolution.push(entry); } }
        if (before.phase !== after.phase) { const transition = {participant_id: pid, execution_id: run.execution_id, from_phase: before.phase, to_phase: after.phase, step, trigger: 'engine_state_transition', reason: null}; transitions.push(transition); run.phase_transitions.push(transition); }
        const decision = {participant_id: pid, execution_id: run.execution_id, step, decision_type: result.finished ? 'TERMINATE' : 'NEXT_QUESTION', decision_reason: null, decision_inputs: {phase: after.phase, question_count: after.questionCount}, decision_output: result.nextQuestion?.id || null}; decisionEvents.push(decision); run.decisions.push(decision);
        state = result.profile; question = result.nextQuestion; if (result.finished) { run.final_result = {results: result.results || [], final_ranking: ranked(state), final_area: result.results?.[0]?.area || ranked(state)[0]?.area || null, final_score: result.results?.[0]?.score ?? ranked(state)[0]?.score ?? null, final_confidence: result.results?.[0]?.confidence ?? ranked(state)[0]?.confidence ?? null, final_uncertainty: null, termination_reason: null, total_questions: state.questionCount, total_steps: step, phases_used: [...new Set(run.steps.map(s => s.question.phase))]}; break; }
      }
      if (step >= 80 && question) throw new Error('SAFETY_LIMIT_80_STEPS');
      if (!run.final_result) run.final_result = {results: [], final_ranking: ranked(state), final_area: ranked(state)[0]?.area || null, final_score: ranked(state)[0]?.score || null, final_confidence: ranked(state)[0]?.confidence || null, final_uncertainty: null, termination_reason: null, total_questions: state.questionCount, total_steps: step, phases_used: [...new Set(run.steps.map(s => s.question.phase))]};
    } catch (e) { error = {error_type: 'ORIENTAAI', error_message: e.message, stack_trace: e.stack, status: 'NON_RECOVERABLE'}; run.error = error; }
    console.log = originalConsole.log; console.warn = originalConsole.warn; console.error = originalConsole.error; console.table = originalConsole.table; console.group = originalConsole.group; console.groupEnd = originalConsole.groupEnd;
    const status = error ? 'FAILED' : 'COMPLETE'; const final = run.final_result || {}; results.push({participant_id: pid, execution_id: run.execution_id, final_area: final.final_area || null, final_score: final.final_score ?? null, final_confidence: final.final_confidence ?? null, final_uncertainty: null, total_questions: final.total_questions || 0, questions_per_phase: Object.fromEntries(['Perfil inicial','Exploración','Contraste','Confirmación','Descarte'].map(p => [p, run.steps.filter(s => s.question.phase === p).length])), phases_used: final.phases_used || [], contrast_used: run.steps.some(s => s.question.phase === 'Contraste'), confirmation_used: run.steps.some(s => s.question.phase === 'Confirmación'), discard_used: run.steps.some(s => s.question.phase === 'Descarte'), termination_reason: final.termination_reason || null, execution_status: status}); participantManifest.push({participant_id: pid, chaside_record_id: pid, reference_profile_id: pid, synthetic_person_id: `SYN_${pid}`, experiment_id: 'ORIENTAAI_EXPERIMENT_V1', execution_seed: seed, status}); fs.writeFileSync(path.join(RUNS, `${pid}.json`), JSON.stringify(run, null, 2));
  }
  const restore = originalConsole; Object.assign(console, restore);
  const qFields = ['participant_id','execution_id','step','phase','question_id','source_question_id','question_type','question_text','options','selected_options','ranking','response','raw_simulator_response','orientaai_formatted_response','response_seed','confidence_before','confidence_after','uncertainty_before','uncertainty_after','candidate_questions','selection_reason','selection_score','timestamp'];
  const jsonFields = new Set(['options','selected_options','ranking','response','raw_simulator_response','orientaai_formatted_response','confidence_before','confidence_after','candidate_questions']);
  writeCsv(path.join(OUT, 'question_events.csv'), questionEvents.map(r => Object.fromEntries(Object.entries(r).map(([k,v]) => [k, jsonFields.has(k) ? safeJson(v) : v]))), qFields);
  writeCsv(path.join(OUT, 'signal_events.csv'), signalEvents, Object.keys(signalEvents[0] || {participant_id:null})); writeCsv(path.join(OUT, 'area_evolution.csv'), areaEvents, Object.keys(areaEvents[0] || {participant_id:null})); writeCsv(path.join(OUT, 'decision_events.csv'), decisionEvents.map(r => ({...r, decision_inputs: safeJson(r.decision_inputs), decision_output: safeJson(r.decision_output)})), Object.keys(decisionEvents[0] || {participant_id:null})); writeCsv(path.join(OUT, 'phase_transitions.csv'), transitions, Object.keys(transitions[0] || {participant_id:null})); writeCsv(path.join(OUT, 'results.csv'), results.map(r => ({...r, questions_per_phase: safeJson(r.questions_per_phase), phases_used: safeJson(r.phases_used)})), Object.keys(results[0] || {participant_id:null})); writeCsv(path.join(OUT, 'participants.csv'), results.map(r => ({...r, participant_id: r.participant_id})), Object.keys(results[0] || {participant_id:null})); writeCsv(path.join(OUT, 'participants_manifest.csv'), participantManifest, Object.keys(participantManifest[0]));
  const counts = results.map(r => r.total_questions).sort((a,b)=>a-b); const mean = counts.reduce((a,b)=>a+b,0) / counts.length; const median = counts.length % 2 ? counts[(counts.length-1)/2] : (counts[counts.length/2-1] + counts[counts.length/2])/2; const complete = results.filter(r => r.execution_status === 'COMPLETE').length; const areaCounts = Object.fromEntries(AREAS.map(a => [a, results.filter(r => r.final_area === a).length])); const phaseCounts = Object.fromEntries(['Perfil inicial','Exploración','Contraste','Confirmación','Descarte'].map(p => [p, questionEvents.filter(q => q.phase === p).length]));
  const manifest = {experiment_id:'ORIENTAAI_EXPERIMENT_V1', phase:5, reference_model_version:'REFERENCE_MODEL_V1', simulator_version:'SIMULATOR_V1_VALIDATED', orientaai_version:'frontend/vocational engine 1.0.0', question_bank_version:'VOCATIONAL_VERSIONS.questionnaire 1.0.0', configuration_version:'SIMULATOR_V1 config + frozen frontend engine configuration', chaside_dataset_version:'reference_profiles_A1_A12.csv', random_seed_policy:'sha256(experiment_id|participant_id|base_seed), base_seed:'+BASE_SEED, started_at:new Date().toISOString(), status: complete === profiles.length ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED_WITH_WARNINGS', participants_expected: profiles.length, participants_executed: profiles.length, execution_ids: results.map(r=>r.execution_id), execution_started:true};
  fs.writeFileSync(path.join(OUT, 'experiment_manifest.json'), JSON.stringify(manifest, null, 2));
  const summary = {experiment_id:manifest.experiment_id, phase:5, participants_expected:profiles.length, participants_executed:profiles.length, complete_runs:complete, failed_runs:profiles.length-complete, total_questions:questionEvents.length, mean_questions_per_participant:mean, median_questions_per_participant:median, contrast_usage_rate:results.filter(r=>r.contrast_used).length/profiles.length, confirmation_usage_rate:results.filter(r=>r.confirmation_used).length/profiles.length, discard_usage_rate:results.filter(r=>r.discard_used).length/profiles.length, reproducibility_tested:false, reproducibility_failures:0, phase_question_counts:phaseCounts, final_area_distribution:areaCounts, status: complete===profiles.length?'COMPLETED_WITH_WARNINGS':'COMPLETED_WITH_WARNINGS', next_phase:'PHASE_6'};
  fs.writeFileSync(path.join(OUT, 'phase_5_summary.json'), JSON.stringify(summary, null, 2));
  fs.writeFileSync(path.join(OUT, 'phase_5_execution_report.md'), `# Fase 5 — Ejecución principal\n\nEstado: **${summary.status}**\n\nSe ejecutaron ${profiles.length} participantes, el tamaño real validado del dataset. Se utilizó la versión versionada del motor con la política de Descarte corregida. Se registraron ${questionEvents.length} preguntas, ${signalEvents.length} señales y ${areaEvents.length} cambios de áreas.\n\n- Media de preguntas: ${mean.toFixed(4)}\n- Mediana de preguntas: ${median}\n- Ejecuciones completas: ${complete}\n- Ejecuciones fallidas: ${profiles.length-complete}\n- Contraste: ${results.filter(r=>r.contrast_used).length}\n- Confirmación: ${results.filter(r=>r.confirmation_used).length}\n- Descarte: ${results.filter(r=>r.discard_used).length}\n\nLa incertidumbre externa no es un campo nativo del estado de OrientaAI y se registró como null; no se inventó una métrica. La selección interna de preguntas no expone una razón formal, por lo que esos campos quedan null.\n\nNo se ejecutaron todavía replicaciones, baselines ni análisis de concordancia.\n`);
  console.log(JSON.stringify({status:summary.status, participants:profiles.length, complete, failed:profiles.length-complete, questions:questionEvents.length, mean, median}));
}
if (require.main === module) main();
else module.exports = { ROOT, FRONTEND, OUT, RUNS, AREAS, BASE_SEED, readCsv, writeCsv, stableSeed, makeSimulator, snapshot, ranked, clone, engine, createInitialProfile, SIGNALS };
