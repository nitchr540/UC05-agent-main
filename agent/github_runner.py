import argparse
import json
import os
from pathlib import Path

from .tools import write_json, write_text


def gate_only(path):
    with Path(path).open(encoding="utf-8") as handle:
        result = json.load(handle)
    if result.get("severity") == "Critical":
        print("Impact Analysis gate failed: Critical feature-branch commit.")
        return 1
    print(f"Impact Analysis gate passed: {result.get('severity', 'Unknown')} impact.")
    return 0


def _write_llm_artifacts(review):
    telemetry = review.get("telemetry", {}) if isinstance(review, dict) else {}
    write_json(os.environ.get("UC_LLM_TELEMETRY_JSON", "llm-telemetry.json"), telemetry)
    write_json(
        os.environ.get("UC_LLM_REQUEST_JSON", "llm-request-sanitized.json"),
        telemetry.get("request_payload_sanitized", {}),
    )
    write_json(
        os.environ.get("UC_LLM_RESPONSE_JSON", "llm-response-sanitized.json"),
        telemetry.get("response_payload_sanitized", {}),
    )


def _pr_comment(markdown):
    """PR comment = report without the Dependency graph section (same as before the graph was added)."""
    start = markdown.find("## Dependency graph\n")
    end = markdown.find("## Findings\n", start)
    if start == -1 or end == -1:
        return markdown
    return markdown[:start] + markdown[end:]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-only")
    args = parser.parse_args()
    if args.gate_only:
        return gate_only(args.gate_only)

    from .graph import agent

    result = agent.invoke({
        "base_sha": os.environ["UC_BASE_SHA"],
        "head_sha": os.environ["UC_HEAD_SHA"],
        "branch_name": os.environ.get("UC_BRANCH", "unknown"),
        "commit_sha": os.environ.get("UC_COMMIT_SHA", os.environ["UC_HEAD_SHA"]),
        "error": None,
    })
    serializable = {key: value for key, value in result.items() if key != "markdown_report"}
    serializable.update({"schemaVersion": "2.2", "trigger": "feature-branch-commit"})
    write_json(os.environ.get("UC_OUTPUT_JSON", "impact-result.json"), serializable)
    write_text(os.environ.get("UC_OUTPUT_MARKDOWN", "impact-report.md"), result["markdown_report"])
    write_text(os.environ.get("UC_OUTPUT_PR_COMMENT", "pr-comment.md"), _pr_comment(result["markdown_report"]))
    _write_llm_artifacts(result.get("llm_review", {}))
    print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
