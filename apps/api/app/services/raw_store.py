from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, *, provider: str, external_id: str, payload: dict) -> tuple[str, str]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        now = datetime.now(UTC)
        folder = self.root / provider / now.strftime("%Y/%m") / external_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}.json"
        path.write_bytes(serialized)
        return str(path.resolve()), digest
