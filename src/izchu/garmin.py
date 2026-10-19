import json
import zipfile
from pathlib import Path
from threading import Lock
from typing import Any

from garminconnect import Garmin
from garminconnect.api.activities import ActivityDownloadFormat

from .config import Settings
from .fit import FitParser


class GarminError(RuntimeError):
    pass


class GarminClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Garmin | None = None
        self._lock = Lock()
        self.fit_parser = FitParser()

    def status(self) -> dict[str, Any]:
        token_file = self.settings.garmin_token_dir / "garmin_tokens.json"
        return {
            "connected": token_file.exists(),
            "token_directory": str(self.settings.garmin_token_dir),
        }

    def activities(
        self,
        *,
        start: int = 0,
        limit: int = 30,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._api().get_activities(start, limit, activity_type)

    def activity(self, activity_id: int) -> dict[str, Any]:
        api = self._api()
        bundle = {
            "summary": api.get_activity(activity_id),
            "details": api.get_activity_details(activity_id),
            "laps": self._optional(api.get_activity_laps, activity_id),
            "heart_rate_zones": self._optional(
                api.get_activity_hr_in_timezones, activity_id
            ),
            "power_zones": self._optional(api.get_activity_power_in_timezones, activity_id),
            "weather": self._optional(api.get_activity_weather, activity_id),
        }
        output = self._activity_path(activity_id) / "garmin.json"
        output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str), "utf-8")
        output.chmod(0o600)
        return bundle

    def download_fit(self, activity_id: int) -> Path:
        destination = self._activity_path(activity_id)
        payload = self._api().download_activity(
            activity_id,
            dl_fmt=ActivityDownloadFormat.ORIGINAL,
        )
        if payload[:2] == b"PK":
            archive_path = destination / "activity.zip"
            archive_path.write_bytes(payload)
            archive_path.chmod(0o600)
            with zipfile.ZipFile(archive_path) as archive:
                fit_members = [
                    member
                    for member in archive.infolist()
                    if not member.is_dir() and Path(member.filename).suffix.lower() == ".fit"
                ]
                if not fit_members:
                    raise GarminError("Garmin original download did not contain a FIT file")
                fit_path = destination / "activity.fit"
                fit_path.write_bytes(archive.read(fit_members[0]))
        else:
            fit_path = destination / "activity.fit"
            fit_path.write_bytes(payload)
        fit_path.chmod(0o600)
        return fit_path

    def download_and_parse_fit(
        self, activity_id: int, *, include_records: bool = False
    ) -> dict[str, Any]:
        fit_path = self.download_fit(activity_id)
        decoded_path = fit_path.with_name("fit-decoded.json")
        decoded = self.fit_parser.write_decoded_json(fit_path, decoded_path)
        if include_records:
            return decoded
        return self.fit_parser.parse(fit_path, include_records=False)

    def login_interactive(self, email: str, password: str, prompt_mfa: Any) -> None:
        self.settings.garmin_token_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        api = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
        api.login(str(self.settings.garmin_token_dir))
        self._client = api

    def _api(self) -> Garmin:
        with self._lock:
            if self._client is None:
                try:
                    client = Garmin()
                    client.login(str(self.settings.garmin_token_dir))
                    self._client = client
                except Exception as error:
                    raise GarminError(
                        "Garmin is not connected. Run `docker compose run --rm izchu "
                        "izchu garmin-login` first."
                    ) from error
            return self._client

    def _activity_path(self, activity_id: int) -> Path:
        destination = self.settings.activity_dir / f"garmin-{activity_id}"
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        return destination

    @staticmethod
    def _optional(method: Any, activity_id: int) -> Any:
        try:
            return method(activity_id)
        except Exception as error:
            return {"available": False, "reason": str(error)}

