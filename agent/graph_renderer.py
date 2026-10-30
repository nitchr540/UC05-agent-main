from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

COLORS = {
    "changed": ("#fee2e2", "#b91c1c"),
    "direct": ("#fef3c7", "#d97706"),
    "transitive": ("#f3f4f6", "#6b7280"),
    "schema": ("#ede9fe", "#7c3aed"),
    "test": ("#dcfce7", "#15803d"),
}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def add_node(parts: list[str], x: int, y: int, w: int, h: int, title: str, details: list[str], kind: str) -> None:
    fill, stroke = COLORS[kind]
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    parts.append(f'<text x="{x+w/2}" y="{y+25}" text-anchor="middle" font-size="16" font-weight="700" fill="#111827">{esc(title)}</text>')
    for index, detail in enumerate([item for item in details if item][:4]):
        parts.append(f'<text x="{x+w/2}" y="{y+47+index*17}" text-anchor="middle" font-size="12" fill="#374151">{esc(detail)}</text>')


def add_arrow(parts: list[str], x1: int, y1: int, x2: int, y2: int, dashed: bool = False) -> None:
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"{dash}/>')


def test_name(test: Any) -> str:
    if isinstance(test, dict):
        return str(test.get("name") or test.get("path") or "Test suite")
    return str(test)


def render(view: dict[str, Any], output: Path) -> None:
    changed = list(view.get("changed", []))[:4]
    direct = list(view.get("direct", []))[:8]
    transitive = list(view.get("transitive", []))[:8]
    schemas = list(view.get("schema", []))[:4]
    tests = list(view.get("tests", []))[:6]
    width = 1400
    body_rows = max(1, (len(direct) + 1) // 2, len(transitive))
    height = 700 + body_rows * 120 + ((len(tests) + 2) // 3) * 105
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="40" y="48" font-size="28" font-weight="700" fill="#172b4d">UC-05 Dependency Blast Radius</text>',
        f'<text x="40" y="78" font-size="14" fill="#475467">Branch: {esc(view.get("branch"))} | Commit: {esc(view.get("commit"))} | Severity: {esc(view.get("severity"))} | Gate: {esc(view.get("gate_status"))}</text>',
    ]
    roots: list[tuple[int, int]] = []
    root_items = changed or [{"name": "Changed files", "files": len(view.get("unmapped_files", []))}]
    for index, item in enumerate(root_items):
        x, y = 60 + index * 315, 110
        add_node(svg, x, y, 270, 88, str(item.get("name", "Changed service")), [f'{item.get("files", 0)} file(s) changed'], "changed")
        roots.append((x + 135, y + 88))

    direct_positions: dict[str, tuple[int, int]] = {}
    direct_y = 250
    for index, item in enumerate(direct):
        x, y = 390 + (index % 2) * 330, direct_y + (index // 2) * 120
        details = []
        if item.get("owner"):
            details.append(f'Team: {item["owner"]}')
        if item.get("consumer_type") and item.get("consumer_type") != "internal_service":
            details.append(str(item["consumer_type"]))
        if item.get("runtime_calls") is not None:
            details.append(f'Runtime calls: {item["runtime_calls"]}')
        if item.get("missing_files"):
            details.append(f'{item["missing_files"]} dependent file(s) missing')
        add_node(svg, x, y, 285, 92, str(item.get("name", "Affected service")), details, "direct")
        direct_positions[str(item.get("name", "")).lower()] = (x, y)
        if roots:
            direct_evidence = bool(set(item.get("via", [])) & {"breaking", "lineage", "runtime", "registered+runtime"})
            root = roots[min(index, len(roots) - 1)]
            add_arrow(svg, root[0], root[1], x, y + 46, dashed=not direct_evidence)

    for index, item in enumerate(transitive):
        x, y = 1070, direct_y + index * 110
        details = [f'Level {item.get("level", 2)}']
        if item.get("owner"):
            details.append(f'Team: {item["owner"]}')
        add_node(svg, x, y, 270, 82, str(item.get("name", "Transitive service")), details, "transitive")
        parent = direct_positions.get(str(item.get("parent", "")).lower())
        if parent:
            add_arrow(svg, parent[0] + 285, parent[1] + 46, x, y + 40, dashed=True)

    lower_y = direct_y + body_rows * 120 + 60
    for index, item in enumerate(schemas):
        title = Path(str(item.get("file") or "schema")).name
        details = ["Schema change"]
        if item.get("column"):
            details.append(f'Column: {item["column"]}')
        add_node(svg, 60 + index * 320, lower_y, 280, 82, title, details, "schema")

    tests_y = lower_y + 145
    svg.append(f'<text x="60" y="{tests_y-18}" font-size="19" font-weight="700" fill="#172b4d">Test suites to run ({len(view.get("tests", []))})</text>')
    for index, test in enumerate(tests):
        details = []
        if isinstance(test, dict):
            if test.get("type"):
                details.append(str(test["type"]))
            details.append(f'{test["count"]} tests' if test.get("count") is not None else "count unavailable")
        else:
            details.append("count unavailable")
        add_node(svg, 60 + (index % 3) * 430, tests_y + (index // 3) * 105, 380, 78, test_name(test), details, "test")

    gate_y = tests_y + max(1, (len(tests) + 2) // 3) * 105 + 55
    severity = str(view.get("severity", "Low")).upper()
    failed = view.get("gate_status") == "failed"
    gate = "FAILED" if failed else "PASSED"
    gate_color = "#b91c1c" if failed else "#15803d"
    svg.extend([
        f'<rect x="470" y="{gate_y}" width="460" height="76" rx="14" fill="{gate_color}"/>',
        f'<text x="700" y="{gate_y+31}" text-anchor="middle" font-size="20" font-weight="700" fill="white">Severity: {esc(severity)}</text>',
        f'<text x="700" y="{gate_y+55}" text-anchor="middle" font-size="14" fill="white">CI gate {gate}</text>',
        "</svg>",
    ])
    svg_markup = "\n".join(svg)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UC-05 Dependency Graph</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f7f8fa;color:#172b4d}}
main{{max-width:1440px;margin:auto;padding:24px}}
.card{{background:white;border:1px solid #d0d5dd;border-radius:14px;padding:12px;box-shadow:0 2px 12px #0002;overflow:auto}}
.meta{{color:#475467;margin:8px 0 18px}}
svg{{width:100%;height:auto;min-width:900px}}
</style>
</head>
<body><main>
<h1>UC-05 Dependency Graph</h1>
<div class="meta">Feature-branch commit impact visualization</div>
<div class="card"><picture>{svg_markup}</picture></div>
</main></body></html>'''
    output.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="impact-result.json")
    parser.add_argument("--output", default="dependency-graph.html")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    view = payload.get("impact_graph") or payload.get("impactGraph") or {}
    if not isinstance(view, dict):
        view = {}
    render(view, Path(args.output))


if __name__ == "__main__":
    main() 
