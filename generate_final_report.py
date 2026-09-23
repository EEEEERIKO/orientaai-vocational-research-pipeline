#!/usr/bin/env python3
"""Generate a browsable HTML/PDF report from the completed final analysis."""
from __future__ import annotations

import base64
import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/final_analysis"
FIGURES = DATA / "figures"


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def esc(value):
    return html.escape("" if value is None else str(value))


def inline_markdown(value):
    """Render the small Markdown subset used by the generated reports."""
    rendered = esc(value)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    return rendered


def markdown_to_html(text):
    """Convert headings, paragraphs and lists without exposing raw Markdown."""
    output = []
    paragraph = []
    list_items = []

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{' '.join(paragraph)}</p>")
            paragraph.clear()

    def flush_list():
        if list_items:
            output.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{inline_markdown(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            list_items.append(inline_markdown(bullet.group(1)))
            continue
        flush_list()
        paragraph.append(inline_markdown(line))

    flush_paragraph()
    flush_list()
    return "".join(output)


def table(title, name, limit=None):
    rows = read_csv(name)
    if not rows:
        return f"<h3>{esc(title)}</h3><p>Sin datos.</p>"
    shown = rows[:limit] if limit else rows
    headers = list(rows[0])
    body = "".join("<tr>" + "".join(f"<td>{esc(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in shown)
    note = f"<p class='note'>Mostrando {len(shown)} de {len(rows)} filas.</p>" if limit and len(rows) > limit else ""
    return f"<h3>{esc(title)}</h3><div class='table-wrap'><table><thead><tr>{''.join(f'<th>{esc(h)}</th>' for h in headers)}</tr></thead><tbody>{body}</tbody></table></div>{note}"


def figure(path, title, explanation):
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"<figure><img src='data:image/png;base64,{encoded}' alt='{esc(title)}'><figcaption>{esc(title)}</figcaption><p class='figure-help'>{esc(explanation)}</p></figure>"


def main():
    summary = json.loads((DATA / "final_summary.json").read_text(encoding="utf-8"))
    tests = read_csv("statistical_tests.csv")
    report_text = (DATA / "final_research_report.md").read_text(encoding="utf-8")
    images = [
        ("figure_01_question_distribution.png", "Figura 1 — Distribución de preguntas", "Cada barra indica cuántos participantes recibieron ese número total de preguntas. Permite ver la duración típica del test y si existen recorridos excepcionalmente cortos o largos. La concentración de barras alrededor de 18 preguntas representa el comportamiento habitual de esta muestra."),
        ("figure_02_questions_by_phase.png", "Figura 2 — Preguntas por fase", "Compara la carga promedio de Perfil Inicial, Exploración, Contraste, Confirmación y Descarte. No representa una puntuación de calidad: muestra cuánto contribuye cada fase a la duración del recorrido. Descarte se activa solo cuando persiste ambigüedad relevante."),
        ("figure_03_strategy_questions.png", "Figura 3 — Comparación de estrategias", "Cada caja resume la distribución de preguntas por participante bajo cada estrategia. La línea central representa la mediana y la altura de la caja la variabilidad central. El adaptativo administra menos preguntas porque puede terminar antes; los controles recorren el banco completo de 37 preguntas."),
        ("figure_05_ambiguity_length.png", "Figura 5 — Ambigüedad y longitud", "Cada punto es un participante. El eje horizontal mide ambigüedad del perfil de referencia: valores altos significan que las áreas principales están más próximas. El eje vertical muestra la cantidad de preguntas. La tendencia observada es una asociación descriptiva, no prueba que la ambigüedad cause recorridos más largos."),
        ("figure_06_concordance_profile_type.png", "Figura 6 — Concordancia Top-1 por tipo de perfil", "Compara la proporción de casos en que el área final de OrientaAI coincide con el área principal de referencia dentro de cada grupo operativo. Los grupos fueron definidos mediante umbrales reproducibles; no son categorías clínicas ni un ranking de perfiles."),
        ("figure_08_area_concordance.png", "Figura 8 — Matriz de concordancia por área", "Las filas representan el área Top-1 del perfil de referencia y las columnas el área final de OrientaAI. Las celdas más oscuras concentran más casos. La diagonal representa coincidencias exactas; las celdas fuera de la diagonal muestran discrepancias entre ambos instrumentos."),
    ]
    eff = summary["efficiency"]
    con = summary["concordance"]
    stab = summary["stability"]
    strategy = summary["strategy_comparison"]
    cards = [
        ("Participantes", summary["participants"]["analyzed"]),
        ("Media preguntas", f"{eff['mean']:.2f}"),
        ("Top-1", f"{con['top1_rate']:.2%}"),
        ("Top-3", f"{con['top3_rate']:.2%}"),
        ("Estabilidad final", f"{stab['final_result_stability']:.2%}"),
        ("Ahorro vs. no adaptativo", f"{strategy['mean_saving_vs_non_adaptive']:.2f}"),
    ]
    card_html = "".join(f"<div class='card'><span>{esc(label)}</span><strong>{esc(value)}</strong></div>" for label, value in cards)
    image_html = "".join(figure(FIGURES / filename, title, explanation) for filename, title, explanation in images)
    table_html = "".join([
        table("Estadísticas de eficiencia", "table_01_efficiency.csv"),
        table("Estadísticas por fase", "table_03_phase_statistics.csv"),
        table("Concordancia", "table_06_concordance.csv"),
        table("Estabilidad", "table_08_stability.csv"),
        table("Comparación de estrategias", "table_10_strategy_comparison.csv"),
        table("Tipos de perfil", "table_09_profile_types.csv"),
        table("Casos representativos", "table_12_representative_cases.csv"),
        table("Pruebas estadísticas", "statistical_tests.csv"),
    ])
    findings = (DATA / "final_findings.md").read_text(encoding="utf-8")
    conclusion = (DATA / "final_conclusion.md").read_text(encoding="utf-8")
    findings_html = markdown_to_html(findings)
    report_html = markdown_to_html(report_text)
    conclusion_html = markdown_to_html(conclusion)
    content = f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Informe final — OrientaAI</title>
<style>
*, *::before, *::after {{ box-sizing:border-box; }} html,body {{ overflow-x:hidden; }} body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; line-height:1.5; color:#172033; width:100%; max-width:1400px; margin:0 auto; padding:32px; background:#f5f7fb; }}
h1,h2 {{ color:#14213d; }} h1 {{ margin-bottom:4px; }}
.subtitle {{ color:#526077; margin-top:0; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin:24px 0; }}
.card {{ background:white; border:1px solid #e2e8f0; border-radius:12px; padding:18px; box-shadow:0 2px 8px #17203310; }}
.card span {{ display:block; color:#64748b; font-size:13px; }} .card strong {{ display:block; font-size:27px; margin-top:6px; color:#2563eb; }}
section {{ background:white; border-radius:12px; padding:24px; margin:22px 0; box-shadow:0 2px 8px #17203310; min-width:0; overflow:hidden; }}
.figures {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:22px; }} figure {{ margin:0; }} img {{ max-width:100%; border:1px solid #e2e8f0; border-radius:8px; }} figcaption {{ font-weight:600; margin-top:6px; }} .figure-help {{ color:#526077; font-size:14px; margin-top:5px; }}
.table-wrap {{ max-width:100%; overflow-x:auto; overflow-y:auto; max-height:520px; border:1px solid #e2e8f0; }} table {{ border-collapse:collapse; width:100%; font-size:13px; background:white; }} th,td {{ border-bottom:1px solid #e2e8f0; padding:8px 10px; text-align:left; white-space:nowrap; }} th {{ position:sticky; top:0; background:#eaf0ff; color:#1e3a8a; }} tr:nth-child(even) {{ background:#f8fafc; }}
.markdown {{ overflow-wrap:anywhere; word-break:break-word; }} .markdown h1 {{ font-size:25px; margin:0 0 14px; }} .markdown h2 {{ font-size:20px; margin:22px 0 8px; border-bottom:1px solid #e2e8f0; padding-bottom:5px; }} .markdown h3 {{ font-size:16px; margin:16px 0 6px; }} .markdown p {{ margin:8px 0; }} .markdown ul {{ margin:8px 0; padding-left:22px; }} .markdown code {{ background:#eef2ff; border-radius:4px; padding:2px 5px; overflow-wrap:anywhere; }}
.markdown strong {{ color:#1e3a8a; }}
.note {{ color:#64748b; font-size:13px; }} .source {{ color:#64748b; font-size:13px; }}
@media print {{ body {{ background:white; padding:0; }} section {{ box-shadow:none; break-inside:avoid; }} .table-wrap {{ max-height:none; }} .figures {{ grid-template-columns:1fr 1fr; }} }}
</style>
</head>
<body>
<h1>Informe final del experimento OrientaAI</h1>
<p class='subtitle'>Análisis estadístico final · FINAL_ANALYSIS_V1 · generado {esc(datetime.now().strftime('%Y-%m-%d %H:%M'))}</p>
<div class='cards'>{card_html}</div>
<section><h2>Resumen ejecutivo</h2><p>Este informe reúne los datos, tablas, gráficos y resultados finales del experimento con 218 personas sintéticas. La referencia CHASIDE→A1–A12 es experimental y no constituye ground truth absoluto.</p><p class='source'>Fuente: data/final_analysis/final_summary.json</p></section>
<section><div class='markdown'>{findings_html}</div></section>
<section><h2>Cómo interpretar los gráficos</h2><p>Las figuras describen el comportamiento observado en 218 personas sintéticas. No muestran una verdad clínica ni permiten afirmar causalidad por sí solas. En cada figura se explica qué representa cada eje, cómo leer la distribución y qué limitación debe tenerse en cuenta.</p><div class='figures'>{image_html}</div></section>
<section><h2>Tablas y estadísticas</h2>{table_html}</section>
<section><h2>Informe metodológico completo</h2><div class='markdown'>{report_html}</div></section>
<section><div class='markdown'>{conclusion_html}</div></section>
<section><h2>Archivos fuente</h2><p>Los datos detallados permanecen en <code>data/final_analysis/</code>, incluyendo datasets de participantes, replicaciones, baselines, tablas, figuras, amenazas a la validez y manifest de reproducibilidad.</p></section>
</body></html>"""
    output = DATA / "final_research_report.html"
    output.write_text(content, encoding="utf-8")
    pdf_status = "not_attempted"
    try:
        from weasyprint import HTML
        HTML(string=content, base_url=str(DATA)).write_pdf(str(DATA / "final_research_report.pdf"))
        pdf_status = "generated"
    except Exception as error:
        (DATA / "pdf_generation_note.txt").write_text(f"No se generó PDF automáticamente: {error}\nPara imprimir el HTML a PDF, abre final_research_report.html y usa Imprimir → Guardar como PDF.\n", encoding="utf-8")
        pdf_status = "html_only"
    print(json.dumps({"html": str(output), "pdf": pdf_status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
