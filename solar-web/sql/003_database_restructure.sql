-- =============================================================================
-- Database Restructure: Replace org_home.custom JSONB with proper tables
-- Run in Supabase SQL Editor (Dashboard → SQL Editor)
-- =============================================================================

-- STEP 0: Shared trigger function for auto-updating updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- STEP 1: Drop old org_home (CASCADE drops its RLS policies + triggers)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS public.org_home CASCADE;


-- STEP 2: Create new org_home with real columns
-- ---------------------------------------------------------------------------
CREATE TABLE public.org_home (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id              uuid NOT NULL,
  home_index          text NOT NULL,

  -- Sales pipeline
  stage               text,
  priority            int4,
  assigned_to         uuid,

  -- Tags
  tags                text[] DEFAULT '{}',

  -- Home info (observed by sales rep)
  roof_condition      text,
  roofing_material    text,
  energy_bill_kwh     numeric,
  interest_in_solar   text,
  interest_in_battery text,
  ev_ownership        text,

  -- Metadata
  created_by          uuid NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  UNIQUE(org_id, home_index)
);

CREATE INDEX idx_org_home_org ON org_home(org_id);
CREATE INDEX idx_org_home_interest_solar ON org_home(org_id, interest_in_solar) WHERE interest_in_solar IS NOT NULL;
CREATE INDEX idx_org_home_interest_battery ON org_home(org_id, interest_in_battery) WHERE interest_in_battery IS NOT NULL;
CREATE INDEX idx_org_home_tags ON org_home USING gin(tags);

CREATE TRIGGER org_home_updated_at
  BEFORE UPDATE ON org_home
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS
ALTER TABLE public.org_home ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_home_select" ON org_home
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_insert" ON org_home
  FOR INSERT TO authenticated
  WITH CHECK (
    org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid())
    AND created_by = auth.uid()
  );

CREATE POLICY "org_home_update" ON org_home
  FOR UPDATE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()))
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_delete" ON org_home
  FOR DELETE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));


-- STEP 3: Create org_home_contacts
-- ---------------------------------------------------------------------------
CREATE TABLE public.org_home_contacts (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  preferred_name  text,
  phone_number    text,
  email           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_org_home_contacts_lookup ON org_home_contacts(org_id, home_index);
CREATE INDEX idx_org_home_contacts_email ON org_home_contacts(org_id, email) WHERE email IS NOT NULL;

CREATE TRIGGER org_home_contacts_updated_at
  BEFORE UPDATE ON org_home_contacts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE public.org_home_contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_home_contacts_select" ON org_home_contacts
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_contacts_insert" ON org_home_contacts
  FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_contacts_update" ON org_home_contacts
  FOR UPDATE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()))
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_contacts_delete" ON org_home_contacts
  FOR DELETE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));


-- STEP 4: Create org_home_action_items
-- ---------------------------------------------------------------------------
CREATE TABLE public.org_home_action_items (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  body            text NOT NULL,
  completed       boolean NOT NULL DEFAULT false,
  created_by      uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz
);

CREATE INDEX idx_org_home_actions_lookup ON org_home_action_items(org_id, home_index);
CREATE INDEX idx_org_home_actions_open ON org_home_action_items(org_id, completed) WHERE NOT completed;

ALTER TABLE public.org_home_action_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_home_action_items_select" ON org_home_action_items
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_action_items_insert" ON org_home_action_items
  FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_action_items_update" ON org_home_action_items
  FOR UPDATE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()))
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_action_items_delete" ON org_home_action_items
  FOR DELETE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));


-- STEP 5: Add org_id to home_notes
-- ---------------------------------------------------------------------------
ALTER TABLE public.home_notes ADD COLUMN IF NOT EXISTS org_id uuid;

-- Backfill from author's profile
UPDATE public.home_notes
SET org_id = p.org_id
FROM public.profiles p
WHERE p.user_id = home_notes.author_id
  AND home_notes.org_id IS NULL;

-- Replace slow double-subquery RLS with direct org_id check
DROP POLICY IF EXISTS "home_notes_select_same_org" ON home_notes;
CREATE POLICY "home_notes_select_same_org" ON home_notes
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE INDEX IF NOT EXISTS idx_home_notes_org_home ON home_notes(org_id, home_index);


-- STEP 6: Create org_owner_emails (future — email enrichment)
-- ---------------------------------------------------------------------------
CREATE TABLE public.org_owner_emails (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  owner_name      text NOT NULL,
  email           text,
  source          text,
  status          text NOT NULL DEFAULT 'pending',
  looked_up_by    uuid,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_org_owner_emails_unique ON org_owner_emails(org_id, home_index, owner_name, COALESCE(email, ''));
CREATE INDEX idx_org_owner_emails_lookup ON org_owner_emails(org_id, home_index);

ALTER TABLE public.org_owner_emails ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_owner_emails_select" ON org_owner_emails
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_owner_emails_insert" ON org_owner_emails
  FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_owner_emails_delete" ON org_owner_emails
  FOR DELETE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));


-- STEP 7: Create org_home_files (future — file storage)
-- ---------------------------------------------------------------------------
CREATE TABLE public.org_home_files (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  uploaded_by     uuid NOT NULL REFERENCES auth.users(id),
  file_name       text NOT NULL,
  file_path       text NOT NULL,
  file_size       bigint,
  mime_type       text,
  label           text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_org_home_files_lookup ON org_home_files(org_id, home_index);

ALTER TABLE public.org_home_files ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_home_files_select" ON org_home_files
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_files_insert" ON org_home_files
  FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "org_home_files_delete" ON org_home_files
  FOR DELETE TO authenticated
  USING (uploaded_by = auth.uid());


-- =============================================================================
-- Done. Summary of what was created:
--
--   TABLES:
--     org_home              (rebuilt — scalar columns, no more custom JSONB)
--     org_home_contacts     (new)
--     org_home_action_items (new)
--     org_owner_emails      (new, future use)
--     org_home_files        (new, future use)
--
--   MODIFIED:
--     home_notes            (added org_id column, backfilled, simpler RLS)
--
--   FUNCTION:
--     update_updated_at()   (shared trigger function)
--
-- =============================================================================
