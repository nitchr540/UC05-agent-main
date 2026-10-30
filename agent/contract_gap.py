from __future__ import annotations

import re
from typing import Any

CS_PROPERTY_RE = re.compile(
    r"\bpublic\s+(?:required\s+)?(?P<type>[A-Za-z_][A-Za-z0-9_<>?\[\].]*)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{\s*get\s*;",
    re.IGNORECASE,
)
CS_METHOD_RE = re.compile(
    r"\bpublic\s+(?:async\s+)?(?P<return>[A-Za-z_][A-Za-z0-9_<>?\[\]., ]*)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)",
    re.IGNORECASE,
)
SQL_COLUMN_RE = re.compile(
    r"^\s*\[?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\]?\s+"
    r"(?P<type>bigint|int|smallint|tinyint|uniqueidentifier|varchar|nvarchar|char|nchar|decimal|numeric|bit|date|datetime|datetime2|text|xml|json)"
    r"(?:\s*\([^)]*\))?\b",
    re.IGNORECASE,
)
TYPE_MAP = {
    "int": "int", "int32": "int", "system.int32": "int",
    "long": "bigint", "int64": "bigint", "system.int64": "bigint",
    "guid": "uniqueidentifier", "system.guid": "uniqueidentifier",
    "string": "string", "system.string": "string",
}


def _patch_lines(patch: str) -> tuple[list[str], list[str]]:
    removed, added = [], []
    for line in (patch or "").splitlines():
        if line.startswith(("---", "+++", "@@", "diff ", "index ")):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return removed, added


def _normalize_type(value: str) -> str:
    value = re.sub(r"\s+", "", value or "").lower().rstrip("?")
    return TYPE_MAP.get(value, value)


def _extract_properties(lines: list[str]) -> dict[str, dict[str, str]]:
    result = {}
    for line in lines:
        match = CS_PROPERTY_RE.search(line)
        if match:
            result[match.group("name").lower()] = {
                "name": match.group("name"), "type": match.group("type")
            }
    return result


def _normalize_params(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _extract_methods(lines: list[str]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for line in lines:
        match = CS_METHOD_RE.search(line)
        if match:
            item = {
                "name": match.group("name"),
                "return_type": re.sub(r"\s+", " ", match.group("return")).strip(),
                "params": _normalize_params(match.group("params")),
                "signature": match.group(0).strip(),
            }
            result.setdefault(item["name"].lower(), []).append(item)
    return result


def _extract_sql(lines: list[str]) -> dict[str, dict[str, str]]:
    result = {}
    for line in lines:
        match = SQL_COLUMN_RE.search(line)
        if match:
            result[match.group("name").lower()] = {
                "name": match.group("name"), "type": match.group("type")
            }
    return result


def detect_breaking_contract_changes(changed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for changed in changed_files:
        path = str(changed.get("path", ""))
        removed, added = _patch_lines(str(changed.get("patch", "")))
        lower_path = path.lower()

        if lower_path.endswith(".cs"):
            old_props = _extract_properties(removed)
            new_props = _extract_properties(added)

            for key in sorted(old_props.keys() & new_props.keys()):
                old, new = old_props[key], new_props[key]
                if _normalize_type(old["type"]) != _normalize_type(new["type"]):
                    changes.append({
                        "symbol": new["name"], "old_symbol": old["name"],
                        "old_type": old["type"], "new_type": new["type"],
                        "path": path, "layer": "contract",
                        "change_type": "property_datatype_changed", "breaking": True,
                    })

            removed_only = [old_props[k] for k in old_props.keys() - new_props.keys()]
            added_only = [new_props[k] for k in new_props.keys() - old_props.keys()]
            used_added: set[str] = set()
            for old in removed_only:
                rename = next((
                    new for new in added_only
                    if new["name"].lower() not in used_added
                    and _normalize_type(new["type"]) == _normalize_type(old["type"])
                ), None)
                if rename:
                    used_added.add(rename["name"].lower())
                    changes.append({
                        "symbol": old["name"], "old_symbol": old["name"],
                        "new_symbol": rename["name"], "old_type": old["type"],
                        "new_type": rename["type"], "path": path, "layer": "contract",
                        "change_type": "property_renamed", "breaking": True,
                    })
                else:
                    changes.append({
                        "symbol": old["name"], "old_symbol": old["name"],
                        "old_type": old["type"], "new_type": None,
                        "path": path, "layer": "contract",
                        "change_type": "property_deleted", "breaking": True,
                    })

            old_methods = _extract_methods(removed)
            new_methods = _extract_methods(added)
            for key in sorted(set(old_methods) | set(new_methods)):
                old_list, new_list = old_methods.get(key, []), new_methods.get(key, [])
                if old_list and new_list:
                    old, new = old_list[0], new_list[0]
                    if (old["return_type"].lower(), old["params"]) != (new["return_type"].lower(), new["params"]):
                        changes.append({
                            "symbol": old["name"], "old_signature": old["signature"],
                            "new_signature": new["signature"], "path": path,
                            "layer": "api", "change_type": "public_method_signature_changed",
                            "breaking": True,
                        })
                elif old_list and not new_list:
                    old = old_list[0]
                    changes.append({
                        "symbol": old["name"], "old_signature": old["signature"],
                        "new_signature": None, "path": path, "layer": "api",
                        "change_type": "public_method_deleted", "breaking": True,
                    })

        elif lower_path.endswith(".sql"):
            old_cols, new_cols = _extract_sql(removed), _extract_sql(added)
            for key in sorted(old_cols.keys() & new_cols.keys()):
                old, new = old_cols[key], new_cols[key]
                if _normalize_type(old["type"]) != _normalize_type(new["type"]):
                    changes.append({
                        "symbol": new["name"], "old_symbol": old["name"],
                        "old_type": old["type"], "new_type": new["type"],
                        "path": path, "layer": "schema",
                        "change_type": "sql_column_datatype_changed", "breaking": True,
                    })
            for key in sorted(old_cols.keys() - new_cols.keys()):
                old = old_cols[key]
                changes.append({
                    "symbol": old["name"], "old_symbol": old["name"],
                    "old_type": old["type"], "new_type": None,
                    "path": path, "layer": "schema",
                    "change_type": "sql_column_deleted", "breaking": True,
                })
    return changes


def _normalized_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip("/").lower()


def analyze_contract_gaps(changed_files: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    changes = detect_breaking_contract_changes(changed_files)
    changed_paths = {_normalized_path(item.get("path", "")) for item in changed_files}
    mappings = graph.get("contractArtifacts", [])
    dependent_artifacts: dict[tuple[str, str], dict[str, Any]] = {}

    for change in changes:
        matches = [m for m in mappings if str(m.get("symbol", "")).lower() == str(change["symbol"]).lower()]
        for match in matches:
            for artifact in match.get("artifacts", []):
                expected = str(artifact.get("path", ""))
                if expected:
                    key = (str(change["symbol"]).lower(), _normalized_path(expected))
                    dependent_artifacts[key] = {
                        "symbol": change["symbol"],
                        "change_type": change["change_type"],
                        "trigger_file": change["path"],
                        "expected_file": expected,
                        "artifact_type": artifact.get("type", "dependent-artifact"),
                        "consumer_type": artifact.get("consumerType"),
                        "consumer_name": artifact.get("name") or artifact.get("service"),
                        "service": artifact.get("service"),
                        "schema": artifact.get("schema"),
                        "external": artifact.get("external", False),
                        "reason": artifact.get("reason", "Required for contract consistency"),
                        "changed": _normalized_path(expected) in changed_paths,
                    }

    all_dependents = list(dependent_artifacts.values())
    missing = [item for item in all_dependents if not item["changed"] and not item["external"]]
    return {
        "breaking_contract_changes": changes,
        "contract_type_changes": [x for x in changes if "datatype_changed" in x["change_type"]],
        "deleted_contract_members": [x for x in changes if x["change_type"] in {"property_deleted", "public_method_deleted", "sql_column_deleted"}],
        "renamed_contract_members": [x for x in changes if x["change_type"] == "property_renamed"],
        "changed_method_signatures": [x for x in changes if x["change_type"] == "public_method_signature_changed"],
        "dependent_artifacts": all_dependents,
        "missing_dependent_changes": missing,
        "missing_schema_changes": [x for x in missing if x["artifact_type"] in {"schema", "migration"}],
        "missing_consumer_changes": [x for x in missing if x["artifact_type"] in {"consumer", "pipeline", "sdk", "external_integration"}],
        "missing_test_changes": [x for x in missing if x["artifact_type"] == "test"],
        "contract_gap_critical": bool(changes and missing),
    }


def build_critical_summary(state: dict[str, Any]) -> str:
    changes = state.get("breaking_contract_changes", [])
    missing = state.get("missing_dependent_changes", [])
    changed_text = "; ".join(
        f"{item['symbol']} ({item['change_type']}) in {item['path']}" for item in changes
    ) or "Breaking contract change detected"
    missing_text = ", ".join(item["expected_file"] for item in missing) or "none"
    return (
        f"Critical impact: {changed_text}. Required dependent changes missing from the commit: "
        f"{missing_text}. Update all flagged schema, implementation, consumer, pipeline, and test "
        "artifacts before merge. Gate status: failed."
    )
