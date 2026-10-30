import json
from pathlib import Path
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
def mock_changed_files(scenario="critical"):
    with (FIXTURES / f"{scenario}_changes.json").open(encoding="utf-8") as handle:
        return json.load(handle)
