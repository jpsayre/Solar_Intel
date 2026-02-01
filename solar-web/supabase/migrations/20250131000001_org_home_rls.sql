-- RLS for org_home: only users in the same org can see/edit their org's overlay.
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor).

-- 1. Enable RLS on org_home
ALTER TABLE public.org_home ENABLE ROW LEVEL SECURITY;

-- 2. SELECT: user can see only rows for their org
CREATE POLICY "org_home_select_same_org"
ON public.org_home
FOR SELECT
USING (
  org_id = (SELECT org_id FROM public.profiles WHERE user_id = auth.uid())
);

-- 3. INSERT: user can insert only for their org (org_id must match profile)
CREATE POLICY "org_home_insert_same_org"
ON public.org_home
FOR INSERT
WITH CHECK (
  org_id = (SELECT org_id FROM public.profiles WHERE user_id = auth.uid())
  AND created_by = auth.uid()
);

-- 4. UPDATE: user can update only their org's rows
CREATE POLICY "org_home_update_same_org"
ON public.org_home
FOR UPDATE
USING (org_id = (SELECT org_id FROM public.profiles WHERE user_id = auth.uid()))
WITH CHECK (org_id = (SELECT org_id FROM public.profiles WHERE user_id = auth.uid()));

-- 5. DELETE: user can delete only their org's rows
CREATE POLICY "org_home_delete_same_org"
ON public.org_home
FOR DELETE
USING (org_id = (SELECT org_id FROM public.profiles WHERE user_id = auth.uid()));
