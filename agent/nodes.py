from .contract_gap import analyze_contract_gaps, build_critical_summary
from .dependency_analyzer import (
    build_impact_view,
    classify_api_consumers,
    find_column_lineage,
    map_tests,
    match_services,
    resolve_contract_consumers,
)
from .llm_analysis import SEVERITIES, review_impact
from .report_generator import generate_markdown
from .severity_engine import dropped_columns, highest_severity, is_api_breaking_change, is_comment_only
from .tools import get_changed_files, load_metadata
def collect_changes_node(state):
    return {} if state.get("changed_files") is not None else {
        "changed_files": get_changed_files(state["base_sha"], state["head_sha"])
    }
def identify_services_node(state):
    catalog = load_metadata("service_catalog.json")
    services = {}
    for changed in state.get("changed_files", []):
        for service in match_services(changed["path"], catalog):
            services[service["name"]] = service
    return {"impacted_services": sorted(services.values(), key=lambda item: item["name"])}
def _consumer_names(groups):
    return [item["name"] for key in ("internal_services", "sdks", "external_integrations") for item in groups[key]]
def analyze_changes_node(state):
    graph = load_metadata("dependency_graph.json")
    catalog = load_metadata("service_catalog.json")
    findings, schema, apis, evidence, effective_changes = [], [], [], [], []
    affected = {"internal_services": [], "sdks": [], "external_integrations": []}
    affected_seen = {key: set() for key in affected}
    def merge_consumers(groups):
        for key, values in groups.items():
            for value in values:
                identity = str(value.get("name", "")).lower()
                if identity and identity not in affected_seen[key]:
                    affected_seen[key].add(identity)
                    affected[key].append(value)
    for changed in state.get("changed_files", []):
        path, patch = changed["path"], changed.get("patch", "")
        if is_comment_only(path, patch):
            findings.append({"file": path, "category": "Comment/documentation", "severity": "Low", "rationale": "Only comments or documentation changed."})
            continue
        effective_changes.append(changed)
        columns = dropped_columns(patch) if path.lower().endswith(".sql") else []
        for column in columns:
            lineage = find_column_lineage(column, graph)
            consumers = sorted({item.get("consumer") for item in lineage if item.get("consumer")})
            schema.append({"file": path, "column": column, "lineage": lineage})
            severity = "Critical" if consumers else "High"
            rationale = f"Dropped column '{column}' has proven downstream lineage to: {', '.join(consumers)}." if consumers else f"Dropped column '{column}' has no registered downstream lineage."
            findings.append({"file": path, "category": "Breaking schema" if consumers else "Schema change", "severity": severity, "rationale": rationale})
            evidence.extend(f"{column}: {item.get('source')} -> {item.get('via')} -> {item.get('consumer')}" for item in lineage)
        breaking = is_api_breaking_change(path, patch)
        if breaking:
            apis.append({"file": path, "type": "deleted-public-contract"})
            providers = {service["name"] for service in match_services(path, catalog)}
            groups = classify_api_consumers(providers, graph)
            merge_consumers(groups)
            parts = []
            if groups["internal_services"]: parts.append("internal services: " + ", ".join(x["name"] for x in groups["internal_services"]))
            if groups["sdks"]: parts.append("SDKs: " + ", ".join(x["name"] for x in groups["sdks"]))
            if groups["external_integrations"]: parts.append("external integrations: " + ", ".join(x["name"] for x in groups["external_integrations"]))
            rationale = "A deleted route, public signature, or contract may be breaking."
            if parts: rationale += " Registered API consumers include " + "; ".join(parts) + "."
            findings.append({"file": path, "category": "API/contract", "severity": "High", "rationale": rationale})
            for key, label in (("internal_services", "Internal service"), ("sdks", "SDK"), ("external_integrations", "External integration")):
                evidence.extend(f"{label}: {item.get('provider')} -> {item['name']}" for item in groups[key])
        if not columns and not breaking:
            severity = "Medium" if path.lower().endswith((".json", ".yaml", ".yml", ".xml", ".toml", ".props")) else "Low"
            findings.append({"file": path, "category": "Code/configuration", "severity": severity, "rationale": "No registered breaking lineage was found."})
    gap = analyze_contract_gaps(effective_changes, graph)
    if gap["breaking_contract_changes"]:
        breaking_paths = {item["path"].replace("\\", "/").lower() for item in gap["breaking_contract_changes"]}
        findings = [item for item in findings if not (item["file"].replace("\\", "/").lower() in breaking_paths and item["category"] == "Code/configuration")]
    for change in gap["breaking_contract_changes"]:
        groups = resolve_contract_consumers(change["symbol"], graph)
        merge_consumers(groups)
        evidence.append(f"Breaking contract: {change['symbol']} [{change['change_type']}] in {change['path']}")
        for key, label in (("internal_services", "Internal service"), ("sdks", "SDK"), ("external_integrations", "External integration")):
            evidence.extend(f"{label} affected by {change['symbol']}: {item['name']}" for item in groups[key])
    for missing in gap["missing_dependent_changes"]:
        findings.append({
            "file": missing["expected_file"], "category": "Missing dependent change", "severity": "Critical",
            "rationale": f"Breaking {missing['change_type']} for '{missing['symbol']}' requires {missing['artifact_type']} artifact '{missing['expected_file']}', but it was not changed. {missing['reason']}",
        })
        evidence.append(f"Missing {missing['artifact_type']}: {missing['expected_file']} for {missing['symbol']}")
    if gap["breaking_contract_changes"] and not gap["missing_dependent_changes"]:
        for change in gap["breaking_contract_changes"]:
            findings.append({"file": change["path"], "category": "Breaking contract", "severity": "High", "rationale": f"Detected {change['change_type']} for '{change['symbol']}', with all registered local dependent artifacts included."})
    if not findings:
        findings = [{"file": "(none)", "category": "No change", "severity": "Low", "rationale": "No changed files were detected."}]
    for values in affected.values():
        values.sort(key=lambda item: str(item["name"]).lower())
    return {
        "findings": findings, "schema_changes": schema, "api_changes": apis,
        "affected_api_consumers": affected,
        "affected_internal_services": affected["internal_services"],
        "affected_sdks": affected["sdks"],
        "affected_external_integrations": affected["external_integrations"],
        "dependency_evidence": sorted(set(evidence)), **gap,
    }
def identify_tests_node(state):
    mapped_tests = map_tests([item["path"] for item in state.get("changed_files", [])], load_metadata("test_mappings.json"))
    return {"required_tests": mapped_tests, "missing_test_files": [item["expected_file"] for item in state.get("missing_test_changes", [])]}
def determine_severity_node(state):
    severity = highest_severity(state.get("findings", []))
    if state.get("contract_gap_critical"):
        severity, summary = "Critical", build_critical_summary(state)
    else:
        summary = f"{severity} impact for commit {state['commit_sha'][:7]} on {state['branch_name']}: {len(state.get('changed_files', []))} file(s), {len(state.get('impacted_services', []))} service(s), {len(state.get('required_tests', []))} test suite(s)."
    return {"severity": severity, "summary": summary, "gate_status": "failed" if severity == "Critical" else "passed"}
def llm_review_node(state):
    deterministic_severity = state["severity"]
    review = review_impact(state)
    result = {"deterministic_severity": deterministic_severity, "llm_review": review}
    if review.get("status") != "completed": return result
    severity = max([deterministic_severity, review["severity"]] + [item["severity"] for item in review["findings"]], key=SEVERITIES.get)
    result.update({"severity": severity, "gate_status": "failed" if severity == "Critical" else "passed"})
    return result
def generate_report_node(state):
    try:
        view = build_impact_view(state, load_metadata("dependency_graph.json"), load_metadata("service_catalog.json"))
    except Exception as error:  # the graph is optional; never block the report
        view = {"error": f"{type(error).__name__}: {error}"[:300]}
    report_state = {**state, "impact_graph": view if "error" not in view else None}
    return {"markdown_report": generate_markdown(report_state), "impact_graph": view}
