# Home File Storage Feature Plan

## Use Case
Sales reps attach documents (electricity bills, contracts, photos) to individual home records. All org members can view files for homes in their territory.

## Architecture

- **Storage**: Supabase Storage bucket `org-files` (private)
- **Path structure**: `{org_id}/{home_index}/{timestamp}_{filename}`
- **Metadata**: `home_files` table tracking uploads
- **Access control**: RLS scoped to org membership via `profiles.org_id`
- **No Vercel/server-side changes needed** — all client-side Supabase calls

## SQL

### Table

```sql
CREATE TABLE home_files (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  org_id text NOT NULL,
  home_index text NOT NULL,
  uploaded_by uuid NOT NULL REFERENCES auth.users(id),
  file_name text NOT NULL,
  file_path text NOT NULL,
  file_size bigint,
  mime_type text,
  label text,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE home_files ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own org files"
  ON home_files FOR SELECT TO authenticated
  USING (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "Users can insert own org files"
  ON home_files FOR INSERT TO authenticated
  WITH CHECK (org_id = (SELECT org_id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "Users can delete own uploads"
  ON home_files FOR DELETE TO authenticated
  USING (uploaded_by = auth.uid());

CREATE INDEX idx_home_files_home ON home_files (home_index, org_id);
```

### Storage bucket policies

```sql
CREATE POLICY "Org members can upload"
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'org-files'
    AND (storage.foldername(name))[1] = (SELECT org_id FROM profiles WHERE user_id = auth.uid())
  );

CREATE POLICY "Org members can download"
  ON storage.objects FOR SELECT TO authenticated
  USING (
    bucket_id = 'org-files'
    AND (storage.foldername(name))[1] = (SELECT org_id FROM profiles WHERE user_id = auth.uid())
  );

CREATE POLICY "Uploader can delete"
  ON storage.objects FOR DELETE TO authenticated
  USING (
    bucket_id = 'org-files'
    AND owner = auth.uid()
  );
```

## Frontend

Collapsible "Files" section on home detail page (same pattern as Permit History):

- **File list**: filename, label, upload date, size, download/delete buttons
- **Upload**: file input (`.pdf, .jpg, .png`), optional label field, upload button
- **Upload flow**: upload to storage -> insert metadata row -> refresh list
- **Download**: signed URL (30 min expiry), open in new tab
- **Delete**: remove from storage + delete metadata row (only for uploader)

## Constraints

- **File size limit**: 10MB per file
- **Allowed types**: PDF, JPEG, PNG
- **Storage**: Supabase free tier = 1GB, Pro = 100GB
- **No virus scanning** on Supabase uploads
- **No in-browser preview** for v1 — download only

## Bucket setup (Supabase dashboard)

1. Create bucket `org-files` (private, not public)
2. Set max file size to 10MB
3. Set allowed MIME types: `application/pdf, image/jpeg, image/png`
4. Apply storage policies above
