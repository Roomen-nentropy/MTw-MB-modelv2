"""
BBBike .xz area sampler for the current simulation model.

The provided BBBike file is a compressed tab-separated stream of OSM element IDs.
It does not expose explicit lat/lon columns, but its filename encodes the bounding
box as: planet_<lon_min>,<lat_min>_<lon_max>,<lat_max>.osm.csv.xz

This module turns that into a reproducible pool of local (x, y) points in km:
  1) parse bbox from filename,
  2) read node IDs from the file,
  3) deterministically map IDs into the bbox,
  4) project lat/lon to local metric coordinates (equirectangular approximation).
"""

from __future__ import annotations

import lzma
import math
import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


_BBOX_RE = re.compile(
    r"planet_(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\.osm\.csv\.xz$"
)


def parse_bbox_from_filename(path: str) -> Tuple[float, float, float, float]:
    """
    Return (lon_min, lat_min, lon_max, lat_max) parsed from BBBike filename.
    """
    name = Path(path).name
    m = _BBOX_RE.search(name)
    if not m:
        raise ValueError(
            "Could not parse BBBike bbox from filename. Expected pattern: "
            "planet_<lon_min>,<lat_min>_<lon_max>,<lat_max>.osm.csv.xz"
        )
    lon_min, lat_min, lon_max, lat_max = map(float, m.groups())
    if lon_min >= lon_max or lat_min >= lat_max:
        raise ValueError("Invalid bbox ordering in BBBike filename.")
    return lon_min, lat_min, lon_max, lat_max


def read_node_ids_from_xz(path: str, max_lines: int = 1_500_000) -> List[int]:
    """
    Read node IDs from BBBike .xz stream.
    """
    ids: List[int] = []
    with lzma.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= max_lines:
                break
            parts = line.rstrip("\n").split("\t")
            # Typical row prefix: node\t<id>...
            if len(parts) >= 2 and parts[0] == "node":
                try:
                    ids.append(int(parts[1]))
                except ValueError:
                    continue
    if not ids:
        raise ValueError("No node IDs found in BBBike .xz file.")
    return ids


def _id_to_latlon(node_id: int, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """
    Deterministic ID -> (lat, lon) embedding inside bbox.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    # Use two independent multiplicative hashes to spread IDs across unit square.
    fx = ((node_id * 2654435761) % 2_147_483_647) / 2_147_483_647.0
    fy = ((node_id * 40503) % 2_147_483_647) / 2_147_483_647.0
    lon = lon_min + fx * (lon_max - lon_min)
    lat = lat_min + fy * (lat_max - lat_min)
    return lat, lon


def latlon_to_local_xy_km(
    lat: float,
    lon: float,
    origin_lat: float,
    origin_lon: float,
) -> Tuple[float, float]:
    """
    Convert lat/lon to local x/y in kilometers (small-area approximation).
    """
    # Earth radius approximation by degrees.
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(origin_lat))
    x = (lon - origin_lon) * km_per_deg_lon
    y = (lat - origin_lat) * km_per_deg_lat
    return x, y


def build_local_task_pool_from_bbbike(
    xz_path: str,
    pool_size: int = 20_000,
) -> List[Tuple[float, float]]:
    """
    Return reproducible local (x, y) km points sampled from BBBike file universe.
    """
    bbox = parse_bbox_from_filename(xz_path)
    node_ids = read_node_ids_from_xz(xz_path)
    if pool_size < 1:
        raise ValueError("pool_size must be >= 1")

    # Deterministic spread over full node universe.
    step = max(1, len(node_ids) // pool_size)
    picked = node_ids[::step][:pool_size]
    if not picked:
        picked = node_ids[: min(len(node_ids), pool_size)]

    # Local projection origin: bbox center.
    lon_min, lat_min, lon_max, lat_max = bbox
    origin_lat = (lat_min + lat_max) / 2.0
    origin_lon = (lon_min + lon_max) / 2.0

    xy: List[Tuple[float, float]] = []
    for nid in picked:
        lat, lon = _id_to_latlon(nid, bbox)
        x, y = latlon_to_local_xy_km(lat, lon, origin_lat=origin_lat, origin_lon=origin_lon)
        xy.append((x, y))

    return xy


def suggest_sindelfingen_depot_xy(xz_path: str) -> Tuple[float, float]:
    """
    Project Mercedes-Benz Sindelfingen plant area into local x/y km coordinates.
    """
    # Mercedes-Benz Sindelfingen reference coordinate.
    sindelfingen_lat = 48.7000
    sindelfingen_lon = 8.9900
    lon_min, lat_min, lon_max, lat_max = parse_bbox_from_filename(xz_path)
    origin_lat = (lat_min + lat_max) / 2.0
    origin_lon = (lon_min + lon_max) / 2.0
    return latlon_to_local_xy_km(
        sindelfingen_lat,
        sindelfingen_lon,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
    )
