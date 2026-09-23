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

