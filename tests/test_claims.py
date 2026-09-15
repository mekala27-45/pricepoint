import json
from pathlib import Path

from scripts.check_no_em_dash import violations
from scripts.check_published_numbers import check_claims


def test_claim_gate_rejects_wrong_number(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/evidence.json").write_text('{"count": 17}', encoding="utf-8")
    registry = {
        "claims": [
            {
                "id": "rows",
                "artifact": "artifacts/evidence.json",
                "pointer": "count",
                "document": "RESULTS.md",
                "template": "Rows: {value}",
            }
        ]
    }
    (tmp_path / "artifacts/claims.json").write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "RESULTS.md").write_text("Rows: 18", encoding="utf-8")
    assert len(check_claims(tmp_path)) == 1
    (tmp_path / "RESULTS.md").write_text("Rows: 17", encoding="utf-8")
    assert check_claims(tmp_path) == []


def test_punctuation_gate_detects_deliberate_violation(tmp_path: Path) -> None:
    (tmp_path / "sample.md").write_text("wrong" + chr(0x2014), encoding="utf-8")
    assert violations(tmp_path, ["sample.md"]) == ["sample.md"]
