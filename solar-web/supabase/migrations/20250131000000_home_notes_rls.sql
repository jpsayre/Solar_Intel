-- RLS for home_notes: only users in the same org can see notes.
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor).

-- 1. Enable RLS on home_notes
ALTER TABLE public.home_notes ENABLE ROW LEVEL SECURITY;

-- 2. SELECT: user can see notes only when the note's author is in the same org as the current user
CREATE POLICY "home_notes_select_same_org"
ON public.home_notes
FOR SELECT
USING (
  (SELECT org_id FROM public.profiles WHERE user_id = auth.uid())
  =
  (SELECT org_id FROM public.profiles WHERE user_id = home_notes.author_id)
);

-- 3. INSERT: user can insert only their own note (author_id must be current user)
CREATE POLICY "home_notes_insert_own"
ON public.home_notes
FOR INSERT
WITH CHECK (author_id = auth.uid());

-- 4. UPDATE: user can update only their own notes
CREATE POLICY "home_notes_update_own"
ON public.home_notes
FOR UPDATE
USING (author_id = auth.uid())
WITH CHECK (author_id = auth.uid());

-- 5. DELETE: user can delete only their own notes
CREATE POLICY "home_notes_delete_own"
ON public.home_notes
FOR DELETE
USING (author_id = auth.uid());
