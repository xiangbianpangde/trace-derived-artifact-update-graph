import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple
from daug.ledger import ValidationError

REQUIRED_EVENT_FIELDS = [
    "schema_version",
    "event_id",
    "trace_id",
    "repository_id",
    "sequence_no",
    "operation",
    "access_origin"
]

ALLOWED_OPERATIONS = {
    "read", "search", "edit", "write", "delete", "test", "execute", "commit", "approve", "reject"
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+[a-z0-9_\-\.]{20,})"),
    re.compile(r"(?i)(api[_\-]?key\s*[:=]\s*['\"]?[a-z0-9_\-]{16,}['\"]?)"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"]?[^\s'\"]{6,}['\"]?)"),
    re.compile(r"(sk-[a-zA-Z0-9]{20,})"),
]

def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted

class Normalizer:
    def __init__(self, schema_version: str = "daug.tool-event.v1"):
        self.schema_version = schema_version

    def validate_and_normalize_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        for field in REQUIRED_EVENT_FIELDS:
            if field not in raw_event or raw_event[field] is None:
                raise ValidationError(f"Missing required field: '{field}'")

        op = raw_event["operation"]
        if op not in ALLOWED_OPERATIONS:
            raise ValidationError(f"Invalid operation '{op}'. Allowed: {ALLOWED_OPERATIONS}")

        origin = raw_event["access_origin"]
        if origin not in {"organic", "system_recommended", "human_directed", "replay", "unknown"}:
            raise ValidationError(f"Invalid access_origin '{origin}'")

        if origin == "system_recommended" and not raw_event.get("recommendation_id"):
            raise ValidationError(f"Event {raw_event.get('event_id')} is 'system_recommended' but lacks recommendation_id")

        normalized = dict(raw_event)

        # Redact target selector or tool input if present
        if isinstance(normalized.get("target_selector"), str):
            normalized["target_selector"] = redact_secrets(normalized["target_selector"])

        # Compute fallback digests if absent
        if not normalized.get("input_digest") and normalized.get("target_selector"):
            h = hashlib.sha256(normalized["target_selector"].encode("utf-8")).hexdigest()
            normalized["input_digest"] = f"sha256:{h}"

        return normalized

    @classmethod
    def read_jsonl(cls, file_path: str) -> Generator[Dict[str, Any], None, None]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {file_path}")
        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    data = json.loads(clean_line)
                    yield data
                except json.JSONDecodeError as e:
                    raise ValidationError(f"Invalid JSON at line {line_no} in {file_path}: {e}")
