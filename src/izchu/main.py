import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from . import __version__
from .config import get_settings
from .fit import FitError
from .garmin import GarminClient, GarminError
from .strava import StravaClient, StravaError

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
strava = StravaClient(settings)
garmin = GarminClient(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await strava.http.aclose()


app = FastAPI(
    title="izchu",
    description="Private read-only Strava and Garmin activity service",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "izchu",
        "version": __version__,
        "docs": "/docs",
        "strava": strava.status(),
        "garmin": garmin.status(),
    }


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/strava/connect")
async def strava_connect() -> RedirectResponse:
    try:
        return RedirectResponse(strava.authorization_url(), status_code=302)
    except StravaError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/strava/callback")
async def strava_callback(code: str, state: str) -> dict[str, Any]:
    try:
        return await strava.exchange_code(code, state)
    except StravaError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/strava/athlete")
async def strava_athlete() -> dict[str, Any]:
    return await _strava_call(strava.athlete())


@app.get("/api/strava/activities")
async def strava_activities(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    before: int | None = None,
    after: int | None = None,
) -> list[dict[str, Any]]:
    return await _strava_call(
        strava.activities(page=page, per_page=per_page, before=before, after=after)
    )


@app.get("/api/strava/activities/{activity_id}")
async def strava_activity(activity_id: int) -> dict[str, Any]:
    return await _strava_call(strava.activity(activity_id))


@app.get("/api/strava/activities/{activity_id}/streams")
async def strava_streams(activity_id: int) -> dict[str, Any]:
    return await _strava_call(strava.streams(activity_id))


@app.get("/api/garmin/activities")
async def garmin_activities(
    start: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    activity_type: str | None = None,
) -> list[dict[str, Any]]:
    return await _garmin_call(
        garmin.activities, start=start, limit=limit, activity_type=activity_type
    )


@app.get("/api/garmin/activities/{activity_id}")
async def garmin_activity(activity_id: int) -> dict[str, Any]:
    return await _garmin_call(garmin.activity, activity_id)


@app.post("/api/garmin/activities/{activity_id}/fit")
async def garmin_fit(
    activity_id: int,
    include_records: bool = False,
) -> dict[str, Any]:
    return await _garmin_call(
        garmin.download_and_parse_fit,
        activity_id,
        include_records=include_records,
    )


async def _strava_call(operation: Any) -> Any:
    try:
        return await operation
    except StravaError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


async def _garmin_call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except (GarminError, FitError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

