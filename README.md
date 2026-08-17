# ExaCommand

**AI-driven crisis resource allocation for South Chennai, on Exasol Personal Local.**

Given a crisis state (flooded zones, blocked roads, available ambulances/boats), ExaCommand
computes the resource deployment that covers the most people — and re-solves live when the
situation changes. Built for the Exasol AI Build Challenge 2026, VIT Chennai (track: AI for
the Real World).

Submission deadline: **23 Aug 2026, 9:00 PM IST.**

## Status as of this session (17 Aug 2026)

Everything below was actually run, not just written. Where something is unverified, it says so.

| Piece | Status |
|---|---|
| Corridor data generator (`data/`) | ✅ Runs, produces 20 zones / 396,992 people, 6 roads, 10 facilities, 28 assets |
| MCLP solver (`solver/mclp_solver.py`) | ✅ Runs, `OPTIMAL` status, and can now auto-block roads from Exasol Q1 |
| Road-network routing (ambulances only; boats bypass roads by design) | ✅ Wired to Exasol flood-road status plus manual/judge-clicked road blocks |
| AI tool-calling contract + rule-based fallback (`agent/tools.py`) | ✅ Fallback parser tested against 3 phrasings |
| Exasol schema (`sql/01_schema.sql`) | ✅ Live-tested against Exasol Personal Local on `127.0.0.1:8563` |
| Exasol spatial queries (`sql/02_queries.sql`) | ✅ Q1 live-tested through `pyexasol` and independently through `exapump`; Q2-Q5 are written but still need live query-specific checks |
| pyexasol loader (`scripts/load_data.py`) | ✅ Live-run against Exasol Personal Local; loads 20 zones, 3 flood zones, 6 roads, 10 facilities, 28 assets |
| Frontend (map, sliders, road-click) | ❌ Not started this session |
| Real OSM road network / real flood-hazard data (opencity.in) | ❌ Not started — current data is synthetic, anchored on real coordinates (see `data/generate_corridor_data.py` docstring) |

## The verified killer metric

Running `solver/mclp_solver.py --use-exasol-road-status` with 60% fleet availability
(a credible early-crisis assumption, not everything-is-fine):

```
BEFORE (uncoordinated — each unit independently drives to its own nearest zone,
        no visibility into what other units are doing):
  Coverage: 28.2%  (112,144 / 396,992 people, 5/20 zones actually reached)

EXASOL ROAD STATUS:
  ST_INTERSECTS auto-closes roads R001, R003, R004, R005, R006

AFTER (ExaCommand — CP-SAT solves the coverage-maximization problem centrally,
       using Exasol's flooded-road list, OPTIMAL status):
  Coverage: 69.5%  (275,929 / 396,992 people)

+41.3 percentage points, same fleet, same day, just coordinated.

JUDGE ROAD-CLICK MOMENT:
  Blocking the one remaining passable connector (`R002`) on top of Exasol's
  flood closures drops optimized coverage from 69.5% to 56.2%.
```

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

**Verified end to end:** Exasol's Q1 spatial join detects five flooded roads
(`R001`, `R003`, `R004`, `R005`, `R006`) via `ST_INTERSECTS`; the solver now
passes those IDs into `blocked_road_ids` automatically, so ambulances route only
over the remaining passable road graph. With those flood closures active, a
manual/judge-click block of `R002` changes optimized coverage from 69.5% to
56.2%. That is the demo road-click to rehearse.

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

# Run solver with Exasol's ST_INTERSECTS road closures wired in
.\.venv\Scripts\python.exe solver\mclp_solver.py --use-exasol-road-status --password-file "$env:USERPROFILE\.exasol-starter-kit\credentials\nano_sys_password"

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

# Run solver with Exasol's ST_INTERSECTS road closures wired in
python solver/mclp_solver.py --use-exasol-road-status --password-file ~/.exasol-starter-kit/credentials/nano_sys_password

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
     Exasol (GEOMETRY tables, ST_INTERSECTS, read-only MCP access)
     detects flooded roads; the solver currently keeps distance/routing
     local until Q3's distance matrix is wired in
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
