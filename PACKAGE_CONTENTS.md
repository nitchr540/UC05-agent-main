# Metadata refresh telemetry package

## Existing metadata refresh logic remains unchanged
Keep the repository's current `agent/metadata_updater.py`. The workflow no longer calls it directly. Instead, `agent.metadata_refresh_runner` instruments `urllib.request.urlopen` and then executes the existing updater module. The updater continues to own all dependency graph, service catalog, test mapping, validation, declared-service, audit, and draft-PR behavior.

## Updated files
- `agent/llm_telemetry.py`
- `.github/workflows/metadata-refresh.yml`
- `.github/workflows/impact-analysis.yml`

## New files
- `agent/metadata_refresh_runner.py`
- `agent/metadata_refresh_telemetry.py`
- `tests/test_metadata_refresh_telemetry.py`

## Generated evidence
- `metadata-refresh-result.json`
- `metadata-refresh-summary.md`
- `metadata-refresh-telemetry.json`
- `metadata-refresh-request-sanitized.json`
- `metadata-refresh-response-sanitized.json`
