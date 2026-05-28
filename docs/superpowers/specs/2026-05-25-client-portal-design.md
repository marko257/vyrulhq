# VyrulHQ Client Portal — Design Spec
**Date:** 2026-05-25  
**Status:** Approved

---

## Overview

A fully functional V1 client portal for VyrulHQ — a managed short-form content agency. Clients log in to submit footage, view the clips produced for them, track performance stats across managed social accounts, chat with their account manager, view their content strategy, and manage billing. A companion admin panel lets VyrulHQ manage everything from one place.

---

## Architecture

### Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | Next.js 14 (App Router) | Vercel-native, server components, API routes, file-based routing |
| Hosting | Vercel | Already used for marketing site |
| Domain | hub.vyrulhq.com | Subdomain of vyrulhq.com, pointed to Vercel via CNAME |
| Database | Supabase (Postgres) | Already chosen infrastructure |
| Auth | Supabase Auth + Google OAuth | Invite-only, no password management |
| File Storage | Supabase Storage | Footage uploads + clip delivery |
| Billing | Stripe Subscriptions | Auto-billing, embedded customer portal |
| Email | Resend | Invite emails, billing notifications |
| Realtime | Supabase Realtime | Live messaging (client ↔ account manager) |
| Social APIs | TikTok Business API, Meta Graph API, YouTube Data API v3 | Stats pulled daily, cached in DB |
| Design | Space Grotesk, dark theme, #a8ff57 green | Matches VyrulHQ marketing site |

### App Structure

Two route groups in one Next.js repo:

```
/app
  /(portal)        — Client-facing portal (requires auth + active client record)
    /dashboard
    /submit
    /clips
    /performance
    /strategy
    /messages
    /billing
  /admin           — Admin panel (requires auth + admin role)
    /clients
    /clients/[id]
    /invites
  /auth
    /callback      — Google OAuth callback handler
  /onboarding      — 3-step wizard (new clients only, post-first-login)
  /accept/[token]  — Invite acceptance landing page
```

---

## Data Model

### Tables

**`clients`**
```
id               uuid PK
user_id          uuid FK → auth.users (nullable until invite accepted)
email            text unique
name             text
company          text
plan_tier        enum (starter, growth, scale)
status           enum (invited, onboarding, active, paused, churned)
stripe_customer_id  text
stripe_subscription_id  text
onboarding_completed  boolean default false
account_manager_name  text
invited_at       timestamptz
created_at       timestamptz
```

**`invites`**
```
id               uuid PK
email            text
name             text
company          text
plan_tier        enum
token            text unique
expires_at       timestamptz
accepted_at      timestamptz (nullable)
created_by       uuid FK → auth.users (admin who sent it)
created_at       timestamptz
```

**`footage_submissions`**
```
id               uuid PK
client_id        uuid FK → clients
file_url         text (Supabase Storage URL)
file_name        text
file_size_bytes  bigint
title            text
notes            text
uploaded_at      timestamptz
```

**`clips`**
```
id               uuid PK
client_id        uuid FK → clients
title            text
platform         enum (tiktok, instagram, youtube)
video_url        text (Supabase Storage URL)
thumbnail_url    text
caption          text
posted_at        timestamptz
created_at       timestamptz
```

**`messages`**
```
id               uuid PK
client_id        uuid FK → clients
sender_id        uuid FK → auth.users
sender_role      enum (client, admin)
body             text
read_at          timestamptz (nullable)
created_at       timestamptz
```

**`strategy_boards`**
```
id               uuid PK
client_id        uuid FK → clients unique
content          jsonb (structured content blocks — formats, hooks, themes)
updated_by       uuid FK → auth.users
updated_at       timestamptz
```

**`social_accounts`** (VyrulHQ's managed accounts)
```
id               uuid PK
client_id        uuid FK → clients
platform         enum (tiktok, instagram, youtube)
platform_account_id  text
access_token     text (encrypted)
token_expires_at timestamptz
created_at       timestamptz
```

**`performance_snapshots`**
```
id               uuid PK
client_id        uuid FK → clients
platform         enum
snapshot_date    date
views            bigint
likes            bigint
comments         bigint
shares           bigint
followers        bigint
posts_count      integer
created_at       timestamptz
```

### Row-Level Security

- Clients can only read/write rows where `client_id = auth.uid()` (via clients join)
- Admins bypass RLS via service role in API routes
- `messages` readable by sender OR matching client
- `strategy_boards`, `clips`, `performance_snapshots` — client read-only
- `footage_submissions` — client insert + read own

---

## Key Flows

### Invite → Onboard → Dashboard

1. Admin fills invite form in `/admin/invites` (email, name, company, plan)
2. System creates `invites` record + `clients` record (status: `invited`)
3. Resend sends invite email with link to `/accept/[token]`
4. Client clicks link — token validated, not expired
5. Client authenticates with Google OAuth (Supabase Auth)
6. System links `auth.users.id` to `clients.user_id`, sets status → `onboarding`
7. Client redirected to `/onboarding` — 3-step wizard:
   - **Step 1:** Confirm name, company, billing email (pre-filled from invite)
   - **Step 2:** What's included in their plan (rendered from plan_tier)
   - **Step 3:** How to submit footage — walkthrough with CTA to upload first file
8. Wizard completion sets `onboarding_completed = true`, status → `active`
9. Client lands on `/dashboard`

### Footage Submission

1. Client visits `/submit` — drag-and-drop upload zone
2. File uploads directly to Supabase Storage bucket `footage-submissions/{client_id}/`
3. On upload complete, `footage_submissions` record written via API route
4. Admin sees new submission in `/admin/clients/[id]` — badge on client row

### Clip Delivery (Admin → Client)

1. Admin opens `/admin/clients/[id]` → Clips tab
2. Admin uploads video file + fills metadata (title, platform, posted date, caption)
3. File goes to Supabase Storage bucket `clips/{client_id}/`
4. `clips` record created — client sees it immediately in `/clips`

### Performance Stats

1. Vercel cron job runs daily at 6am UTC
2. Fetches stats from TikTok Business API, Meta Graph API, YouTube Data API v3 for each `social_accounts` record
3. Writes one `performance_snapshots` row per client per platform per day
4. Client `/performance` page reads from snapshot cache — no live API calls on page load
5. OAuth tokens refreshed automatically; failure logged and alerted to admin

### Messaging

1. Both `/messages` (client) and `/admin/clients/[id]` (admin) subscribe to Supabase Realtime on `messages` table filtered by `client_id`
2. New message → insert to `messages` → both sides update in real time
3. Unread count: messages where `read_at IS NULL AND sender_role != current_role`
4. Sidebar badge updates via Realtime subscription on session load

### Billing

1. Admin assigns Stripe subscription to client during invite setup (or after)
2. Stripe webhook → `/api/webhooks/stripe` → updates `stripe_subscription_id`, plan status
3. Client `/billing` page:
   - Shows plan tier, price, next charge date (from Stripe API)
   - Payment method (last 4 digits)
   - Invoice history
   - "Update payment method" → opens Stripe Customer Portal session
4. Subscription cancellation flows through Stripe; webhook updates `clients.status → churned`

---

## Client Portal Pages

### Dashboard (`/dashboard`)
- Summary stats: clips posted this month, total views across platforms, platforms active, next billing date
- Recent clips strip (last 5)
- Unread message alert if any
- "Getting started" checklist hidden once onboarding_completed = true

### Submit Footage (`/submit`)
- Drag-and-drop upload zone (video files, max 4GB)
- Title field (required), notes field (optional)
- Upload progress bar
- History: past submissions listed below with date and title

### Clip Library (`/clips`)
- Filter by platform (All / TikTok / Instagram / YouTube)
- Grid of clip cards: thumbnail, title, platform badge, posted date
- Click → modal with full clip details (caption, posted date, platform) — per-clip metrics deferred to V2

### Performance (`/performance`)
- Platform tabs: All / TikTok / Instagram / YouTube
- Time range selector: 7d / 30d / 90d
- Metrics: total views, total likes, follower growth, posts count
- Chart: views over time (line chart)
- Top clips table: ranked by views

### Strategy Board (`/strategy`)
- Read-only view of client's strategy board
- Sections: Active Formats, Hook Angles Being Tested, Upcoming Themes, Notes from Manager
- "Last updated" timestamp

### Messages (`/messages`)
- Chat UI: message thread with account manager
- New message input at bottom
- Realtime updates
- Manager name + avatar shown in header

### Billing (`/billing`)
- Plan card: tier name, price, next charge date
- Payment method card: card brand + last 4
- "Update payment method" button → Stripe portal
- Invoice history table: date, amount, status, PDF download link

---

## Admin Panel Pages

### Client List (`/admin/clients`)
- Table: name, company, plan, status, last active, footage submissions (count), unread messages badge
- Search + filter by status / plan
- "Invite new client" button

### Client Detail (`/admin/clients/[id]`)
Tabbed view:
- **Overview**: contact info, plan, account manager assignment, edit fields
- **Footage**: all submissions with download links
- **Clips**: clip library + upload new clip form
- **Performance**: same view as client, plus raw API data
- **Strategy**: editable strategy board
- **Messages**: full thread
- **Billing**: Stripe subscription status, plan change, cancel

### Invites (`/admin/invites`)
- Form: email, name, company, plan tier → send invite
- List of pending/accepted invites with resend option

---

## Social API Integration

### Architecture
- VyrulHQ authenticates once per managed account (not per client)
- Tokens stored encrypted in `social_accounts`
- Daily Vercel cron at `/api/cron/sync-stats` fetches and caches stats

### Platform Notes
| Platform | API | Auth |
|---|---|---|
| TikTok | TikTok for Business Content API | OAuth 2.0, Business account required |
| Instagram | Meta Graph API | Facebook Business OAuth, Instagram Business/Creator account |
| YouTube | YouTube Data API v3 | Google OAuth, quota: 10,000 units/day (sufficient for daily cron) |

### Failure Handling
- Failed sync logged to `sync_errors` table with platform + error message
- Stale data shown with "Last updated X hours ago" warning
- Admin alerted via email (Resend) if sync fails 2+ consecutive days

---

## What's in V1 vs Deferred

### V1
- Google OAuth invite-only auth
- Full client portal (all 7 sections)
- Full admin panel (client management, clip uploads, messaging, strategy editor)
- Stripe subscription billing + customer portal
- Social stats for TikTok, Instagram, YouTube (daily cron cache)
- Supabase Realtime messaging
- 3-step onboarding wizard

### Deferred to V2
- Client self-serve plan upgrade/downgrade
- Clip approval flows
- Deeper analytics (per-clip breakdowns, cohort views)
- Bulk footage upload
- Automated clip delivery notifications (email/SMS)
- Billing history export (CSV)
- White-label portal (custom domain per client)

---

## Open Items

- Confirm max footage file size limit (4GB assumed — Supabase Storage supports up to 5GB per file on Pro plan)
- Decide whether strategy board is rich text (Tiptap) or structured blocks (custom JSON)
- Confirm which Stripe plan IDs map to which tier during invite setup
- TikTok Business API access requires approval — apply early, may have waitlist
