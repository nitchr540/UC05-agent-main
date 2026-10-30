from __future__ import annotations
from typing import Any, TypedDict

class ImpactAnalysisState(TypedDict, total=False):
    base_sha: str
    head_sha: str
    branch_name: str
    commit_sha: str
    changed_files: list[dict[str, Any]]
    impacted_services: list[dict[str, Any]]
    schema_changes: list[dict[str, Any]]
    api_changes: list[dict[str, Any]]
    required_tests: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    dependent_artifacts: list[dict[str, Any]]
    dependency_evidence: list[str]
    affected_api_consumers: list[dict[str, Any]]
    affected_internal_services: list[dict[str, Any]]
    affected_sdks: list[dict[str, Any]]
    affected_external_integrations: list[dict[str, Any]]
    breaking_contract_changes: list[dict[str, Any]]
    deleted_contract_members: list[dict[str, Any]]
    renamed_contract_members: list[dict[str, Any]]
    changed_method_signatures: list[dict[str, Any]]
    contract_type_changes: list[dict[str, Any]]
    missing_dependent_changes: list[dict[str, Any]]
    missing_schema_changes: list[dict[str, Any]]
    missing_consumer_changes: list[dict[str, Any]]
    missing_test_changes: list[dict[str, Any]]
    contract_gap_critical: bool
    severity: str
    deterministic_severity: str
    summary: str
    llm_review: dict[str, Any]
    markdown_report: str
    gate_status: str
    impact_graph: dict[str, Any]
    error: str | None
