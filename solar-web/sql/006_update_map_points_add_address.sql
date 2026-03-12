-- Add address and city to get_map_points RPC for map hover tooltips
-- Run this in Supabase SQL editor to update the existing function

CREATE OR REPLACE FUNCTION get_map_points(
  p_county TEXT DEFAULT NULL,
  p_city TEXT DEFAULT NULL,
  p_south DOUBLE PRECISION DEFAULT NULL,
  p_north DOUBLE PRECISION DEFAULT NULL,
  p_west DOUBLE PRECISION DEFAULT NULL,
  p_east DOUBLE PRECISION DEFAULT NULL,
  p_limit INT DEFAULT 1000,
  p_exclude_solar BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
  index TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  model_score NUMERIC,
  roof_score NUMERIC,
  hybrid_score NUMERIC,
  address TEXT,
  city TEXT,
  has_solar BOOLEAN
)
LANGUAGE sql STABLE
AS $$
  SELECT
    h.index,
    h.latitude::DOUBLE PRECISION,
    h.longitude::DOUBLE PRECISION,
    s.model_score,
    s.roof_score,
    CASE
      WHEN s.model_score IS NOT NULL AND s.roof_score IS NOT NULL
        THEN ROUND(0.6 * s.model_score + 0.4 * s.roof_score, 1)
      WHEN s.model_score IS NOT NULL THEN s.model_score
      WHEN s.roof_score IS NOT NULL THEN s.roof_score
      ELSE NULL
    END AS hybrid_score,
    h.address,
    h.city,
    h.has_solar
  FROM homes h
  LEFT JOIN home_scores s ON s.home_index = h.index
  WHERE h.latitude IS NOT NULL
    AND h.longitude IS NOT NULL
    AND (p_county IS NULL OR h.county = p_county)
    AND (p_city IS NULL OR h.city = p_city)
    AND (p_south IS NULL OR h.latitude >= p_south)
    AND (p_north IS NULL OR h.latitude <= p_north)
    AND (p_west IS NULL OR h.longitude >= p_west)
    AND (p_east IS NULL OR h.longitude <= p_east)
    AND (NOT p_exclude_solar OR h.has_solar IS NOT TRUE)
  LIMIT p_limit;
$$;
