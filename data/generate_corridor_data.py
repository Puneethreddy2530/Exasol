"""
ExaCommand — South Chennai flood-corridor data generator (MVP / Day-1 placeholder)

WHAT THIS IS:
  Real, verified anchor points (locality centroids, Velachery Lake, Pallikaranai
  marsh — the documented 2015-flood epicenter) with a SIMPLIFIED SYNTHETIC road
  network, flood-zone polygons, facilities, and assets built around them.

WHAT THIS IS NOT:
  Real OSM road geometry or the real opencity.in flood-hazard-zone dataset.
  This exists so the SQL, the solver, and the app can be built and tested
  TODAY, in parallel with the Day-1 spike of pulling the real OSM extract and
  the real flood-hazard polygons and dropping them in with the same schema.

Coordinate source: Wikipedia infobox coordinates for each locality (verified
16 Aug 2026). Format is WKT, SRID 4326, POINT/LINESTRING/POLYGON as (lon lat).
"""

import csv
import math
import random
from pathlib import Path

random.seed(42)

OUT = Path(__file__).resolve().parent  # writes CSVs alongside this script,
# i.e. into data/ — works regardless of where the repo is cloned

# ---------------------------------------------------------------------------
# Real, verified locality anchors (lat, lon) — South Chennai flood corridor
# ---------------------------------------------------------------------------
LOCALITIES = {
    "Velachery":    (12.9758, 80.2205),
    "Pallikaranai": (12.9349, 80.2137),
    "Adyar":        (13.0063, 80.2574),
    "Guindy":       (13.0102, 80.2157),
    "Saidapet":     (13.0213, 80.2231),
}

# Velachery Lake and the Pallikaranai marsh are the two documented low-lying
# sinks that drove the 2015 flooding in this corridor.
VELACHERY_LAKE = (12.988, 80.213)
PALLIKARANAI_MARSH = (12.9349, 80.2137)


def pt_wkt(lat, lon):
    return f"POINT({lon:.6f} {lat:.6f})"


def jitter(lat, lon, scale=0.006):
    return lat + random.uniform(-scale, scale), lon + random.uniform(-scale, scale)


def circle_polygon_wkt(center_lat, center_lon, radius_deg, n=12):
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        lat = center_lat + radius_deg * math.cos(ang)
        lon = center_lon + radius_deg * math.sin(ang) / math.cos(math.radians(center_lat))
        pts.append((lon, lat))
    pts.append(pts[0])
    coord_str = ", ".join(f"{lon:.6f} {lat:.6f}" for lon, lat in pts)
    return f"POLYGON(({coord_str}))"


# ---------------------------------------------------------------------------
# 1. POPULATION ZONES — sub-zones per locality, population budget loosely
#    anchored on published locality totals (Velachery ~144k, Pallikaranai
#    ~43k; split across sub-zones so the allocation problem has real texture)
# ---------------------------------------------------------------------------
ZONE_POP_BUDGET = {
    "Velachery": 144000,
    "Pallikaranai": 43000,
    "Adyar": 95000,
    "Guindy": 60000,
    "Saidapet": 55000,
}
SUBZONES_PER_LOCALITY = 4

zones = []
zone_id = 1
for name, (lat, lon) in LOCALITIES.items():
    budget = ZONE_POP_BUDGET[name]
    weights = [random.uniform(0.6, 1.4) for _ in range(SUBZONES_PER_LOCALITY)]
    total_w = sum(weights)
    for i, w in enumerate(weights):
        zlat, zlon = jitter(lat, lon, scale=0.008)
        pop = int(budget * w / total_w)
        zones.append({
            "zone_id": f"Z{zone_id:03d}",
            "locality": name,
            "name": f"{name} Sub-zone {i+1}",
            "population": pop,
            "priority_children_elderly_pct": round(random.uniform(0.12, 0.28), 2),
            "geo_wkt": pt_wkt(zlat, zlon),
        })
        zone_id += 1

# ---------------------------------------------------------------------------
# 2. FLOOD ZONES — polygons anchored on the two documented low-lying sinks
# ---------------------------------------------------------------------------
flood_zones = [
    {
        "flood_id": "F001",
        "name": "Velachery Lake overflow zone",
        "severity": "severe",
        "geo_wkt": circle_polygon_wkt(*VELACHERY_LAKE, radius_deg=0.012),
    },
    {
        "flood_id": "F002",
        "name": "Pallikaranai marsh overflow zone",
        "severity": "severe",
        "geo_wkt": circle_polygon_wkt(*PALLIKARANAI_MARSH, radius_deg=0.015),
    },
    {
        "flood_id": "F003",
        "name": "Saidapet riverbank zone (Adyar river)",
        "severity": "moderate",
        "geo_wkt": circle_polygon_wkt(13.0213, 80.2231, radius_deg=0.007),
    },
]

# ---------------------------------------------------------------------------
# 3. ROADS — simplified synthetic corridor network connecting the five
#    localities plus the two flood sinks (replace with real OSM extract)
# ---------------------------------------------------------------------------
road_specs = [
    ("R001", "Velachery Main Road",        "Velachery",    "Guindy"),
    ("R002", "100 Feet Road",              "Velachery",    "Adyar"),
    ("R003", "Velachery-Pallikaranai Link", "Velachery",   "Pallikaranai"),
    ("R004", "Pallikaranai-Perungudi Link", "Pallikaranai", "Adyar"),
    ("R005", "Guindy-Saidapet Road",       "Guindy",       "Saidapet"),
    ("R006", "Saidapet Bridge (Adyar river)", "Saidapet",  "Adyar"),
    # Saidapet's only two links are R005 and R006 -> it's a real bottleneck:
    # block the bridge (R006) and Saidapet-bound ambulances detour via
    # Guindy -> Velachery -> Adyar instead of a direct crossing. No
    # duplicate/parallel edges between any pair of localities -- each
    # blockable road actually matters to at least one route.
]

roads = []
for rid, name, a, b in road_specs:
    (lat1, lon1), (lat2, lon2) = LOCALITIES[a], LOCALITIES[b]
    roads.append({
        "road_id": rid,
        "name": name,
        "from_locality": a,
        "to_locality": b,
        "geo_wkt": f"LINESTRING({lon1:.6f} {lat1:.6f}, {lon2:.6f} {lat2:.6f})",
    })

# ---------------------------------------------------------------------------
# 4. FACILITIES — hospitals/shelters, generic labels (swap for real OSM POI
#    tags — amenity=hospital / amenity=shelter — during the Day-1 spike)
# ---------------------------------------------------------------------------
facilities = []
fid = 1
for name, (lat, lon) in LOCALITIES.items():
    for ftype, cap in [("hospital", random.randint(80, 220)), ("shelter", random.randint(200, 600))]:
        flat, flon = jitter(lat, lon, scale=0.004)
        facilities.append({
            "facility_id": f"FC{fid:03d}",
            "name": f"{name} {ftype.capitalize()}",
            "type": ftype,
            "capacity": cap,
            "geo_wkt": pt_wkt(flat, flon),
        })
        fid += 1

# ---------------------------------------------------------------------------
# 5. ASSETS — ambulances and boats, staged near a subset of localities
# ---------------------------------------------------------------------------
assets = []
aid = 1
asset_plan = [
    ("ambulance", "Velachery", 6), ("ambulance", "Guindy", 5), ("ambulance", "Saidapet", 2),
    # Saidapet is deliberately under-resourced relative to its own population
    # (55k) -- realistic (not every locality gets to be self-sufficient in a
    # disaster), and it's what makes blocking Saidapet's connecting roads
    # (R005, R006) an actual coverage trade-off in the demo's default
    # scenario, not just in a specially constructed stress test.
    ("boat", "Pallikaranai", 8), ("boat", "Velachery", 7),
]
for atype, base, count in asset_plan:
    lat, lon = LOCALITIES[base]
    for _ in range(count):
        alat, alon = jitter(lat, lon, scale=0.003)
        assets.append({
            "asset_id": f"A{aid:03d}",
            "type": atype,
            "base_locality": base,
            "geo_wkt": pt_wkt(alat, alon),
            "status": "available",
        })
        aid += 1


def write_csv(rows, filename):
    if not rows:
        return
    path = f"{OUT}/{filename}"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows):4d} rows -> {path}")


if __name__ == "__main__":
    write_csv(zones, "zones.csv")
    write_csv(flood_zones, "flood_zones.csv")
    write_csv(roads, "roads.csv")
    write_csv(facilities, "facilities.csv")
    write_csv(assets, "assets.csv")

    total_pop = sum(z["population"] for z in zones)
    print(f"\nTotal modeled population across corridor: {total_pop:,}")
    print(f"Ambulances: {sum(1 for a in assets if a['type']=='ambulance')}, "
          f"Boats: {sum(1 for a in assets if a['type']=='boat')}")
