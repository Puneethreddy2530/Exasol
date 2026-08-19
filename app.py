"""
ExaCommand Streamlit frontend.

Run from the repo root with:
    streamlit run app.py
"""

import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.tools import rule_based_fallback, validate_and_clamp
from solver.mclp_solver import (
    combine_blocked_road_ids,
    fetch_asset_zone_distances_from_exasol,
    fetch_flooded_road_ids_from_exasol,
    load_data,
    parse_point,
    parse_polygon,
    solve_mclp,
    solve_uncoordinated_baseline,
    zone_is_flooded,
)


DEFAULT_DSN = "127.0.0.1:8563"
DEFAULT_SCHEMA = "EXACOMMAND"
DEFAULT_PASSWORD_FILE = Path.home() / ".exasol-starter-kit" / "credentials" / "nano_sys_password"
MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"


def parse_linestring(wkt):
    """Return [[lon, lat], ...] for pydeck PathLayer."""
    inner = wkt[wkt.index("(") + 1: wkt.index(")")]
    return [[float(value) for value in pair.strip().split()] for pair in inner.split(",")]


def to_lonlat(lat, lon):
    return [lon, lat]


def read_password_file(path_text):
    if not path_text:
        return None
    try:
        path = Path(path_text).expanduser()
        if not path.exists():
            return None
        return path.read_text().strip()
    except OSError:
        return None


def select_scenario_assets(assets, fleet_pct):
    keep = max(0.0, min(1.0, fleet_pct))
    ambulances = [asset for asset in assets if asset["type"] == "ambulance"]
    boats = [asset for asset in assets if asset["type"] == "boat"]
    return (
        ambulances[: max(1, int(len(ambulances) * keep))]
        + boats[: max(1, int(len(boats) * keep))]
    )


def fetch_live_exasol_inputs(dsn, user, password, schema, validate_cert=False):
    flooded_road_ids = fetch_flooded_road_ids_from_exasol(
        dsn=dsn,
        user=user,
        password=password,
        schema=schema,
        validate_cert=validate_cert,
    )
    distance_lookup = fetch_asset_zone_distances_from_exasol(
        dsn=dsn,
        user=user,
        password=password,
        schema=schema,
        validate_cert=validate_cert,
    )
    return flooded_road_ids, distance_lookup


def solve_scenario(
    zones,
    flood_zones,
    assets,
    roads,
    fleet_pct,
    prioritize,
    manual_blocked_road_ids,
    exasol_flooded_road_ids=None,
    distance_lookup=None,
):
    scenario_assets = select_scenario_assets(assets, fleet_pct)
    blocked_road_ids = combine_blocked_road_ids(exasol_flooded_road_ids, manual_blocked_road_ids)

    uncoordinated = solve_uncoordinated_baseline(
        zones,
        flood_zones,
        scenario_assets,
        roads=roads,
        blocked_road_ids=blocked_road_ids,
        distance_lookup=distance_lookup,
    )
    optimal = solve_mclp(
        zones,
        flood_zones,
        scenario_assets,
        roads=roads,
        blocked_road_ids=blocked_road_ids,
        prioritize_children_elderly=prioritize,
        distance_lookup=distance_lookup,
    )

    return {
        "scenario_assets": scenario_assets,
        "blocked_road_ids": blocked_road_ids,
        "uncoordinated": uncoordinated,
        "optimal": optimal,
    }


def build_map_rows(zones, flood_zones, assets, roads, scenario_assets, optimal, blocked_road_ids):
    flooded_zone_ids = {zone["zone_id"] for zone in zones if zone_is_flooded(zone, flood_zones)}
    covered_zone_ids = {assignment["zone_id"] for assignment in optimal["assignments"]}
    active_asset_ids = {asset["asset_id"] for asset in scenario_assets}
    asset_by_id = {asset["asset_id"]: asset for asset in assets}
    zone_by_id = {zone["zone_id"]: zone for zone in zones}
    blocked_set = set(blocked_road_ids)

    flood_rows = []
    for flood_zone in flood_zones:
        flood_rows.append({
            "label": flood_zone["name"],
            "detail": flood_zone["severity"],
            "polygon": [to_lonlat(lat, lon) for lat, lon in parse_polygon(flood_zone["geo_wkt"])],
        })

    road_rows = []
    for road in roads:
        blocked = road["road_id"] in blocked_set
        road_rows.append({
            "label": f"{road['road_id']} - {road['name']}",
            "detail": "blocked" if blocked else "passable",
            "road_id": road["road_id"],
            "path": parse_linestring(road["geo_wkt"]),
            "color": [220, 55, 55] if blocked else [80, 180, 105],
        })

    zone_rows = []
    for zone in zones:
        lat, lon = parse_point(zone["geo_wkt"])
        covered = zone["zone_id"] in covered_zone_ids
        flooded = zone["zone_id"] in flooded_zone_ids
        zone_rows.append({
            "label": f"{zone['zone_id']} - {zone['name']}",
            "detail": f"{zone['population']:,} people; {'flooded' if flooded else 'dry'}",
            "zone_id": zone["zone_id"],
            "position": to_lonlat(lat, lon),
            "radius": 70 + (zone["population"] / 3200),
            "color": [72, 178, 113, 205] if covered else [135, 135, 135, 135],
        })

    asset_rows = []
    for asset in assets:
        lat, lon = parse_point(asset["geo_wkt"])
        active = asset["asset_id"] in active_asset_ids
        is_ambulance = asset["type"] == "ambulance"
        active_color = [245, 160, 45, 230] if is_ambulance else [45, 145, 235, 230]
        asset_rows.append({
            "label": f"{asset['asset_id']} - {asset['type']}",
            "detail": "ready" if active else "not in current fleet slice",
            "asset_id": asset["asset_id"],
            "position": to_lonlat(lat, lon),
            "radius": 50 if active else 22,
            "color": active_color if active else [160, 160, 160, 85],
        })

    assignment_rows = []
    for assignment in optimal["assignments"]:
        asset = asset_by_id.get(assignment["asset_id"])
        zone = zone_by_id.get(assignment["zone_id"])
        if not asset or not zone:
            continue
        asset_lat, asset_lon = parse_point(asset["geo_wkt"])
        zone_lat, zone_lon = parse_point(zone["geo_wkt"])
        is_ambulance = asset["type"] == "ambulance"
        assignment_rows.append({
            "label": f"{asset['asset_id']} -> {zone['zone_id']}",
            "detail": f"{assignment['distance_m']:,} m",
            "source": to_lonlat(asset_lat, asset_lon),
            "target": to_lonlat(zone_lat, zone_lon),
            "color": [245, 160, 45, 210] if is_ambulance else [45, 145, 235, 210],
        })

    return {
        "floods": flood_rows,
        "roads": road_rows,
        "zones": zone_rows,
        "assets": asset_rows,
        "assignments": assignment_rows,
    }


@st.cache_data(show_spinner=False)
def cached_base_data():
    return load_data()


@st.cache_data(ttl=15, show_spinner=False)
def cached_live_exasol_inputs(dsn, user, password, schema, validate_cert):
    return fetch_live_exasol_inputs(dsn, user, password, schema, validate_cert)


def render_deck(rows):
    layers = [
        pdk.Layer(
            "PolygonLayer",
            data=rows["floods"],
            get_polygon="polygon",
            get_fill_color=[220, 45, 45, 65],
            get_line_color=[235, 85, 85, 190],
            line_width_min_pixels=2,
            pickable=True,
        ),
        pdk.Layer(
            "PathLayer",
            data=rows["roads"],
            get_path="path",
            get_color="color",
            width_min_pixels=4,
            pickable=True,
        ),
        pdk.Layer(
            "LineLayer",
            data=rows["assignments"],
            get_source_position="source",
            get_target_position="target",
            get_color="color",
            get_width=3,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=rows["zones"],
            get_position="position",
            get_radius="radius",
            get_fill_color="color",
            stroked=True,
            get_line_color=[245, 245, 245],
            line_width_min_pixels=1,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=rows["assets"],
            get_position="position",
            get_radius="radius",
            get_fill_color="color",
            pickable=True,
        ),
    ]

    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(latitude=12.99, longitude=80.225, zoom=12, pitch=30),
            map_style=MAP_STYLE,
            tooltip={
                "html": "<b>{label}</b><br/>{detail}",
                "style": {"backgroundColor": "#111827", "color": "#f9fafb"},
            },
        ),
        use_container_width=True,
    )


def apply_parsed_scenario(text):
    parsed = validate_and_clamp(rule_based_fallback(text))
    st.session_state.fleet_pct = parsed.fleet_availability_pct
    st.session_state.prioritize = parsed.prioritize_children_elderly
    st.session_state.manual_blocks = parsed.blocked_road_ids


def main():
    st.set_page_config(page_title="ExaCommand", layout="wide")

    zones, flood_zones, assets, roads = cached_base_data()
    road_options = {road["road_id"]: road["name"] for road in roads}

    st.sidebar.title("ExaCommand")
    st.sidebar.caption("Live crisis resource allocation for the South Chennai flood corridor")

    st.session_state.setdefault("fleet_pct", 0.6)
    st.session_state.setdefault("prioritize", False)
    st.session_state.setdefault("manual_blocks", [])

    scenario_text = st.sidebar.text_area(
        "Describe the scenario",
        placeholder=(
            "Only 60% of the fleet has reported ready. Prioritize children "
            "and elderly zones. 100 Feet Road is blocked."
        ),
        height=92,
    )
    if st.sidebar.button("Parse scenario", use_container_width=True):
        apply_parsed_scenario(scenario_text)
        st.rerun()

    st.sidebar.divider()
    fleet_pct = st.sidebar.slider(
        "Fleet availability",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        key="fleet_pct",
    )
    prioritize = st.sidebar.checkbox("Prioritize children and elderly zones", key="prioritize")
    manual_blocks = st.sidebar.multiselect(
        "Manually block additional roads",
        options=list(road_options.keys()),
        format_func=lambda road_id: f"{road_id} - {road_options[road_id]}",
        key="manual_blocks",
    )

    st.sidebar.divider()
    use_live_exasol = st.sidebar.checkbox(
        "Use live Exasol spatial queries",
        value=True,
        help="Fetch Q1 flooded roads and Q3 asset-zone distances from Exasol Personal Local.",
    )

    exasol_flooded_road_ids = []
    distance_lookup = None
    live_status = "Offline CSV mode"
    if use_live_exasol:
        with st.sidebar.expander("Exasol connection", expanded=False):
            dsn = st.text_input("DSN", value=DEFAULT_DSN)
            user = st.text_input("User", value="sys")
            schema = st.text_input("Schema", value=DEFAULT_SCHEMA)
            password_file = st.text_input("Password file", value=str(DEFAULT_PASSWORD_FILE))
            password_override = st.text_input("Password override", type="password")
            validate_cert = st.checkbox("Validate TLS certificate", value=False)

        password = password_override or read_password_file(password_file)
        if not password:
            st.sidebar.error("Live Exasol mode needs a password or readable password file.")
        else:
            try:
                exasol_flooded_road_ids, distance_lookup = cached_live_exasol_inputs(
                    dsn,
                    user,
                    password,
                    schema,
                    validate_cert,
                )
                live_status = (
                    f"Live Exasol: {len(exasol_flooded_road_ids)} flooded roads, "
                    f"{len(distance_lookup)} distances"
                )
            except Exception as exc:
                st.sidebar.error(f"Live Exasol query failed: {exc}")
                live_status = "Live Exasol failed; using offline distances and manual road blocks"

    result = solve_scenario(
        zones,
        flood_zones,
        assets,
        roads,
        fleet_pct=fleet_pct,
        prioritize=prioritize,
        manual_blocked_road_ids=manual_blocks,
        exasol_flooded_road_ids=exasol_flooded_road_ids,
        distance_lookup=distance_lookup,
    )
    rows = build_map_rows(
        zones,
        flood_zones,
        assets,
        roads,
        result["scenario_assets"],
        result["optimal"],
        result["blocked_road_ids"],
    )

    st.title("ExaCommand Live Deployment Plan")
    st.caption(live_status)

    before = result["uncoordinated"]
    after = result["optimal"]
    delta = after["coverage_pct"] - before["coverage_pct"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Before", f"{before['coverage_pct']}%")
    col2.metric("After", f"{after['coverage_pct']}%", delta=f"{delta:+.1f} pp")
    col3.metric("Covered People", f"{after['covered_population']:,}", f"of {after['total_population']:,}")
    col4.metric("Solver", after["status"], f"{after['solve_time_s'] * 1000:.0f} ms", delta_color="off")

    render_deck(rows)

    blocked_label = ", ".join(result["blocked_road_ids"]) or "none"
    auto_label = ", ".join(exasol_flooded_road_ids) or "none"
    st.caption(
        f"Auto-closed by Exasol Q1: {auto_label} | Effective blocked roads: {blocked_label} | "
        "green zones are covered, gray zones are uncovered, red roads are blocked."
    )

    with st.expander("Assignments"):
        st.dataframe(pd.DataFrame(after["assignments"]), use_container_width=True)


if __name__ == "__main__":
    main()
