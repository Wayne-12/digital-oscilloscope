"""JSON, UTF-8-BOM CSV, and escaped standalone HTML reports."""
import csv
import html
import json
from pathlib import Path


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_reports(report, out):
    write_json(out / "report.json", report)
    fields = ["id", "status", "evidence", "compared", "mismatches", "max_abs_error", "rmse",
              "reference_seconds", "observed_wall_seconds", "error"]
    with (out / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["cases"])
    with (out / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields2 = ["name", "value", "unit", "status", "scope", "source_sha256"]
        writer = csv.DictWriter(f, fieldnames=fields2, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["metrics"])
    esc = lambda x: html.escape(str(x))
    rows, sections = [], []
    for c in report["cases"]:
        rows.append("<tr>" + "".join(f"<td>{esc(c.get(k, '—'))}</td>" for k in fields[:-1]) + "</tr>")
        sections.append(f"<details><summary>{esc(c['id'])}: {esc(c['status'])}</summary>"
                        f"<pre>{esc(json.dumps(c, ensure_ascii=False, indent=2))}</pre></details>")
    metric_rows = "".join("<tr>" + "".join(f"<td>{esc(m.get(k, '—'))}</td>" for k in fields2) + "</tr>"
                          for m in report["metrics"])
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>黄金参考验证报告</title><style>
body{{font:15px/1.6 system-ui,sans-serif;max-width:1400px;margin:36px auto;padding:0 24px;color:#182638;background:#f5f7fa}}
table{{border-collapse:collapse;background:white;width:100%;font-size:13px}}td,th{{border:1px solid #d7dfe8;padding:8px;text-align:left;overflow-wrap:anywhere}}
.scroll{{overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px}}details{{margin:12px 0}}.note{{padding:16px;background:#e5edf8}}
</style><h1>{esc(report['suite'])} · {esc(report['status'])}</h1>
<p>{esc(report['generated_at_utc'])} · {esc(report['summary'])}</p>
<p class="note">PASS 只说明配置的输入、参考模型及容差下结果一致。离线文件比对不等于本次上板验收。
reference_seconds 为主机参考计算时间；observed_wall_seconds 含外部进程启动、文件 I/O 和运行时间，不能视为 FPGA 延迟。
资源及性能指标缺失时显示 UNAVAILABLE；导入指标的来源与适用范围见下表和 JSON。</p>
<div class="scroll"><table><thead><tr>{''.join('<th>'+esc(k)+'</th>' for k in fields[:-1])}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div><h2>性能 / 资源证据</h2>
<div class="scroll"><table><thead><tr>{''.join('<th>'+esc(k)+'</th>' for k in fields2)}</tr></thead><tbody>{metric_rows}</tbody></table></div>
<h2>套件配置与附加证据</h2><pre>{esc(json.dumps({k: report.get(k) for k in ('configuration','evidence_files','evidence_error','metrics')},ensure_ascii=False,indent=2))}</pre>
<h2>逐项详情与溯源</h2>{''.join(sections)}
<h2>运行环境</h2><pre>{esc(json.dumps(report['environment'],ensure_ascii=False,indent=2))}</pre>
<p>完整机器报告：report.json；汇总：summary.csv；导入指标：metrics.csv；输入副本及参考/实际输出：artifacts/。</p></html>"""
    (out / "report.html").write_text(document, encoding="utf-8")
