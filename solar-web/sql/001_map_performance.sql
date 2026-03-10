-- =============================================================
-- Map Performance: View + RPC for pre-joined scores
-- Run in Supabase SQL Editor
-- =============================================================

-- 1. View: homes with scores and hybrid calculation
-- Use this anywhere you previously queried homes + home_scores separately.
DROP VIEW IF EXISTS homes_with_scores;

CREATE VIEW homes_with_scores AS
SELECT
  h.*,
  s.model_score,
  s.roof_score,
  CASE
    WHEN s.model_score IS NOT NULL AND s.roof_score IS NOT NULL
      THEN ROUND(0.6 * s.model_score + 0.4 * s.roof_score)
    WHEN s.model_score IS NOT NULL THEN s.model_score
    WHEN s.roof_score IS NOT NULL THEN s.roof_score
    ELSE NULL
  END AS hybrid_score
FROM homes h
LEFT JOIN home_scores s ON h.index = s.home_index;

-- 2. RPC: lightweight map points with scores
-- Returns only what the map needs. ~400KB for 20K homes.
CREATE OR REPLACE FUNCTION get_map_points(
  p_county text DEFAULT NULL,
  p_city text DEFAULT NULL,
  p_south double precision DEFAULT NULL,
  p_north double precision DEFAULT NULL,
  p_west double precision DEFAULT NULL,
  p_east double precision DEFAULT NULL,
  p_limit int DEFAULT 1000
)
RETURNS TABLE(
  index text,
  latitude double precision,
  longitude double precision,
  model_score numeric,
  roof_score numeric,
  hybrid_score numeric
) AS $$
  SELECT
    h.index,
    h.latitude::double precision,
    h.longitude::double precision,
    s.model_score,
    s.roof_score,
    CASE
      WHEN s.model_score IS NOT NULL AND s.roof_score IS NOT NULL
        THEN ROUND(0.6 * s.model_score + 0.4 * s.roof_score)
      WHEN s.model_score IS NOT NULL THEN s.model_score
      WHEN s.roof_score IS NOT NULL THEN s.roof_score
      ELSE NULL
    END AS hybrid_score
  FROM homes h
  LEFT JOIN home_scores s ON h.index = s.home_index
  WHERE (p_county IS NULL OR h.county = p_county)
    AND (p_city IS NULL OR h.city = p_city)
    AND (p_south IS NULL OR h.latitude >= p_south)
    AND (p_north IS NULL OR h.latitude <= p_north)
    AND (p_west IS NULL OR h.longitude >= p_west)
    AND (p_east IS NULL OR h.longitude <= p_east)
  LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- 3. Indexes for performance
CREATE INDEX IF NOT EXISTS idx_homes_lat_lng ON homes (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_homes_county_city ON homes (county, city);
CREATE INDEX IF NOT EXISTS idx_home_scores_home_index ON home_scores (home_index);
