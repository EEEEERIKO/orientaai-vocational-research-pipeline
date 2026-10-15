# OrientaAI Vocational Research Pipeline

Scripts reproducibles para preparar, validar y analizar el experimento de orientación vocacional basado en CHASIDE y el motor vocacional de OrientaAI.

> Este directorio contiene la capa de análisis y ejecución. Los scripts no son un paquete independiente: deben ejecutarse desde la raíz de un proyecto que también contenga `frontend/`, el dataset de entrada y las dependencias de Python/Node.

## Qué hace el pipeline

```text
Excel CHASIDE
    ↓
Fase 1 · limpieza y validación
    ↓
Fase 2 · modelo de referencia CHASIDE → A1–A12
    ↓
Fase 3 · personas sintéticas
    ↓
Fase 4 · validación del simulador
    ↓
Fase 5 · ejecución de los participantes
    ↓
Fase 6 · replicaciones y baselines
    ↓
Fase 7 · concordancia
    ↓
Fase 8 · comportamiento adaptativo
    ↓
Fase 9 · análisis final y reporte HTML
```

El dataset validado de este proyecto contiene 218 participantes identificables. El pipeline utiliza ese número real y no inventa registros para alcanzar 220.

## Estructura mínima esperada

```text
project-root/
├── frontend/
│   └── vocational/
├── data/
│   ├── raw/                         # entrada local, no pública
│   └── ...                          # salidas generadas por las fases
├── scripts/                         # este directorio
└── TEST DE ORIENTACIÓN VOCACIONAL OCUPACIONAL - CHASIDE - (respuestas).xlsx
```

El Excel original debe conservarse localmente o en un repositorio privado. No se incluye en este repositorio público.

## Instalación

Requisitos:

- Python 3.11 o posterior.
- Node.js 20 o posterior.
- TypeScript instalado como dependencia de `frontend`.
- El código de `frontend/vocational`, especialmente el motor y el banco de preguntas.

Crear un entorno Python e instalar las dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r scripts/requirements.txt
```

Instalar las dependencias JavaScript desde el proyecto frontend:

```bash
cd frontend
npm install
cd ..
```

## Ejecución recomendada

Ejecutar los comandos desde la raíz del proyecto:

```bash
python3 scripts/phase1_chaside.py
python3 scripts/phase2_reference_model.py
python3 scripts/phase3_synthetic_person.py
python3 scripts/phase4_validate_simulator.py
node scripts/phase5_run_218.cjs
node scripts/phase6_run_replications.cjs
python3 scripts/phase7_evaluate_concordance.py
python3 scripts/phase8_analyze_adaptive.py
python3 scripts/phase9_final_analysis.py
python3 scripts/generate_final_report.py
```

Los scripts escriben sus resultados en `data/`. La ejecución de Fase 5 requiere que el motor TypeScript esté disponible en `frontend/`.

## Preflight y scripts auxiliares

Estos scripts comprueban condiciones previas y son útiles antes de una ejecución completa:

```bash
python3 scripts/phase6_replication_preflight.py
python3 scripts/phase7_concordance_preflight.py
```

`phase5_execute_experiment.py` conserva el preflight histórico del protocolo original de 220 participantes y puede bloquearse cuando el dataset real contiene 218. Para este proyecto debe utilizarse `phase5_run_218.cjs` después de validar las fases anteriores.

## Resultados principales

Las salidas más importantes son:

```text
data/validation/                  calidad del Excel
data/reference_model/             perfiles CHASIDE → A1–A12
data/simulator/                   especificación y validación del simulador
data/experiment/                  ejecución de los participantes
data/replications/                replicaciones y baselines
data/evaluation/                  concordancia con la referencia
data/adaptive_analysis/           análisis de adaptación
data/final_analysis/              tablas, figuras, HTML y conclusiones
```

El informe navegable se genera en:

```text
data/final_analysis/final_research_report.html
```

## Reproducibilidad

- Las seeds están definidas en los scripts y manifests generados.
- Las versiones del simulador y del motor se registran en los manifests.
- Los resultados de `data/` son artefactos derivados, no código fuente.
- Las replicaciones son medidas repetidas de los mismos participantes, no participantes independientes.
- La referencia CHASIDE → A1–A12 es conceptual y experimental; no representa verdad clínica absoluta.

## Especificación investigativa del experimento

Esta sección fija el protocolo utilizado para el análisis CHASIDE → test adaptativo. Su objetivo es permitir auditoría, replicación y diferenciación entre código, datos de entrada, parámetros y resultados derivados.

### Versiones y procedencia

El commit del repositorio raíz utilizado para los scripts es:

```text
7cac0c6ea4576743b46059b4ea272a864184813d
```

Los scripts ejecutables principales y sus hashes SHA-256 son:

```text
scripts/phase5_run_218.cjs              13c1175c70ff5854a8a1cd7214746296564588c63f16e5e717b294565784dc1b
scripts/phase6_run_replications.cjs     96f38a3641316fda95f8590df837595a388d755d192527d4e2f433026e169f48
scripts/phase7_evaluate_concordance.py  4c73e46698917b7b93eb1c0321cbaedf294303fceb01c58dae4a7d804d101bf6
scripts/phase8_analyze_adaptive.py      dffc854375931b571313746bf15a951d40e0e7e4ef1c2f35e29c8116e894b4e1
scripts/phase9_final_analysis.py         0b328ad7ee0567a0e9b530274adb624bcf751b03dfd7630baf5694d4b57c34c0
```

El manifiesto identifica las versiones lógicas como `REFERENCE_MODEL_V1`, `SIMULATOR_V1_VALIDATED`, `ORIENTAAI_EXPERIMENT_V1` y `FINAL_ANALYSIS_V1`. El frontend actualmente registrado en el repositorio es `64962cb27a7c391a1bb979606bba916d4e55183d`; el backend no participa en la simulación del experimento.

> **Advertencia de integridad histórica.** `SNAPSHOT.md` declara el frontend `f43b209`, pero una ejecución con ese commit produjo resultados diferentes de los artefactos archivados. Antes de publicar los resultados como réplica exacta debe corregirse el manifiesto para registrar el commit real del frontend utilizado. Los resultados que siguen corresponden a los artefactos archivados y son consistentes con el frontend actualmente registrado.

### Datos y generadores

- La muestra validada contiene 218 participantes identificables; no se duplicaron registros para alcanzar el protocolo histórico de 220.
- El modelo de referencia transforma las dimensiones CHASIDE `C/H/A/S/I/D/E` en un perfil normalizado de áreas `A1–A12`.
- Las personas sintéticas se generan a partir de esos perfiles normalizados.
- Los perfiles de las opciones se derivan de las señales del banco de preguntas y sus `areaEffects`.
- La compatibilidad opción-persona se calcula como producto punto entre el perfil A1–A12 y el perfil de la opción.
- La selección usa softmax y muestreo ponderado sin reemplazo. Las preguntas contextuales sin representación vocacional se marcan como `SIMULATION_UNCERTAIN`.

Archivos de referencia: `data/reference_model/reference_profiles_A1_A12.csv`, `data/simulator/question_profiles.json`, `data/simulator/simulator_specification.json` y `data/simulator/simulator_config.json`.

### Semillas y configuración aleatoria

La semilla base de la Fase 5 es `20260922`. Para cada participante se deriva una semilla mediante:

```text
SHA-256(experiment_id | participant_id | base_seed)
```

Las replicaciones y baselines utilizan las semillas `101`, `202`, `303`, `404` y `505`. La Fase 4 emplea adicionalmente `606`, `707`, `808`, `909` y `1001`. El simulador deriva el generador por pregunta mediante `SHA-256(seed | question_id)` y un generador lineal congruencial determinista.

### Métricas y procedimiento de cálculo

- **Longitud:** cantidad de eventos de pregunta por participante; se resumen media, mediana, desviación estándar, rango y percentiles.
- **Top-1:** el área final coincide con el área principal del ranking CHASIDE de referencia.
- **Top-3:** el área final pertenece a las tres primeras áreas de referencia.
- **Solapamiento Top-3:** intersección de los tres primeros lugares dividida por tres.
- **Similitud de ranking:** correlación de Spearman sobre las posiciones A1–A12; los empates se resuelven con el orden fijo A1–A12.
- **Distancia de perfil:** distancia euclidiana entre los vectores de referencia y OrientaAI después de normalización min-max independiente, dividida por `sqrt(12)`.
- **Estabilidad:** frecuencia relativa del área final modal entre las cinco replicaciones de cada participante.
- **Comparación de eficiencia:** diferencias pareadas por participante, prueba de rangos con signo de Wilcoxon e intervalo bootstrap de 10.000 muestras. Se aplica Bonferroni a las dos comparaciones de eficiencia.

Las definiciones implementadas están en `phase7_evaluate_concordance.py`, `phase8_analyze_adaptive.py` y `phase9_final_analysis.py`. Las replicaciones se consideran medidas repetidas y no nuevos participantes independientes.

### Resultados archivados y verificación de ejecución

La ejecución principal archivada contiene:

```text
Participantes                         218
Ejecuciones completas                 218
Ejecuciones fallidas                    0
Preguntas totales                    4214
Media de preguntas                 19.3303
Mediana                                19
```

La Fase 6 contiene 3.295 ejecuciones: 1.090 adaptativas, 1.090 no adaptativas, 1.090 exhaustivas y 25 ejecuciones de perfiles controlados. No se introdujeron condiciones `NOISE_LOW` o `NOISE_MEDIUM` porque `SIMULATOR_V1` no define un parámetro de ruido versionado.

Resultados agregados:

```text
                         Media preguntas   Top-1       Top-3
ADAPTIVE                     19.1440       51.38%      84.22%
NON_ADAPTIVE                 28.5954       42.11%      77.89%
EXHAUSTIVE                  37.0000       41.10%      77.52%
```

Comparaciones principales:

```text
Ahorro ADAPTIVE vs NON_ADAPTIVE       9.4514 preguntas
Ahorro ADAPTIVE vs EXHAUSTIVE        17.8560 preguntas
Concordancia Top-1 de la ejecución   40.37%
Concordancia Top-3 de la ejecución   80.28%
Spearman promedio                     0.7259
Estabilidad final media               0.6523
Top-1 entre replicaciones             44.46%
Top-3 entre replicaciones             79.97%
```

Estos resultados son descriptivos y están condicionados por perfiles sintéticos, una referencia CHASIDE conceptual, la ausencia de ruido versionado y la diferencia de terminación entre los baselines.

### Artefactos de auditoría

- `data/experiment/experiment_manifest.json`: versión y configuración de la ejecución principal.
- `data/experiment/phase_5_summary.json`: resumen de preguntas y áreas finales.
- `data/replications/replication_manifest.json`: semillas y cantidad de replicaciones.
- `data/evaluation/concordance_summary.json`: concordancia y estabilidad comparativa.
- `data/adaptive_analysis/phase_8_summary.json`: comportamiento adaptativo y pruebas pareadas.
- `data/final_analysis/final_summary.json`: consolidación final de resultados.
- `data/final_analysis/reproducibility_manifest.json`: entorno y semilla del análisis final.

## Publicación recomendada

Para un repositorio público, subir:

- `scripts/`.
- El código relevante de `frontend/vocational/`.
- Este README y los archivos de dependencias.
- Documentación metodológica y, si se desea, tablas agregadas pequeñas.

No subir:

- El Excel original.
- Respuestas individuales identificables.
- `data/experiment/runs/`.
- `data/experiment/question_events.csv`.
- `data/replications/runs/`.
- `data/baselines/*/runs/`.
- Entornos virtuales, `node_modules/` o archivos `.env`.

Los artefactos completos pueden distribuirse aparte mediante Zenodo u otro repositorio de datos, usando los hashes de los manifests para verificar la descarga.

