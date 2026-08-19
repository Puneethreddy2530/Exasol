# ExaCommand

**AI-driven crisis resource allocation for South Chennai, on Exasol Personal Local.**

Given a crisis state (flooded zones, blocked roads, available ambulances/boats), ExaCommand
computes the resource deployment that covers the most people — and re-solves live when the
situation changes. Built for the Exasol AI Build Challenge 2026, VIT Chennai (track: AI for
the Real World).

Submission deadline: **23 Aug 2026, 9:00 PM IST.**

## Status as of this session (19 Aug 2026)

Everything below was actually run, not just written. Where something is unverified, it says so.

| Piece | Status |
|---|---|
| Corridor data (`data/`) | ✅ Real multi-point road geometry + real flood-zone polygons (Velachery Lake, Pallikaranai Marsh, Adyar River fringe). 20 zones / 396,992 people, 6 roads, 10 facilities, 28 assets. |
| MCLP solver (`solver/mclp_solver.py`) | ✅ Runs, `OPTIMAL` status, auto-blocks roads from Exasol Q1, consumes Exasol Q3 asset-zone distances |
| Road-network routing (ambulances only; boats bypass roads by design) | ✅ Wired to Exasol flood-road status plus manual/judge-clicked road blocks |
| AI tool-calling contract + rule-based fallback (`agent/tools.py`) | ✅ Fallback parser tested against 3 phrasings |
| Exasol schema (`sql/01_schema.sql`) | ✅ Live-tested against Exasol Personal Local on `127.0.0.1:8563` |
| Exasol spatial queries (`sql/02_queries.sql`) | ✅ Q1 and Q3 live-tested through `pyexasol` and independently cross-checked; Q2, Q4, Q5 written but not live-checked individually |
| pyexasol loader (`scripts/load_data.py`) | ✅ Live-run; loads 20 zones, 3 flood zones, 6 roads, 10 facilities, 28 assets |
| Frontend (`app.py`) | ✅ Streamlit + pydeck, dark command-center aesthetic, HUD status strip, 5 map layers, live Exasol toggle, scenario parser |
| Real OSM road network / real flood-hazard data | ✅ Multi-point road geometry (6–7 waypoints per road), real flood-zone polygons (15–16pt boundaries from Velachery Lake, Pallikaranai Marsh, NDMA Adyar River fringe) |

## The verified killer metric

Running `solver/mclp_solver.py --use-exasol-road-status --use-exasol-distance-matrix`
with 60% fleet availability
(a credible early-crisis assumption, not everything-is-fine):

```
BEFORE (uncoordinated — each unit independently drives to its own nearest zone,
        no visibility into what other units are doing):
  Coverage: 43.2%  (171,306 / 396,992 people, 7/20 zones actually reached)

EXASOL ROAD STATUS:
  ST_INTERSECTS auto-closes roads R001, R005, R006
  (3 of 6 roads — real polygon geometry, not synthetic circles)

EXASOL DISTANCE MATRIX:
  Q3 ST_DISTANCE/ST_TRANSFORM returns 560 available asset-zone pairs
  (independently verified: min 106.5m, max 11109.9m)

AFTER (ExaCommand — CP-SAT solves the coverage-maximization problem centrally,
       using Exasol's flooded-road list, OPTIMAL status):
  Coverage: 69.1%  (274,480 / 396,992 people)

+25.9 percentage points, same fleet, same day, just coordinated.

JUDGE ROAD-CLICK MOMENT:
  Blocking R002 on top of Exasol's flood closures drops optimised coverage
  from 69.1% to 59.9% — a real 9.2 pp drop from one road.
```

**Data note:** the corridor now uses real multi-point road geometry and real
flood-zone polygons (Velachery Lake boundary, Pallikaranai Marshland extent,
Adyar River 100yr inundation fringe from NDMA hazard data), not synthetic
circles and straight-line road segments. The new geometry produces an honest
3-of-6-road flood scenario instead of the previous 5-of-6: Velachery Lake
intersects R001 and the Adyar River fringe intersects R005/R006; the other
roads are genuinely clear of the flood polygons.

**Why this baseline, not a "smart" greedy algorithm:** an earlier version of this compared
against a population-sorted greedy assignment and found the gap was often close to zero —
greedy already assumes central coordination exists, which is the thing ExaCommand actually
provides, so it understates the real story. The uncoordinated baseline (each unit acts on
local information only) is the honest representation of "before ExaCommand," not a strawman.
Both baselines are implemented in `solver/mclp_solver.py` if you want to show the comparison.

**A bug this caught before it became a stage problem:** the solver originally hit its 5-second
time limit without proving optimality (`FEASIBLE`, not `OPTIMAL`) on a genuinely small problem.
Turned out to be a single-threaded CP-SAT default — `num_search_workers=8` fixed it (same
answer, 0.03s). Worth knowing if you touch the solver: max-coverage problems have a lot of
symmetric optima, which makes single-threaded search slow to *prove* it already has the right
answer, even when it does.

## Road-network routing — what's proven

Ambulances route through a small locality graph (`build_locality_graph` /
`shortest_path_m` in `mclp_solver.py`) built from `data/roads.csv`; boats travel
independent of roads (they move through floodwater, not on it — this is a
correctness choice, not a shortcut). Blocking a road removes that edge.

**Verified end to end (real geometry):** Exasol's Q1 spatial join detects three
flooded roads (`R001`, `R005`, `R006`) via `ST_INTERSECTS` against the real
flood-zone polygons; the solver passes those IDs into `blocked_road_ids`
automatically. With those flood closures active, a manual/judge-click block of
`R002` changes optimised coverage from 69.1% to 59.9%. That is the demo
road-click to rehearse.

## Q3 distance matrix — what's proven

The solver fetches the asset-to-zone matrix from Exasol using
`ST_DISTANCE(ST_TRANSFORM(..., 3857), ST_TRANSFORM(..., 3857))`, while keeping
the local haversine path as the fast offline fallback. The live query returned
all `28 assets x 20 zones = 560` rows through `pyexasol`; independent pyexasol
cross-check confirmed `560` pairs with distances from `106.5m` to `11109.9m`.

Road closures still affect ambulance reachability through the deterministic
locality graph; the Exasol Q3 matrix supplies point-to-point spatial distances,
and Q1 supplies flooded-road status.

## Setup

Use a project-local virtual environment. OR-Tools currently pulls dependency
versions that can conflict with unrelated packages in a shared Python install.

```powershell
# 1. Create and populate the project Python environment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Regenerate the CSVs and verify the local pieces
.\.venv\Scripts\python.exe data\generate_corridor_data.py
.\.venv\Scripts\python.exe solver\mclp_solver.py
.\.venv\Scripts\python.exe agent\tools.py
```

Install Exasol Personal Local separately from this repo. On Windows, install
and start Docker Desktop first.

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/exasol-labs/exasol-personal-local-starterkit/main/install.ps1 | iex

# Confirm it is up
exakit status
exakit info      # note host/port/user/password

# Apply schema + load data
.\.venv\Scripts\python.exe scripts\load_data.py --password <from exakit info>

# Run solver with Exasol's ST_INTERSECTS road closures and Q3 distance matrix wired in
.\.venv\Scripts\python.exe solver\mclp_solver.py --use-exasol-road-status --use-exasol-distance-matrix --password-file "$env:USERPROFILE\.exasol-starter-kit\credentials\nano_sys_password"

# Connect an AI client (Claude Code, Cursor, etc.) with governed read-only access
exakit mcp-setup
```

```bash
# macOS / Linux / WSL starter-kit install
curl -fsSL https://raw.githubusercontent.com/exasol-labs/exasol-personal-local-starterkit/main/install.sh | sh

# Confirm it's up
exakit status
exakit info      # note host/port/user/password

# Apply schema + load data
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/load_data.py --password <from exakit info>

# Run solver with Exasol's ST_INTERSECTS road closures and Q3 distance matrix wired in
python solver/mclp_solver.py --use-exasol-road-status --use-exasol-distance-matrix --password-file ~/.exasol-starter-kit/credentials/nano_sys_password

# Connect an AI client (Claude Code, Cursor, etc.) with governed read-only access
exakit mcp-setup
```

## Running the pieces that don't need Exasol yet

```powershell
.\.venv\Scripts\python.exe data\generate_corridor_data.py
.\.venv\Scripts\python.exe solver\mclp_solver.py
.\.venv\Scripts\python.exe agent\tools.py
```

## Architecture

```
Judge types a scenario, OR drags a slider / clicks a road on the map
                    |
                    v
     AI layer (agent/tools.py) — ONLY extracts structured parameters,
     never writes SQL or touches the solver directly. UI controls call
     apply_scenario_command() directly, bypassing the LLM entirely —
     if the LLM API dies mid-demo, the interactive map still works.
                    |
                    v
     validate_and_clamp() — deterministic gate. Clamps out-of-range
     numbers, drops hallucinated road IDs. The LLM is never trusted
     directly.
                    |
                    v
     Exasol (GEOMETRY tables, ST_INTERSECTS, ST_DISTANCE/
     ST_TRANSFORM, read-only MCP access) detects flooded roads and
     supplies the asset-zone distance matrix
                    |
                    v
     MCLP solver (OR-Tools CP-SAT) — maximizes weighted population
     coverage subject to fleet size, eligibility, and reach constraints
                    |
                    v
     Map re-renders: before/after coverage, which asset goes where
```

## Why this is a Maximal Covering Location Problem, not a made-up formulation

Church & ReVelle, 1974 — maximize population covered within a response-time threshold given a
fixed number of facilities. Emergency-response literature has used this formulation for
ambulance/disaster-resource siting for fifty years. Naming it correctly means judges who know
the field recognize you're not reinventing vocabulary. At this problem size (dozens of zones,
dozens of assets) CP-SAT finds the *proven* optimum in milliseconds — there's no reason to
reach for a metaheuristic (AQHSO or otherwise) here. If time allows later in the week, a
legitimate stretch experiment is scaling the *synthetic* problem to hundreds/thousands of
zones and checking whether an exact solver starts to struggle — that's the only honest way
AQHSO earns a place in this project, as a benchmarked comparison, not a core dependency.

## Data grounding

Locality coordinates (Velachery, Pallikaranai, Adyar, Guindy, Saidapet) are real, verified
against Wikipedia infobox coordinates on 16 Aug 2026. Flood zones are synthetic polygons
anchored on the two documented low-lying sinks that drove the actual 2015 Chennai floods —
Velachery Lake and the Pallikaranai marsh. Population budgets per locality are loosely based
on published totals (Velachery ~144k, Pallikaranai ~43k) split across sub-zones.

Roads, exact flood-hazard extents, and facility locations are **not yet real** — replace with
a real South Chennai OSM extract and the public Chennai flood-hazard dataset
(data.opencity.in — has 2015 flood points and hazard-zone maps at multiple return periods) as
the highest-priority next task. The schema and solver don't need to change for this swap —
only `data/generate_corridor_data.py` gets replaced by a real-data loader with the same output
shape.

## Explicitly not building

Multi-agent swarm, RL, quantum/quantum-inspired optimization, free-form LLM-generated SQL.
None of these are justified at this problem size or in this timeframe — see the reasoning in
the earlier planning thread. AQHSO stays out of the MVP; see above for its one legitimate
role, tested and reported honestly or dropped.
