-- Table for user-reported data issues on homes
CREATE TABLE home_issues (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  home_index TEXT NOT NULL REFERENCES homes(index),
  category TEXT NOT NULL CHECK (category IN ('permit_issue', 'solar_status', 'image_issue', 'home_info', 'other')),
  description TEXT,
  user_id UUID REFERENCES auth.users(id),
  resolved BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for looking up issues by home
CREATE INDEX idx_home_issues_home_index ON home_issues(home_index);

-- Index for filtering unresolved issues
CREATE INDEX idx_home_issues_unresolved ON home_issues(resolved) WHERE NOT resolved;

-- RLS: authenticated users can insert, read their own
ALTER TABLE home_issues ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone authenticated can report an issue"
  ON home_issues FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view their own reports"
  ON home_issues FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);
