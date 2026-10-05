"""Extract schema statements from this project's phpMyAdmin export; never data."""

import json
import re
from pathlib import Path

source = Path("seeds/nationalacts20.sql").read_text(encoding="utf-8-sig")
statements = re.findall(
    r"^(?:CREATE TABLE|ALTER TABLE) `[^`]+`[\s\S]*?;\s*$", source, re.MULTILINE
)
creates = re.findall(r"^CREATE TABLE `([^`]+)`", source, re.MULTILINE)
unsupported = re.findall(r"^CREATE (?!TABLE |DATABASE )[^\n]+", source, re.MULTILINE)
if unsupported or "DELIMITER " in source:
    raise SystemExit("Unsupported schema objects: extract and review these manually")
if not creates or len(creates) != len(set(creates)):
    raise SystemExit("Missing or duplicate table definitions")
statements = [
    re.sub(r",?\s*AUTO_INCREMENT=\d+", "", statement).strip()
    for statement in statements
]
Path("migrations/baseline.json").write_text(
    json.dumps(statements, indent=2) + "\n", encoding="utf-8"
)
print(
    f"Extracted {len(creates)} tables and {len(statements)} schema statements; no rows"
)
