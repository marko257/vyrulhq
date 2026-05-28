# VyrulHQ Portal — Content Calendar & Per-Clip Performance Design

**Date:** 2026-05-26
**Status:** Draft (awaiting Marko review)
**Supersedes:** strategy_boards + performance_snapshots from the original portal spec
**Phased delivery:** Plan 5 = calendar foundation (this spec). Plans 6/7/8 = per-platform automated stat sync (separate specs).

---

## 1. Why this exists

The original portal had two passive features that don't match how the client actually thinks about their content:

1. **Performance page** showed account-level metrics (followers, comments, shares). But VyrulHQ owns the fan pages — the client doesn't own those accounts. Follower growth on a page they don't own is noise.
2. **Strategy board** was a static text document with no timeline. It didn't show what was happening, what was coming, or what action the client needed to take.

This spec redesigns both around the actual question the client is asking: **"What did you post for me, how is it doing, and what do you need from me next?"**

---

## 2. Goals

- Give the client a single page that shows: clips posted, clips in production, clips upcoming, gaps where we need footage.
- Show per-clip view counts (the only platform metric that matters to the client — it measures audience reach for their content, not their fan page).
- Let the account manager assign dates, statuses, and asks per clip without leaving the admin panel.
- Phase platform-stat automation as separate plans — the calendar must work with manually-entered view counts so it ships without waiting on API approvals.

## 3. Non-goals (this plan)

- Automated stat pulling from TikTok / Instagram / YouTube (Plans 6–8)
- OAuth account connection flow (Plans 6–8)
- Click-through tracking (deferred — link strategy not yet decided)
- Client-authored asks (admin-only for V1)
- Approval workflow on clips before publishing
- Per-clip likes/comments/shares (only views matter for V1)

---

## 4. Personas

- **Client (any tier):** Logs in to see what's been posted, how each clip performed, what we're working on, and what we need from them.
- **Account manager (admin):** Schedules clips on the calendar, sets clip status as work progresses, fills in view counts (until automation), authors asks for Scale-tier clients.

---

## 5. Core concepts

### 5.1 Clip
A **clip** is one short-form video that VyrulHQ produced for a client. Each clip can be cross-posted to multiple platforms (TikTok / Instagram / YouTube) — but it's one row in the database, with `platforms` as an array.

A clip has a **status** that moves forward as work progresses:

| Status | Meaning | Calendar visual |
|---|---|---|
| `planned` | Footage assigned, not yet started | 🟡 Yellow tile, "Planned" |
| `editing` | Account manager / editor is cutting it | 🟡 Yellow tile, "Editing" |
| `scheduled` | Cut, captioned, queued for post at `scheduled_for` | 🔵 Blue tile, "Scheduled" |
| `published` | Live on its platforms, has `posted_at` | 🟢 Green tile, thumbnail + view count |

A clip also has:
- `scheduled_for` (date) — when it goes / went out. Used for calendar positioning. For `published`, this can also be `posted_at`'s date.
- `views` (bigint) — total views across all platforms it's on. Single rolled-up number for V1. (Per-platform breakdown deferred until automated sync.)
- `stats_updated_at` — last time view count was updated.
- `platform_video_ids` (jsonb) — map of platform → video ID for posted clips. Populated when AM moves clip to `published`. Inert in Plan 5 (no reader). Plans 6/7/8 use these IDs to query each platform's API for view counts.
  - Example: `{"tiktok": "7234567890123456789", "instagram": "C5xY8nXyz12", "youtube": "dQw4w9WgXcQ"}`
  - The admin "Edit clip" form, when transitioning to `published`, requires a URL per platform in `platforms[]`. We parse the video ID out of each URL on save.

### 5.2 Empty slot
The calendar shows **expected slots per day** based on the client's plan tier:

- Starter ($997/mo) = **1 unique clip/day**, 1 platform
- Growth ($1,997/mo) = **2 unique clips/day**, cross-posted to all 3 platforms
- Scale ($3,497/mo) = **3 unique clips/day**, cross-posted to all 3 platforms

If a day has fewer clips assigned than the tier expects, the remaining slots render as **empty slots** with a "Upload needed" prompt that routes the client to `/submit`.

### 5.3 Calendar note (admin "ask")
A `calendar_notes` row is a date-tagged ask from the account manager to the client (e.g. "Send us 10 min from yesterday's livestream"). Shows on a calendar day as a 🔔 badge. Has a `resolved` boolean so the client can mark it done.

**Authoring is admin-only.** Asks only appear in the admin UI for **Scale-tier** clients (Starter/Growth don't get advisory). The client UI shows asks for all tiers, but in practice only Scale clients will have any.

---

## 6. Client-facing pages

### 6.1 Calendar — `/calendar` (replaces `/strategy`)

**Nav change:** Sidebar item "Strategy" → "Calendar". The strategy page route is deleted.

**Two views, user-toggleable, persisted in `localStorage`:**

#### View A — Monthly grid (default)
- 7-day-wide grid, full current month visible
- Header: month name with `<` / `>` to navigate months, "Today" button to jump back
- Each day cell shows:
  - The day number top-left
  - Up to N tiles stacked vertically, where N = plan tier slot count (1 / 2 / 3)
  - Each tile shows: clip thumbnail (if published) OR status pill (if not), platform icons, view count (if published)
  - 🔔 badge in the corner of the cell if there's an unresolved calendar note for that date
  - Empty slots render as dashed-outline tiles with text "Upload needed →"
- Day cell click target priorities:
  - Click on a filled tile → opens clip detail drawer
  - Click on an empty slot → routes to `/submit`
  - Click on the 🔔 badge → opens ask drawer

#### View C — Vertical agenda
- Scrolling vertical list. Today's section pinned at top.
- Each date is a section header: "Tue · May 28" with the day number on the left
- Section body: all tiles for that day stacked, full-width, more detail than the grid view
- Past dates scroll above today (greyed slightly); future dates scroll below
- Empty slots appear inline with "Upload needed →" CTA
- Calendar notes appear as their own list-item at the top of their date's section

**View toggle:** A segmented control top-right ("Month" / "Agenda"). Selection persists across reloads via `localStorage` key `calendar-view-mode`.

#### Clip detail drawer
Opens when user clicks a published-clip tile. Slides in from the right (desktop) or full-screen (mobile).

Contents:
- Clip title
- Thumbnail (full-width inside drawer)
- Platforms (icons) and "Posted on [date]"
- Total views (large)
- Status pill
- "Manager notes" if any (free-text field on `clips`)
- Close button

#### Ask drawer
Opens when user clicks a 🔔 badge.

Contents:
- Ask text
- "Mark done" button (sets `resolved = true` on the calendar_note row)
- Posted date / by whom (admin name)

### 6.2 Performance — `/performance` (reworked)

**Top row — three KPI cards:**
1. **Total views (last 30 days)** — sum of `clips.views` for clips whose `posted_at` is in the last 30 days
2. **Clips published (last 30 days)** — count
3. **Top platform** — which platform appears most in `clips.platforms` across last 30 days' published clips, by view-weighted share

**Middle — Top 5 clips (last 30 days):**
- Compact table: thumbnail, title, posted date, platforms (icons), views
- Click a row → opens the same clip detail drawer as the calendar

**Bottom — Views trend chart:**
- Line chart, 30-day window
- X-axis: date
- Y-axis: daily total views (sum of `clips.views` for clips posted that day) — simple V1 line
- One line, no per-platform split (deferred until per-platform stats land)

**Drop entirely from the page:**
- Follower count, account comments, account shares, daily aggregate snapshots — none of these appear anywhere.

---

## 7. Admin-facing changes

### 7.1 Replace "Strategy" tab on admin client detail

The existing `/admin/clients/[id]?tab=strategy` tab is removed. A new **`?tab=calendar`** tab takes its place.

**Calendar tab contents:**
- Same monthly grid as the client sees, but tiles are interactive — admin can:
  - Drag-free edit (no drag-drop required for V1): click a tile to open an edit form
  - Edit clip: change `status`, `scheduled_for`, `views`, `platforms` (multi-select), `title`, `manager_notes`
  - Click an empty slot → opens "Add clip" form pre-filled with that date as `scheduled_for`
- **Asks panel** below the grid (Scale-tier clients only): list of all `calendar_notes` for this client with add/edit/resolve controls

### 7.2 Clip CRUD endpoints
- `POST /api/admin/clips/[clientId]` — already exists from Plan 4, augment to accept `platforms[]`, `status`, `scheduled_for`, `views`
- `PATCH /api/admin/clips/[clientId]/[clipId]` — new, updates an existing clip
- `DELETE /api/admin/clips/[clientId]/[clipId]` — new, soft delete (sets a `deleted_at` column? Or hard delete? V1: hard delete)

### 7.3 Calendar notes endpoints
- `POST /api/admin/calendar-notes/[clientId]` — admin creates an ask
- `PATCH /api/admin/calendar-notes/[id]` — admin edits note text
- `DELETE /api/admin/calendar-notes/[id]` — admin removes
- `POST /api/calendar-notes/[id]/resolve` — client marks resolved (RLS: client can only resolve their own)

---

## 8. Database changes

### 8.1 `clips` table — alter

Add columns:
```sql
alter table public.clips
  add column scheduled_for date,
  add column status text not null default 'planned'
    check (status in ('planned','editing','scheduled','published')),
  add column views bigint not null default 0,
  add column stats_updated_at timestamptz,
  add column platforms platform_type[] not null default '{}',
  add column manager_notes text,
  add column platform_video_ids jsonb not null default '{}'::jsonb;
```

Migrate existing `platform` column to `platforms[]`:
```sql
update public.clips set platforms = array[platform];
alter table public.clips drop column platform;
```
(Safe — no real clip data yet.)

### 8.2 `calendar_notes` table — new
```sql
create table public.calendar_notes (
  id          uuid primary key default uuid_generate_v4(),
  client_id   uuid not null references public.clients(id) on delete cascade,
  note_date   date not null,
  note        text not null,
  created_by  uuid references auth.users(id),
  resolved    boolean not null default false,
  created_at  timestamptz not null default now()
);

create index calendar_notes_client_date_idx
  on public.calendar_notes(client_id, note_date);

alter table public.calendar_notes enable row level security;

-- Client can read & resolve their own notes
create policy "calendar_notes_read_own" on public.calendar_notes
  for select using (client_id = public.my_client_id());

create policy "calendar_notes_resolve_own" on public.calendar_notes
  for update using (client_id = public.my_client_id())
  with check (client_id = public.my_client_id());
-- Admin uses service role for all writes (no client INSERT/DELETE policy)
```

### 8.3 Drop deprecated tables
```sql
drop table if exists public.strategy_boards cascade;
drop table if exists public.performance_snapshots cascade;
```

Wrap migrations in a single migration file `006_calendar.sql`.

---

## 9. RLS & auth

- Calendar page uses `getCurrentClient()` server-side, then queries clips + calendar_notes via RLS-scoped supabase server client.
- Admin pages use `requireAdmin()` (already exists from Plan 4) then bypass RLS via `supabaseAdmin`.
- Client cannot mutate clips or create/delete asks — only resolve their own asks.

---

## 10. Plan-tier slot count

Constants in `lib/plans.ts`:
```typescript
export const SLOTS_PER_DAY: Record<string, number> = {
  starter: 1,
  growth: 2,
  scale: 3,
}
```

Calendar component reads `client.plan_tier` and uses this map to determine empty-slot count per day.

---

## 11. Out of scope (future plans)

- **Plan 6 — YouTube stat sync:** OAuth connect flow, YouTube Data API v3 integration, cron updates `clips.views` for clips whose `platforms` includes 'youtube'.
- **Plan 7 — TikTok stat sync:** TikTok app approval + Display API + OAuth.
- **Plan 8 — Instagram stat sync:** Meta App Review + Graph API + OAuth.
- **Per-platform view breakdown:** once two or more platforms automated, split `clips.views` into per-platform columns (e.g., `views_tiktok`, `views_instagram`, `views_youtube`).
- **Click-through tracking:** depends on link-in-bio strategy (TBD).
- **Drag-and-drop calendar scheduling:** V1 uses click-to-edit; drag-drop is a nice-to-have.
- **Client-authored asks / requests:** V1 admin-only.

---

## 12. Open questions resolved during brainstorming

| Question | Decision |
|---|---|
| Calendar layout style | Option A (monthly grid) + Option C (vertical agenda), user toggle persisted in localStorage |
| Track click-throughs? | No — defer until link strategy decided |
| One tile per cross-posted clip, or one per platform? | One tile per clip, platform icons inside |
| Plan-tier slot counts | Starter=1, Growth=2, Scale=3 unique clips/day |
| Can clients author asks? | No — admin-only |
| Replace "Strategy" in nav? | Yes — rename to "Calendar" |
| Performance KPIs | Total views (30d), Clips published (30d), Top platform |
| `clips.platform` → `clips.platforms[]` | Yes, breaking change OK (no real data yet) |
| Stat entry V1 | Manual (admin types in views). Automated per-platform sync = Plans 6–8 |

---

## 13. Acceptance criteria

A successful Plan 5 implementation means:
- [ ] Client can visit `/calendar`, see the current month with all their clips, switch to agenda view, click published clips to see stats, click empty slots to upload
- [ ] Client can see and resolve admin asks (🔔 badges)
- [ ] Admin can manage a client's calendar from `/admin/clients/[id]?tab=calendar`: add clips, edit status / date / views / platforms, author asks for Scale clients
- [ ] Performance page shows the 3 KPI cards, top 5 clips, views trend chart
- [ ] Old strategy page returns 404 (route deleted); old performance tabbed UI replaced
- [ ] Database migration `006_calendar.sql` runs cleanly, drops `strategy_boards` and `performance_snapshots`, alters `clips`, creates `calendar_notes`
- [ ] No regressions in messages, billing, footage upload, dashboard, admin invites
- [ ] All existing tests still pass; new tests cover the calendar data layer and API routes

---
