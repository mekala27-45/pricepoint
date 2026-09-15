"""Fail if a published measured claim differs from its stored evidence.

The registry is created before results. Each claim identifies a JSON artifact,
a dotted field path and the exact rendered text. Numeric markdown tables are
generated from the same records and checked byte for byte.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def resolve(value: Any, pointer: str) -> Any:
    for key in pointer.split("."):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def check_claims(root: Path) -> list[str]:
    registry = json.loads((root / "artifacts/claims.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for claim in registry["claims"]:
        artifact = json.loads((root / claim["artifact"]).read_text(encoding="utf-8"))
        value = resolve(artifact, claim["pointer"])
        rendered = format(value, claim.get("format", ""))
        expected = claim["template"].replace("{value}", rendered)
        document = (root / claim["document"]).read_text(encoding="utf-8")
        if expected not in document:
            errors.append(f"{claim['id']}: expected {expected!r} in {claim['document']}")
    for block in registry.get("blocks", []):
        document = (root / block["document"]).read_text(encoding="utf-8")
        source = (root / block["source"]).read_text(encoding="utf-8").strip()
        start, end = f"<!-- {block['id']}:start -->", f"<!-- {block['id']}:end -->"
        if start not in document or end not in document:
            errors.append(f"{block['id']}: missing evidence block")
        elif document.split(start, 1)[1].split(end, 1)[0].strip() != source:
            errors.append(f"{block['id']}: published block differs from evidence")
    return errors


def main() -> None:
    errors = check_claims(ROOT)
    if errors:
        raise SystemExit("\n".join(errors))
    print("Published number gate passed")


if __name__ == "__main__":
    main()
