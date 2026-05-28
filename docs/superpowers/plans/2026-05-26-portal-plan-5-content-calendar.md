# Content Calendar & Per-Clip Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static strategy board with a live content calendar (monthly grid + agenda toggle) and rework performance to per-clip metrics.

**Architecture:** Server components fetch clips and calendar notes; a client-side `CalendarView` handles the month/agenda toggle (persisted to localStorage) and opens drawers for clip detail / asks. Admin gets a new calendar tab on the client detail page with CRUD endpoints. `clips` schema is reworked to `platforms text[]`, with status state machine and per-clip view count. `calendar_notes` is a new table; `strategy_boards` and `performance_snapshots` are dropped.

**Tech Stack:** Next.js 14 App Router (server + client components), Supabase (Postgres + RLS), Tailwind with CSS variable brand tokens, Zod, Jest (ts-jest), lucide-react.

**Spec:** `/Users/markonikolic/Documents/Claude/Projects/VyrulHQ/docs/superpowers/specs/2026-05-26-content-calendar-design.md`

**Project root:** `/Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal`

---

## File Structure

**New files:**
- `supabase/migrations/006_calendar.sql` — schema migration (drop deprecated tables, alter `clips`, create `calendar_notes`)
- `lib/plans.ts` — `SLOTS_PER_DAY` constant
- `lib/platform-urls.ts` — `parsePlatformVideoId(url, platform)` URL parsing helper
- `lib/calendar.ts` — `getMonthGrid`, `groupClipsByDate`, `buildDaySlots`
- `app/(portal)/calendar/page.tsx` — server component, fetches data
- `app/(portal)/calendar/calendar-view.tsx` — client component, month/agenda toggle
- `app/(portal)/calendar/clip-drawer.tsx` — clip detail drawer
- `app/(portal)/calendar/ask-drawer.tsx` — calendar-note drawer
- `app/api/calendar-notes/[id]/resolve/route.ts` — client resolves their own note
- `app/api/admin/calendar-notes/[clientId]/route.ts` — admin creates note
- `app/api/admin/calendar-notes/[id]/route.ts` — admin updates / deletes note
- `app/api/admin/clips/[clientId]/[clipId]/route.ts` — admin patch / delete individual clip
- `app/admin/clients/[id]/calendar-editor.tsx` — admin calendar tab UI
- `__tests__/lib/plans.test.ts`
- `__tests__/lib/platform-urls.test.ts`
- `__tests__/lib/calendar.test.ts`
- `__tests__/api/calendar-notes-resolve.test.ts`
- `__tests__/api/admin-calendar-notes.test.ts`
- `__tests__/api/admin-clips-update.test.ts`

**Modified files:**
- `components/portal-sidebar.tsx` — rename Strategy → Calendar
- `app/api/admin/clips/[id]/route.ts` — augment POST schema for new clip fields
- `app/admin/clients/[id]/page.tsx` — replace strategy tab with calendar tab; update fetch for new clip schema
- `app/(portal)/performance/page.tsx` — rewrite for per-clip metrics
- `app/(portal)/clips/page.tsx` — use `platforms[]` instead of `platform`
- `app/(portal)/clips/clip-grid.tsx` — render `platforms[]` icons

**Deleted files:**
- `app/(portal)/strategy/page.tsx`
- `app/admin/clients/[id]/strategy-editor.tsx`
- `app/api/admin/strategy/[id]/route.ts`
- `app/(portal)/performance/range-tabs.tsx` (no longer needed; new performance page is fixed at 30d)

---

## Task 1: Database migration `006_calendar.sql`

**Files:**
- Create: `supabase/migrations/006_calendar.sql`

- [ ] **Step 1: Write the migration file**

Create `supabase/migrations/006_calendar.sql`:

```sql
-- ============================================================
-- Plan 5: Content Calendar migration
-- Drops strategy_boards + performance_snapshots
-- Alters clips: status, scheduled_for, platforms[], views,
--   stats_updated_at, manager_notes, platform_video_ids
-- Creates calendar_notes
-- ============================================================

-- 1. Drop deprecated tables
drop table if exists public.strategy_boards cascade;
drop table if exists public.performance_snapshots cascade;

-- 2. Alter clips table
alter table public.clips
  add column if not exists scheduled_for date,
  add column if not exists status text not null default 'planned'
    check (status in ('planned','editing','scheduled','published')),
  add column if not exists stats_updated_at timestamptz,
  add column if not exists platforms platform_type[] not null default '{}',
  add column if not exists manager_notes text,
  add column if not exists platform_video_ids jsonb not null default '{}'::jsonb;

-- Migrate existing single `platform` column into platforms[] (idempotent)
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'clips' and column_name = 'platform'
  ) then
    update public.clips
      set platforms = array[platform]::platform_type[]
      where platforms = '{}'::platform_type[];
    alter table public.clips drop column platform;
  end if;
end $$;

-- Index for calendar-style date lookups
create index if not exists clips_client_scheduled_idx
  on public.clips(client_id, scheduled_for);

-- 3. Create calendar_notes table
create table if not exists public.calendar_notes (
  id          uuid primary key default uuid_generate_v4(),
  client_id   uuid not null references public.clients(id) on delete cascade,
  note_date   date not null,
  note        text not null,
  created_by  uuid references auth.users(id),
  resolved    boolean not null default false,
  created_at  timestamptz not null default now()
);

create index if not exists calendar_notes_client_date_idx
  on public.calendar_notes(client_id, note_date);

alter table public.calendar_notes enable row level security;

-- Client may read their own notes
drop policy if exists "calendar_notes_read_own" on public.calendar_notes;
create policy "calendar_notes_read_own" on public.calendar_notes
  for select using (client_id = public.my_client_id());

-- Client may resolve (update) their own notes — used by /api/calendar-notes/:id/resolve
drop policy if exists "calendar_notes_update_own" on public.calendar_notes;
create policy "calendar_notes_update_own" on public.calendar_notes
  for update using (client_id = public.my_client_id())
  with check (client_id = public.my_client_id());
-- Admin writes use service role (no client INSERT/DELETE policy needed)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add supabase/migrations/006_calendar.sql
git commit -m "feat: migration 006 — calendar schema rework"
```

> **Manual step (NOT automated):** Open Supabase SQL Editor and run this migration against the production database. The build will fail at runtime if not run, but the code does not block on it.

---

## Task 2: Plan-tier slot count constant

**Files:**
- Create: `lib/plans.ts`
- Test: `__tests__/lib/plans.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/lib/plans.test.ts`:

```typescript
import { SLOTS_PER_DAY, slotsForTier } from '@/lib/plans'

describe('SLOTS_PER_DAY', () => {
  it('defines slot counts for all three tiers', () => {
    expect(SLOTS_PER_DAY.starter).toBe(1)
    expect(SLOTS_PER_DAY.growth).toBe(2)
    expect(SLOTS_PER_DAY.scale).toBe(3)
  })
})

describe('slotsForTier', () => {
  it('returns the correct count for known tiers', () => {
    expect(slotsForTier('starter')).toBe(1)
    expect(slotsForTier('growth')).toBe(2)
    expect(slotsForTier('scale')).toBe(3)
  })

  it('returns 1 for unknown tier (safe default)', () => {
    expect(slotsForTier('unknown')).toBe(1)
    expect(slotsForTier('')).toBe(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx jest __tests__/lib/plans.test.ts
```

Expected: FAIL with "Cannot find module '@/lib/plans'"

- [ ] **Step 3: Write the implementation**

Create `lib/plans.ts`:

```typescript
export const SLOTS_PER_DAY: Record<string, number> = {
  starter: 1,
  growth: 2,
  scale: 3,
}

export function slotsForTier(tier: string): number {
  return SLOTS_PER_DAY[tier] ?? 1
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx jest __tests__/lib/plans.test.ts
```

Expected: PASS, all tests green.

- [ ] **Step 5: Commit**

```bash
git add lib/plans.ts __tests__/lib/plans.test.ts
git commit -m "feat: plan-tier slot constants"
```

---

## Task 3: Platform URL parsing helper

**Files:**
- Create: `lib/platform-urls.ts`
- Test: `__tests__/lib/platform-urls.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/lib/platform-urls.test.ts`:

```typescript
import { parsePlatformVideoId } from '@/lib/platform-urls'

describe('parsePlatformVideoId — youtube', () => {
  it('parses youtu.be short URLs', () => {
    expect(parsePlatformVideoId('https://youtu.be/dQw4w9WgXcQ', 'youtube'))
      .toBe('dQw4w9WgXcQ')
  })

  it('parses youtube.com watch URLs', () => {
    expect(parsePlatformVideoId('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'youtube'))
      .toBe('dQw4w9WgXcQ')
  })

  it('parses youtube shorts URLs', () => {
    expect(parsePlatformVideoId('https://www.youtube.com/shorts/abc123XYZ_-', 'youtube'))
      .toBe('abc123XYZ_-')
  })

  it('returns null on a malformed youtube URL', () => {
    expect(parsePlatformVideoId('not a url', 'youtube')).toBeNull()
  })
})

describe('parsePlatformVideoId — tiktok', () => {
  it('parses tiktok video URLs with @username', () => {
    expect(parsePlatformVideoId('https://www.tiktok.com/@somebody/video/7234567890123456789', 'tiktok'))
      .toBe('7234567890123456789')
  })

  it('handles trailing query string', () => {
    expect(parsePlatformVideoId('https://www.tiktok.com/@somebody/video/7234567890123456789?is_from_webapp=1', 'tiktok'))
      .toBe('7234567890123456789')
  })

  it('returns null on malformed tiktok URL', () => {
    expect(parsePlatformVideoId('https://www.tiktok.com/foo', 'tiktok')).toBeNull()
  })
})

describe('parsePlatformVideoId — instagram', () => {
  it('parses instagram reel URLs', () => {
    expect(parsePlatformVideoId('https://www.instagram.com/reel/C5xY8nXyz12/', 'instagram'))
      .toBe('C5xY8nXyz12')
  })

  it('parses instagram p/ post URLs', () => {
    expect(parsePlatformVideoId('https://www.instagram.com/p/C5xY8nXyz12/?utm_source=ig', 'instagram'))
      .toBe('C5xY8nXyz12')
  })

  it('returns null on malformed instagram URL', () => {
    expect(parsePlatformVideoId('https://instagram.com/somebody', 'instagram')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx jest __tests__/lib/platform-urls.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `lib/platform-urls.ts`:

```typescript
export type Platform = 'tiktok' | 'instagram' | 'youtube'

/**
 * Extracts the platform-native video ID from a URL.
 * Returns null if the URL doesn't match the expected platform pattern.
 *
 * Examples:
 *   parsePlatformVideoId('https://youtu.be/dQw4w9WgXcQ', 'youtube') -> 'dQw4w9WgXcQ'
 *   parsePlatformVideoId('https://www.tiktok.com/@x/video/7234567890', 'tiktok') -> '7234567890'
 *   parsePlatformVideoId('https://www.instagram.com/reel/C5xY8/', 'instagram') -> 'C5xY8'
 */
export function parsePlatformVideoId(url: string, platform: Platform): string | null {
  if (!url || typeof url !== 'string') return null

  try {
    const u = new URL(url)

    if (platform === 'youtube') {
      // youtu.be/<id>
      if (u.hostname === 'youtu.be') {
        return u.pathname.replace(/^\//, '').split('/')[0] || null
      }
      // youtube.com/watch?v=<id>
      const v = u.searchParams.get('v')
      if (v) return v
      // youtube.com/shorts/<id>
      const shortsMatch = u.pathname.match(/^\/shorts\/([^/?]+)/)
      if (shortsMatch) return shortsMatch[1]
      return null
    }

    if (platform === 'tiktok') {
      const m = u.pathname.match(/\/video\/(\d+)/)
      return m ? m[1] : null
    }

    if (platform === 'instagram') {
      const m = u.pathname.match(/\/(?:reel|p|reels)\/([^/]+)/)
      return m ? m[1] : null
    }

    return null
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx jest __tests__/lib/platform-urls.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/platform-urls.ts __tests__/lib/platform-urls.test.ts
git commit -m "feat: platform URL → video ID parser"
```

---

## Task 4: Calendar grid helpers

**Files:**
- Create: `lib/calendar.ts`
- Test: `__tests__/lib/calendar.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/lib/calendar.test.ts`:

```typescript
import { getMonthGrid, groupClipsByDate, buildDaySlots } from '@/lib/calendar'

describe('getMonthGrid', () => {
  it('returns 42 cells (6 weeks × 7 days) for any month', () => {
    const grid = getMonthGrid(2026, 4) // May 2026 (month is 0-indexed)
    expect(grid).toHaveLength(42)
  })

  it('pads with previous-month days at the start (Sunday-first)', () => {
    // May 1 2026 is a Friday → grid[0..4] are April days
    const grid = getMonthGrid(2026, 4)
    expect(grid[0].inMonth).toBe(false) // April day
    expect(grid[5].inMonth).toBe(true)  // May 1
    expect(grid[5].date.getDate()).toBe(1)
  })

  it('marks every day in the target month as inMonth=true', () => {
    const grid = getMonthGrid(2026, 4) // May 2026 has 31 days
    const inMonth = grid.filter((c) => c.inMonth)
    expect(inMonth).toHaveLength(31)
  })

  it('includes a stable ISO date string per cell', () => {
    const grid = getMonthGrid(2026, 4)
    const may1 = grid.find((c) => c.inMonth && c.date.getDate() === 1)!
    expect(may1.iso).toBe('2026-05-01')
  })
})

describe('groupClipsByDate', () => {
  it('keys clips by scheduled_for ISO date string', () => {
    const clips = [
      { id: 'a', scheduled_for: '2026-05-10' },
      { id: 'b', scheduled_for: '2026-05-10' },
      { id: 'c', scheduled_for: '2026-05-11' },
      { id: 'd', scheduled_for: null },
    ]
    const grouped = groupClipsByDate(clips)
    expect(grouped['2026-05-10']).toHaveLength(2)
    expect(grouped['2026-05-11']).toHaveLength(1)
    expect(grouped['null']).toBeUndefined()
  })

  it('returns empty object for empty input', () => {
    expect(groupClipsByDate([])).toEqual({})
  })
})

describe('buildDaySlots', () => {
  it('pads with empty slots up to slotCount', () => {
    const clips = [{ id: 'a' }]
    const slots = buildDaySlots(clips, 3)
    expect(slots).toHaveLength(3)
    expect(slots[0].kind).toBe('clip')
    expect(slots[1].kind).toBe('empty')
    expect(slots[2].kind).toBe('empty')
  })

  it('returns all clips when count >= slotCount (no truncation)', () => {
    const clips = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]
    const slots = buildDaySlots(clips, 2)
    expect(slots).toHaveLength(4)
    expect(slots.every((s) => s.kind === 'clip')).toBe(true)
  })

  it('returns N empty slots for empty input', () => {
    expect(buildDaySlots([], 2)).toEqual([
      { kind: 'empty' },
      { kind: 'empty' },
    ])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx jest __tests__/lib/calendar.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `lib/calendar.ts`:

```typescript
export interface MonthCell {
  date: Date
  inMonth: boolean
  iso: string // 'YYYY-MM-DD'
}

/**
 * Builds a 42-cell (6 weeks × 7 days) Sunday-first calendar grid for a given month.
 * Cells outside the target month are still returned so the grid renders cleanly.
 */
export function getMonthGrid(year: number, month: number): MonthCell[] {
  const first = new Date(year, month, 1)
  const startOffset = first.getDay() // 0 = Sunday
  const start = new Date(year, month, 1 - startOffset)

  const cells: MonthCell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    cells.push({
      date: d,
      inMonth: d.getMonth() === month,
      iso: toIso(d),
    })
  }
  return cells
}

function toIso(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

interface DatedClip {
  id: string
  scheduled_for: string | null
}

export function groupClipsByDate<T extends DatedClip>(clips: T[]): Record<string, T[]> {
  const result: Record<string, T[]> = {}
  for (const c of clips) {
    if (!c.scheduled_for) continue
    const key = c.scheduled_for
    if (!result[key]) result[key] = []
    result[key].push(c)
  }
  return result
}

export type Slot<T> =
  | { kind: 'clip'; clip: T }
  | { kind: 'empty' }

export function buildDaySlots<T>(clips: T[], slotCount: number): Slot<T>[] {
  const slots: Slot<T>[] = clips.map((clip) => ({ kind: 'clip', clip }))
  while (slots.length < slotCount) {
    slots.push({ kind: 'empty' })
  }
  return slots
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx jest __tests__/lib/calendar.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/calendar.ts __tests__/lib/calendar.test.ts
git commit -m "feat: calendar grid + clip grouping helpers"
```

---

## Task 5: Augment admin clip POST to accept new fields

**Files:**
- Modify: `app/api/admin/clips/[id]/route.ts`
- Test: `__tests__/api/admin-clips-update.test.ts` (covers both POST + future PATCH)

- [ ] **Step 1: Write the failing test for new POST fields**

Create `__tests__/api/admin-clips-update.test.ts`:

```typescript
import { NextRequest } from 'next/server'

jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(),
}))

jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: { from: jest.fn() },
}))

const { createClient } = jest.requireMock('@/lib/supabase/server')
const { supabaseAdmin } = jest.requireMock('@/lib/supabase/admin')

function asAdmin() {
  createClient.mockReturnValue({
    auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1', app_metadata: { role: 'admin' } } } }) },
  })
}

function asAnonymous() {
  createClient.mockReturnValue({
    auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
  })
}

function makeReq(body: unknown) {
  return new NextRequest('http://localhost/api/admin/clips/client-1', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('POST /api/admin/clips/[id] (augmented)', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 when not admin', async () => {
    asAnonymous()
    const { POST } = require('@/app/api/admin/clips/[id]/route')
    const res = await POST(makeReq({}), { params: { id: 'client-1' } })
    expect(res.status).toBe(401)
  })

  it('accepts the new fields and inserts them', async () => {
    asAdmin()
    const insert = jest.fn().mockResolvedValue({ error: null })
    supabaseAdmin.from.mockReturnValue({ insert })

    const { POST } = require('@/app/api/admin/clips/[id]/route')
    const res = await POST(makeReq({
      title: 'Hook clip',
      platforms: ['tiktok', 'instagram'],
      status: 'scheduled',
      scheduled_for: '2026-06-01',
      thumbnail_url: null,
      video_url: null,
      views: 0,
      manager_notes: 'cross-post next week',
      platform_video_ids: {},
    }), { params: { id: 'client-1' } })

    expect(res.status).toBe(201)
    expect(insert).toHaveBeenCalledWith(expect.objectContaining({
      client_id: 'client-1',
      title: 'Hook clip',
      platforms: ['tiktok', 'instagram'],
      status: 'scheduled',
      scheduled_for: '2026-06-01',
      manager_notes: 'cross-post next week',
    }))
  })

  it('rejects invalid status', async () => {
    asAdmin()
    const { POST } = require('@/app/api/admin/clips/[id]/route')
    const res = await POST(makeReq({
      title: 't',
      platforms: ['tiktok'],
      status: 'bogus',
    }), { params: { id: 'client-1' } })
    expect(res.status).toBe(400)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npx jest __tests__/api/admin-clips-update.test.ts -t "augmented"
```

Expected: FAIL — current schema rejects `platforms` and `status`.

- [ ] **Step 3: Rewrite `app/api/admin/clips/[id]/route.ts`**

Replace the file with:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

const PlatformEnum = z.enum(['tiktok', 'instagram', 'youtube'])

const ClipSchema = z.object({
  title: z.string().min(1),
  platforms: z.array(PlatformEnum).default([]),
  status: z.enum(['planned', 'editing', 'scheduled', 'published']).default('planned'),
  scheduled_for: z.string().nullable().optional(),
  thumbnail_url: z.string().url().nullable().optional(),
  video_url: z.string().url().nullable().optional(),
  views: z.number().int().nonnegative().nullable().optional(),
  manager_notes: z.string().nullable().optional(),
  platform_video_ids: z.record(z.string(), z.string()).default({}),
})

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const raw = await request.json().catch(() => null)
  const parsed = ClipSchema.safeParse(raw)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  const row = {
    client_id: params.id,
    title: parsed.data.title,
    platforms: parsed.data.platforms,
    status: parsed.data.status,
    scheduled_for: parsed.data.scheduled_for ?? null,
    thumbnail_url: parsed.data.thumbnail_url ?? null,
    video_url: parsed.data.video_url ?? null,
    views: parsed.data.views ?? 0,
    manager_notes: parsed.data.manager_notes ?? null,
    platform_video_ids: parsed.data.platform_video_ids,
  }

  const { error } = await supabaseAdmin.from('clips').insert(row)
  if (error) return NextResponse.json({ error: 'Failed to create clip' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 201 })
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx jest __tests__/api/admin-clips-update.test.ts -t "augmented"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/admin/clips/\[id\]/route.ts __tests__/api/admin-clips-update.test.ts
git commit -m "feat: admin clip POST accepts platforms[], status, scheduled_for, platform_video_ids"
```

---

## Task 6: Admin PATCH + DELETE for individual clips

**Files:**
- Create: `app/api/admin/clips/[id]/[clipId]/route.ts`
- Test: append to `__tests__/api/admin-clips-update.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `__tests__/api/admin-clips-update.test.ts`:

```typescript
describe('PATCH /api/admin/clips/[id]/[clipId]', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 when not admin', async () => {
    asAnonymous()
    const { PATCH } = require('@/app/api/admin/clips/[id]/[clipId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const res = await PATCH(req, { params: { id: 'c1', clipId: 'clip1' } })
    expect(res.status).toBe(401)
  })

  it('updates the clip with partial fields', async () => {
    asAdmin()
    const eq2 = jest.fn().mockResolvedValue({ error: null })
    const eq1 = jest.fn().mockReturnValue({ eq: eq2 })
    const update = jest.fn().mockReturnValue({ eq: eq1 })
    supabaseAdmin.from.mockReturnValue({ update })

    const { PATCH } = require('@/app/api/admin/clips/[id]/[clipId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'published', views: 1234 }),
    })
    const res = await PATCH(req, { params: { id: 'c1', clipId: 'clip1' } })

    expect(res.status).toBe(200)
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ status: 'published', views: 1234 }))
    expect(eq1).toHaveBeenCalledWith('id', 'clip1')
    expect(eq2).toHaveBeenCalledWith('client_id', 'c1')
  })

  it('sets stats_updated_at when views is patched', async () => {
    asAdmin()
    const eq2 = jest.fn().mockResolvedValue({ error: null })
    const eq1 = jest.fn().mockReturnValue({ eq: eq2 })
    const update = jest.fn().mockReturnValue({ eq: eq1 })
    supabaseAdmin.from.mockReturnValue({ update })

    const { PATCH } = require('@/app/api/admin/clips/[id]/[clipId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ views: 999 }),
    })
    await PATCH(req, { params: { id: 'c1', clipId: 'clip1' } })

    const args = update.mock.calls[0][0]
    expect(args.stats_updated_at).toBeDefined()
  })
})

describe('DELETE /api/admin/clips/[id]/[clipId]', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 when not admin', async () => {
    asAnonymous()
    const { DELETE } = require('@/app/api/admin/clips/[id]/[clipId]/route')
    const req = new NextRequest('http://localhost/x', { method: 'DELETE' })
    const res = await DELETE(req, { params: { id: 'c1', clipId: 'clip1' } })
    expect(res.status).toBe(401)
  })

  it('deletes the clip scoped by client + clip', async () => {
    asAdmin()
    const eq2 = jest.fn().mockResolvedValue({ error: null })
    const eq1 = jest.fn().mockReturnValue({ eq: eq2 })
    const del = jest.fn().mockReturnValue({ eq: eq1 })
    supabaseAdmin.from.mockReturnValue({ delete: del })

    const { DELETE } = require('@/app/api/admin/clips/[id]/[clipId]/route')
    const req = new NextRequest('http://localhost/x', { method: 'DELETE' })
    const res = await DELETE(req, { params: { id: 'c1', clipId: 'clip1' } })

    expect(res.status).toBe(204)
    expect(del).toHaveBeenCalled()
    expect(eq1).toHaveBeenCalledWith('id', 'clip1')
    expect(eq2).toHaveBeenCalledWith('client_id', 'c1')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npx jest __tests__/api/admin-clips-update.test.ts -t "PATCH /api/admin/clips"
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create the route file**

Create `app/api/admin/clips/[id]/[clipId]/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

const PlatformEnum = z.enum(['tiktok', 'instagram', 'youtube'])

const PatchSchema = z.object({
  title: z.string().min(1).optional(),
  platforms: z.array(PlatformEnum).optional(),
  status: z.enum(['planned', 'editing', 'scheduled', 'published']).optional(),
  scheduled_for: z.string().nullable().optional(),
  thumbnail_url: z.string().url().nullable().optional(),
  video_url: z.string().url().nullable().optional(),
  views: z.number().int().nonnegative().optional(),
  manager_notes: z.string().nullable().optional(),
  platform_video_ids: z.record(z.string(), z.string()).optional(),
})

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string; clipId: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const raw = await request.json().catch(() => null)
  const parsed = PatchSchema.safeParse(raw)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  const updates: Record<string, unknown> = { ...parsed.data }
  if ('views' in parsed.data) {
    updates.stats_updated_at = new Date().toISOString()
  }

  const { error } = await supabaseAdmin
    .from('clips')
    .update(updates)
    .eq('id', params.clipId)
    .eq('client_id', params.id)

  if (error) return NextResponse.json({ error: 'Failed to update clip' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 200 })
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string; clipId: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { error } = await supabaseAdmin
    .from('clips')
    .delete()
    .eq('id', params.clipId)
    .eq('client_id', params.id)

  if (error) return NextResponse.json({ error: 'Failed to delete clip' }, { status: 500 })
  return new NextResponse(null, { status: 204 })
}
```

- [ ] **Step 4: Run the tests**

```bash
npx jest __tests__/api/admin-clips-update.test.ts
```

Expected: PASS — all groups green.

- [ ] **Step 5: Commit**

```bash
git add app/api/admin/clips/\[id\]/\[clipId\]/route.ts __tests__/api/admin-clips-update.test.ts
git commit -m "feat: admin PATCH/DELETE individual clip"
```

---

## Task 7: Admin calendar_notes API (POST / PATCH / DELETE)

**Files:**
- Create: `app/api/admin/calendar-notes/[clientId]/route.ts`
- Create: `app/api/admin/calendar-notes/[id]/route.ts`
- Test: `__tests__/api/admin-calendar-notes.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `__tests__/api/admin-calendar-notes.test.ts`:

```typescript
import { NextRequest } from 'next/server'

jest.mock('@/lib/supabase/server', () => ({ createClient: jest.fn() }))
jest.mock('@/lib/supabase/admin', () => ({ supabaseAdmin: { from: jest.fn() } }))

const { createClient } = jest.requireMock('@/lib/supabase/server')
const { supabaseAdmin } = jest.requireMock('@/lib/supabase/admin')

function asAdmin() {
  createClient.mockReturnValue({
    auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1', app_metadata: { role: 'admin' } } } }) },
  })
}
function asAnonymous() {
  createClient.mockReturnValue({
    auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
  })
}

describe('POST /api/admin/calendar-notes/[clientId]', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 when not admin', async () => {
    asAnonymous()
    const { POST } = require('@/app/api/admin/calendar-notes/[clientId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const res = await POST(req, { params: { clientId: 'c1' } })
    expect(res.status).toBe(401)
  })

  it('creates a note with client_id, note_date, note, created_by', async () => {
    asAdmin()
    const insert = jest.fn().mockResolvedValue({ error: null })
    supabaseAdmin.from.mockReturnValue({ insert })

    const { POST } = require('@/app/api/admin/calendar-notes/[clientId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note_date: '2026-06-01', note: 'send footage' }),
    })
    const res = await POST(req, { params: { clientId: 'c1' } })

    expect(res.status).toBe(201)
    expect(insert).toHaveBeenCalledWith(expect.objectContaining({
      client_id: 'c1',
      note_date: '2026-06-01',
      note: 'send footage',
      created_by: 'u1',
    }))
  })

  it('rejects missing note text', async () => {
    asAdmin()
    const { POST } = require('@/app/api/admin/calendar-notes/[clientId]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note_date: '2026-06-01' }),
    })
    const res = await POST(req, { params: { clientId: 'c1' } })
    expect(res.status).toBe(400)
  })
})

describe('PATCH /api/admin/calendar-notes/[id]', () => {
  beforeEach(() => jest.clearAllMocks())

  it('updates the note text and resolved state', async () => {
    asAdmin()
    const eq = jest.fn().mockResolvedValue({ error: null })
    const update = jest.fn().mockReturnValue({ eq })
    supabaseAdmin.from.mockReturnValue({ update })

    const { PATCH } = require('@/app/api/admin/calendar-notes/[id]/route')
    const req = new NextRequest('http://localhost/x', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: 'updated', resolved: true }),
    })
    const res = await PATCH(req, { params: { id: 'n1' } })

    expect(res.status).toBe(200)
    expect(update).toHaveBeenCalledWith({ note: 'updated', resolved: true })
    expect(eq).toHaveBeenCalledWith('id', 'n1')
  })
})

describe('DELETE /api/admin/calendar-notes/[id]', () => {
  beforeEach(() => jest.clearAllMocks())

  it('deletes the note by id', async () => {
    asAdmin()
    const eq = jest.fn().mockResolvedValue({ error: null })
    const del = jest.fn().mockReturnValue({ eq })
    supabaseAdmin.from.mockReturnValue({ delete: del })

    const { DELETE } = require('@/app/api/admin/calendar-notes/[id]/route')
    const req = new NextRequest('http://localhost/x', { method: 'DELETE' })
    const res = await DELETE(req, { params: { id: 'n1' } })

    expect(res.status).toBe(204)
    expect(eq).toHaveBeenCalledWith('id', 'n1')
  })
})
```

- [ ] **Step 2: Run the failing tests**

```bash
npx jest __tests__/api/admin-calendar-notes.test.ts
```

Expected: FAIL — modules not found.

- [ ] **Step 3: Create both route files**

Create `app/api/admin/calendar-notes/[clientId]/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

const CreateSchema = z.object({
  note_date: z.string().min(1),
  note: z.string().min(1),
})

export async function POST(
  request: NextRequest,
  { params }: { params: { clientId: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const raw = await request.json().catch(() => null)
  const parsed = CreateSchema.safeParse(raw)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  const { error } = await supabaseAdmin.from('calendar_notes').insert({
    client_id: params.clientId,
    note_date: parsed.data.note_date,
    note: parsed.data.note,
    created_by: user.id,
  })

  if (error) return NextResponse.json({ error: 'Failed to create note' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 201 })
}
```

Create `app/api/admin/calendar-notes/[id]/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

const PatchSchema = z.object({
  note: z.string().min(1).optional(),
  resolved: z.boolean().optional(),
  note_date: z.string().min(1).optional(),
})

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const raw = await request.json().catch(() => null)
  const parsed = PatchSchema.safeParse(raw)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  const { error } = await supabaseAdmin
    .from('calendar_notes')
    .update(parsed.data)
    .eq('id', params.id)

  if (error) return NextResponse.json({ error: 'Failed to update note' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 200 })
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { error } = await supabaseAdmin
    .from('calendar_notes')
    .delete()
    .eq('id', params.id)

  if (error) return NextResponse.json({ error: 'Failed to delete note' }, { status: 500 })
  return new NextResponse(null, { status: 204 })
}
```

- [ ] **Step 4: Run tests**

```bash
npx jest __tests__/api/admin-calendar-notes.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/admin/calendar-notes __tests__/api/admin-calendar-notes.test.ts
git commit -m "feat: admin calendar_notes CRUD API"
```

---

## Task 8: Client resolves their own calendar note

**Files:**
- Create: `app/api/calendar-notes/[id]/resolve/route.ts`
- Test: `__tests__/api/calendar-notes-resolve.test.ts`

- [ ] **Step 1: Write the failing test**

Create `__tests__/api/calendar-notes-resolve.test.ts`:

```typescript
import { NextRequest } from 'next/server'

jest.mock('@/lib/client', () => ({ getCurrentClient: jest.fn() }))
jest.mock('@/lib/supabase/server', () => ({ createClient: jest.fn() }))

const { getCurrentClient } = jest.requireMock('@/lib/client')
const { createClient } = jest.requireMock('@/lib/supabase/server')

describe('POST /api/calendar-notes/[id]/resolve', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 when not authenticated', async () => {
    getCurrentClient.mockResolvedValue(null)
    const { POST } = require('@/app/api/calendar-notes/[id]/resolve/route')
    const req = new NextRequest('http://localhost/x', { method: 'POST' })
    const res = await POST(req, { params: { id: 'n1' } })
    expect(res.status).toBe(401)
  })

  it('updates resolved=true (RLS scopes to client)', async () => {
    getCurrentClient.mockResolvedValue({ id: 'c1' })
    const eq = jest.fn().mockResolvedValue({ error: null })
    const update = jest.fn().mockReturnValue({ eq })
    const from = jest.fn().mockReturnValue({ update })
    createClient.mockReturnValue({ from })

    const { POST } = require('@/app/api/calendar-notes/[id]/resolve/route')
    const req = new NextRequest('http://localhost/x', { method: 'POST' })
    const res = await POST(req, { params: { id: 'n1' } })

    expect(res.status).toBe(200)
    expect(from).toHaveBeenCalledWith('calendar_notes')
    expect(update).toHaveBeenCalledWith({ resolved: true })
    expect(eq).toHaveBeenCalledWith('id', 'n1')
  })
})
```

- [ ] **Step 2: Run the failing test**

```bash
npx jest __tests__/api/calendar-notes-resolve.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create the route**

Create `app/api/calendar-notes/[id]/resolve/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'

export async function POST(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const client = await getCurrentClient()
  if (!client) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  // RLS policy "calendar_notes_update_own" enforces client_id = my_client_id()
  const supabase = createClient()
  const { error } = await supabase
    .from('calendar_notes')
    .update({ resolved: true })
    .eq('id', params.id)

  if (error) return NextResponse.json({ error: 'Failed to resolve' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 200 })
}
```

- [ ] **Step 4: Run test**

```bash
npx jest __tests__/api/calendar-notes-resolve.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/calendar-notes __tests__/api/calendar-notes-resolve.test.ts
git commit -m "feat: client resolves own calendar note (RLS-scoped)"
```

---

## Task 9: Update existing clips library page to use `platforms[]`

**Files:**
- Modify: `app/(portal)/clips/page.tsx`
- Modify: `app/(portal)/clips/clip-grid.tsx`

- [ ] **Step 1: Update `app/(portal)/clips/page.tsx`**

Replace the select column list to read `platforms` instead of `platform`:

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { ClipGrid } from './clip-grid'

export default async function ClipsPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/auth/login')

  const supabase = createClient()
  const { data: clips } = await supabase
    .from('clips')
    .select('id, title, platforms, thumbnail_url, video_url, views, created_at')
    .eq('client_id', client.id)
    .order('created_at', { ascending: false })

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Your clips</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          {(clips ?? []).length} clip{(clips ?? []).length !== 1 ? 's' : ''} total
        </p>
      </div>
      <ClipGrid clips={clips ?? []} />
    </div>
  )
}
```

- [ ] **Step 2: Update `app/(portal)/clips/clip-grid.tsx` to render platforms array**

Open the existing file and replace any reference to `clip.platform` with iteration over `clip.platforms`. The icons map stays the same. The interface becomes:

```typescript
interface Clip {
  id: string
  title: string
  platforms: ('tiktok' | 'instagram' | 'youtube')[]
  thumbnail_url: string | null
  video_url: string | null
  views: number | null
  created_at: string
}
```

And in JSX, where the single platform icon was rendered, replace with:

```tsx
<div className="flex gap-1">
  {clip.platforms.map((p) => (
    <span key={p}>{PLATFORM_ICONS[p]}</span>
  ))}
</div>
```

- [ ] **Step 3: Type-check the project**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add app/\(portal\)/clips
git commit -m "refactor: clips library reads platforms[] instead of platform"
```

---

## Task 10: Sidebar nav — rename Strategy to Calendar

**Files:**
- Modify: `components/portal-sidebar.tsx`

- [ ] **Step 1: Update the Growth section item**

In `components/portal-sidebar.tsx`, change the icon import from `Lightbulb` to `Calendar`, and replace the strategy item:

```typescript
import {
  LayoutDashboard, Upload, Film, BarChart2,
  Calendar, MessageCircle, CreditCard, LogOut,
} from 'lucide-react'
```

And in the sections array:

```typescript
{
  label: 'Growth',
  items: [
    { href: '/performance', label: 'Performance', icon: BarChart2, badge: 0 },
    { href: '/calendar', label: 'Calendar', icon: Calendar, badge: 0 },
  ],
},
```

- [ ] **Step 2: Type-check**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add components/portal-sidebar.tsx
git commit -m "refactor: sidebar — Strategy → Calendar"
```

---

## Task 11: Calendar page server shell

**Files:**
- Create: `app/(portal)/calendar/page.tsx`

- [ ] **Step 1: Create the server component**

Create `app/(portal)/calendar/page.tsx`:

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { CalendarView } from './calendar-view'

export interface CalendarClip {
  id: string
  title: string
  platforms: ('tiktok' | 'instagram' | 'youtube')[]
  thumbnail_url: string | null
  video_url: string | null
  views: number
  status: 'planned' | 'editing' | 'scheduled' | 'published'
  scheduled_for: string | null
  posted_at: string | null
  manager_notes: string | null
}

export interface CalendarNote {
  id: string
  note_date: string
  note: string
  resolved: boolean
  created_at: string
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: { year?: string; month?: string }
}) {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const now = new Date()
  const year = parseInt(searchParams.year ?? '', 10) || now.getFullYear()
  const month = parseInt(searchParams.month ?? '', 10)
  const monthIdx = Number.isNaN(month) ? now.getMonth() : month - 1

  // Fetch a 90-day window centered on the displayed month so the agenda view
  // (which can scroll past month boundaries) has data on both sides.
  const windowStart = new Date(year, monthIdx - 1, 1).toISOString().split('T')[0]
  const windowEnd = new Date(year, monthIdx + 2, 0).toISOString().split('T')[0]

  const supabase = createClient()

  const [clipsRes, notesRes] = await Promise.all([
    supabase
      .from('clips')
      .select('id, title, platforms, thumbnail_url, video_url, views, status, scheduled_for, posted_at, manager_notes')
      .eq('client_id', client.id)
      .gte('scheduled_for', windowStart)
      .lte('scheduled_for', windowEnd)
      .order('scheduled_for', { ascending: true }),
    supabase
      .from('calendar_notes')
      .select('id, note_date, note, resolved, created_at')
      .eq('client_id', client.id)
      .gte('note_date', windowStart)
      .lte('note_date', windowEnd),
  ])

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Calendar</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          What we&apos;ve posted, what&apos;s coming, and what we need from you
        </p>
      </div>
      <CalendarView
        clips={(clipsRes.data ?? []) as CalendarClip[]}
        notes={(notesRes.data ?? []) as CalendarNote[]}
        planTier={client.plan_tier}
        initialYear={year}
        initialMonthIdx={monthIdx}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit (CalendarView is a stub at this point — file does not yet exist, build will fail until Task 12)**

Skip the commit until Task 12 to keep the codebase compilable per task. Move directly to Task 12.

---

## Task 12: CalendarView component — monthly grid

**Files:**
- Create: `app/(portal)/calendar/calendar-view.tsx`

- [ ] **Step 1: Create the client component**

Create `app/(portal)/calendar/calendar-view.tsx`:

```typescript
'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { ChevronLeft, ChevronRight, Bell } from 'lucide-react'
import { clsx } from 'clsx'
import { getMonthGrid, groupClipsByDate, buildDaySlots } from '@/lib/calendar'
import { slotsForTier } from '@/lib/plans'
import type { CalendarClip, CalendarNote } from './page'
import { ClipDrawer } from './clip-drawer'
import { AskDrawer } from './ask-drawer'

interface Props {
  clips: CalendarClip[]
  notes: CalendarNote[]
  planTier: string
  initialYear: number
  initialMonthIdx: number
}

const PLATFORM_ICONS: Record<string, string> = { tiktok: '🎵', instagram: '📸', youtube: '▶️' }
const MONTH_NAMES = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

export function CalendarView({ clips, notes, planTier, initialYear, initialMonthIdx }: Props) {
  const router = useRouter()
  const [year, setYear] = useState(initialYear)
  const [monthIdx, setMonthIdx] = useState(initialMonthIdx)
  const [view, setView] = useState<'month' | 'agenda'>(readStoredView())
  const [openClip, setOpenClip] = useState<CalendarClip | null>(null)
  const [openNote, setOpenNote] = useState<CalendarNote | null>(null)

  const slotCount = slotsForTier(planTier)
  const grid = useMemo(() => getMonthGrid(year, monthIdx), [year, monthIdx])
  const clipsByDate = useMemo(() => groupClipsByDate(clips), [clips])
  const notesByDate = useMemo(() => {
    const map: Record<string, CalendarNote[]> = {}
    for (const n of notes) {
      if (!map[n.note_date]) map[n.note_date] = []
      map[n.note_date].push(n)
    }
    return map
  }, [notes])

  function setMonth(y: number, m: number) {
    setYear(y); setMonthIdx(m)
    router.replace(`/calendar?year=${y}&month=${m + 1}`, { scroll: false })
  }
  function goPrev() {
    const d = new Date(year, monthIdx - 1, 1)
    setMonth(d.getFullYear(), d.getMonth())
  }
  function goNext() {
    const d = new Date(year, monthIdx + 1, 1)
    setMonth(d.getFullYear(), d.getMonth())
  }
  function goToday() {
    const t = new Date()
    setMonth(t.getFullYear(), t.getMonth())
  }
  function toggleView(v: 'month' | 'agenda') {
    setView(v)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('calendar-view-mode', v)
    }
  }

  return (
    <div className="space-y-4">
      <Toolbar
        title={`${MONTH_NAMES[monthIdx]} ${year}`}
        onPrev={goPrev}
        onNext={goNext}
        onToday={goToday}
        view={view}
        onViewChange={toggleView}
      />

      {view === 'month' ? (
        <MonthGrid
          grid={grid}
          clipsByDate={clipsByDate}
          notesByDate={notesByDate}
          slotCount={slotCount}
          onClipClick={setOpenClip}
          onNoteClick={setOpenNote}
        />
      ) : (
        <AgendaView
          clips={clips}
          notes={notes}
          slotCount={slotCount}
          onClipClick={setOpenClip}
          onNoteClick={setOpenNote}
        />
      )}

      {openClip && <ClipDrawer clip={openClip} onClose={() => setOpenClip(null)} />}
      {openNote && <AskDrawer note={openNote} onClose={() => setOpenNote(null)} onResolved={() => router.refresh()} />}
    </div>
  )
}

function readStoredView(): 'month' | 'agenda' {
  if (typeof window === 'undefined') return 'month'
  const v = window.localStorage.getItem('calendar-view-mode')
  return v === 'agenda' ? 'agenda' : 'month'
}

function Toolbar({ title, onPrev, onNext, onToday, view, onViewChange }: {
  title: string
  onPrev: () => void
  onNext: () => void
  onToday: () => void
  view: 'month' | 'agenda'
  onViewChange: (v: 'month' | 'agenda') => void
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button onClick={onPrev} className="p-1.5 rounded-md text-[var(--muted)] hover:text-white hover:bg-white/5">
          <ChevronLeft size={16} />
        </button>
        <h2 className="text-lg font-bold text-white px-1">{title}</h2>
        <button onClick={onNext} className="p-1.5 rounded-md text-[var(--muted)] hover:text-white hover:bg-white/5">
          <ChevronRight size={16} />
        </button>
        <button onClick={onToday} className="ml-2 px-3 py-1.5 rounded-md text-xs text-[var(--muted)] border border-[var(--border)] hover:text-white">
          Today
        </button>
      </div>
      <div className="inline-flex rounded-md border border-[var(--border)] overflow-hidden text-xs">
        <button
          onClick={() => onViewChange('month')}
          className={clsx('px-3 py-1.5', view === 'month' ? 'bg-[var(--brand)] text-black font-bold' : 'text-[var(--muted)]')}
        >Month</button>
        <button
          onClick={() => onViewChange('agenda')}
          className={clsx('px-3 py-1.5', view === 'agenda' ? 'bg-[var(--brand)] text-black font-bold' : 'text-[var(--muted)]')}
        >Agenda</button>
      </div>
    </div>
  )
}

function MonthGrid({ grid, clipsByDate, notesByDate, slotCount, onClipClick, onNoteClick }: {
  grid: ReturnType<typeof getMonthGrid>
  clipsByDate: Record<string, CalendarClip[]>
  notesByDate: Record<string, CalendarNote[]>
  slotCount: number
  onClipClick: (c: CalendarClip) => void
  onNoteClick: (n: CalendarNote) => void
}) {
  const todayIso = new Date().toISOString().split('T')[0]
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <div className="grid grid-cols-7 text-[10px] uppercase tracking-widest text-[var(--muted)] border-b border-[var(--border)]">
        {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map((d) => (
          <div key={d} className="px-2 py-2">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {grid.map((cell, i) => {
          const dayClips = clipsByDate[cell.iso] ?? []
          const dayNotes = (notesByDate[cell.iso] ?? []).filter((n) => !n.resolved)
          const slots = buildDaySlots(dayClips, slotCount)
          return (
            <div
              key={i}
              className={clsx(
                'min-h-[96px] border-b border-r border-[var(--border)] p-1.5 flex flex-col gap-1',
                !cell.inMonth && 'bg-[#0a0a0a] opacity-50',
                cell.iso === todayIso && 'bg-[var(--brand)]/5'
              )}
            >
              <div className="flex items-center justify-between">
                <div className="text-xs text-[var(--muted)]">{cell.date.getDate()}</div>
                {dayNotes.length > 0 && (
                  <button
                    onClick={() => onNoteClick(dayNotes[0])}
                    className="text-[var(--brand)]"
                    aria-label="Open ask"
                  >
                    <Bell size={12} />
                  </button>
                )}
              </div>
              {slots.map((s, idx) => (
                <SlotTile key={idx} slot={s} onClipClick={onClipClick} />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SlotTile({ slot, onClipClick }: {
  slot: { kind: 'clip'; clip: CalendarClip } | { kind: 'empty' }
  onClipClick: (c: CalendarClip) => void
}) {
  if (slot.kind === 'empty') {
    return (
      <a href="/submit" className="block text-[10px] text-[var(--muted)] border border-dashed border-[var(--border)] rounded-md px-1 py-1 hover:text-[var(--brand)] hover:border-[var(--brand)]/40">
        Upload needed →
      </a>
    )
  }
  const c = slot.clip
  const statusColor = c.status === 'published'
    ? 'bg-[var(--brand)]/15 text-[var(--brand)] border-[var(--brand)]/30'
    : c.status === 'scheduled'
    ? 'bg-blue-900/30 text-blue-300 border-blue-700/50'
    : 'bg-yellow-900/30 text-yellow-200 border-yellow-700/50'
  return (
    <button
      onClick={() => onClipClick(c)}
      className={clsx('text-left text-[10px] border rounded-md px-1.5 py-1 hover:brightness-125', statusColor)}
    >
      <div className="flex items-center gap-1 mb-0.5">
        {c.platforms.map((p) => (
          <span key={p}>{PLATFORM_ICONS[p]}</span>
        ))}
      </div>
      <div className="truncate font-medium">{c.title}</div>
      {c.status === 'published' && (
        <div className="opacity-80 mt-0.5">{c.views.toLocaleString()} views</div>
      )}
    </button>
  )
}

function AgendaView({ clips, notes, slotCount, onClipClick, onNoteClick }: {
  clips: CalendarClip[]
  notes: CalendarNote[]
  slotCount: number
  onClipClick: (c: CalendarClip) => void
  onNoteClick: (n: CalendarNote) => void
}) {
  // Build a set of all dates that have any content
  const dates = new Set<string>()
  for (const c of clips) if (c.scheduled_for) dates.add(c.scheduled_for)
  for (const n of notes) dates.add(n.note_date)
  const sorted = [...dates].sort()
  if (sorted.length === 0) {
    return (
      <div className="text-center py-16 text-[var(--muted)] border border-[var(--border)] rounded-xl">
        <p className="text-sm">Nothing scheduled in this window.</p>
      </div>
    )
  }

  const todayIso = new Date().toISOString().split('T')[0]
  const clipsByDate = groupClipsByDate(clips)
  const notesByDate: Record<string, CalendarNote[]> = {}
  for (const n of notes) {
    if (!notesByDate[n.note_date]) notesByDate[n.note_date] = []
    notesByDate[n.note_date].push(n)
  }

  return (
    <div className="space-y-4">
      {sorted.map((iso) => {
        const dayClips = clipsByDate[iso] ?? []
        const dayNotes = (notesByDate[iso] ?? []).filter((n) => !n.resolved)
        const slots = buildDaySlots(dayClips, slotCount)
        const date = new Date(iso + 'T00:00:00')
        return (
          <div key={iso} className={clsx('rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4', iso === todayIso && 'border-[var(--brand)]/40')}>
            <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">
              {date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
              {iso === todayIso && <span className="ml-2 text-[var(--brand)]">Today</span>}
            </div>
            {dayNotes.map((n) => (
              <button
                key={n.id}
                onClick={() => onNoteClick(n)}
                className="w-full text-left text-sm text-[var(--brand)] py-2 px-3 mb-2 rounded-md bg-[var(--brand)]/5 border border-[var(--brand)]/20 flex items-center gap-2"
              >
                <Bell size={14} /> {n.note}
              </button>
            ))}
            <div className="space-y-2">
              {slots.map((s, idx) => (
                <AgendaSlot key={idx} slot={s} onClipClick={onClipClick} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AgendaSlot({ slot, onClipClick }: {
  slot: { kind: 'clip'; clip: CalendarClip } | { kind: 'empty' }
  onClipClick: (c: CalendarClip) => void
}) {
  if (slot.kind === 'empty') {
    return (
      <a href="/submit" className="block px-3 py-2 rounded-md border border-dashed border-[var(--border)] text-sm text-[var(--muted)] hover:text-[var(--brand)] hover:border-[var(--brand)]/40">
        Upload footage for this slot →
      </a>
    )
  }
  const c = slot.clip
  return (
    <button
      onClick={() => onClipClick(c)}
      className="w-full text-left flex items-center gap-3 px-3 py-2 rounded-md border border-[var(--border)] hover:bg-white/5"
    >
      {c.thumbnail_url ? (
        <img src={c.thumbnail_url} alt="" className="w-12 h-12 rounded object-cover" />
      ) : (
        <div className="w-12 h-12 rounded bg-[var(--surface-2)]" />
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-white truncate">{c.title}</div>
        <div className="text-xs text-[var(--muted)] flex items-center gap-2 mt-0.5">
          <span>{c.platforms.map((p) => PLATFORM_ICONS[p]).join(' ')}</span>
          <span>·</span>
          <span className="capitalize">{c.status}</span>
          {c.status === 'published' && (
            <>
              <span>·</span>
              <span>{c.views.toLocaleString()} views</span>
            </>
          )}
        </div>
      </div>
    </button>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
npx tsc --noEmit
```

Expected: errors about missing `ClipDrawer` and `AskDrawer` — those are next. Other errors should be zero.

- [ ] **Step 3: Hold commit until Task 13 (drawers are required)**

---

## Task 13: ClipDrawer + AskDrawer components

**Files:**
- Create: `app/(portal)/calendar/clip-drawer.tsx`
- Create: `app/(portal)/calendar/ask-drawer.tsx`

- [ ] **Step 1: Create `app/(portal)/calendar/clip-drawer.tsx`**

```typescript
'use client'

import { X } from 'lucide-react'
import type { CalendarClip } from './page'

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok', instagram: 'Instagram', youtube: 'YouTube',
}

interface Props {
  clip: CalendarClip
  onClose: () => void
}

export function ClipDrawer({ clip, onClose }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end sm:items-stretch sm:justify-end bg-black/60"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full sm:w-[420px] bg-[var(--surface)] border-l border-[var(--border)] p-6 overflow-y-auto"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-bold text-white pr-4">{clip.title}</h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-white">
            <X size={18} />
          </button>
        </div>

        {clip.thumbnail_url && (
          <img src={clip.thumbnail_url} alt="" className="w-full aspect-[9/16] object-cover rounded-lg mb-4 bg-[var(--surface-2)]" />
        )}

        <div className="space-y-3 text-sm">
          <Row label="Status">
            <span className="capitalize text-white">{clip.status}</span>
          </Row>
          <Row label="Platforms">
            <span className="text-white">{clip.platforms.map((p) => PLATFORM_LABELS[p]).join(', ') || '—'}</span>
          </Row>
          {clip.scheduled_for && (
            <Row label={clip.status === 'published' ? 'Posted' : 'Scheduled'}>
              <span className="text-white">
                {new Date(clip.scheduled_for + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
            </Row>
          )}
          {clip.status === 'published' && (
            <Row label="Total views">
              <span className="text-white text-lg font-bold">{clip.views.toLocaleString()}</span>
            </Row>
          )}
          {clip.manager_notes && (
            <div className="pt-3 border-t border-[var(--border)]">
              <div className="text-xs text-[var(--muted)] uppercase tracking-widest mb-1">Manager notes</div>
              <p className="text-sm text-white whitespace-pre-wrap">{clip.manager_notes}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[var(--muted)] text-xs uppercase tracking-widest">{label}</span>
      {children}
    </div>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/calendar/ask-drawer.tsx`**

```typescript
'use client'

import { useState } from 'react'
import { X, Check } from 'lucide-react'
import type { CalendarNote } from './page'

interface Props {
  note: CalendarNote
  onClose: () => void
  onResolved: () => void
}

export function AskDrawer({ note, onClose, onResolved }: Props) {
  const [busy, setBusy] = useState(false)

  async function markDone() {
    setBusy(true)
    try {
      const res = await fetch(`/api/calendar-notes/${note.id}/resolve`, { method: 'POST' })
      if (res.ok) {
        onResolved()
        onClose()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end sm:items-stretch sm:justify-end bg-black/60"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full sm:w-[420px] bg-[var(--surface)] border-l border-[var(--border)] p-6 overflow-y-auto"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-bold text-white">Ask from your manager</h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="text-xs text-[var(--muted)] uppercase tracking-widest mb-2">
          {new Date(note.note_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
        </div>
        <p className="text-sm text-white leading-relaxed whitespace-pre-wrap mb-6">{note.note}</p>

        {note.resolved ? (
          <div className="flex items-center gap-2 text-sm text-[var(--brand)]">
            <Check size={16} /> Marked done
          </div>
        ) : (
          <button
            onClick={markDone}
            disabled={busy}
            className="w-full px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Mark done'}
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Type-check and lint the full project**

```bash
npx tsc --noEmit
npx next lint
```

Expected: zero TS errors. Lint may flag `<img>` (Next.js prefers `<Image>`) — disable per-file with `/* eslint-disable @next/next/no-img-element */` at the top of `clip-drawer.tsx` and `calendar-view.tsx`, OR replace `<img>` with `<Image>` from `next/image` and use `unoptimized`. Pick whichever the project already uses (check existing pages with thumbnails first; `app/(portal)/clips/clip-grid.tsx` is the precedent).

- [ ] **Step 4: Commit Tasks 11 + 12 + 13 together (calendar UI is one feature)**

```bash
git add app/\(portal\)/calendar
git commit -m "feat: content calendar page with month + agenda views"
```

---

## Task 14: Performance page rework

**Files:**
- Modify: `app/(portal)/performance/page.tsx`
- Delete: `app/(portal)/performance/range-tabs.tsx`

- [ ] **Step 1: Replace `app/(portal)/performance/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok', instagram: 'Instagram', youtube: 'YouTube',
}
const PLATFORM_ICONS: Record<string, string> = {
  tiktok: '🎵', instagram: '📸', youtube: '▶️',
}

interface ClipRow {
  id: string
  title: string
  platforms: ('tiktok' | 'instagram' | 'youtube')[]
  thumbnail_url: string | null
  views: number
  scheduled_for: string | null
  posted_at: string | null
  status: string
}

export default async function PerformancePage() {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
    .toISOString().split('T')[0]

  const supabase = createClient()
  const { data: clips } = await supabase
    .from('clips')
    .select('id, title, platforms, thumbnail_url, views, scheduled_for, posted_at, status')
    .eq('client_id', client.id)
    .eq('status', 'published')
    .gte('scheduled_for', since)
    .order('views', { ascending: false })

  const rows = (clips ?? []) as ClipRow[]

  const totalViews = rows.reduce((s, c) => s + (c.views ?? 0), 0)
  const clipsPublished = rows.length

  // View-weighted top platform: each clip contributes its views to each of its platforms
  const platformViewSum: Record<string, number> = {}
  for (const c of rows) {
    for (const p of c.platforms) {
      platformViewSum[p] = (platformViewSum[p] ?? 0) + (c.views ?? 0)
    }
  }
  const topPlatform = Object.entries(platformViewSum).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null

  const top5 = rows.slice(0, 5)

  // Trend: daily total views over last 30 days
  const trend: { iso: string; views: number }[] = []
  for (let i = 29; i >= 0; i--) {
    const d = new Date(Date.now() - i * 24 * 60 * 60 * 1000)
    const iso = d.toISOString().split('T')[0]
    const total = rows.filter((c) => c.scheduled_for === iso).reduce((s, c) => s + c.views, 0)
    trend.push({ iso, views: total })
  }
  const maxTrend = Math.max(...trend.map((t) => t.views), 1)

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Performance</h1>
        <p className="text-[var(--muted)] text-sm mt-1">Last 30 days</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Kpi label="Total views" value={totalViews.toLocaleString()} />
        <Kpi label="Clips published" value={clipsPublished.toString()} />
        <Kpi label="Top platform" value={topPlatform ? `${PLATFORM_ICONS[topPlatform]} ${PLATFORM_LABELS[topPlatform]}` : '—'} />
      </div>

      {/* Top clips */}
      <div>
        <h2 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-widest mb-3">Top 5 clips</h2>
        {top5.length === 0 ? (
          <div className="text-center py-10 rounded-xl border border-[var(--border)] text-[var(--muted)] text-sm">
            No published clips in the last 30 days.
          </div>
        ) : (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
            {top5.map((c) => (
              <div key={c.id} className="flex items-center gap-3 px-4 py-3">
                {c.thumbnail_url ? (
                  <img src={c.thumbnail_url} alt="" className="w-12 h-12 rounded object-cover" />
                ) : (
                  <div className="w-12 h-12 rounded bg-[var(--surface-2)]" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{c.title}</div>
                  <div className="text-xs text-[var(--muted)] mt-0.5 flex items-center gap-1">
                    <span>{c.platforms.map((p) => PLATFORM_ICONS[p]).join(' ')}</span>
                    {c.scheduled_for && (
                      <span className="ml-2">
                        {new Date(c.scheduled_for + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-white">{c.views.toLocaleString()}</div>
                  <div className="text-[10px] text-[var(--muted)]">views</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Trend */}
      <div>
        <h2 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-widest mb-3">Views trend (30d)</h2>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <TrendChart data={trend} max={maxTrend} />
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
      <div className="text-xs uppercase tracking-widest text-[var(--muted)]">{label}</div>
      <div className="text-2xl font-bold text-white mt-2">{value}</div>
    </div>
  )
}

function TrendChart({ data, max }: { data: { iso: string; views: number }[]; max: number }) {
  const w = 600, h = 120, pad = 8
  const xStep = (w - pad * 2) / Math.max(data.length - 1, 1)
  const points = data.map((d, i) => {
    const x = pad + i * xStep
    const y = h - pad - ((d.views / max) * (h - pad * 2))
    return `${x},${y}`
  }).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-32" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="var(--brand)" strokeWidth="2" />
    </svg>
  )
}
```

- [ ] **Step 2: Delete `app/(portal)/performance/range-tabs.tsx`**

```bash
rm app/\(portal\)/performance/range-tabs.tsx
```

- [ ] **Step 3: Type-check**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add app/\(portal\)/performance
git commit -m "feat: rework performance page to per-clip metrics"
```

---

## Task 15: Replace admin Strategy tab with Calendar tab

**Files:**
- Create: `app/admin/clients/[id]/calendar-editor.tsx`
- Modify: `app/admin/clients/[id]/page.tsx`
- Delete: `app/admin/clients/[id]/strategy-editor.tsx`
- Delete: `app/api/admin/strategy/[id]/route.ts`

- [ ] **Step 1: Create the calendar editor component**

Create `app/admin/clients/[id]/calendar-editor.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { parsePlatformVideoId, Platform } from '@/lib/platform-urls'

interface Clip {
  id: string
  title: string
  platforms: Platform[]
  status: 'planned' | 'editing' | 'scheduled' | 'published'
  scheduled_for: string | null
  views: number
  thumbnail_url: string | null
  video_url: string | null
  manager_notes: string | null
  platform_video_ids: Record<string, string>
}

interface Note {
  id: string
  note_date: string
  note: string
  resolved: boolean
}

interface Props {
  clientId: string
  clips: Clip[]
  notes: Note[]
  planTier: string
}

const PLATFORM_LABELS: Record<Platform, string> = {
  tiktok: 'TikTok', instagram: 'Instagram', youtube: 'YouTube',
}

export function CalendarEditor({ clientId, clips, notes, planTier }: Props) {
  const router = useRouter()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [addingNote, setAddingNote] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Calendar (plan: {planTier})</h2>
          <p className="text-xs text-[var(--muted)] mt-1">
            Edit clip status, dates, view counts, and platform URLs. Admin asks are visible to the client as 🔔 badges.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setAdding(true)} className="px-3 py-1.5 rounded-md bg-[var(--brand)] text-black text-xs font-bold">+ Clip</button>
          <button onClick={() => setAddingNote(true)} className="px-3 py-1.5 rounded-md border border-[var(--border)] text-[var(--muted)] text-xs">+ Ask</button>
        </div>
      </div>

      {adding && <ClipForm clientId={clientId} onClose={() => { setAdding(false); router.refresh() }} />}
      {addingNote && <NoteForm clientId={clientId} onClose={() => { setAddingNote(false); router.refresh() }} />}

      {/* Clip list */}
      <div className="rounded-xl border border-[var(--border)] divide-y divide-[var(--border)]">
        {clips.length === 0 ? (
          <div className="p-6 text-center text-sm text-[var(--muted)]">No clips yet.</div>
        ) : clips.map((c) => (
          <div key={c.id} className="p-3">
            {editingId === c.id ? (
              <ClipEditForm
                clientId={clientId}
                clip={c}
                onClose={() => { setEditingId(null); router.refresh() }}
              />
            ) : (
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <div className="text-sm text-white truncate">{c.title}</div>
                  <div className="text-xs text-[var(--muted)] mt-0.5">
                    {c.status} · {c.scheduled_for ?? 'no date'} · {c.platforms.join(',') || 'no platforms'} · {c.views.toLocaleString()} views
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setEditingId(c.id)} className="text-xs text-[var(--muted)] hover:text-white">Edit</button>
                  <button
                    onClick={async () => {
                      if (!confirm('Delete this clip?')) return
                      await fetch(`/api/admin/clips/${clientId}/${c.id}`, { method: 'DELETE' })
                      router.refresh()
                    }}
                    className="text-xs text-red-400 hover:text-red-300"
                  >Delete</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Notes (asks) list */}
      <div>
        <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Asks</h3>
        <div className="rounded-xl border border-[var(--border)] divide-y divide-[var(--border)]">
          {notes.length === 0 ? (
            <div className="p-4 text-center text-sm text-[var(--muted)]">No asks.</div>
          ) : notes.map((n) => (
            <div key={n.id} className="p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">{n.note}</div>
                <div className="text-xs text-[var(--muted)] mt-0.5">
                  {n.note_date} · {n.resolved ? '✓ Resolved' : 'Open'}
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!confirm('Delete this ask?')) return
                  await fetch(`/api/admin/calendar-notes/${n.id}`, { method: 'DELETE' })
                  router.refresh()
                }}
                className="text-xs text-red-400 hover:text-red-300"
              >Delete</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ClipForm({ clientId, onClose }: { clientId: string; onClose: () => void }) {
  const [saving, setSaving] = useState(false)
  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaving(true)
    const fd = new FormData(e.currentTarget)
    const platforms = ['tiktok','instagram','youtube'].filter((p) => fd.get(`p_${p}`))
    const body = {
      title: fd.get('title'),
      platforms,
      status: fd.get('status') ?? 'planned',
      scheduled_for: (fd.get('scheduled_for') as string) || null,
      thumbnail_url: (fd.get('thumbnail_url') as string) || null,
      views: Number(fd.get('views') || 0),
    }
    const res = await fetch(`/api/admin/clips/${clientId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    setSaving(false)
    if (res.ok) onClose()
  }
  return (
    <form onSubmit={handleSubmit} className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
      <input name="title" required placeholder="Title" className="w-full input" />
      <div className="grid grid-cols-3 gap-2">
        <select name="status" defaultValue="planned" className="input">
          <option value="planned">planned</option>
          <option value="editing">editing</option>
          <option value="scheduled">scheduled</option>
          <option value="published">published</option>
        </select>
        <input name="scheduled_for" type="date" className="input" />
        <input name="views" type="number" min="0" placeholder="views" className="input" />
      </div>
      <input name="thumbnail_url" type="url" placeholder="Thumbnail URL (optional)" className="w-full input" />
      <div className="flex gap-3 text-xs text-[var(--muted)]">
        {(['tiktok','instagram','youtube'] as const).map((p) => (
          <label key={p} className="flex items-center gap-1">
            <input type="checkbox" name={`p_${p}`} /> {PLATFORM_LABELS[p]}
          </label>
        ))}
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="px-3 py-1.5 rounded-md bg-[var(--brand)] text-black text-xs font-bold">
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs">Cancel</button>
      </div>
      <style jsx>{`
        .input {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 13px;
          color: white;
        }
      `}</style>
    </form>
  )
}

function ClipEditForm({ clientId, clip, onClose }: { clientId: string; clip: Clip; onClose: () => void }) {
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaving(true)
    const fd = new FormData(e.currentTarget)
    const platforms = (['tiktok','instagram','youtube'] as Platform[]).filter((p) => fd.get(`p_${p}`))

    // Build platform_video_ids by parsing pasted URLs
    const platform_video_ids: Record<string, string> = {}
    for (const p of platforms) {
      const url = (fd.get(`url_${p}`) as string) || ''
      const id = parsePlatformVideoId(url, p)
      if (id) platform_video_ids[p] = id
    }

    const body = {
      title: fd.get('title'),
      platforms,
      status: fd.get('status'),
      scheduled_for: (fd.get('scheduled_for') as string) || null,
      views: Number(fd.get('views') || 0),
      manager_notes: (fd.get('manager_notes') as string) || null,
      platform_video_ids,
    }
    const res = await fetch(`/api/admin/clips/${clientId}/${clip.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    setSaving(false)
    if (res.ok) onClose()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <input name="title" defaultValue={clip.title} required className="w-full input" />
      <div className="grid grid-cols-3 gap-2">
        <select name="status" defaultValue={clip.status} className="input">
          <option value="planned">planned</option>
          <option value="editing">editing</option>
          <option value="scheduled">scheduled</option>
          <option value="published">published</option>
        </select>
        <input name="scheduled_for" type="date" defaultValue={clip.scheduled_for ?? ''} className="input" />
        <input name="views" type="number" min="0" defaultValue={clip.views} className="input" />
      </div>
      <div className="flex gap-3 text-xs text-[var(--muted)]">
        {(['tiktok','instagram','youtube'] as const).map((p) => (
          <label key={p} className="flex items-center gap-1">
            <input type="checkbox" name={`p_${p}`} defaultChecked={clip.platforms.includes(p)} /> {PLATFORM_LABELS[p]}
          </label>
        ))}
      </div>
      <div className="space-y-2">
        <div className="text-xs text-[var(--muted)]">Paste post URLs (one per platform). Used by sync in Plans 6-8.</div>
        {(['tiktok','instagram','youtube'] as const).map((p) => (
          <input
            key={p}
            name={`url_${p}`}
            type="url"
            placeholder={`${PLATFORM_LABELS[p]} URL`}
            defaultValue={clip.platform_video_ids[p]
              ? `(stored id: ${clip.platform_video_ids[p]})`
              : ''
            }
            className="w-full input"
          />
        ))}
      </div>
      <textarea
        name="manager_notes"
        rows={2}
        defaultValue={clip.manager_notes ?? ''}
        placeholder="Manager notes (shown to client)"
        className="w-full input"
      />
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="px-3 py-1.5 rounded-md bg-[var(--brand)] text-black text-xs font-bold">
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs">Cancel</button>
      </div>
      <style jsx>{`
        .input {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 13px;
          color: white;
        }
      `}</style>
    </form>
  )
}

function NoteForm({ clientId, onClose }: { clientId: string; onClose: () => void }) {
  const [saving, setSaving] = useState(false)
  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaving(true)
    const fd = new FormData(e.currentTarget)
    const res = await fetch(`/api/admin/calendar-notes/${clientId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        note_date: fd.get('note_date'),
        note: fd.get('note'),
      }),
    })
    setSaving(false)
    if (res.ok) onClose()
  }
  return (
    <form onSubmit={handleSubmit} className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <input name="note_date" type="date" required className="input" />
        <input name="note" required placeholder="What do you need from the client?" className="col-span-2 input" />
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="px-3 py-1.5 rounded-md bg-[var(--brand)] text-black text-xs font-bold">
          {saving ? 'Saving…' : 'Add Ask'}
        </button>
        <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-md border border-[var(--border)] text-xs">Cancel</button>
      </div>
      <style jsx>{`
        .input {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 13px;
          color: white;
        }
      `}</style>
    </form>
  )
}
```

- [ ] **Step 2: Update `app/admin/clients/[id]/page.tsx`**

Replace the `TABS` array, `TAB_LABELS`, the strategy/performance/clips data fetches, and the tab body for strategy. The full replacement:

```typescript
import { notFound } from 'next/navigation'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { AdminThread } from './admin-thread'
import { CalendarEditor } from './calendar-editor'
import Link from 'next/link'

const TABS = ['overview', 'footage', 'calendar', 'messages', 'billing'] as const
type Tab = typeof TABS[number]

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  footage: 'Footage',
  calendar: 'Calendar',
  messages: 'Messages',
  billing: 'Billing',
}

const PLAN_OPTIONS = ['starter', 'growth', 'scale'] as const
const STATUS_OPTIONS = ['invited', 'onboarding', 'active', 'paused', 'churned'] as const

export default async function AdminClientPage({
  params,
  searchParams,
}: {
  params: { id: string }
  searchParams: { tab?: string }
}) {
  const tab: Tab = (TABS as readonly string[]).includes(searchParams.tab ?? '')
    ? (searchParams.tab as Tab)
    : 'overview'

  const clientResult = await supabaseAdmin
    .from('clients')
    .select('id, name, company, email, plan_tier, status, stripe_customer_id, stripe_subscription_id, created_at')
    .eq('id', params.id)
    .single()

  const client = clientResult.data
  if (!client) notFound()

  const footage = tab === 'footage' ? await supabaseAdmin
    .from('footage_submissions')
    .select('id, filename, storage_path, notes, created_at')
    .eq('client_id', params.id)
    .order('created_at', { ascending: false })
    .then(r => r.data ?? []) : undefined

  const calendarData = tab === 'calendar' ? await (async () => {
    const [clips, notes] = await Promise.all([
      supabaseAdmin
        .from('clips')
        .select('id, title, platforms, status, scheduled_for, views, thumbnail_url, video_url, manager_notes, platform_video_ids')
        .eq('client_id', params.id)
        .order('scheduled_for', { ascending: false, nullsFirst: false }),
      supabaseAdmin
        .from('calendar_notes')
        .select('id, note_date, note, resolved')
        .eq('client_id', params.id)
        .order('note_date', { ascending: true }),
    ])
    return { clips: clips.data ?? [], notes: notes.data ?? [] }
  })() : undefined

  const messages = tab === 'messages' ? await supabaseAdmin
    .from('messages')
    .select('id, body, sender_role, read_at, created_at')
    .eq('client_id', params.id)
    .order('created_at', { ascending: true })
    .then(r => r.data ?? []) : undefined

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <Link href="/admin/clients" className="text-xs text-[var(--muted)] hover:text-white">← All clients</Link>

      <div>
        <h1 className="text-2xl font-bold text-white">{client.name}</h1>
        <p className="text-[var(--muted)] text-sm mt-1">{client.company} · {client.email}</p>
      </div>

      <div className="flex gap-2 border-b border-[var(--border)] -mb-px">
        {TABS.map((t) => (
          <Link
            key={t}
            href={`/admin/clients/${params.id}?tab=${t}`}
            className={`px-3 py-2 text-sm border-b-2 ${
              tab === t ? 'border-[var(--brand)] text-white' : 'border-transparent text-[var(--muted)] hover:text-white'
            }`}
          >{TAB_LABELS[t]}</Link>
        ))}
      </div>

      {tab === 'overview' && (
        <form action={`/api/admin/clients/${params.id}`} method="post" className="space-y-4 max-w-md">
          <div>
            <label className="text-xs text-[var(--muted)] block mb-1">Plan tier</label>
            <select name="plan_tier" defaultValue={client.plan_tier} className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white">
              {PLAN_OPTIONS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-[var(--muted)] block mb-1">Status</label>
            <select name="status" defaultValue={client.status} className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white">
              {STATUS_OPTIONS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-[var(--muted)] block mb-1">Stripe customer ID</label>
            <input name="stripe_customer_id" defaultValue={client.stripe_customer_id ?? ''} className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <div>
            <label className="text-xs text-[var(--muted)] block mb-1">Stripe subscription ID</label>
            <input name="stripe_subscription_id" defaultValue={client.stripe_subscription_id ?? ''} className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <button type="submit" className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold">Save</button>
        </form>
      )}

      {tab === 'footage' && (
        <div className="space-y-2">
          {(footage ?? []).length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No footage submitted.</p>
          ) : (footage ?? []).map((f) => (
            <div key={f.id} className="p-3 rounded-lg border border-[var(--border)] flex items-center justify-between">
              <div>
                <div className="text-sm text-white">{f.filename}</div>
                {f.notes && <div className="text-xs text-[var(--muted)] mt-0.5">{f.notes}</div>}
                <div className="text-xs text-[var(--muted)] mt-0.5">{new Date(f.created_at).toLocaleDateString()}</div>
              </div>
              <a href={`/api/admin/footage/${f.id}/download`} className="text-xs text-[var(--brand)] hover:underline">Download</a>
            </div>
          ))}
        </div>
      )}

      {tab === 'calendar' && calendarData && (
        <CalendarEditor
          clientId={params.id}
          clips={calendarData.clips as any}
          notes={calendarData.notes as any}
          planTier={client.plan_tier}
        />
      )}

      {tab === 'messages' && (
        <AdminThread clientId={params.id} initialMessages={messages ?? []} />
      )}

      {tab === 'billing' && (
        <div className="text-sm text-[var(--muted)]">
          Stripe IDs editable on the Overview tab. Subscription state syncs via Stripe webhook.
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Delete deprecated admin files**

```bash
rm app/admin/clients/\[id\]/strategy-editor.tsx
rm app/admin/clients/\[id\]/clip-upload-form.tsx
rm -rf app/api/admin/strategy
```

- [ ] **Step 4: Type-check**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add app/admin/clients/\[id\] app/api/admin
git commit -m "feat: admin calendar tab replaces strategy tab"
```

---

## Task 16: Delete deprecated client-side files

**Files:**
- Delete: `app/(portal)/strategy/page.tsx`
- Delete: `app/(portal)/strategy/` directory if empty

- [ ] **Step 1: Remove the strategy route**

```bash
rm -rf app/\(portal\)/strategy
```

- [ ] **Step 2: Type-check and lint**

```bash
npx tsc --noEmit
npx next lint
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove deprecated strategy page"
```

---

## Task 17: Run full test suite + build + deploy

- [ ] **Step 1: Run all tests**

```bash
npx jest
```

Expected: All tests pass — no regressions in existing footage/messages/onboarding/invites tests; new tests for plans, platform-urls, calendar, admin-clips-update, admin-calendar-notes, calendar-notes-resolve all pass.

- [ ] **Step 2: Production build**

```bash
npx next build
```

Expected: Successful build, no TypeScript errors, no ESLint errors.

- [ ] **Step 3: Push to deploy**

```bash
git push origin main
```

Vercel auto-deploys. Wait for the deployment to complete (~60s), then verify in production:

- `/calendar` renders with the current month
- Toggle to Agenda view works and persists across reload
- `/performance` shows the three KPI cards, top 5, and trend chart
- `/strategy` returns 404 (route deleted)
- `/admin/clients/[id]?tab=calendar` works; old `?tab=strategy`, `?tab=clips`, `?tab=performance` URLs gracefully default to overview
- Sidebar shows "Calendar" instead of "Strategy Board"

- [ ] **Step 4: Run the production migration**

In Supabase SQL Editor, paste and execute the contents of `supabase/migrations/006_calendar.sql`. Verify:

```sql
select column_name from information_schema.columns
  where table_name = 'clips' and column_name in
  ('status','scheduled_for','platforms','views','stats_updated_at','manager_notes','platform_video_ids');
-- expect 7 rows

select count(*) from public.calendar_notes; -- expect 0
select * from public.strategy_boards; -- expect error: relation does not exist
```

- [ ] **Step 5: Smoke-test the workflow**

1. From admin panel `/admin/clients/[id]?tab=calendar`, click "+ Clip" — create a clip with status=published, today's date, views=12345, all three platforms checked.
2. Refresh the client portal at `/calendar` — the published clip appears in today's cell with the view count and platform icons.
3. Click the tile — drawer opens showing the view count.
4. From admin, click "+ Ask" — create an ask for tomorrow's date.
5. From client, refresh — see the 🔔 badge on tomorrow's cell.
6. Click the bell, mark as done. Confirm the ask disappears.
7. From client, click an empty-slot tile → should route to `/submit`.
8. From client, toggle to Agenda view → published clip + ask appear correctly.

---

## Self-review checklist

- [x] **Spec coverage:**
  - 5.1 clip status state machine → Task 1 + Task 5/6
  - 5.2 plan-tier slot count → Task 2 (`lib/plans.ts`)
  - 5.3 calendar notes → Task 1 + Task 7 + Task 8
  - 6.1 calendar page (month + agenda) → Tasks 11/12/13
  - 6.2 performance rework → Task 14
  - 7.1 admin calendar tab → Task 15
  - 7.2/7.3 admin APIs → Tasks 5/6/7
  - 8 database changes → Task 1
  - 10 plan-tier slot logic → Task 2 + used in Task 12
  - 13 acceptance criteria → Tasks 17 step 5

- [x] **No placeholders.** Every step contains the actual code or command.

- [x] **Type consistency.** `CalendarClip` type is defined in `page.tsx` and exported for use in `calendar-view.tsx`, `clip-drawer.tsx`. `CalendarNote` likewise. `Platform` from `lib/platform-urls.ts` is reused in admin form. `parsePlatformVideoId` signature matches across producer (lib) and consumer (admin form).

- [x] **Migration safety.** Task 1 uses `if not exists` / `drop if exists` and does the column drop only when the legacy `platform` column is still present.

---
