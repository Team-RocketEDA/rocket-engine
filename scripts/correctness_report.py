#!/usr/bin/env python3
"""HTML report for the ENGINE-CORRECTNESS gate (static, file:// safe).

Reads tmp/correctness/report.json (produced by scripts/correctness.py)
plus per-case artifacts under tmp/correctness/cases/<case>/ and writes
tmp/correctness/report.html.

Stdlib only, no network, no JavaScript: semantic tables with captions
and scoped headers, status as text (never color alone), native
<details> for failure excerpts, keyboard-operable throughout.
"""

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PASS_KINDS = {"good", "layout-stays"}

ARTIFACT_FILES = ("verdict.json", "native.log", "run_record.json")

EXCERPT_LINES = 30
EXCERPT_CHARS = 3000

STATUS_LABEL = {
    "pass": "PASS",
    "fail": "FAIL",
    "quarantined": "QUARANTINED",
}


def intended_actual(entry):
    """Return (intended, actual) result strings for one case entry."""
    kind = entry.get("kind", "")
    status = entry.get("status", "")
    if entry.get("expected") is not None:
        intended = str(entry["expected"])
    elif kind in PASS_KINDS:
        intended = "PASS"
    elif kind == "mutant":
        intended = "FAIL"
    else:
        intended = "\u2014"
    if entry.get("got") is not None:
        actual = str(entry["got"])
    elif status == "pass":
        actual = intended
    elif status == "quarantined":
        actual = "not run"
    else:
        actual = "\u2014"
    return intended, actual


PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
THREE_CDN = (
    "https://cdnjs.cloudflare.com/ajax/libs/three.js/0.149.0/three.min.js"
)

LAYOUT_SUFFIXES = (".gds", ".gds.gz", ".oas")


def _explicit_case_dir(entry):
    """Case dir only when the gate recorded one (fail entries).

    Passing and quarantined cases write no artifacts; never link a
    stale directory left by an older run.
    """
    artifacts = entry.get("artifacts")
    if artifacts:
        candidate = Path(artifacts)
        if candidate.is_dir():
            return candidate
    return None


def _layout_refs(report, out_dir):
    """GDS/OAS source names referenced by this run's run records."""
    refs = []
    seen = set()
    flows = report.get("flows", {})
    for flow_name in sorted(flows):
        for entry in flows[flow_name].get("cases", []):
            case_dir = _explicit_case_dir(entry)
            if case_dir is None:
                continue
            record = case_dir / "run_record.json"
            try:
                sources = (
                    json.loads(record.read_text())
                    .get("ingredients", {})
                    .get("sources", [])
                )
            except (OSError, ValueError):
                continue
            for source in sources:
                name = str(source.get("name", ""))
                if not name.lower().endswith(LAYOUT_SUFFIXES):
                    continue
                key = (str(entry.get("case", "")), name)
                if key in seen:
                    continue
                seen.add(key)
                rel = Path(os.path.relpath(record, out_dir)).as_posix()
                refs.append((str(entry.get("case", "")), name, rel))
    return refs


def _artifact_links(case_dir, out_dir):
    """Links to artifact files that exist on disk, relative to the HTML."""
    links = []
    for name in ARTIFACT_FILES:
        target = case_dir / name
        if target.is_file():
            rel = Path(os.path.relpath(target, out_dir)).as_posix()
            links.append((name, rel))
    return links


def _excerpt(native_log):
    """Last lines of a native.log, or None when unreadable/empty."""
    try:
        text = Path(native_log).read_text(errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    tail = "\n".join(lines[-EXCERPT_LINES:])
    if len(tail) > EXCERPT_CHARS:
        tail = "\u2026(truncated)\n" + tail[-EXCERPT_CHARS:]
    return tail.strip() or None


CSS = """
:root { color-scheme: light; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5; color: #1a1a1a; background: #fff;
  max-width: 72rem; margin: 0 auto; padding: 1rem;
}
.skip {
  position: absolute; left: -9999px; top: 0; background: #1d4ed8;
  color: #fff; padding: 0.5rem 1rem; z-index: 100;
}
.skip:focus { left: 0; }
:focus-visible { outline: 3px solid #1d4ed8; outline-offset: 2px; }
.banner {
  font-size: 1.25rem; font-weight: bold; padding: 0.75rem 1rem;
  border-radius: 0.25rem; border: 2px solid;
}
.banner.pass { color: #14532d; background: #dcfce7; border-color: #14532d; }
.banner.fail { color: #fff; background: #7f1d1d; border-color: #7f1d1d; }
.badge {
  display: inline-block; font-weight: bold; padding: 0.1rem 0.5rem;
  border-radius: 0.25rem; border: 1px solid;
}
.badge.pass { color: #14532d; background: #dcfce7; border-color: #14532d; }
.badge.fail { color: #7f1d1d; background: #fee2e2; border-color: #7f1d1d; }
.badge.quarantined {
  color: #713f12; background: #fef3c7; border-color: #713f12;
}
.chart-note { font-size: 0.9rem; color: #404040; }
#flow-chart { min-height: 3rem; }
#layout-viewer canvas { max-width: 100%; height: auto; border: 1px solid #525252; }
.table-wrap { overflow-x: auto; margin-bottom: 2rem; }
table { border-collapse: collapse; width: 100%; }
caption {
  text-align: left; font-weight: bold; padding: 0.5rem 0;
}
th, td {
  border: 1px solid #525252; padding: 0.4rem 0.6rem;
  text-align: left; vertical-align: top;
}
thead th { background: #f5f5f5; }
pre {
  background: #f5f5f5; color: #1a1a1a; padding: 0.75rem;
  overflow-x: auto; white-space: pre-wrap; word-break: break-word;
}
footer { margin-top: 2rem; font-size: 0.9rem; color: #404040; }
"""


def _flow_counts(cases):
    counts = {"pass": 0, "fail": 0, "quarantined": 0}
    for entry in cases:
        status = entry.get("status", "")
        if status in counts:
            counts[status] += 1
    return counts


def _row_html(entry, out_dir):
    case = str(entry.get("case", ""))
    intended, actual = intended_actual(entry)
    status = entry.get("status", "")
    label = STATUS_LABEL.get(status, html.escape(status))
    case_dir = _explicit_case_dir(entry)
    links = _artifact_links(case_dir, out_dir) if case_dir else []
    if links:
        artifacts = "<br>".join(
            f'<a href="{html.escape(href, quote=True)}">'
            f"{html.escape(name)}</a>"
            for name, href in links
        )
    else:
        artifacts = "none"
    reason = entry.get("reason")
    ref = entry.get("ref")
    if reason or ref:
        bits = []
        if reason:
            bits.append(html.escape(str(reason)))
        if ref:
            bits.append(f"ref: {html.escape(str(ref))}")
        details = "<br>".join(bits)
    elif status == "fail" and case_dir is not None:
        native_log = case_dir / "native.log"
        excerpt = _excerpt(native_log)
        if excerpt:
            details = (
                "<details><summary>native.log excerpt "
                f"(last {EXCERPT_LINES} lines)</summary>"
                f"<pre>{html.escape(excerpt)}</pre></details>"
            )
        else:
            details = "no native.log excerpt available"
    else:
        details = "\u2014"
    return (
        f"<tr><th scope=\"row\">{html.escape(case)}</th>"
        f"<td>{html.escape(str(entry.get('design', '')))}</td>"
        f"<td>{html.escape(str(entry.get('kind', '')))}</td>"
        f"<td>{html.escape(intended)}</td>"
        f"<td>{html.escape(actual)}</td>"
        f'<td><span class="badge {html.escape(status)}">'
        f"{html.escape(label)}</span></td>"
        f"<td>{artifacts}</td>"
        f"<td>{details}</td></tr>"
    )


def render_html(report, cases_dir, generated_at=None, out_dir=None):
    """Render the full report page for a parsed report.json dict."""
    link_base = Path(out_dir) if out_dir else Path(cases_dir).parent
    verdict = str(report.get("verdict", "unknown"))
    totals = report.get("totals", {})
    banner_class = "pass" if verdict == "PASS" else "fail"
    stamp = generated_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    flows = report.get("flows", {})
    sections = []
    for flow_name in sorted(flows):
        spec = flows[flow_name]
        cases = spec.get("cases", [])
        counts = _flow_counts(cases)
        flow_verdict = html.escape(str(spec.get("verdict", "")))
        summary = (
            f"{len(cases)} cases: {counts['pass']} pass, "
            f"{counts['fail']} fail, {counts['quarantined']} quarantined. "
            f"Flow verdict: {flow_verdict}."
        )
        rows = "\n".join(
            _row_html(entry, link_base)
            for entry in cases
        )
        sections.append(
            f"<section aria-labelledby=\"flow-{html.escape(flow_name)}\">"
            f"<h2 id=\"flow-{html.escape(flow_name)}\">"
            f"Flow: {html.escape(flow_name)} \u2014 {flow_verdict}</h2>"
            f"<p>{html.escape(summary)}</p>"
            '<div class="table-wrap" role="region" '
            f'tabindex="0" aria-label="Cases table for flow '
            f'{html.escape(flow_name)}">'
            "<table>"
            f"<caption>Cases for flow {html.escape(flow_name)}: "
            f"intended vs actual result, status, and artifacts</caption>"
            "<thead><tr>"
            '<th scope="col">Case</th>'
            '<th scope="col">Design</th>'
            '<th scope="col">Kind</th>'
            '<th scope="col">Intended</th>'
            '<th scope="col">Actual</th>'
            '<th scope="col">Status</th>'
            '<th scope="col">Artifacts</th>'
            '<th scope="col">Details</th>'
            "</tr></thead>"
            f"<tbody>\n{rows}\n</tbody>"
            "</table></div></section>"
        )
    totals_line = (
        f"{totals.get('flows', 0)} flows "
        f"({totals.get('flows_pass', 0)} green) \u00b7 "
        f"{totals.get('cases', 0)} cases: "
        f"{totals.get('cases_pass', 0)} pass, "
        f"{totals.get('cases_fail', 0)} fail, "
        f"{totals.get('cases_quarantined', 0)} quarantined."
    )
    chart = {"flows": [], "pass": [], "fail": [], "quarantined": []}
    chart_bits = []
    for flow_name in sorted(flows):
        counts = _flow_counts(flows[flow_name].get("cases", []))
        chart["flows"].append(flow_name)
        chart["pass"].append(counts["pass"])
        chart["fail"].append(counts["fail"])
        chart["quarantined"].append(counts["quarantined"])
        chart_bits.append(
            f"{flow_name}: {counts['pass']} pass, "
            f"{counts['fail']} fail, {counts['quarantined']} quarantined"
        )
    chart_json = json.dumps(chart)
    chart_label = "Cases by flow. " + "; ".join(chart_bits) + "."
    refs = _layout_refs(report, link_base)
    if refs:
        layout_list = "<ul>" + "".join(
            f"<li>{html.escape(case)}: "
            f'<a href="{html.escape(href, quote=True)}">'
            f"{html.escape(name)}</a> (run record)</li>"
            for case, name, href in refs
        ) + "</ul>"
    else:
        layout_list = (
            "<p>No GDS/OAS sources recorded in this run's "
            "case artifacts.</p>"
        )
    dashboard_html = f"""<section aria-labelledby="dashboard">
<h2 id="dashboard">Dashboard</h2>
<div id="flow-chart" role="img" aria-label="{html.escape(chart_label, quote=True)}">
<p class="chart-note">Interactive chart needs network access for the
Plotly CDN. Exact counts are in the flow tables below.</p>
</div>
<script type="application/json" id="flow-data">{chart_json}</script>
</section>
<section aria-labelledby="layout">
<h2 id="layout">Layout preview</h2>
<p>Schematic Mach&ndash;Zehnder illustration (not to scale, not from
GDSII data). For signoff, open the GDSII sources in KLayout.</p>
<div id="layout-viewer" role="img" aria-label="Schematic 3D illustration of a Mach-Zehnder interferometer: substrate slab, two waveguide arms, input and output couplers.">
<p class="chart-note">3D preview needs network access for the
Three.js CDN.</p>
</div>
<h3>GDSII sources referenced by this run</h3>
{layout_list}
</section>"""
    scripts_html = f"""<script src="{PLOTLY_CDN}"></script>
<script src="{THREE_CDN}"></script>
<script>
(function () {{
  var dataEl = document.getElementById('flow-data');
  var chartEl = document.getElementById('flow-chart');
  if (!dataEl || !chartEl || !window.Plotly) {{ return; }}
  var data = JSON.parse(dataEl.textContent);
  Plotly.newPlot(chartEl, [
    {{ x: data.flows, y: data.pass, name: 'Pass', type: 'bar',
       marker: {{ color: '#14532d' }} }},
    {{ x: data.flows, y: data.fail, name: 'Fail', type: 'bar',
       marker: {{ color: '#7f1d1d' }} }},
    {{ x: data.flows, y: data.quarantined, name: 'Quarantined',
       type: 'bar', marker: {{ color: '#a16207' }} }}
  ], {{ barmode: 'stack', margin: {{ t: 30, r: 10, b: 50, l: 40 }},
       xaxis: {{ title: 'Flow' }}, yaxis: {{ title: 'Cases', dtick: 1 }},
       font: {{ family: 'system-ui, sans-serif' }} }},
    {{ responsive: true, displayModeBar: false }});
}})();
(function () {{
  var box = document.getElementById('layout-viewer');
  if (!box || !window.THREE) {{ return; }}
  var reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = box.clientWidth || 640, H = 360;
  var renderer = new THREE.WebGLRenderer({{ antialias: true }});
  renderer.setSize(W, H);
  renderer.domElement.setAttribute('aria-hidden', 'true');
  box.appendChild(renderer.domElement);
  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffffff);
  var camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
  camera.position.set(6, 5, 8);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  var sun = new THREE.DirectionalLight(0xffffff, 0.6);
  sun.position.set(5, 10, 7);
  scene.add(sun);
  var group = new THREE.Group();
  scene.add(group);
  function slab(w, h, d, color, x, y, z) {{
    var mesh = new THREE.Mesh(
      new THREE.BoxGeometry(w, h, d),
      new THREE.MeshLambertMaterial({{ color: color }}));
    mesh.position.set(x, y, z);
    group.add(mesh);
  }}
  slab(8, 0.2, 5, 0xe5e5e5, 0, -0.6, 0);
  slab(1.2, 0.3, 0.5, 0xb45309, -2.5, 0, 0);
  slab(1.2, 0.3, 0.5, 0xb45309, 2.5, 0, 0);
  slab(4, 0.2, 0.25, 0x0f766e, 0, 0, -0.6);
  slab(4, 0.2, 0.25, 0x0f766e, 0, 0, 0.6);
  function draw() {{ renderer.render(scene, camera); }}
  if (reduce) {{ draw(); return; }}
  var angle = 0;
  (function sway() {{
    angle += 0.004;
    group.rotation.y = Math.sin(angle) * 0.4;
    draw();
    requestAnimationFrame(sway);
  }})();
}})();
</script>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Correctness gate: {html.escape(verdict)}</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip" href="#cases">Skip to results</a>
<main>
<h1>Rocket-engine correctness gate</h1>
<p class="banner {banner_class}" role="status">GATE {html.escape(verdict)} \u2014 {html.escape(totals_line)}</p>
<p>Generated {html.escape(stamp)}. Tables and text work offline; the
dashboard chart and 3D preview load Plotly and Three.js from CDNs when
network is available.</p>
{dashboard_html}
<div id="cases">
{chr(10).join(sections)}
</div>
</main>
<footer>
<p>Source: tmp/correctness/report.json plus per-case artifacts under
tmp/correctness/cases/&lt;case&gt;/. Regenerate with
scripts/correctness.py then scripts/correctness_report.py.</p>
</footer>
{scripts_html}
</body>
</html>
"""


def write_html_report(report_json, out_html=None):
    """Write report.html for a report.json path. Returns the output path."""
    report_json = Path(report_json)
    report = json.loads(report_json.read_text())
    cases_dir = report_json.parent / "cases"
    out_html = Path(out_html) if out_html else report_json.parent / "report.html"
    page = render_html(report, cases_dir, out_dir=out_html.parent)
    out_html.write_text(page)
    return out_html


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render tmp/correctness/report.html for the "
        "ENGINE-CORRECTNESS gate."
    )
    parser.add_argument("--report", default=None,
                        help="report.json path "
                        "(default: tmp/correctness/report.json)")
    parser.add_argument("--out", default=None,
                        help="report.html path "
                        "(default: next to report.json)")
    args = parser.parse_args(argv)
    report_json = Path(args.report) if args.report else (
        ROOT / "tmp" / "correctness" / "report.json")
    try:
        out = write_html_report(report_json, args.out)
    except (OSError, ValueError) as exc:
        print(f"correctness_report: {exc}")
        return 1
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
