import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from garmin_fit_sdk import Decoder, Stream


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes | bytearray):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return value


class FitError(RuntimeError):
    pass


class FitParser:
    def parse(self, path: Path, *, include_records: bool = False) -> dict[str, Any]:
        stream = Stream.from_file(str(path))
        decoder = Decoder(stream)
        messages, errors = decoder.read()
        if errors:
            raise FitError("; ".join(str(error) for error in errors))

        safe_messages = _json_value(messages)
        records = safe_messages.get("record_mesgs", [])
        sessions = safe_messages.get("session_mesgs", [])
        laps = safe_messages.get("lap_mesgs", [])
        record_fields = sorted(
            {field for record in records for field in record if isinstance(record, dict)}
        )

        result: dict[str, Any] = {
            "file": path.name,
            "message_counts": {name: len(values) for name, values in safe_messages.items()},
            "record_count": len(records),
            "record_fields": record_fields,
            "sessions": sessions,
            "laps": laps,
            "devices": safe_messages.get("device_info_mesgs", []),
            "activity": safe_messages.get("activity_mesgs", []),
        }
        if include_records:
            result["records"] = records
        return result

    def write_decoded_json(self, fit_path: Path, output_path: Path) -> dict[str, Any]:
        result = self.parse(fit_path, include_records=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        output_path.chmod(0o600)
        return result

