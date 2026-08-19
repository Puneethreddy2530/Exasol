
CREATE OR REPLACE LUA SCALAR SCRIPT GET_TOPOLOGICAL_ROUTE(
    start_lat DOUBLE, start_lon DOUBLE,
    end_lat DOUBLE, end_lon DOUBLE,
    blocked_roads VARCHAR(1000)
) RETURNS VARCHAR(2000) AS
function run(ctx)
    -- Hackathon shortcut: instead of a full PostGIS graph inside the UDF,
    -- we calculate a dynamic waypoint (midpoint with offset) based on the blocked edges
    -- to simulate a reroute. Returns a JSON array of [lon, lat] coordinates for Pydeck.
    
    local dlat = ctx.end_lat - ctx.start_lat
    local dlon = ctx.end_lon - ctx.start_lon
    
    local mid_lat = ctx.start_lat + (dlat / 2.0)
    local mid_lon = ctx.start_lon + (dlon / 2.0)
    
    -- If roads are blocked, simulate a detour by perturbing the midpoint perpendicularly
    if ctx.blocked_roads ~= nil and ctx.blocked_roads ~= "" then
        mid_lat = mid_lat - (dlon * 0.2)
        mid_lon = mid_lon + (dlat * 0.2)
    end
    
    -- Return PyDeck PathLayer format: [[lon, lat], [lon, lat], [lon, lat]]
    local path = string.format("[[%.5f, %.5f], [%.5f, %.5f], [%.5f, %.5f]]", 
        ctx.start_lon, ctx.start_lat, 
        mid_lon, mid_lat, 
        ctx.end_lon, ctx.end_lat)
        
    return path
end
