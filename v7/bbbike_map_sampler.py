"""
BBBike/OSM map sampling utilities for simulation task generation.

Supported inputs:
  - planet_*.osm.csv.xz: lightweight TSV export (legacy fallback)
  - planet_*.osm.xz: full OSM XML with node coordinates and way tags

For full OSM files we build task candidates from real road ways and classify each
sampled point into simulation road domains (Highway / Rural / Urban) using
highway=* tags.
"""

from __future__ import annotations

import csv
import lzma
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


_BBOX_RE = re.compile(
    r"planet_(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\.osm(?:\.csv)?\.xz$"
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
            "planet_<lon_min>,<lat_min>_<lon_max>,<lat_max>.osm(.csv).xz"
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


def _parse_bbox_from_osm_bounds(path: str) -> Tuple[float, float, float, float]:
    """
    Read bbox from <bounds .../> in full OSM XML.
    """
    with lzma.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for _, elem in ET.iterparse(fh, events=("start",)):
            if elem.tag == "bounds":
                lat_min = float(elem.attrib["minlat"])
                lon_min = float(elem.attrib["minlon"])
                lat_max = float(elem.attrib["maxlat"])
                lon_max = float(elem.attrib["maxlon"])
                return lon_min, lat_min, lon_max, lat_max
    raise ValueError("Could not locate <bounds> in OSM file.")


def _highway_to_domain(highway_value: str) -> str:
    """
    Collapse OSM highway classes into the simulation's 3-level road domain.
    """
    key = highway_value.split(";", 1)[0].strip().lower()

    if key in {
        "motorway",
        "motorway_link",
        "trunk",
        "trunk_link",
        "primary",
        "primary_link",
    }:
        return "Highway"

    if key in {
        "residential",
        "living_street",
        "service",
        "pedestrian",
        "road",
    }:
        return "Urban"

    return "Rural"


def _read_way_point_pool_from_osm_xz(
    path: str,
    max_way_points: int = 500_000,
) -> List[Tuple[float, float, str]]:
    """
    Parse full OSM XML and return (lat, lon, domain) points from way mid-nodes.
    """
    node_latlon: Dict[int, Tuple[float, float]] = {}
    pool: List[Tuple[float, float, str]] = []

    with lzma.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag == "node":
                node_id = elem.attrib.get("id")
                lat = elem.attrib.get("lat")
                lon = elem.attrib.get("lon")
                if node_id and lat and lon:
                    try:
                        node_latlon[int(node_id)] = (float(lat), float(lon))
                    except ValueError:
                        pass
                elem.clear()
                continue

            if elem.tag == "way":
                highway_val: Optional[str] = None
                refs: List[int] = []
                for child in elem:
                    if child.tag == "tag" and child.attrib.get("k") == "highway":
                        highway_val = child.attrib.get("v")
                    elif child.tag == "nd":
                        ref = child.attrib.get("ref")
                        if ref:
                            try:
                                refs.append(int(ref))
                            except ValueError:
                                pass

                if highway_val and refs:
                    # Try midpoint first, then nearest neighbor around midpoint.
                    mid = len(refs) // 2
                    latlon = None
                    for idx in range(mid, len(refs)):
                        latlon = node_latlon.get(refs[idx])
                        if latlon is not None:
                            break
                    if latlon is None:
                        for idx in range(mid - 1, -1, -1):
                            latlon = node_latlon.get(refs[idx])
                            if latlon is not None:
                                break

                    if latlon is not None:
                        lat, lon = latlon
                        pool.append((lat, lon, _highway_to_domain(highway_val)))
                        if len(pool) >= max_way_points:
                            elem.clear()
                            break

                elem.clear()

    if not pool:
        raise ValueError("No drivable way points with highway tags found in OSM file.")
    return pool


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


def build_local_task_pool_with_domain_from_bbbike(
    xz_path: str,
    pool_size: int = 20_000,
) -> List[Tuple[float, float, Optional[str]]]:
    """
    Return local (x, y, road_domain?) points.

    - For full .osm.xz files: road_domain is map-derived from way highway tags.
    - For legacy .osm.csv.xz files: road_domain is None (caller can sample by
      configured weights).
    """
    if pool_size < 1:
        raise ValueError("pool_size must be >= 1")

    xz_name = Path(xz_path).name.lower()
    is_full_osm = xz_name.endswith(".osm.xz") and not xz_name.endswith(".osm.csv.xz")

    if is_full_osm:
        cache_path = Path(xz_path).with_name(f"{Path(xz_path).name}.pool_{pool_size}.csv")
        if cache_path.exists():
            cached: List[Tuple[float, float, Optional[str]]] = []
            with open(cache_path, "r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                for row in reader:
                    if len(row) != 3:
                        continue
                    try:
                        cached.append((float(row[0]), float(row[1]), row[2] or None))
                    except ValueError:
                        continue
            if cached:
                return cached

        try:
            bbox = parse_bbox_from_filename(xz_path)
        except ValueError:
            bbox = _parse_bbox_from_osm_bounds(xz_path)

        way_points = _read_way_point_pool_from_osm_xz(
            xz_path,
            max_way_points=max(pool_size * 8, 100_000),
        )
        step = max(1, len(way_points) // pool_size)
        picked = way_points[::step][:pool_size]
        if not picked:
            picked = way_points[: min(len(way_points), pool_size)]

        lon_min, lat_min, lon_max, lat_max = bbox
        origin_lat = (lat_min + lat_max) / 2.0
        origin_lon = (lon_min + lon_max) / 2.0

        out: List[Tuple[float, float, Optional[str]]] = []
        for lat, lon, domain in picked:
            x, y = latlon_to_local_xy_km(lat, lon, origin_lat=origin_lat, origin_lon=origin_lon)
            out.append((x, y, domain))

        # Cache the projected pool to make subsequent runs fast.
        with open(cache_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerows((x, y, domain or "") for x, y, domain in out)
        return out

    xy = build_local_task_pool_from_bbbike(xz_path, pool_size=pool_size)
    return [(x, y, None) for x, y in xy]


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
