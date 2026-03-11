# Security

## solar-web (Next.js)

- **Route protection**: Middleware protects `/homes`, `/follows`, and `/following`. Unauthenticated users are redirected to `/login`.
- **Supabase RLS**: Row-level security policies restrict data access by org. See `solar-web/supabase/migrations/`.
- **Env vars**: Use `.env.local` for `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. These are safe to expose (anon key is public by design).

## Flask tools (view_solar_classifications, solar_score_designer, view_solar_classifications_permit)

- **Optional auth**: When `ADMIN_SECRET` (or `FLASK_ADMIN_SECRET`) is set, all `/api/*` and `/images/*` routes require authentication.
- **Usage**: Send `X-Admin-Token: <your-secret>` or `Authorization: Bearer <your-secret>` in requests.
- **Local dev**: Leave `ADMIN_SECRET` unset for local-only use (default: 127.0.0.1).
- **Production**: If exposing these tools beyond localhost, set `ADMIN_SECRET` and use HTTPS.

## API keys (Python scripts)

- **Never commit** API keys. Use environment variables:
  - `GOOGLE_MAPS_API_KEY`, `GOOGLE_SOLAR_API_KEY` for Google APIs
  - `OPEN_AI_API_KEY` for OpenAI
- Scripts exit with a clear error if required keys are missing.
