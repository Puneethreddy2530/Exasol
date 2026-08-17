-- ExaCommand — core spatial queries
-- This is the layer the AI agent is allowed to call (all read-only SELECTs,
-- which is exactly what the bundled Exasol MCP server permits by default).

OPEN SCHEMA EXACOMMAND;

-- =============================================================================
-- Q1. Which roads intersect an active flood zone right now?
--     This is the ST_INTERSECTS query the R-tree geo-index accelerates.
-- =============================================================================
SELECT r.ROAD_ID, r.NAME, f.NAME AS FLOODED_BY, f.SEVERITY
FROM ROADS r
JOIN FLOOD_ZONES f
  ON ST_INTERSECTS(r.GEO, f.GEO);

-- =============================================================================
-- Q2. Passable-roads view: everything NOT touching an active flood zone.
--     The optimizer only ever sees this view — it never sees blocked roads.
-- =============================================================================
CREATE OR REPLACE VIEW PASSABLE_ROADS AS
SELECT r.*
FROM ROADS r
WHERE NOT EXISTS (
    SELECT 1 FROM FLOOD_ZONES f WHERE ST_INTERSECTS(r.GEO, f.GEO)
)
AND r.IS_BLOCKED = FALSE;   -- also respects manual/judge-triggered blocks

-- =============================================================================
-- Q3. Asset -> Zone distance matrix, in metres.
--     ST_TRANSFORM to SRID 3857 (Web Mercator) before ST_DISTANCE — SRID 4326
--     distances are in degrees, not metres, and are not directly usable.
--     This is the matrix the MCLP solver consumes.
-- =============================================================================
SELECT
    a.ASSET_ID,
    a.TYPE          AS ASSET_TYPE,
    z.ZONE_ID,
    z.POPULATION,
    ST_DISTANCE(ST_TRANSFORM(a.GEO, 3857), ST_TRANSFORM(z.GEO, 3857)) AS DISTANCE_M
FROM ASSETS a
CROSS JOIN ZONES z
WHERE a.STATUS = 'available'
ORDER BY a.ASSET_ID, DISTANCE_M;

-- =============================================================================
-- Q4. Zone -> nearest facility distance (for capacity-constrained routing).
-- =============================================================================
SELECT
    z.ZONE_ID,
    fc.FACILITY_ID,
    fc.TYPE          AS FACILITY_TYPE,
    fc.CAPACITY,
    ST_DISTANCE(ST_TRANSFORM(z.GEO, 3857), ST_TRANSFORM(fc.GEO, 3857)) AS DISTANCE_M
FROM ZONES z
CROSS JOIN FACILITIES fc
ORDER BY z.ZONE_ID, DISTANCE_M;

-- =============================================================================
-- Q5. Coverage check: which zones are within a given travel-time-equivalent
--     radius (metres) of ANY available asset? Used for the before/after
--     "coverage %" metric shown in the demo.
--     :radius_m is bound by the app (e.g. 30-min drive ~= 12000-15000m
--     in flood conditions — tune against real data once available).
-- =============================================================================
SELECT z.ZONE_ID, z.POPULATION,
       MIN(ST_DISTANCE(ST_TRANSFORM(a.GEO, 3857), ST_TRANSFORM(z.GEO, 3857))) AS NEAREST_ASSET_M
FROM ZONES z
CROSS JOIN ASSETS a
WHERE a.STATUS = 'available'
GROUP BY z.ZONE_ID, z.POPULATION;
