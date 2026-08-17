-- ExaCommand — Exasol schema
-- Run with: exapump interactive -p starter-kit   (paste this file)
-- or:       exapump upload --sql-file sql/01_schema.sql -p starter-kit
--
-- GEOMETRY columns use SRID 4326 (WGS84 lat/lon degrees), which is what the
-- WKT in data/*.csv is generated in. Distance calculations transform to
-- SRID 3857 (Web Mercator, metres) at query time — see 02_queries.sql.

CREATE SCHEMA IF NOT EXISTS EXACOMMAND;
OPEN SCHEMA EXACOMMAND;

CREATE OR REPLACE TABLE ZONES (
    ZONE_ID                         VARCHAR(10) PRIMARY KEY,
    LOCALITY                        VARCHAR(50),
    NAME                             VARCHAR(100),
    POPULATION                      DECIMAL(10,0),
    PRIORITY_CHILDREN_ELDERLY_PCT   DECIMAL(4,2),
    GEO                              GEOMETRY(4326)
);

CREATE OR REPLACE TABLE FLOOD_ZONES (
    FLOOD_ID     VARCHAR(10) PRIMARY KEY,
    NAME          VARCHAR(100),
    SEVERITY      VARCHAR(20),
    GEO           GEOMETRY(4326)
);

CREATE OR REPLACE TABLE ROADS (
    ROAD_ID         VARCHAR(10) PRIMARY KEY,
    NAME             VARCHAR(100),
    FROM_LOCALITY    VARCHAR(50),
    TO_LOCALITY      VARCHAR(50),
    GEO              GEOMETRY(4326),
    -- computed per scenario by 02_queries.sql, not loaded from CSV
    IS_BLOCKED       BOOLEAN DEFAULT FALSE
);

CREATE OR REPLACE TABLE FACILITIES (
    FACILITY_ID   VARCHAR(10) PRIMARY KEY,
    NAME           VARCHAR(100),
    TYPE           VARCHAR(20),   -- 'hospital' | 'shelter'
    CAPACITY       DECIMAL(10,0),
    GEO            GEOMETRY(4326)
);

CREATE OR REPLACE TABLE ASSETS (
    ASSET_ID        VARCHAR(10) PRIMARY KEY,
    TYPE             VARCHAR(20),  -- 'ambulance' | 'boat'
    BASE_LOCALITY    VARCHAR(50),
    GEO              GEOMETRY(4326),
    STATUS           VARCHAR(20) DEFAULT 'available'
);
