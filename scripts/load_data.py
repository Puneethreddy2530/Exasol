"""
ExaCommand — load the corridor CSVs into Exasol Personal Local.

Prereqs (do this once, on your machine, not in a sandbox):
    1. Install the starter kit:
       curl -fsSL https://raw.githubusercontent.com/exasol-labs/exasol-personal-local-starterkit/main/install.sh | sh
    2. exakit status        # confirm the DB is up
    3. exakit info           # get host/port/user/password
    4. pip install pyexasol  # already bundled by the starter kit's own venv,
                              # but if you're running this from elsewhere:
                              # pip install pyexasol --break-system-packages

Usage:
    python3 scripts/load_data.py --dsn 127.0.0.1:8563 --user sys --password <from exakit info>

This intentionally does NOT use exapump's generic CSV loader, even though
it's faster to type — exapump's implicit type casting for GEOMETRY columns
is untested by us as of this writing. Explicit INSERTs with WKT literals are
exactly the pattern Exasol's own geospatial docs show (INSERT INTO t1 VALUES
(1, 'POINT (...)')), so this script is slower but verified-correct.
"""

import argparse
import csv
import ssl
from pathlib import Path

import pyexasol

ROOT = Path(__file__).resolve().parent.parent  # works regardless of cwd
SCHEMA_SQL = (ROOT / "sql" / "01_schema.sql").read_text()


def load_csv(conn, table, csv_path, columns):
    """columns: list of (csv_field, sql_column, kind) where kind is
    'geo' (wrap the WKT string as a GEOMETRY literal), 'num', or 'str'."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    col_names = ", ".join(sql_col for _, sql_col, _ in columns)
    placeholders = ", ".join("?" for _ in columns)
    stmt = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

    params = []
    for row in rows:
        values = []
        for csv_field, _, kind in columns:
            v = row[csv_field]
            if kind == "num":
                v = float(v)
            values.append(v)  # WKT strings pass through as-is; Exasol casts
            # VARCHAR literals to GEOMETRY implicitly on INSERT, per
            # docs.exasol.com/db/latest/sql_references/geospatialdata
        params.append(values)

    conn.execute(f"TRUNCATE TABLE {table}")
    conn.ext.insert_multi(table, params, columns=[c for _, c, _ in columns])
    print(f"loaded {len(params)} rows into {table}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="127.0.0.1:8563")
    ap.add_argument("--user", default="sys")
    ap.add_argument("--password", required=True)
    ap.add_argument("--schema", default="EXACOMMAND")
    ap.add_argument(
        "--validate-cert",
        action="store_true",
        help="Require normal TLS certificate validation. Leave off for the local starter-kit self-signed cert.",
    )
    args = ap.parse_args()

    websocket_sslopt = None if args.validate_cert else {"cert_reqs": ssl.CERT_NONE}
    conn = pyexasol.connect(
        dsn=args.dsn,
        user=args.user,
        password=args.password,
        websocket_sslopt=websocket_sslopt,
    )

    print("Applying schema (sql/01_schema.sql)...")
    for stmt in SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)

    conn.execute(f"OPEN SCHEMA {args.schema}")

    load_csv(conn, "ZONES", str(ROOT / "data" / "zones.csv"), [
        ("zone_id", "ZONE_ID", "str"), ("locality", "LOCALITY", "str"),
        ("name", "NAME", "str"), ("population", "POPULATION", "num"),
        ("priority_children_elderly_pct", "PRIORITY_CHILDREN_ELDERLY_PCT", "num"),
        ("geo_wkt", "GEO", "geo"),
    ])
    load_csv(conn, "FLOOD_ZONES", str(ROOT / "data" / "flood_zones.csv"), [
        ("flood_id", "FLOOD_ID", "str"), ("name", "NAME", "str"),
        ("severity", "SEVERITY", "str"), ("geo_wkt", "GEO", "geo"),
    ])
    load_csv(conn, "ROADS", str(ROOT / "data" / "roads.csv"), [
        ("road_id", "ROAD_ID", "str"), ("name", "NAME", "str"),
        ("from_locality", "FROM_LOCALITY", "str"), ("to_locality", "TO_LOCALITY", "str"),
        ("geo_wkt", "GEO", "geo"),
    ])
    load_csv(conn, "FACILITIES", str(ROOT / "data" / "facilities.csv"), [
        ("facility_id", "FACILITY_ID", "str"), ("name", "NAME", "str"),
        ("type", "TYPE", "str"), ("capacity", "CAPACITY", "num"), ("geo_wkt", "GEO", "geo"),
    ])
    load_csv(conn, "ASSETS", str(ROOT / "data" / "assets.csv"), [
        ("asset_id", "ASSET_ID", "str"), ("type", "TYPE", "str"),
        ("base_locality", "BASE_LOCALITY", "str"), ("geo_wkt", "GEO", "geo"),
        ("status", "STATUS", "str"),
    ])

    print("\nSanity check — running Q1 (roads intersecting flood zones) live:")
    sanity_q1 = """
        SELECT r.ROAD_ID, r.NAME, f.NAME AS FLOODED_BY, f.SEVERITY
        FROM ROADS r
        JOIN FLOOD_ZONES f
          ON ST_INTERSECTS(r.GEO, f.GEO)
    """
    result = conn.execute(sanity_q1)
    for row in result:
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
