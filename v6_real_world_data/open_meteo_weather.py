"""
Open-Meteo integration: 7-day archive + 7-day forecast as one hourly series.

Uses the official openmeteo-requests client.
Focused variables: daylight length, sunshine, precipitation (rain/showers/snow),
visibility, cloud layers, plus temperature for context.

Default coordinates: Stuttgart metro / Sindelfingen area (Mercedes-Benz plant region).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

# ── Default location: Stuttgart region (Sindelfingen / plant area proxy) ──
DEFAULT_LATITUDE = 48.7036
DEFAULT_LONGITUDE = 9.0321

# API variable order must match unpacking below (hourly then daily).
_HOURLY_PARAMS: List[str] = [
    "temperature_2m",
    "rain",
    "showers",
    "snowfall",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "is_day",
    "sunshine_duration",
]

_DAILY_PARAMS: List[str] = [
    "daylight_duration",
    "uv_index_max",
]


def _make_client():
    """Why: cache + retries match the sample and reduce flaky API calls."""
    try:
        import openmeteo_requests
        import requests_cache
        from retry_requests import retry
    except ImportError as e:
        raise ImportError(
            "Install Open-Meteo client deps: pip install openmeteo-requests "
            "pandas requests-cache retry-requests"
        ) from e

    cache_dir = Path(__file__).resolve().parent / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(str(cache_dir), expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    return openmeteo_requests.Client(session=retry_session)


def fetch_open_meteo_combined_hourly(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    past_days: int = 7,
    forecast_days: int = 7,
    url: str = "https://api.open-meteo.com/v1/forecast",
) -> pd.DataFrame:
    """
    Fetch hourly weather for ``past_days`` + ``forecast_days`` (contiguous).

    Merges daily ``daylight_duration`` (seconds) and ``uv_index_max`` onto each
    hour by calendar date (UTC date of the hour).

    Returns
    -------
    DataFrame with columns including:
      time_utc, date_utc, temperature_2m, rain, showers, snowfall,
      cloud_cover, cloud_cover_low, cloud_cover_mid, cloud_cover_high,
      visibility, is_day, sunshine_duration,
      daylight_duration_s, uv_index_max,
      total_liquid_precip_mm (rain + showers),
      precip_water_equiv_mm (rain + showers + snowfall as mm water approx: snow * 0.1)
    """
    openmeteo = _make_client()
    params: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": _HOURLY_PARAMS,
        "daily": _DAILY_PARAMS,
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    hourly = response.Hourly()
    hourly_time = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    )
    hourly_data: Dict[str, Any] = {"time_utc": hourly_time}
    for idx, name in enumerate(_HOURLY_PARAMS):
        hourly_data[name] = hourly.Variables(idx).ValuesAsNumpy()

    hourly_df = pd.DataFrame(hourly_data)

    daily = response.Daily()
    daily_time = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left",
    )
    daily_data: Dict[str, Any] = {"date_utc": daily_time.normalize()}
    for idx, name in enumerate(_DAILY_PARAMS):
        daily_data[name] = daily.Variables(idx).ValuesAsNumpy()

    daily_df = pd.DataFrame(daily_data)
    daily_df = daily_df.rename(
        columns={"daylight_duration": "daylight_duration_s", "uv_index_max": "uv_index_max"}
    )

    # Join daily aggregates onto each hour by UTC calendar day.
    hourly_df["date_utc"] = hourly_df["time_utc"].dt.normalize()
    merged = hourly_df.merge(daily_df, on="date_utc", how="left")

    # Derived columns for analysis / routing heuristics.
    merged["total_liquid_precip_mm"] = merged["rain"].fillna(0) + merged["showers"].fillna(0)
    # Open-Meteo snowfall is in cm; rough water-equivalent ~ 1 cm ≈ 10 mm liquid (tunable).
    merged["precip_water_equiv_mm"] = (
        merged["total_liquid_precip_mm"] + merged["snowfall"].fillna(0) * 10.0
    )

    # Sunshine share of the hour (0–1) when possible.
    sec_per_hour = 3600.0
    sd = merged["sunshine_duration"].fillna(0).clip(lower=0)
    merged["sunshine_fraction_hour"] = (sd / sec_per_hour).clip(upper=1.0)

    return merged


def save_open_meteo_hourly_csv(df: pd.DataFrame, path: Union[str, Path]) -> None:
    """Persist merged hourly table (UTF-8, ISO timestamps)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")


def load_open_meteo_hourly_csv(path: Union[str, Path]) -> pd.DataFrame:
    """Load CSV written by ``save_open_meteo_hourly_csv``."""
    df = pd.read_csv(path, parse_dates=["time_utc", "date_utc"])
    return df


def map_row_to_sim_weather_lighting(row: pd.Series) -> Tuple[str, str]:
    """
    Map Open-Meteo row to simulation labels (Clear | Rain | Fog) and (Day | Dusk | Night).

    Why: the rolling model expects the same discrete keys as ``weather_score`` /
    ``lighting_score`` in config.
    """
    vis = float(row.get("visibility") or 10_000)
    liquid = float(row.get("total_liquid_precip_mm", row.get("rain", 0) + row.get("showers", 0)) or 0)
    snow_cm = float(row.get("snowfall") or 0)
    cloud = float(row.get("cloud_cover") or 0)

    # Weather: priority fog / heavy precip / snow-as-adverse.
    if vis < 2_000 or (vis < 4_000 and cloud >= 85):
        weather = "Fog"
    elif liquid > 0.2 or snow_cm > 0.05:
        weather = "Rain"
    else:
        weather = "Clear"

    # Lighting: is_day from API (0/1); approximate dusk from low sunshine fraction while "day".
    is_day = float(row.get("is_day") or 0)
    sun_frac = float(row.get("sunshine_fraction_hour", 0) or 0)
    if is_day >= 0.5:
        if sun_frac < 0.15 and cloud >= 70:
            lighting = "Dusk"
        else:
            lighting = "Day"
    else:
        lighting = "Night"

    return weather, lighting


class OpenMeteoSeriesDriver:
    """
    Period-indexed weather + lighting from a merged hourly DataFrame.

    Why: ``run_simulation`` steps t = 0 .. total_periods-1; each period uses one row.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        if df.empty:
            raise ValueError("Open-Meteo dataframe is empty.")
        self._df = df.reset_index(drop=True)

    @classmethod
    def from_csv(cls, path: Union[str, Path]) -> "OpenMeteoSeriesDriver":
        return cls(load_open_meteo_hourly_csv(path))

    def weather_at(self, period: int) -> str:
        row = self._df.iloc[period % len(self._df)]
        w, _ = map_row_to_sim_weather_lighting(row)
        return w

    def lighting_at(self, period: int) -> str:
        row = self._df.iloc[period % len(self._df)]
        _, l = map_row_to_sim_weather_lighting(row)
        return l

    def raw_row(self, period: int) -> pd.Series:
        return self._df.iloc[period % len(self._df)]

    def __len__(self) -> int:
        return len(self._df)


def fetch_save_default_stuttgart(
    out_csv: Optional[Union[str, Path]] = None,
    past_days: int = 7,
    forecast_days: int = 7,
) -> pd.DataFrame:
    """
    Convenience: download 7+7 days for default Stuttgart coordinates and save CSV.

    Default output: ``v5_real_world_data/open_meteo_stuttgart_hourly_14d.csv``
    """
    df = fetch_open_meteo_combined_hourly(
        latitude=DEFAULT_LATITUDE,
        longitude=DEFAULT_LONGITUDE,
        past_days=past_days,
        forecast_days=forecast_days,
    )
    if out_csv is None:
        out_csv = Path(__file__).resolve().parent / "open_meteo_stuttgart_hourly_14d.csv"
    save_open_meteo_hourly_csv(df, out_csv)
    return df


if __name__ == "__main__":
    df = fetch_save_default_stuttgart()
    print(df.head(3).to_string())
    print(f"\nrows={len(df)}  (expect ~{(7+7)*24})")
    print(f"columns: {list(df.columns)}")
