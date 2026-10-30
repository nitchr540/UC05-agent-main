from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from .tools import ROOT  # repository being analyzed (UC_REPO_ROOT), not the agent folder
TEST_PATTERNS = {
    ".cs": [re.compile(r"^\s*\[(?:Fact|Theory|Test|TestMethod)\b")],
    ".py": [re.compile(r"^\s*(?:async\s+)?def\s+test_[A-Za-z0-9_]+\s*\(")],
    ".js": [re.compile(r"\b(?:test|it)\s*\(")],
    ".jsx": [re.compile(r"\b(?:test|it)\s*\(")],
    ".ts": [re.compile(r"\b(?:test|it)\s*\(")],
    ".tsx": [re.compile(r"\b(?:test|it)\s*\(")],
    ".java": [re.compile(r"^\s*@Test\b")],
    ".go": [re.compile(r"^\s*func\s+Test[A-Za-z0-9_]+\s*\(")],
}
def find_column_lineage(column, graph):
    return [edge for edge in graph.get("columnLineage", []) if edge.get("column", "").lower() == column.lower()]
def match_services(path, catalog):
    normalized = path.replace("\\", "/").strip("/").lower()
    matches = []
    for service in catalog:
        prefixes = [service.get("repositoryPath", ""), *service.get("pathPrefixes", [])]
        normalized_prefixes = [str(prefix).replace("\\", "/").strip("/").lower() for prefix in prefixes if prefix]
        if any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in normalized_prefixes):
            matches.append(service)
    return matches
def _count_tests_in_file(path: Path) -> int | None:
    patterns = TEST_PATTERNS.get(path.suffix.lower())
    if not patterns:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # One declared test method/function = one test. Parameterized rows are not expanded.
    count = 0
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in patterns):
            count += 1
    return count
def _count_tests(path_value: str) -> tuple[int | None, str]:
    relative = Path(str(path_value or "").replace("\\", "/"))
    target = (ROOT / relative).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        return None, "unavailable"
    if target.is_file():
        value = _count_tests_in_file(target)
        return (value, "repository scan") if value is not None else (None, "unavailable")
    if target.is_dir():
        total = 0
        found_supported = False
        for file in target.rglob("*"):
            if not file.is_file() or file.suffix.lower() not in TEST_PATTERNS:
                continue
            found_supported = True
            value = _count_tests_in_file(file)
            if value is not None:
                total += value
        return (total, "repository scan") if found_supported else (None, "unavailable")
    return None, "unavailable"
def _normalize_test_suite(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        name = item
        path = item
        suite_type = "unspecified"
        configured_count = None
    else:
        name = item.get("name") or item.get("path") or "Unnamed test suite"
        path = item.get("path") or item.get("name") or ""
        suite_type = item.get("type") or "unspecified"
        configured_count = item.get("count", item.get("testCount"))
    if isinstance(configured_count, int) and configured_count >= 0:
        count, source = configured_count, "test_mappings.json"
    else:
        count, source = _count_tests(path)
    return {
        "name": str(name),
        "path": str(path),
        "type": str(suite_type),
        "count": count,
        "count_source": source,
    }
def map_tests(paths, mappings):
    tests: dict[str, dict[str, Any]] = {}
    normalized_paths = [str(path).replace("\\", "/").lower() for path in paths]
    for item in mappings:
        prefixes = [str(p).replace("\\", "/").lower() for p in item.get("pathPrefixes", [])]
        if any(path.startswith(prefix) for path in normalized_paths for prefix in prefixes):
            for raw_test in item.get("tests", []):
                test = _normalize_test_suite(raw_test)
                key = test["path"].replace("\\", "/").lower() or test["name"].lower()
                tests[key] = test
    return sorted(tests.values(), key=lambda value: value["name"].lower())
def classify_api_consumers(providers, graph):
    provider_names = {str(item).lower() for item in providers if item}
    grouped = {"internal_services": [], "sdks": [], "external_integrations": []}
    seen = set()
    def add(item):
        name = item.get("consumer") or item.get("name") or item.get("service")
        if not name:
            return
        consumer_type = str(item.get("consumerType") or "internal_service").lower()
        key = (consumer_type, str(name).lower())
        if key in seen:
            return
        seen.add(key)
        normalized = {"name": name, "consumer_type": consumer_type, "provider": item.get("provider"),
                      "path": item.get("path"), "external": bool(item.get("external", consumer_type != "internal_service")),
                      "reason": item.get("reason")}
        grouped["sdks" if consumer_type == "sdk" else "external_integrations" if consumer_type == "external_integration" else "internal_services"].append(normalized)
    for item in graph.get("apiConsumers", []):
        if str(item.get("provider", "")).lower() in provider_names:
            add(item)
    for mapping in graph.get("apiContractConsumers", []):
        if str(mapping.get("provider", "")).lower() in provider_names:
            for consumer in mapping.get("consumers", []):
                add({**consumer, "provider": mapping.get("provider")})
    for values in grouped.values():
        values.sort(key=lambda item: str(item["name"]).lower())
    return grouped
def resolve_contract_consumers(symbol, graph):
    wanted = str(symbol or "").lower()
    grouped = {"internal_services": [], "sdks": [], "external_integrations": []}
    seen = set()
    def add(item, provider=None):
        consumer_type = str(item.get("consumerType") or "").lower()
        artifact_type = str(item.get("type") or "").lower()
        if not consumer_type:
            if artifact_type == "sdk": consumer_type = "sdk"
            elif artifact_type in {"external", "external_integration"}: consumer_type = "external_integration"
            elif artifact_type in {"consumer", "pipeline"}: consumer_type = "internal_service"
            else: return
        name = item.get("name") or item.get("service") or item.get("consumer") or item.get("path")
        if not name: return
        key = (consumer_type, str(name).lower())
        if key in seen: return
        seen.add(key)
        value = {"name": name, "consumer_type": consumer_type, "provider": provider, "path": item.get("path"),
                 "external": bool(item.get("external", consumer_type != "internal_service")), "reason": item.get("reason")}
        grouped["sdks" if consumer_type == "sdk" else "external_integrations" if consumer_type == "external_integration" else "internal_services"].append(value)
    for mapping in graph.get("apiContractConsumers", []):
        if str(mapping.get("symbol", "")).lower() == wanted:
            for consumer in mapping.get("consumers", []): add(consumer, mapping.get("provider"))
    for mapping in graph.get("contractArtifacts", []):
        if str(mapping.get("symbol", "")).lower() == wanted:
            for artifact in mapping.get("artifacts", []): add(artifact, mapping.get("provider"))
    for values in grouped.values(): values.sort(key=lambda item: str(item["name"]).lower())
    return grouped
PLACEHOLDER_OWNERS = {"", "tbd", "todo", "unknown", "n/a", "none", "not listed"}
def _owner(service):
    owner = str((service or {}).get("owner") or "").strip()
    return "" if owner.lower() in PLACEHOLDER_OWNERS else owner
def _downstream(name, graph):
    key = str(name).lower(); found = {}
    for edge in graph.get("serviceDependencies", []):
        if str(edge.get("source", "")).lower() == key and edge.get("target"):
            found.setdefault(str(edge["target"]).lower(), {"name": edge["target"], "consumer_type": "internal_service"})
    for edge in graph.get("apiConsumers", []):
        if str(edge.get("provider", "")).lower() == key and edge.get("consumer"):
            found.setdefault(str(edge["consumer"]).lower(), {"name": edge["consumer"], "consumer_type": str(edge.get("consumerType") or "internal_service").lower()})
    for edge in graph.get("runtimeDependencies", []):
        if str(edge.get("source", "")).lower() == key and edge.get("target"):
            found.setdefault(str(edge["target"]).lower(), {"name": edge["target"], "consumer_type": str(edge.get("consumerType") or "internal_service").lower()})
    return list(found.values())
def build_impact_view(state, graph, catalog, transitive_depth=1):
    by_name = {str(s.get("name", "")).lower(): s for s in catalog if s.get("name")}
    alias = {}
    for group in graph.get("apiContractConsumers", []):
        for item in group.get("consumers", []):
            if item.get("name") and item.get("service"): alias[str(item["name"]).lower()] = item["service"]
    for group in graph.get("contractArtifacts", []):
        for item in group.get("artifacts", []):
            if item.get("name") and item.get("service"): alias[str(item["name"]).lower()] = item["service"]
    def canonical(name): return alias.get(str(name or "").lower(), name)
    def kind(name, default="internal_service"):
        return str(by_name.get(str(name).lower(), {}).get("consumerType") or default).lower()
    changed = []
    for service in state.get("impacted_services", []):
        name = service.get("name")
        if name and str(name).lower() not in {c["name"].lower() for c in changed}:
            files = [f["path"] for f in state.get("changed_files", []) if match_services(f["path"], [service])]
            changed.append({"name": name, "owner": _owner(service), "files": len(files)})
    changed_keys = {c["name"].lower() for c in changed}; direct = {}
    def add_direct(name, via, provider, consumer_type=None, reason=""):
        name = canonical(name); key = str(name or "").lower()
        if not key or key in changed_keys: return
        entry = direct.setdefault(key, {"name": name, "owner": _owner(by_name.get(key)), "consumer_type": consumer_type or kind(name), "via": set(), "providers": set(), "reasons": set(), "missing_files": 0})
        entry["via"].add(via)
        if provider: entry["providers"].add(str(provider))
        if reason: entry["reasons"].add(reason)
    for service in changed:
        for item in _downstream(service["name"], graph): add_direct(item["name"], "registered", service["name"], item["consumer_type"])
    for api in state.get("api_changes", []) or []:
        providers = [s["name"] for s in changed if match_services(api.get("file", ""), [by_name.get(s["name"].lower(), {})])]
        groups = classify_api_consumers(providers, graph)
        for group in groups.values():
            for item in group: add_direct(item["name"], "breaking", item.get("provider") or (providers[0] if providers else ""), item.get("consumer_type"), "deleted route/public signature")
    for group in ("affected_internal_services", "affected_sdks", "affected_external_integrations"):
        for item in state.get(group, []) or []: add_direct(item.get("name"), "breaking", item.get("provider") or (changed[0]["name"] if changed else ""), item.get("consumer_type"))
    for dep in state.get("dependent_artifacts", []) or []:
        if dep.get("artifact_type") in {"consumer", "pipeline", "sdk", "external_integration"}:
            name = dep.get("service") or dep.get("consumer_name")
            providers = [s["name"] for s in changed if match_services(dep.get("trigger_file", ""), [by_name.get(s["name"].lower(), {})])]
            add_direct(name, "breaking", providers[0] if providers else "", dep.get("consumer_type"), dep.get("symbol", ""))
            key = str(canonical(name) or "").lower()
            if not dep.get("changed") and not dep.get("external") and key in direct: direct[key]["missing_files"] += 1
    schema = []
    for change in state.get("schema_changes", []) or []:
        owners = [s["name"] for s in changed if match_services(change.get("file", ""), [by_name.get(s["name"].lower(), {})])]
        consumers = sorted({l.get("consumer") for l in change.get("lineage", []) if l.get("consumer")})
        schema.append({"file": change.get("file", ""), "column": change.get("column", ""), "service": owners[0] if owners else "", "consumers": consumers})
        for consumer in consumers: add_direct(consumer, "lineage", owners[0] if owners else "", None, f"column {change.get('column')}")
    seen_schema = {x["file"] for x in schema}
    for f in state.get("changed_files", []) or []:
        if str(f.get("path", "")).lower().endswith(".sql") and f["path"] not in seen_schema:
            owners = [s["name"] for s in changed if match_services(f["path"], [by_name.get(s["name"].lower(), {})])]
            schema.append({"file": f["path"], "column": "", "service": owners[0] if owners else "", "consumers": []})
    shown = changed_keys | set(direct); transitive = {}; frontier = [(d["name"], 1) for d in direct.values() if d["consumer_type"] == "internal_service"]
    while frontier:
        parent, depth = frontier.pop(0)
        if depth > transitive_depth: continue
        for item in _downstream(parent, graph):
            key = str(item["name"]).lower()
            if key in shown: continue
            shown.add(key); transitive[key] = {"name": item["name"], "owner": _owner(by_name.get(key)), "parent": parent, "level": depth + 1, "consumer_type": item["consumer_type"]}
            if item["consumer_type"] == "internal_service": frontier.append((item["name"], depth + 1))
    direct_list = [{**e, "via": sorted(e["via"]), "providers": sorted(e["providers"]), "reasons": sorted(e["reasons"])} for e in sorted(direct.values(), key=lambda e: (0 if "breaking" in e["via"] or "lineage" in e["via"] else 1, e["name"].lower()))]
    return {"branch": state.get("branch_name", ""), "commit": str(state.get("commit_sha", ""))[:7], "severity": state.get("severity", "Low"), "gate_status": state.get("gate_status", "passed"), "changed": changed, "direct": direct_list, "transitive": sorted(transitive.values(), key=lambda t: (t["level"], t["name"].lower())), "schema": schema, "tests": list(state.get("required_tests", []) or []), "unmapped_files": [f["path"] for f in state.get("changed_files", []) or [] if not any(match_services(f["path"], [by_name.get(c["name"].lower(), {})]) for c in changed)]}
