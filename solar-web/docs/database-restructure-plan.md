# Database Restructure Plan

## Problem

`org_home.custom` JSONB is a junk drawer. Contacts, action items, tags, home info fields, and timestamp hacks are all shoved into one untyped JSON column. This blocks:

- Server-side filtering (interest levels, tags)
- Cross-home queries ("all open action items", "all homes with emails")
- Indexing
- Schema visibility and type safety
- Clean integration of future features (email enrichment, file storage)

Additional issue: `home_notes` lacks `org_id` — RLS uses a double subquery through `profiles` to check org membership, which is slow and makes org-scoped queries impossible.

## Decision: No data migration

Existing `org_home` data can be dropped. Restructure is a clean slate.

---

## Target Schema

### Shared/global tables (unchanged)

```
homes                     -- property records (read-only for web app)
home_scores               -- ML + roof scores
permits                   -- permit records
state_electricity_prices  -- reference data
```

### Per-user tables (unchanged)

```
profiles                  -- user_id → org_id mapping
user_follows              -- user_id + home_index
```

### Per-org tables (restructured)

#### `org_home` — org's relationship to a home

Scalar fields promoted from JSONB to real columns. One row per org+home.

```sql
DROP TABLE IF EXISTS public.org_home CASCADE;

CREATE TABLE public.org_home (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id        uuid NOT NULL,
  home_index    text NOT NULL,

  -- Sales pipeline
  stage         text,          -- e.g. 'new', 'contacted', 'quoted', 'closed', 'lost'
  priority      int4,
  assigned_to   uuid,

  -- Tags (text array, queryable with @> operator)
  tags          text[] DEFAULT '{}',

  -- Home info (observed by sales rep)
  roof_condition    text,      -- Excellent / Good / Fair / Poor
  roofing_material  text,      -- Asphalt Shingles / Ceramic Tile / Metal / etc.
  energy_bill_kwh   numeric,
  interest_in_solar   text,    -- Cold / Cool / Warm / Hot
  interest_in_battery text,    -- Cold / Cool / Warm / Hot
  ev_ownership        text,    -- Unknown / Doesn't Want / Interested / Owns an EV / Owns 2+ EVs

  -- Metadata
  created_by    uuid NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),

  UNIQUE(org_id, home_index)
);

-- Indexes for server-side filtering
CREATE INDEX idx_org_home_org ON org_home(org_id);
CREATE INDEX idx_org_home_interest_solar ON org_home(org_id, interest_in_solar) WHERE interest_in_solar IS NOT NULL;
CREATE INDEX idx_org_home_interest_battery ON org_home(org_id, interest_in_battery) WHERE interest_in_battery IS NOT NULL;
CREATE INDEX idx_org_home_tags ON org_home USING gin(tags);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER org_home_updated_at
  BEFORE UPDATE ON org_home
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

#### `org_home_contacts` — contacts for a home (per org)

```sql
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
```

#### `org_home_action_items` — tasks per home (per org)

```sql
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
```

#### `home_notes` — add org_id column

```sql
ALTER TABLE public.home_notes ADD COLUMN IF NOT EXISTS org_id uuid;

-- Backfill org_id from author's profile
UPDATE home_notes
SET org_id = (SELECT org_id FROM profiles WHERE user_id = home_notes.author_id)
WHERE org_id IS NULL;

-- Simpler RLS: direct org_id check instead of double subquery
DROP POLICY IF EXISTS "home_notes_select_same_org" ON home_notes;
CREATE POLICY "home_notes_select_same_org" ON home_notes
  FOR SELECT USING (
    org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid())
  );

CREATE INDEX idx_home_notes_org_home ON home_notes(org_id, home_index);
```

### Future tables (create structure now, wire up later)

#### `org_owner_emails` — email enrichment results

```sql
CREATE TABLE public.org_owner_emails (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  owner_name      text NOT NULL,       -- which owner (from homes.owner_1 / owner_2)
  email           text,
  source          text,                -- e.g. 'peopledatalabs', 'manual'
  status          text NOT NULL,       -- 'found', 'not_found', 'pending'
  looked_up_by    uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),

  UNIQUE(org_id, home_index, owner_name, email)
);

CREATE INDEX idx_org_owner_emails_lookup ON org_owner_emails(org_id, home_index);
```

#### `org_home_files` — file metadata (already planned in file-storage-plan.md)

```sql
CREATE TABLE public.org_home_files (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id          uuid NOT NULL,
  home_index      text NOT NULL,
  uploaded_by     uuid NOT NULL REFERENCES auth.users(id),
  file_name       text NOT NULL,
  file_path       text NOT NULL,       -- storage bucket path
  file_size       bigint,
  mime_type       text,
  label           text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_org_home_files_lookup ON org_home_files(org_id, home_index);
```

### RLS pattern (same for all org-scoped tables)

```sql
-- Template: apply to org_home_contacts, org_home_action_items,
--           org_owner_emails, org_home_files

ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;

CREATE POLICY "{table}_select" ON {table}
  FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "{table}_insert" ON {table}
  FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "{table}_update" ON {table}
  FOR UPDATE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()))
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "{table}_delete" ON {table}
  FOR DELETE TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));
```

---

## Frontend Changes

### Phase 1: SQL — Create tables, drop old org_home

Run the SQL above in Supabase SQL Editor. Order:
1. Create `update_updated_at()` trigger function
2. Drop old `org_home`
3. Create new `org_home`
4. Create `org_home_contacts`
5. Create `org_home_action_items`
6. Add `org_id` to `home_notes`, backfill, update RLS
7. Create `org_owner_emails` and `org_home_files` (empty, for future)
8. Apply RLS to all new tables
9. Drop old org_home RLS policies, apply new ones

### Phase 2: Detail page (`app/homes/[index]/page.tsx`)

This is the biggest change — all reads and writes touch org_home.

**Reads (on page load):**
- `org_home` → read scalar columns directly (no more JSON parsing)
- `org_home_contacts` → `SELECT * FROM org_home_contacts WHERE org_id = ? AND home_index = ?`
- `org_home_action_items` → `SELECT * FROM org_home_action_items WHERE org_id = ? AND home_index = ? ORDER BY created_at`
- `home_notes` → unchanged (already works)

**Writes (auto-save):**
- `org_home` → upsert scalar fields directly (roof_condition, interest_in_solar, tags, etc.)
- `org_home_contacts` → delete + re-insert (simplest for array-like editing)
- `org_home_action_items` → individual insert/update/delete per item
- Remove all `lastSaved*Ref` and `*_updated_at` timestamp hacks — `updated_at` trigger handles it

**What gets deleted:**
- All `custom` JSONB parsing/building logic
- `COMMON_TAGS` array and `customTags` state → replaced by direct column reads
- `ContactEntry` / `ActionItemEntry` types referencing JSONB shape
- Four `lastSaved*Ref` refs and change detection logic
- Four `*_updated_at` client-side timestamp fields

### Phase 3: Following page (`app/following/page.tsx`)

- Read contacts from `org_home_contacts` instead of `custom.contacts`
- Read action items from `org_home_action_items` instead of `custom.action_items`
- Read tags from `org_home.tags` (real column) instead of `custom.tags`
- `buildFollowingCardRows()` in cardData.ts updated accordingly

### Phase 4: Explorer page (`app/homes/page.tsx`)

- Read interest levels from `org_home.interest_in_solar` / `org_home.interest_in_battery` directly
- Read tags from `org_home.tags` column
- Potential: move interest/tag filtering into the `get_map_points` RPC for true server-side filtering

### Phase 5: Update `get_map_points` RPC (optional, high value)

Add optional interest/tag filter params to the RPC so the server filters before returning 1000 rows:

```sql
CREATE OR REPLACE FUNCTION get_map_points(
  p_limit int DEFAULT 1000,
  p_county text DEFAULT NULL,
  p_city text DEFAULT NULL,
  p_south float8 DEFAULT NULL,
  p_north float8 DEFAULT NULL,
  p_west float8 DEFAULT NULL,
  p_east float8 DEFAULT NULL,
  p_min_model_score int DEFAULT NULL,
  p_min_roof_score int DEFAULT NULL,
  p_interest_in_solar text DEFAULT NULL,
  p_interest_in_battery text DEFAULT NULL
) ...
-- LEFT JOIN org_home and filter on interest levels
```

---

## Entity Relationship Summary

```
homes (global)
  ├── home_scores (1:1)
  ├── permits (1:many)
  ├── user_follows (many:many via user)
  │
  └── org_home (1:1 per org)        ← scalar fields, tags
        ├── org_home_contacts       ← 0..N contacts
        ├── org_home_action_items   ← 0..N action items
        ├── org_home_files          ← 0..N files (future)
        └── org_owner_emails        ← 0..N enriched emails (future)
  │
  └── home_notes (1:many per org)   ← comments/notes
```

---

## What this unlocks

- **Server-side interest filtering** in `get_map_points` RPC
- **"All open action items" dashboard** across homes (simple query)
- **"Homes with contact info" filter** (JOIN exists check)
- **Proper `updated_at` per table** via DB triggers, no client hacks
- **Email enrichment** with proper status tracking and org scoping
- **File storage** with metadata table + Supabase Storage
- **Cleaner frontend code** — no more JSON serialize/deserialize/diff logic
