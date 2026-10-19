import argparse
import getpass
import json
from pathlib import Path

from .config import get_settings
from .fit import FitParser
from .garmin import GarminClient
from .strava import StravaClient


def _garmin_login() -> None:
    settings = get_settings()
    email = settings.garmin_email or input("Garmin email: ").strip()
    password = settings.garmin_password or getpass.getpass("Garmin password: ")
    GarminClient(settings).login_interactive(
        email,
        password,
        prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
    )
    print(f"Garmin connected. Renewable tokens saved under {settings.garmin_token_dir}")


def _status() -> None:
    settings = get_settings()
    value = {
        "strava": StravaClient(settings).status(),
        "garmin": GarminClient(settings).status(),
    }
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _inspect_fit(path: str, include_records: bool) -> None:
    result = FitParser().parse(Path(path), include_records=include_records)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="izchu")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("garmin-login", help="Log in and save renewable Garmin tokens")
    commands.add_parser("status", help="Show connection state without exposing secrets")
    fit = commands.add_parser("inspect-fit", help="Decode a local Garmin FIT file")
    fit.add_argument("path")
    fit.add_argument("--include-records", action="store_true")
    args = parser.parse_args()

    if args.command == "garmin-login":
        _garmin_login()
    elif args.command == "status":
        _status()
    elif args.command == "inspect-fit":
        _inspect_fit(args.path, args.include_records)


if __name__ == "__main__":
    main()

