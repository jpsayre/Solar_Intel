-- =============================================================
-- RPC: get_homes_page — paginated, scored, filtered home list
-- Run in Supabase SQL Editor
-- =============================================================

CREATE OR REPLACE FUNCTION get_homes_page(
  p_south          double precision DEFAULT NULL,
  p_north          double precision DEFAULT NULL,
  p_west           double precision DEFAULT NULL,
  p_east           double precision DEFAULT NULL,
  p_sort_by        text             DEFAULT 'hybrid',
  p_min_model      double precision DEFAULT NULL,
  p_min_roof       double precision DEFAULT NULL,
  p_county         text             DEFAULT NULL,
  p_city           text             DEFAULT NULL,
  p_subdivision    text             DEFAULT NULL,
  p_address_search text             DEFAULT NULL,
  p_show_solar     boolean          DEFAULT false,
  p_limit          int              DEFAULT 100,
  p_offset         int              DEFAULT 0
)
RETURNS TABLE(
  index                  text,
  original_index         bigint,
  address                text,
  city                   text,
  county                 text,
  state                  text,
  zip_code               text,
  latitude               double precision,
  longitude              double precision,
  building_sqft          text,
  calculated_build_year  text,
  calculated_roof_age    text,
  owner_1                text,
  owner_2                text,
  subdivision_formatted  text,
  has_solar              boolean,
  saleprice              text,
  saledate               text,
  qualified_orientations text,
  count_stories          text,
  count_rooms            text,
  count_bath             text,
  count_bath_partial     text,
  count_bedrooms         text,
  roof_type              text,
  owner_unaltered        text,
  model_score            numeric,
  roof_score             numeric,
  hybrid_score           numeric,
  total_count            bigint
) AS $$
  WITH filtered AS (
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
    LEFT JOIN home_scores s ON h.index = s.home_index
    WHERE (p_county IS NULL OR h.county = p_county)
      AND (p_city IS NULL OR h.city = p_city)
      AND (p_subdivision IS NULL OR h.subdivision_formatted = p_subdivision)
      AND (p_address_search IS NULL OR h.address ILIKE '%' || p_address_search || '%')
      AND (p_show_solar = true OR h.has_solar IS NOT TRUE)
      AND (p_south IS NULL OR h.latitude >= p_south)
      AND (p_north IS NULL OR h.latitude <= p_north)
      AND (p_west IS NULL OR h.longitude >= p_west)
      AND (p_east IS NULL OR h.longitude <= p_east)
      AND (p_min_model IS NULL OR s.model_score >= p_min_model)
      AND (p_min_roof IS NULL OR s.roof_score >= p_min_roof)
  )
  SELECT
    f.index,
    f.original_index,
    f.address,
    f.city,
    f.county,
    f.state,
    f.zip_code,
    f.latitude::double precision,
    f.longitude::double precision,
    f.building_sqft,
    f.calculated_build_year,
    f.calculated_roof_age,
    f.owner_1,
    f.owner_2,
    f.subdivision_formatted,
    f.has_solar,
    f.saleprice,
    f.saledate,
    f.qualified_orientations,
    f.count_stories,
    f.count_rooms,
    f.count_bath,
    f.count_bath_partial,
    f.count_bedrooms,
    f.roof_type,
    f.owner_unaltered,
    f.model_score,
    f.roof_score,
    f.hybrid_score,
    COUNT(*) OVER () AS total_count
  FROM filtered f
  ORDER BY
    CASE p_sort_by
      WHEN 'model_score' THEN f.model_score
      WHEN 'roof_score'  THEN f.roof_score
      ELSE f.hybrid_score
    END DESC NULLS LAST,
    f.index ASC
  LIMIT p_limit
  OFFSET p_offset;
$$ LANGUAGE sql STABLE;

-- Additional indexes for sort performance
CREATE INDEX IF NOT EXISTS idx_home_scores_model_desc
  ON home_scores (model_score DESC NULLS LAST, home_index);
CREATE INDEX IF NOT EXISTS idx_home_scores_roof_desc
  ON home_scores (roof_score DESC NULLS LAST, home_index);
CREATE INDEX IF NOT EXISTS idx_homes_subdivision
  ON homes (subdivision_formatted);
