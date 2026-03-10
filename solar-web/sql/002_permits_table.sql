-- =============================================================
-- Permits table: individual permit records linked to homes
-- Run in Supabase SQL Editor
-- =============================================================

-- 1. Table
CREATE TABLE IF NOT EXISTS permits (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  home_index text NOT NULL,
  permit_number text,
  permit_type text NOT NULL,          -- solar, roof, battery, ev_charger, electrical, heat_pump, other
  description text,                   -- human-readable description
  filed_date date NOT NULL,
  valuation numeric,
  county text NOT NULL,
  created_at timestamptz DEFAULT now(),
  UNIQUE(home_index, permit_number, permit_type)
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_permits_home_index ON permits (home_index);
CREATE INDEX IF NOT EXISTS idx_permits_filed_date ON permits (filed_date DESC);
CREATE INDEX IF NOT EXISTS idx_permits_type_date ON permits (permit_type, filed_date DESC);

-- 3. RLS
ALTER TABLE permits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read permits"
  ON permits FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Service role can manage permits"
  ON permits FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- 4. RPC: recent permits for alerts page
CREATE OR REPLACE FUNCTION get_recent_permits(
  p_days int DEFAULT 30,
  p_types text[] DEFAULT ARRAY['solar', 'roof', 'battery', 'ev_charger'],
  p_limit int DEFAULT 100
)
RETURNS TABLE(
  id bigint,
  home_index text,
  permit_number text,
  permit_type text,
  description text,
  filed_date date,
  valuation numeric,
  county text,
  address text,
  city text
) AS $$
  SELECT
    p.id,
    p.home_index,
    p.permit_number,
    p.permit_type,
    p.description,
    p.filed_date,
    p.valuation,
    p.county,
    h.address,
    h.city
  FROM permits p
  LEFT JOIN homes h ON p.home_index = h.index
  WHERE p.filed_date >= CURRENT_DATE - p_days
    AND p.permit_type = ANY(p_types)
  ORDER BY p.filed_date DESC
  LIMIT p_limit;
$$ LANGUAGE sql STABLE;
