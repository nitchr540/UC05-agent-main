import json
import re

MAX_NODES_PER_TIER = 12
MAX_TEST_NODES = 6
SEVERITY_CLASS = {"Critical": "sevCritical", "High": "sevHigh", "Medium": "sevMedium", "Low": "sevLow"}

def _mm_text(value, limit=60):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit: text = text[: limit - 1] + "…"
    for raw, safe in (("&", "#amp;"), ('"', "#quot;"), ("<", "#lt;"), (">", "#gt;"), ("|", "#124;"), ("[", "#91;"), ("]", "#93;"), ("{", "#123;"), ("}", "#125;"), ("`", "#96;")):
        text = text.replace(raw, safe)
    return text

def _mm_label(*parts): return "<br/>".join(_mm_text(p) for p in parts if p not in (None, ""))
def _test_name(test): return str(test.get("name") if isinstance(test, dict) else test)
def _test_count(test): return test.get("count") if isinstance(test, dict) else None
def _test_type(test): return str(test.get("type") or "unspecified") if isinstance(test, dict) else "unspecified"
def _test_source(test): return str(test.get("count_source") or "unavailable") if isinstance(test, dict) else "unavailable"
def _short_test(test): return re.sub(r"\.tests?$", "", _test_name(test).replace("\\", "/").split("/")[-1])

def render_impact_mermaid(view):
    if not view or not (view.get("changed") or view.get("unmapped_files")): return ""
    ids, lines, links, red = {}, ["flowchart TD"], [0], []
    def link(text, proven=False):
        if proven: red.append(links[0])
        links[0] += 1; lines.append(text)
    def node_id(prefix, name):
        key = (prefix, str(name).lower())
        if key not in ids: ids[key] = f"{prefix}{len(ids)}_" + re.sub(r"[^A-Za-z0-9_]", "_", str(name))[:30]
        return ids[key]
    severity = view.get("severity", "Low"); header = f"{view.get('branch', '')} @ {view.get('commit', '')}".strip(" @")
    for svc in view.get("changed", []):
        files = f"{svc['files']} file(s) changed" if svc.get("files") else ""
        lines.append(f'    {node_id("chg", svc["name"])}["{_mm_label(svc["name"], header, files, severity.upper())}"]:::changed')
    if view.get("unmapped_files"):
        lines.append(f'    {node_id("chg", "__unmapped")}["{_mm_label("Files outside any registered service", str(len(view["unmapped_files"])) + " file(s)")}"]:::changed')
    direct, hidden = view.get("direct", [])[:MAX_NODES_PER_TIER], view.get("direct", [])[MAX_NODES_PER_TIER:]
    for item in direct:
        kind = {"sdk": "SDK", "external_integration": "External integration"}.get(item["consumer_type"], "")
        team = f"Team: {item['owner']}" if item.get("owner") else ""; flag = f"{item['missing_files']} dependent file(s) not updated" if item.get("missing_files") else ""
        style = "direct" if ("breaking" in item["via"] or "lineage" in item["via"]) else "registered"
        lines.append(f'    {node_id("dir", item["name"])}["{_mm_label(item["name"], kind, team, flag)}"]:::{style}')
        for provider in item.get("providers") or [s["name"] for s in view.get("changed", [])[:1]]:
            if ("chg", str(provider).lower()) in ids:
                link(f"    {ids[('chg', str(provider).lower())]} {'-->' if style == 'direct' else '-.->'} {node_id('dir', item['name'])}", style == "direct")
    if hidden:
        lines.append(f'    dirMore["{_mm_label(f"+{len(hidden)} more directly affected")}"]:::registered')
    trans = view.get("transitive", [])[:MAX_NODES_PER_TIER]
    for item in trans:
        team = f"Team: {item['owner']}" if item.get("owner") else ""
        lines.append(f'    {node_id("tr", item["name"])}["{_mm_label(item["name"], "Transitive (level " + str(item["level"]) + ")", team)}"]:::transitive')
        parent = str(item["parent"]).lower(); source = ids.get(("dir", parent)) or ids.get(("tr", parent))
        if source: link(f"    {source} -.-> {node_id('tr', item['name'])}")
    for index, change in enumerate(view.get("schema", [])):
        sid = f"sch{index}"; column = f"Column: {change['column']}" if change.get("column") else ""
        lines.append(f'    {sid}[("{_mm_label(change["file"].split("/")[-1], "Schema change", column)}")]:::schema')
        owner = ids.get(("chg", str(change.get("service", "")).lower()))
        if owner: link(f"    {owner} --- {sid}", True)
        for consumer in change.get("consumers", []):
            target = ids.get(("dir", str(consumer).lower()))
            if target: link(f"    {sid} -->|lineage| {target}", True)
    bottom = [ids[k] for k in ids if k[0] == "tr"] or [ids[k] for k in ids if k[0] == "dir"] or [ids[k] for k in ids if k[0] == "chg"]
    tests = view.get("tests", [])
    lines.append(f'    subgraph tests["Test suites to run ({len(tests)})"]')
    if tests:
        for index, test in enumerate(tests[:MAX_TEST_NODES]):
            count = _test_count(test); count_label = f"{count} test(s)" if isinstance(count, int) else "count unavailable"
            lines.append(f'        t{index}["{_mm_label(_short_test(test), _test_type(test), count_label)}"]:::test')
        if len(tests) > MAX_TEST_NODES: lines.append(f'        tMore["{_mm_label(f"+{len(tests) - MAX_TEST_NODES} more suites")}"]:::test')
    else: lines.append('        t0["No mapped test suites"]:::test')
    lines.append("    end")
    gate = "CI gate FAILED" if view.get("gate_status") == "failed" else "CI gate passed"
    lines.append(f'    gate["{_mm_label("Severity: " + severity.upper(), gate)}"]:::{SEVERITY_CLASS.get(severity, "sevLow")}')
    if bottom: link(f"    {bottom[0]} ~~~ t0")
    link("    t0 ~~~ gate")
    if red: lines.append(f"    linkStyle {','.join(map(str, red))} stroke:#c0392b,stroke-width:2px")
    lines += ["    classDef changed fill:#fde2e2,stroke:#c0392b,stroke-width:2px,color:#7b241c", "    classDef direct fill:#fdebd0,stroke:#d68910,stroke-width:2px,color:#784212", "    classDef registered fill:#fef5e7,stroke:#d68910,stroke-dasharray:4 3,color:#784212", "    classDef transitive fill:#f2f3f4,stroke:#95a5a6,color:#424949", "    classDef schema fill:#f2f3f4,stroke:#7d3c98,stroke-width:2px,color:#4a235a", "    classDef test fill:#d5f5e3,stroke:#1e8449,color:#145a32", "    classDef sevCritical fill:#c0392b,stroke:#922b21,color:#ffffff", "    classDef sevHigh fill:#e67e22,stroke:#a04000,color:#ffffff", "    classDef sevMedium fill:#f4d03f,stroke:#b7950b,color:#000000", "    classDef sevLow fill:#58d68d,stroke:#1e8449,color:#000000"]
    return "\n".join(lines)

def render_impact_section(view):
    diagram = render_impact_mermaid(view)
    if not diagram: return ["## Dependency graph", "", "No registered service is affected by this commit."]
    tests = view.get("tests", []); known = sum(int(t.get("count")) for t in tests if isinstance(t, dict) and isinstance(t.get("count"), int)); unknown = sum(1 for t in tests if not isinstance(t, dict) or not isinstance(t.get("count"), int))
    lines = ["## Dependency graph", "", "Red: changed service. Amber (solid): proven affected by this change. Amber (dashed): registered consumer. Grey: transitive downstream. Purple cylinder: schema change.", "", "```mermaid", diagram, "```", "", f"**Impacted test suites:** {len(tests)}  ", f"**Known impacted test cases:** {known}  ", f"**Suites without a test-case count:** {unknown}", "", "<details>", "<summary>Blast radius as a table</summary>", "", "| Service | Impact | Team | Notes |", "|---|---|---|---|"]
    for svc in view.get("changed", []): lines.append(f"| {svc['name']} | Changed | {svc.get('owner') or '-'} | {svc.get('files', 0)} file(s) |")
    for item in view.get("direct", []):
        impact = "Direct (proven)" if ("breaking" in item["via"] or "lineage" in item["via"]) else "Direct (registered consumer)"; notes = "; ".join(filter(None, [", ".join(item.get("reasons", [])), f"{item['missing_files']} dependent file(s) not updated" if item.get("missing_files") else ""]))
        lines.append(f"| {item['name']} | {impact} | {item.get('owner') or '-'} | {notes.replace('|', '/') or '-'} |")
    for item in view.get("transitive", []): lines.append(f"| {item['name']} | Transitive (level {item['level']}) via {item['parent']} | {item.get('owner') or '-'} | - |")
    for change in view.get("schema", []): lines.append(f"| `{change['file']}` | Schema change | - | {('column ' + change['column']) if change.get('column') else '-'} |")
    lines += ["", "</details>"]
    return lines

def _json_fence(payload): return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n```"

def generate_markdown(state):
    lines = ["# GitHub Feature Branch Commit Analysis", "", f"- **Branch:** `{state['branch_name']}`", f"- **Commit:** `{state['commit_sha']}`", f"- **Overall severity:** **{state['severity']}**", "", state["summary"], ""]
    if state.get("impact_graph") is not None: lines += render_impact_section(state.get("impact_graph")) + [""]
    lines += ["## Findings", "", "| File | Category | Severity | Rationale |", "|---|---|---|---|"]
    for item in state.get("findings", []): lines.append(f"| `{item['file']}` | {item['category']} | **{item['severity']}** | {item['rationale'].replace('|', '/')} |")
    dependents = state.get("dependent_artifacts", []); lines += ["", "## Registered dependent files", "", "Files listed by the dependency map for detected contract changes; status indicates whether each path is included in this branch diff.", ""]
    if dependents:
        lines += ["| Trigger file | Dependent file | Type | Branch status | Reason |", "|---|---|---|---|---|"]
        for item in dependents:
            status = "External dependency; verify with owning repository" if item.get("external") else "Included in branch diff" if item.get("changed") else "Not included in branch diff"
            lines.append(f"| `{item['trigger_file']}` | `{item['expected_file']}` | {item['artifact_type']} | {status} | {item.get('reason', '').replace('|', '/')} |")
    else: lines.append("No dependent files are registered for the detected contract changes.")
    lines += ["", "## LLM review", ""]; review = state.get("llm_review", {}); lines.append(f"Review status: **{review.get('status', 'not run')}**.")
    if state.get("deterministic_severity"): lines.append(f"Deterministic severity: **{state['deterministic_severity']}**. Final severity is the higher assessment.")
    if review.get("reason"): lines.append(review["reason"])
    if review.get("status") == "completed":
        lines.append(f"LLM severity: **{review['severity']}**. {review.get('summary', '')}")
        for item in review.get("findings", []): lines.append(f"- **{item['severity']}** `{item['file']}`: {item['rationale'].replace('|', '/')} Evidence: {item['evidence'].replace('|', '/')}")
        if not review.get("findings"): lines.append("No additional evidence-backed risks were identified.")
    telemetry = review.get("telemetry", {}); lines += ["", "## LLM telemetry", ""]
    if telemetry:
        lines += ["| Metric | Value |", "|---|---|", f"| Status | {telemetry.get('status', 'unknown')} |", f"| Model | `{telemetry.get('model') or 'not reported'}` |", f"| Input tokens | {telemetry.get('input_tokens', 0)} |", f"| Output tokens | {telemetry.get('output_tokens', 0)} |", f"| Total tokens | {telemetry.get('total_tokens', 0)} |", f"| Latency | {telemetry.get('latency_ms', 0)} ms |", f"| Finish reason | {telemetry.get('finish_reason') or 'not reported'} |", "", "<details>", "<summary>Sanitized LLM request payload</summary>", "", _json_fence(telemetry.get("request_payload_sanitized", {})), "", "</details>", "", "<details>", "<summary>Sanitized LLM response payload</summary>", "", _json_fence(telemetry.get("response_payload_sanitized", {})), "", "</details>"]
    else: lines.append("LLM telemetry was not available for this run.")
    lines += ["", "## Impacted ownership", ""]; services = state.get("impacted_services", [])
    if services:
        lines += ["| Service | Owning team | Team lead | GitHub contact |", "|---|---|---|---|"]
        for service in services: lines.append(f"| {service.get('name', '')} | {service.get('owner', 'Not listed')} | {service.get('teamLead', 'Not listed')} | {service.get('githubId', 'Not listed')} |")
    else: lines.append("No mapped service ownership found.")
    tests = state.get("required_tests", []) or []; known = sum(int(t.get("count")) for t in tests if isinstance(t, dict) and isinstance(t.get("count"), int)); unknown = sum(1 for t in tests if not isinstance(t, dict) or not isinstance(t.get("count"), int))
    lines += ["", "## Suggested validation", "", "Candidate suites mapped from changed paths; this workflow does not execute them.", "", f"**Impacted test suites:** {len(tests)}  ", f"**Known impacted test cases:** {known}  ", f"**Suites without a test-case count:** {unknown}", ""]
    if tests:
        lines += ["| Test suite | Type | Test cases | Count source |", "|---|---|---:|---|"]
        for t in tests:
            if isinstance(t, dict): lines.append(f"| `{t.get('name','')}` | {t.get('type','unspecified')} | {t.get('count') if isinstance(t.get('count'), int) else 'N/A'} | {t.get('count_source','unavailable')} |")
            else: lines.append(f"| `{t}` | unspecified | N/A | unavailable |")
    else: lines.append("- No mapped test suites found.")
    if state.get("dependency_evidence"): lines += ["", "## Dependency evidence", ""] + [f"- {item}" for item in state["dependency_evidence"]]
    lines += ["", "## Commit decision", "", "**Critical impact detected. The commit check fails; address this before merge.**" if state["severity"] == "Critical" else "**No Critical gate applied to this commit.**"]
    return "\n".join(lines) + "\n"
