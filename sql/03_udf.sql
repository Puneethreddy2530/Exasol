-- ExaCommand — In-Database Python 3 UDF for Vulnerability Scoring
-- Computes a weighted triage score directly inside the SQL engine.
-- Using EXACOMMAND schema.



CREATE OR REPLACE LUA SCALAR SCRIPT CALCULATE_VULNERABILITY_SCORE(
    population INT,
    elderly_pct DOUBLE,
    children_pct DOUBLE,
    elevation_m DOUBLE
) RETURNS DOUBLE AS
function run(ctx)
    local score = ctx.population * 1.0
    local vulnerable_ratio = (ctx.elderly_pct + ctx.children_pct) / 100.0
    score = score + (vulnerable_ratio * 2.0 * ctx.population)
    if ctx.elevation_m < 5.0 then
        score = score * 1.5
    elseif ctx.elevation_m < 15.0 then
        score = score * 1.2
    end
    return score
end
