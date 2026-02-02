-- user_follows: which homes a user follows (for "Following").
-- Run in Supabase SQL Editor if not using migrations.

CREATE TABLE IF NOT EXISTS public.user_follows (
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  home_index text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, home_index)
);

-- RLS: users see and manage only their own follows
ALTER TABLE public.user_follows ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_follows_select_own"
ON public.user_follows
FOR SELECT
USING (user_id = auth.uid());

CREATE POLICY "user_follows_insert_own"
ON public.user_follows
FOR INSERT
WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_follows_delete_own"
ON public.user_follows
FOR DELETE
USING (user_id = auth.uid());

-- Optional: index for listing a user's follows
CREATE INDEX IF NOT EXISTS user_follows_user_id_idx ON public.user_follows(user_id);
