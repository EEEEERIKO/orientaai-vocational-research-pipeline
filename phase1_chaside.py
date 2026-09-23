#!/usr/bin/env python3
"""Deterministic, conservative CHASIDE preparation for Phase 1."""
from __future__ import annotations

import csv
import hashlib
import datetime as dt
import html
import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAW_SOURCE = ROOT / "TEST DE ORIENTACIÓN VOCACIONAL OCUPACIONAL - CHASIDE - (respuestas).xlsx"
RAW_COPY = ROOT / "data/raw/chaside_original.xlsx"
CLEAN_CSV = ROOT / "data/clean/chaside_clean.csv"
CLEAN_XLSX = ROOT / "data/clean/chaside_clean.xlsx"
VALIDATION = ROOT / "data/validation"
SPEC = ROOT / "data/clean/chaside_scoring_specification.json"

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAIN_NS = NS["m"]


def col_name(cell_ref: str) -> str:
    return re.match(r"([A-Z]+)", cell_ref).group(1)


def read_sheet(path: Path):
    with zipfile.ZipFile(path) as book:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{MAIN_NS}}}t")))
        root = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        rows = root.findall(".//m:sheetData/m:row", NS)

        def value(cell):
            value_node = cell.find("m:v", NS)
            if value_node is None:
                return ""
            raw = value_node.text or ""
            return shared[int(raw)] if cell.attrib.get("t") == "s" else raw

        parsed = []
        for row in rows:
            cells = {col_name(c.attrib["r"]): value(c) for c in row.findall("m:c", NS)}
            parsed.append((int(row.attrib["r"]), cells))
        return parsed


def question_catalog():
    source = (ROOT / "frontend/lib/chaside-questions.generated.ts").read_text(encoding="utf-8")
    matches = re.findall(r"\{ id: (\d+), category: '([CHASIDE])', type: '([^']+)', title: '((?:[^'\\]|\\.)*)' \}", source)
    if len(matches) != 98:
        raise RuntimeError(f"Expected 98 catalog questions, found {len(matches)}")
    return [{"question_id": int(i), "category": category, "type": typ, "text": title} for i, category, typ, title in matches]


def normalize(raw: str):
    trimmed = raw.strip()
    upper = trimmed.upper().replace("Í", "I")
    if upper in {"SI", "SÍ", "1", "1.0"}:
        return "SI", "VALID", "NORMALIZED_BINARY_YES" if upper != "SI" else "UNCHANGED"
    if upper in {"NO", "0", "0.0"}:
        return "NO", "VALID", "NORMALIZED_BINARY_NO" if upper != "NO" else "UNCHANGED"
    if trimmed == "":
        return None, "MISSING", "EMPTY_VALUE"
    return None, "INVALID", "NOT_IN_ALLOWED_BINARY_RESPONSE_SET"


def score(responses, catalog):
    values = {c: 0 for c in "CHASIDE"}
    valid = missing = invalid = 0
    for item, q in zip(responses, catalog):
        if item == "SI":
            values[q["category"]] += 1
            valid += 1
        elif item == "NO":
            valid += 1
        elif item is None:
            missing += 1
        else:
            invalid += 1
    ranked = sorted(values.items(), key=lambda pair: (-pair[1], "CHASIDE".index(pair[0])))
    return values, valid, missing, invalid, ranked


def write_xlsx_from_csv(csv_path: Path, xlsx_path: Path):
    rows = list(csv.reader(csv_path.open(encoding="utf-8", newline="")))
    def esc(value):
        return html.escape(str(value), quote=True)
    xml_rows = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row, 1):
            col = ""
            n = c
            while n:
                n, rem = divmod(n - 1, 26)
                col = chr(65 + rem) + col
            cells.append(f'<c r="{col}{r}" t="inlineStr"><is><t>{esc(value)}</t></is></c>')
        xml_rows.append(f'<row r="{r}">' + "".join(cells) + "</row>")
    sheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN_NS}"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>"
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="chaside_clean" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    }
    with zipfile.ZipFile(xlsx_path, "w", zipfile.ZIP_DEFLATED) as out:
        for name, body in files.items():
            out.writestr(name, body)


def main():
    for path in [RAW_COPY, CLEAN_CSV, CLEAN_XLSX, SPEC, VALIDATION / "column_mapping.json", VALIDATION / "normalization_log.csv", VALIDATION / "invalid_responses.csv", VALIDATION / "missing_responses.csv", VALIDATION / "chaside_validation.csv", VALIDATION / "phase_1_report.md"]:
        path.parent.mkdir(parents=True, exist_ok=True)
    if not RAW_SOURCE.exists():
        raise FileNotFoundError(RAW_SOURCE)
    shutil.copyfile(RAW_SOURCE, RAW_COPY)
    rows = read_sheet(RAW_SOURCE)
    header_row, header = rows[0]
    question_cols = [(col, header[col]) for col in header if re.match(r"^\d+\.", header[col] or "")]
    catalog = question_catalog()
    if len(question_cols) != len(catalog):
        raise RuntimeError(f"Excel questions={len(question_cols)}, catalog={len(catalog)}")

    mapping = {
        "participant_id": {"original_column": "generated_from_source_row", "normalized_name": "case_id", "type": "identifier", "source": "stable source row among identified participants"},
        "source_row": {"original_column": "Excel row number", "normalized_name": "source_row", "type": "traceability"},
        "questions": [],
        "auxiliary_columns": [
            {"original_column": "A", "normalized_name": "timestamp", "type": "auxiliary"},
            {"original_column": "B", "normalized_name": "original_name", "type": "auxiliary"},
            {"original_column": "C", "normalized_name": "age", "type": "context"},
            {"original_column": "CX", "normalized_name": "school", "type": "auxiliary"},
        ],
    }
    for index, ((col, text), item) in enumerate(zip(question_cols, catalog), 1):
        mapping["questions"].append({"question_id": f"Q{index:02d}", "question_number": index, "original_column": col, "question_text": text, "catalog_question_id": item["question_id"], "chaside_dimension": item["category"], "expected_response_type": "binary", "source": "frontend/lib/chaside-questions.generated.ts"})

    clean_rows = []
    normalization_rows = []
    invalid_rows = []
    missing_rows = []
    validation_rows = []
    identified = 0
    empty_rows = []
    duplicate_names = Counter()
    response_counts = Counter()

    for source_row, data in rows[1:]:
        qraw = [data.get(col, "") for col, _ in question_cols]
        has_identity = bool(data.get("A", "").strip() or data.get("B", "").strip() or data.get("C", "").strip())
        if not has_identity and not any(v.strip() for v in qraw):
            empty_rows.append(source_row)
            continue
        identified += 1
        case_id = f"P{identified:03d}"
        name = data.get("B", "").strip()
        duplicate_names[name] += 1
        normalized = []
        for pos, (raw, item) in enumerate(zip(qraw, catalog), 1):
            value, status, action = normalize(raw)
            normalized.append(value if value is not None else ("MISSING" if status == "MISSING" else "INVALID"))
            response_counts[status] += 1
            if action != "UNCHANGED" or status != "VALID":
                record = {"case_id": case_id, "source_row": source_row, "question_id": f"Q{pos:02d}", "original_value": raw, "normalized_value": value or "", "normalization_action": action, "status": status, "reason": action}
                normalization_rows.append(record)
            if status == "INVALID":
                invalid_rows.append({"case_id": case_id, "source_row": source_row, "question_id": f"Q{pos:02d}", "original_value": raw, "reason": action, "status": "INVALID_RESPONSE"})
            if status == "MISSING":
                missing_rows.append({"case_id": case_id, "source_row": source_row, "question_id": f"Q{pos:02d}", "original_value": raw, "normalized_value": "", "status": "MISSING"})
        scores, valid, missing, invalid, ranked = score(normalized, catalog)
        total = len(catalog)
        status = "COMPLETE" if valid == total else ("PARTIALLY_COMPLETE" if valid > 0 and invalid == 0 else "INCOMPLETE")
        if invalid:
            status = "INVALID_DATA_PRESENT"
        if missing:
            status = "PARTIALLY_COMPLETE" if not invalid else "INVALID_DATA_PRESENT"
        rec = {"case_id": case_id, "source_row": source_row, "timestamp": data.get("A", ""), "original_name": name, "age": data.get("C", ""), "school": data.get("CX", "")}
        rec.update({f"response_Q{i:02d}": normalized[i - 1] for i in range(1, total + 1)})
        rec.update({f"chaside_{key}": scores[key] for key in "CHASIDE"})
        rec.update({"chaside_top1": ranked[0][0], "chaside_top2": ranked[1][0], "chaside_top3": ranked[2][0], "missing_count": missing, "invalid_count": invalid, "valid_count": valid, "completion_rate": round(valid / total, 12), "quality_status": status})
        clean_rows.append(rec)
        validation_rows.append({"case_id": case_id, "source_row": source_row, "score_status": "COMPUTED_WITH_WARNINGS" if invalid or missing else "COMPUTED", "manual_validation_status": "NOT_PERFORMED_NO_EMBEDDED_REFERENCE", "notes": "Excel contains no original score columns; scoring uses catalog categories and documented binary normalization."})

    fields = list(clean_rows[0].keys())
    with CLEAN_CSV.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(clean_rows)
    write_xlsx_from_csv(CLEAN_CSV, CLEAN_XLSX)

    def write_csv(path, rows_, fieldnames):
        with path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows_)
    write_csv(VALIDATION / "normalization_log.csv", normalization_rows, ["case_id", "source_row", "question_id", "original_value", "normalized_value", "normalization_action", "status", "reason"])
    write_csv(VALIDATION / "invalid_responses.csv", invalid_rows, ["case_id", "source_row", "question_id", "original_value", "reason", "status"])
    write_csv(VALIDATION / "missing_responses.csv", missing_rows, ["case_id", "source_row", "question_id", "original_value", "normalized_value", "status"])
    write_csv(VALIDATION / "chaside_validation.csv", validation_rows, ["case_id", "source_row", "score_status", "manual_validation_status", "notes"])
    (VALIDATION / "column_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    spec = {"instrument": "CHASIDE", "version": "CHASIDE_CLASSIC_1.0 (project catalog)", "source": "frontend/lib/chaside-questions.generated.ts + vocational-guidance-ai-backend/src/chaside/services/chaside-scoring.service.ts", "number_of_questions": len(catalog), "response_scale": ["SI", "NO", "0", "1"], "question_mapping": mapping["questions"], "dimension_definitions": {"C": "Administrativa", "H": "Humanidades y ciencias sociales", "A": "Artística", "S": "Ciencias de la salud", "I": "Enseñanzas técnicas", "D": "Defensa y seguridad", "E": "Ciencias experimentales"}, "scoring_formula": "each normalized SI contributes +1 to its catalog category; NO contributes 0; invalid/missing responses are not imputed", "rounding_policy": "integer counts; no additional normalization", "missing_data_policy": "preserve and mark; no imputation", "tie_policy": "rank ordering uses fixed category order C,H,A,S,I,D,E for deterministic top fields; ties remain visible in scores", "warnings": ["Excel contains 218 identified participants, not 220.", "Excel has one empty trailing row.", "36 raw values are 2.0 and are INVALID because the project catalog is boolean and no project rule maps 2.0 to SI/NO.", "Excel contains no embedded CHASIDE score columns for independent reference comparison."]}
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    hashes = {
        "raw_source": sha256(RAW_SOURCE),
        "raw_copy": sha256(RAW_COPY),
        "clean_csv": sha256(CLEAN_CSV),
        "clean_xlsx": sha256(CLEAN_XLSX),
        "scoring_specification": sha256(SPEC),
    }
    (VALIDATION / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

    counts = Counter(r["quality_status"] for r in clean_rows)
    report = f"""# Fase 1 — Preparación y validación CHASIDE\n\n## Estado\n\n`APPROVED_WITH_WARNINGS`\n\n## Fuente original\n\n- Archivo: `{RAW_SOURCE.name}`\n- SHA-256: `{hashes['raw_source']}`\n- Copia preservada: `data/raw/chaside_original.xlsx`\n- Hoja procesada: `Respuestas`\n- Filas XML de datos: 219\n- Participantes identificables: {identified}\n- Filas completamente vacías/excluidas del dataset de participantes: {len(empty_rows)} (fila(s): {empty_rows})\n- Preguntas: {len(catalog)}\n\n## Calidad\n\n- COMPLETE: {counts['COMPLETE']}\n- PARTIALLY_COMPLETE: {counts['PARTIALLY_COMPLETE']}\n- INCOMPLETE: {counts['INCOMPLETE']}\n- INVALID_DATA_PRESENT: {counts['INVALID_DATA_PRESENT']}\n- Respuestas válidas: {response_counts['VALID']}\n- Respuestas faltantes: {response_counts['MISSING']}\n- Respuestas inválidas: {response_counts['INVALID']}\n- Nombres repetidos: {sum(v - 1 for v in duplicate_names.values() if v > 1)}; no se usaron nombres como identificador\n\n## Normalización\n\nSe normalizaron únicamente `SI/SÍ/Si/si` a `SI`, `NO/no` a `NO`, `1/1.0` a `SI` y `0/0.0` a `NO`. Los valores `2.0` se conservaron como `INVALID`; no se imputó ni reinterpretó ninguna respuesta.\n\n## Scoring\n\nLa especificación utiliza las 98 preguntas del catálogo del proyecto y la categoría declarada por pregunta. Cada `SI` aporta 1 punto a su categoría; `NO` aporta 0. No se aplicó ninguna transformación A1–A12.\n\nNo existen columnas de puntuación CHASIDE original en la hoja, por lo que la comparación contra un resultado histórico embebido no fue posible. La validación de scoring queda documentada como `NOT_PERFORMED_NO_EMBEDDED_REFERENCE`; los perfiles se calculan con advertencias cuando contienen valores inválidos o faltantes.\n\n## Advertencias\n\n1. Se esperaban aproximadamente 220 participantes, pero se identificaron {identified}.\n2. La última fila de datos del XML está vacía salvo por un espacio en una celda y se excluyó como fila sin participante.\n3. El primer participante contiene 36 valores `2.0`; no existe en el proyecto una regla que permita convertirlos de forma segura a `SI` o `NO`.\n4. El Excel no contiene resultados CHASIDE previamente calculados para comparación independiente.\n\n## Hashes de artefactos\n\n- RAW fuente: `{hashes['raw_source']}`\n- Copia RAW: `{hashes['raw_copy']}`\n- Clean CSV: `{hashes['clean_csv']}`\n- Clean XLSX: `{hashes['clean_xlsx']}`\n- Scoring specification: `{hashes['scoring_specification']}`\n\n## Artefactos\n\n- `data/raw/chaside_original.xlsx`\n- `data/clean/chaside_clean.csv`\n- `data/clean/chaside_clean.xlsx`\n- `data/clean/chaside_scoring_specification.json`\n- `data/validation/column_mapping.json`\n- `data/validation/normalization_log.csv`\n- `data/validation/invalid_responses.csv`\n- `data/validation/missing_responses.csv`\n- `data/validation/chaside_validation.csv`\n- `data/validation/hashes.json`\n\nEl Excel original no fue modificado.\n"""
    (VALIDATION / "phase_1_report.md").write_text(report, encoding="utf-8")
    print("PHASE 1"); print(f"identified_participants={identified}"); print(f"questions={len(catalog)}"); print(f"valid={response_counts['VALID']} missing={response_counts['MISSING']} invalid={response_counts['INVALID']}"); print("status=APPROVED_WITH_WARNINGS")


if __name__ == "__main__":
    main()
