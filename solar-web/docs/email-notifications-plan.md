# Email Notification System Plan

## Why email instead of in-app notifications

- No per-user "seen" state to track
- No real-time queries on every page load
- Drives users back into the tool
- Territory scoping happens at send time (in the Python script), not query time
- Naturally batched — one email per week matches the permit refresh cadence

## Two notification types

### 1. Weekly Permit Digest

**Trigger:** After the weekly permit upload script runs.

**Content per org:**
- Summary counts by type: "14 new solar permits, 22 new roof permits, 3 battery, 2 EV charger"
- Top 5 highest-value permits with address and description
- Link to the Permit Alerts page

**Scoping:** Only permits in the org's territory (county/city). Requires `org_territories` table.

**Implementation:**
1. After `upload_permits_to_supabase.py` finishes, query new permits grouped by county
2. For each org, filter to their territory's counties
3. Build HTML email from template
4. Send via transactional email service (Resend, SendGrid, or Supabase Edge Functions)
5. Send to all users in the org (query `profiles` by `org_id`, join `auth.users` for email)

**Email template sketch:**
```
Subject: 41 new permits this week in Boulder County

Hi {name},

This week's permit activity in your territory:

  Solar: 14 new permits
  Roof: 22 new permits
  Battery: 3 new permits
  EV Charger: 2 new permits

Top permits:
  - 1432 Alpine Ave: Solar PV 8.4 kW ($22,400)
  - 2875 Mapleton Ave: Full roof replacement ($14,200)
  ...

[View all permits →]
```

### 2. Followed Home Updates

**Trigger:** After weekly permit upload, check if any new permits match homes the user follows.

**Content per user:**
- List of followed homes that got new permits
- Permit type, description, date, value
- Link to each home's detail page

**Scoping:** Per-user based on `user_follows` table (already exists).

**Implementation:**
1. After permit upload, query: `SELECT DISTINCT home_index FROM permits WHERE created_at > now() - interval '7 days'`
2. Join against `user_follows` to find which users follow those homes
3. Group by user, build personalized email
4. Send

**Email template sketch:**
```
Subject: New activity on homes you follow

Hi {name},

Homes you're following had new permits filed:

  1432 Alpine Ave, Boulder
    - Solar PV installation ($22,400) — filed 3/5/2026

  905 Baseline Rd, Boulder
    - Roof replacement ($14,200) — filed 3/3/2026

[View 1432 Alpine Ave →]
[View 905 Baseline Rd →]
```

## Infrastructure needed

### Email service
- **Resend** is simplest: free tier = 3,000 emails/month, simple API, good Next.js/Node support
- Alternative: SendGrid, Postmark, or Supabase Edge Functions + SMTP

### Database additions
- `org_territories` table: `org_id, county, city` — defines which permits an org sees
- `profiles.email_opt_out` boolean — respect unsubscribe
- No notification state tables needed

### Script additions
- Add email sending to the end of `upload_permits_to_supabase.py`
- Or separate script: `scripts/send_permit_digest.py` that runs after upload
- Cron: upload permits → send digest (two steps, same schedule)

## Rollout order

1. **Now:** Permit Alerts page works, bell icon removed, alerts in hamburger menu
2. **With first paying customer:** Add `org_territories` table, wire up Resend, build weekly digest
3. **Shortly after:** Add followed-home notifications
4. **Later:** User preferences (frequency, types, opt-out per notification type)

## What we decided NOT to do

- In-app notification dot (requires per-user seen state, territory joins on every page load)
- Real-time notifications (websockets/push — overkill for weekly batch data)
- Per-notification read/unread tracking (email handles this naturally)
