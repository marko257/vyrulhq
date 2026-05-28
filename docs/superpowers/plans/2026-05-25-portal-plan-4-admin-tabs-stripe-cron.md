# VyrulHQ Client Portal — Plan 4: Admin Detail Tabs, Stripe Billing, Unread Badge, Social Cron

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the admin client detail page (full tabbed view), add unread badge to client sidebar, wire up Stripe billing (portal session + webhook), and scaffold the daily social stats cron.

**Architecture:** Admin client detail converts from a single-view page to a tabbed layout driven by `searchParams.tab`. Tabs: Overview (edit plan/status), Footage (list + signed URLs), Clips (list + upload form), Performance (same query as client page), Strategy (editable form), Messages (existing AdminThread), Billing (Stripe status). Unread badge is a Realtime subscription inside PortalSidebar that counts `messages where sender_role='admin' and read_at IS NULL`. Stripe integration: `POST /api/billing/portal` creates a Stripe Customer Portal session, `POST /api/webhooks/stripe` handles subscription events. Social cron: `vercel.json` cron schedule + `/api/cron/sync-stats` skeleton (functional structure, API calls are TODOs requiring credentials). The cron fetches per-platform stats and writes to `performance_snapshots`.

**Tech Stack:** Next.js 14 App Router, Supabase (DB + Storage + Realtime), stripe npm package, Tailwind, lucide-react, TypeScript, Zod

---

## File Structure

```
supabase/migrations/004_plan4.sql                         — Stripe columns on clients + social_accounts table
app/admin/clients/[id]/page.tsx                           — MODIFY: tabbed layout (searchParams.tab)
app/admin/clients/[id]/strategy-editor.tsx                — 'use client' editable strategy form
app/admin/clients/[id]/clip-upload-form.tsx               — 'use client' clip creation form
app/api/admin/strategy/[id]/route.ts                      — PUT update strategy_boards content
app/api/admin/clips/[id]/route.ts                         — POST create clip for client
components/portal-sidebar.tsx                             — MODIFY: unread badge via Realtime
lib/stripe.ts                                             — Stripe client singleton
app/api/billing/portal/route.ts                           — POST create Stripe Customer Portal session
app/api/webhooks/stripe/route.ts                          — POST handle Stripe webhook events
app/(portal)/billing/page.tsx                             — MODIFY: show Stripe data when configured
vercel.json                                               — cron schedule for sync-stats
app/api/cron/sync-stats/route.ts                          — daily cron job scaffold
```

## Context for Implementers

- Project: `/Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal/`
- `supabaseAdmin` from `@/lib/supabase/admin` — service role, use for all admin API routes
- `createClient()` from `@/lib/supabase/server` — SSR client for auth checks
- `createClient()` from `@/lib/supabase/client` — browser singleton for Realtime
- CSS vars: `--brand: #a8ff57`, `--surface: #101010`, `--surface-2: #161616`, `--border: #1e1e1e`, `--muted: #666`
- `stripe` package is NOT installed yet — install with `npm install stripe`
- Stripe env vars: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` — in `.env.local` as placeholders
- Admin tabbed page: `/admin/clients/[id]?tab=overview` — `searchParams.tab` with default `'overview'`
- `footage-submissions` Supabase Storage bucket exists (from Plan 2)
- Clips table: `id, client_id, title, platform, thumbnail_url, video_url, views, created_at`
- Messages table: `id, client_id, sender_role, body, read_at, created_at`
- Strategy boards table: `id, client_id, content (jsonb), updated_at`
- Performance snapshots table: `client_id, platform, snapshot_date, views, likes, comments, shares, followers, posts_count`

---

## Task 1: DB migration 004

**Files:**
- Create: `supabase/migrations/004_plan4.sql`

- [ ] **Step 1: Create `supabase/migrations/004_plan4.sql`**

```sql
-- Add Stripe fields to clients table
alter table clients
  add column if not exists stripe_customer_id text,
  add column if not exists stripe_subscription_id text;

-- Social accounts table (one row per managed platform account)
create table if not exists social_accounts (
  id          uuid primary key default gen_random_uuid(),
  platform    platform_type not null,
  account_id  text not null,
  username    text,
  access_token      text,
  refresh_token     text,
  token_expires_at  timestamptz,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now(),
  unique (platform, account_id)
);

-- Social accounts are admin-only (no RLS needed — service role only)
```

- [ ] **Step 2: Run in Supabase SQL Editor**

Copy contents into Supabase → SQL Editor → Run. Expected: "Success. No rows returned."

- [ ] **Step 3: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add supabase/migrations/004_plan4.sql
git commit -m "feat: add Stripe columns to clients, create social_accounts table"
```

---

## Task 2: Admin client detail — tabbed layout

**Files:**
- Modify: `app/admin/clients/[id]/page.tsx`

Replace the current single-view page with a tabbed layout. Tabs: Overview | Footage | Clips | Performance | Strategy | Messages | Billing. Each tab fetches its own data.

- [ ] **Step 1: Rewrite `app/admin/clients/[id]/page.tsx`**

```typescript
import { notFound } from 'next/navigation'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { AdminThread } from './admin-thread'
import { StrategyEditor } from './strategy-editor'
import { ClipUploadForm } from './clip-upload-form'
import Link from 'next/link'

const TABS = ['overview', 'footage', 'clips', 'performance', 'strategy', 'messages', 'billing'] as const
type Tab = typeof TABS[number]

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  footage: 'Footage',
  clips: 'Clips',
  performance: 'Performance',
  strategy: 'Strategy',
  messages: 'Messages',
  billing: 'Billing',
}

const PLAN_OPTIONS = ['starter', 'growth', 'scale'] as const
const STATUS_OPTIONS = ['invited', 'onboarding', 'active', 'paused', 'churned'] as const
const PLATFORM_ICONS: Record<string, string> = { tiktok: '🎵', instagram: '📸', youtube: '▶️' }

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

  // Fetch tab-specific data
  let tabData: Record<string, unknown> = {}

  if (tab === 'footage') {
    const { data } = await supabaseAdmin
      .from('footage_submissions')
      .select('id, filename, storage_path, notes, created_at')
      .eq('client_id', params.id)
      .order('created_at', { ascending: false })
    tabData.footage = data ?? []
  }

  if (tab === 'clips') {
    const { data } = await supabaseAdmin
      .from('clips')
      .select('id, title, platform, thumbnail_url, video_url, views, created_at')
      .eq('client_id', params.id)
      .order('created_at', { ascending: false })
    tabData.clips = data ?? []
  }

  if (tab === 'performance') {
    const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
    const { data } = await supabaseAdmin
      .from('performance_snapshots')
      .select('platform, snapshot_date, views, likes, comments, shares, followers, posts_count')
      .eq('client_id', params.id)
      .gte('snapshot_date', since)
      .order('snapshot_date', { ascending: true })
    tabData.snapshots = data ?? []
  }

  if (tab === 'strategy') {
    const { data } = await supabaseAdmin
      .from('strategy_boards')
      .select('content, updated_at')
      .eq('client_id', params.id)
      .single()
    tabData.board = data
  }

  if (tab === 'messages') {
    const { data } = await supabaseAdmin
      .from('messages')
      .select('id, body, sender_role, read_at, created_at')
      .eq('client_id', params.id)
      .order('created_at', { ascending: true })
    tabData.messages = data ?? []
  }

  const footage = tabData.footage as Array<{ id: string; filename: string; storage_path: string; notes: string | null; created_at: string }> | undefined
  const clips = tabData.clips as Array<{ id: string; title: string; platform: string; thumbnail_url: string | null; video_url: string | null; views: number | null; created_at: string }> | undefined
  const snapshots = tabData.snapshots as Array<{ platform: string; snapshot_date: string; views: number | null; likes: number | null; comments: number | null; shares: number | null; followers: number | null; posts_count: number | null }> | undefined
  const board = tabData.board as { content: { active_formats: string[]; hook_angles: string[]; upcoming_themes: string[]; manager_notes: string } | null; updated_at: string } | null | undefined
  const messages = tabData.messages as Array<{ id: string; body: string; sender_role: string; read_at: string | null; created_at: string }> | undefined

  return (
    <div className="max-w-3xl space-y-6">
      {/* Client header */}
      <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <h1 className="text-xl font-bold text-white">{client.name}</h1>
        <div className="flex flex-wrap gap-4 mt-2 text-xs text-[var(--muted)]">
          <span>{client.company}</span>
          <span>{client.email}</span>
          <span className="capitalize">{client.plan_tier}</span>
          <span className="capitalize">{client.status}</span>
        </div>
      </div>

      {/* Tab nav */}
      <div className="flex gap-1 border-b border-[var(--border)] overflow-x-auto pb-0 -mb-px">
        {TABS.map((t) => (
          <Link
            key={t}
            href={`/admin/clients/${params.id}?tab=${t}`}
            className={`px-4 py-2.5 text-sm font-medium shrink-0 border-b-2 transition-colors ${
              tab === t
                ? 'border-[var(--brand)] text-[var(--brand)]'
                : 'border-transparent text-[var(--muted)] hover:text-white'
            }`}
          >
            {TAB_LABELS[t]}
          </Link>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
            <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest">Contact Info</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                { label: 'Name', value: client.name },
                { label: 'Company', value: client.company },
                { label: 'Email', value: client.email },
                { label: 'Member since', value: new Date(client.created_at).toLocaleDateString() },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div className="text-xs text-[var(--muted)] mb-0.5">{label}</div>
                  <div className="text-white">{value}</div>
                </div>
              ))}
            </div>
          </div>

          <form action={`/api/admin/clients/${params.id}`} method="POST" className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
            <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest">Edit Client</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">Plan</label>
                <select name="plan_tier" defaultValue={client.plan_tier}
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]">
                  {PLAN_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">Status</label>
                <select name="status" defaultValue={client.status}
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]">
                  {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <button type="submit"
              className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors">
              Save Changes
            </button>
          </form>
        </div>
      )}

      {tab === 'footage' && (
        <div className="space-y-2">
          <p className="text-xs text-[var(--muted)]">{footage?.length ?? 0} submission{footage?.length !== 1 ? 's' : ''}</p>
          {footage?.length === 0 ? (
            <p className="text-sm text-[var(--muted)] py-8 text-center">No footage submitted yet.</p>
          ) : (
            <div className="divide-y divide-[var(--border)] border border-[var(--border)] rounded-xl overflow-hidden">
              {footage?.map((f) => (
                <div key={f.id} className="flex items-center gap-4 px-5 py-4 bg-[var(--surface)]">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{f.filename}</div>
                    {f.notes && <div className="text-xs text-[var(--muted)] truncate mt-0.5">{f.notes}</div>}
                    <div className="text-xs text-[var(--muted)] mt-0.5">{new Date(f.created_at).toLocaleDateString()}</div>
                  </div>
                  <a
                    href={`/api/admin/footage/${f.id}/download`}
                    className="text-xs text-[var(--brand)] hover:underline shrink-0"
                  >
                    Download
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'clips' && (
        <div className="space-y-6">
          <ClipUploadForm clientId={params.id} />
          {clips?.length === 0 ? (
            <p className="text-sm text-[var(--muted)] py-8 text-center">No clips yet for this client.</p>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {clips?.map((clip) => (
                <div key={clip.id} className="rounded-xl overflow-hidden bg-[var(--surface)] border border-[var(--border)] aspect-[9/16] relative">
                  {clip.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={clip.thumbnail_url} alt={clip.title} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-2xl">
                      {PLATFORM_ICONS[clip.platform] ?? '🎬'}
                    </div>
                  )}
                  <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/80 to-transparent">
                    <div className="text-xs text-white font-medium truncate">{clip.title}</div>
                    {clip.views != null && (
                      <div className="text-xs text-[var(--muted)]">{clip.views.toLocaleString()} views</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'performance' && (
        <div className="space-y-6">
          {!snapshots || snapshots.length === 0 ? (
            <div className="text-center py-16 text-[var(--muted)]">
              <div className="text-3xl mb-3">📊</div>
              <p className="text-sm">No performance data yet for this client.</p>
            </div>
          ) : (
            ['tiktok', 'instagram', 'youtube'].map((platform) => {
              const rows = snapshots.filter(s => s.platform === platform)
              if (rows.length === 0) return null
              const totalViews = rows.reduce((sum, r) => sum + (r.views ?? 0), 0)
              const totalLikes = rows.reduce((sum, r) => sum + (r.likes ?? 0), 0)
              return (
                <div key={platform} className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
                  <h2 className="text-base font-bold text-white capitalize">{platform}</h2>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-[var(--surface-2)]">
                      <div className="text-lg font-bold text-white">{totalViews.toLocaleString()}</div>
                      <div className="text-xs text-[var(--muted)]">Views (30d)</div>
                    </div>
                    <div className="p-3 rounded-lg bg-[var(--surface-2)]">
                      <div className="text-lg font-bold text-white">{totalLikes.toLocaleString()}</div>
                      <div className="text-xs text-[var(--muted)]">Likes (30d)</div>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}

      {tab === 'strategy' && (
        <StrategyEditor
          clientId={params.id}
          initialContent={board?.content ?? {
            active_formats: [],
            hook_angles: [],
            upcoming_themes: [],
            manager_notes: '',
          }}
        />
      )}

      {tab === 'messages' && (
        <div className="border border-[var(--border)] rounded-xl overflow-hidden flex flex-col h-[60vh]">
          <AdminThread
            initialMessages={messages ?? []}
            clientId={params.id}
            clientName={client.name}
          />
        </div>
      )}

      {tab === 'billing' && (
        <div className="space-y-4">
          <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
            <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest">Subscription</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-[var(--muted)] mb-0.5">Plan</div>
                <div className="text-white capitalize">{client.plan_tier}</div>
              </div>
              <div>
                <div className="text-xs text-[var(--muted)] mb-0.5">Status</div>
                <div className="text-white capitalize">{client.status}</div>
              </div>
              {client.stripe_customer_id && (
                <div>
                  <div className="text-xs text-[var(--muted)] mb-0.5">Stripe Customer ID</div>
                  <div className="text-white font-mono text-xs">{client.stripe_customer_id}</div>
                </div>
              )}
              {client.stripe_subscription_id && (
                <div>
                  <div className="text-xs text-[var(--muted)] mb-0.5">Stripe Subscription ID</div>
                  <div className="text-white font-mono text-xs">{client.stripe_subscription_id}</div>
                </div>
              )}
            </div>
            {!client.stripe_customer_id && (
              <p className="text-xs text-[var(--muted)]">No Stripe customer linked. Add a Stripe customer ID to enable billing features.</p>
            )}
          </div>

          <form action={`/api/admin/clients/${params.id}`} method="POST" className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
            <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest">Update Stripe IDs</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">Stripe Customer ID</label>
                <input name="stripe_customer_id" defaultValue={client.stripe_customer_id ?? ''}
                  placeholder="cus_..."
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">Stripe Subscription ID</label>
                <input name="stripe_subscription_id" defaultValue={client.stripe_subscription_id ?? ''}
                  placeholder="sub_..."
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-[var(--brand)]" />
              </div>
            </div>
            <button type="submit"
              className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors">
              Save
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

Fix any errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/admin/clients/\[id\]/page.tsx
git commit -m "feat: admin client detail tabbed page"
```

---

## Task 3: Admin strategy editor + clip upload form + API routes

**Files:**
- Create: `app/admin/clients/[id]/strategy-editor.tsx`
- Create: `app/admin/clients/[id]/clip-upload-form.tsx`
- Create: `app/api/admin/strategy/[id]/route.ts`
- Create: `app/api/admin/clients/[id]/route.ts`
- Create: `app/api/admin/clips/[id]/route.ts`
- Create: `app/api/admin/footage/[id]/download/route.ts`

- [ ] **Step 1: Create `app/admin/clients/[id]/strategy-editor.tsx`**

```typescript
'use client'

import { useState } from 'react'

interface StrategyContent {
  active_formats: string[]
  hook_angles: string[]
  upcoming_themes: string[]
  manager_notes: string
}

interface Props {
  clientId: string
  initialContent: StrategyContent
}

export function StrategyEditor({ clientId, initialContent }: Props) {
  const [content, setContent] = useState<StrategyContent>(initialContent)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  function updateList(key: keyof Omit<StrategyContent, 'manager_notes'>, value: string) {
    setContent(prev => ({
      ...prev,
      [key]: value.split('\n').map(s => s.trim()).filter(Boolean),
    }))
  }

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    try {
      await fetch(`/api/admin/strategy/${clientId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(content),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  const fields: { key: keyof Omit<StrategyContent, 'manager_notes'>; label: string }[] = [
    { key: 'active_formats', label: 'Active Formats' },
    { key: 'hook_angles', label: 'Hook Angles Being Tested' },
    { key: 'upcoming_themes', label: 'Upcoming Themes' },
  ]

  return (
    <div className="space-y-4">
      {fields.map(({ key, label }) => (
        <div key={key}>
          <label className="text-xs text-[var(--muted)] block mb-1">{label} (one per line)</label>
          <textarea
            defaultValue={content[key].join('\n')}
            onChange={(e) => updateList(key, e.target.value)}
            rows={4}
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)] resize-none"
          />
        </div>
      ))}

      <div>
        <label className="text-xs text-[var(--muted)] block mb-1">Manager Notes</label>
        <textarea
          defaultValue={content.manager_notes}
          onChange={(e) => setContent(prev => ({ ...prev, manager_notes: e.target.value }))}
          rows={5}
          className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)] resize-none"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-40 transition-colors"
      >
        {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Strategy'}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Create `app/admin/clients/[id]/clip-upload-form.tsx`**

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  clientId: string
}

export function ClipUploadForm({ clientId }: Props) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaving(true)
    const form = e.currentTarget
    const data = new FormData(form)
    try {
      const res = await fetch(`/api/admin/clips/${clientId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: data.get('title'),
          platform: data.get('platform'),
          thumbnail_url: data.get('thumbnail_url') || null,
          video_url: data.get('video_url') || null,
          views: Number(data.get('views')) || null,
        }),
      })
      if (res.ok) {
        form.reset()
        setOpen(false)
        router.refresh()
      }
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors"
      >
        + Add Clip
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
      <h3 className="text-sm font-bold text-white">Add New Clip</h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="text-xs text-[var(--muted)] block mb-1">Title *</label>
          <input name="title" required placeholder="Video title"
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1">Platform *</label>
          <select name="platform" required
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]">
            <option value="tiktok">TikTok</option>
            <option value="instagram">Instagram</option>
            <option value="youtube">YouTube</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1">Initial Views</label>
          <input name="views" type="number" min="0" placeholder="0"
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1">Thumbnail URL</label>
          <input name="thumbnail_url" type="url" placeholder="https://..."
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1">Video URL</label>
          <input name="video_url" type="url" placeholder="https://..."
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-40 transition-colors">
          {saving ? 'Saving…' : 'Add Clip'}
        </button>
        <button type="button" onClick={() => setOpen(false)}
          className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm text-[var(--muted)] hover:text-white transition-colors">
          Cancel
        </button>
      </div>
    </form>
  )
}
```

- [ ] **Step 3: Create `app/api/admin/strategy/[id]/route.ts`**

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

const ContentSchema = z.object({
  active_formats: z.array(z.string()),
  hook_angles: z.array(z.string()),
  upcoming_themes: z.array(z.string()),
  manager_notes: z.string(),
})

export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const rawBody = await request.json().catch(() => null)
  const parsed = ContentSchema.safeParse(rawBody)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid content' }, { status: 400 })

  const { error } = await supabaseAdmin
    .from('strategy_boards')
    .upsert(
      { client_id: params.id, content: parsed.data, updated_at: new Date().toISOString() },
      { onConflict: 'client_id' }
    )

  if (error) return NextResponse.json({ error: 'Failed to save' }, { status: 500 })
  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 4: Create `app/api/admin/clients/[id]/route.ts`** (plan/status + Stripe ID updates)

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { redirect } from 'next/navigation'
import { z } from 'zod'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

const UpdateSchema = z.object({
  plan_tier: z.enum(['starter', 'growth', 'scale']).optional(),
  status: z.enum(['invited', 'onboarding', 'active', 'paused', 'churned']).optional(),
  stripe_customer_id: z.string().optional(),
  stripe_subscription_id: z.string().optional(),
})

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const formData = await request.formData()
  const raw: Record<string, string> = {}
  formData.forEach((value, key) => { raw[key] = value.toString() })

  const parsed = UpdateSchema.safeParse(raw)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  // Remove empty string values
  const updates: Record<string, string> = {}
  for (const [k, v] of Object.entries(parsed.data)) {
    if (v !== undefined && v !== '') updates[k] = v as string
  }

  if (Object.keys(updates).length > 0) {
    await supabaseAdmin.from('clients').update(updates).eq('id', params.id)
  }

  return NextResponse.redirect(new URL(`/admin/clients/${params.id}?tab=overview`, request.url))
}
```

- [ ] **Step 5: Create `app/api/admin/clips/[id]/route.ts`**

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

const ClipSchema = z.object({
  title: z.string().min(1),
  platform: z.enum(['tiktok', 'instagram', 'youtube']),
  thumbnail_url: z.string().url().nullable(),
  video_url: z.string().url().nullable(),
  views: z.number().int().nonnegative().nullable(),
})

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const rawBody = await request.json().catch(() => null)
  const parsed = ClipSchema.safeParse(rawBody)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid data' }, { status: 400 })

  const { error } = await supabaseAdmin.from('clips').insert({
    client_id: params.id,
    ...parsed.data,
  })
  if (error) return NextResponse.json({ error: 'Failed to create clip' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 201 })
}
```

- [ ] **Step 6: Create `app/api/admin/footage/[id]/download/route.ts`**

Generates a signed URL for a footage submission so admin can download it.

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

async function requireAdmin() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user || user.app_metadata?.role !== 'admin') return null
  return user
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await requireAdmin()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { data: submission } = await supabaseAdmin
    .from('footage_submissions')
    .select('storage_path')
    .eq('id', params.id)
    .single()

  if (!submission) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  const { data: signedUrl } = await supabaseAdmin
    .storage
    .from('footage-submissions')
    .createSignedUrl(submission.storage_path, 3600)

  if (!signedUrl) return NextResponse.json({ error: 'Failed to generate URL' }, { status: 500 })

  return NextResponse.redirect(signedUrl.signedUrl)
}
```

- [ ] **Step 7: TypeScript check and commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

Fix any errors, then:

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/admin/clients/\[id\]/ app/api/admin/
git commit -m "feat: admin strategy editor, clip upload, footage download, client update API"
```

---

## Task 4: Unread badge in PortalSidebar

**Files:**
- Modify: `components/portal-sidebar.tsx`

Add a Realtime subscription that counts unread admin→client messages and shows a badge on the Messages nav item.

- [ ] **Step 1: Modify `components/portal-sidebar.tsx`**

The sidebar is already a 'use client' component. Add:
1. A `useEffect` on mount that fetches the initial unread count via a fast Supabase query
2. A Realtime subscription on `messages` that updates the count when new inserts happen

The client's `id` isn't available in the sidebar component without a server fetch. Instead, fetch the client record on mount using the browser Supabase client.

Replace the current `PortalSidebar` export with this implementation:

```typescript
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, Upload, Film, BarChart2,
  Lightbulb, MessageCircle, CreditCard, LogOut,
} from 'lucide-react'
import { clsx } from 'clsx'

const supabase = createClient()

export function PortalSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const [unreadCount, setUnreadCount] = useState(0)
  const [clientId, setClientId] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function init() {
      // Get the client record for the current user
      const { data: clients } = await supabase
        .from('clients')
        .select('id')
        .limit(1)
        .single()

      if (!mounted || !clients) return
      const id = clients.id
      setClientId(id)

      // Initial unread count
      const { count } = await supabase
        .from('messages')
        .select('id', { count: 'exact', head: true })
        .eq('client_id', id)
        .eq('sender_role', 'admin')
        .is('read_at', null)

      if (mounted) setUnreadCount(count ?? 0)

      // Realtime subscription
      const channel = supabase
        .channel(`sidebar:messages:${id}`)
        .on('postgres_changes', {
          event: '*',
          schema: 'public',
          table: 'messages',
          filter: `client_id=eq.${id}`,
        }, async () => {
          const { count: newCount } = await supabase
            .from('messages')
            .select('id', { count: 'exact', head: true })
            .eq('client_id', id)
            .eq('sender_role', 'admin')
            .is('read_at', null)
          if (mounted) setUnreadCount(newCount ?? 0)
        })
        .subscribe()

      return () => { supabase.removeChannel(channel) }
    }

    const cleanup = init()
    return () => {
      mounted = false
      cleanup.then(fn => fn?.())
    }
  }, [])

  async function handleSignOut() {
    await supabase.auth.signOut()
    router.push('/auth/login')
    router.refresh()
  }

  const sections = [
    {
      label: 'Content',
      items: [
        { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { href: '/submit', label: 'Submit Footage', icon: Upload },
        { href: '/clips', label: 'Clip Library', icon: Film },
      ],
    },
    {
      label: 'Growth',
      items: [
        { href: '/performance', label: 'Performance', icon: BarChart2 },
        { href: '/strategy', label: 'Strategy Board', icon: Lightbulb },
      ],
    },
    {
      label: 'Account',
      items: [
        { href: '/messages', label: 'Messages', icon: MessageCircle, badge: unreadCount },
        { href: '/billing', label: 'Billing', icon: CreditCard },
      ],
    },
  ]

  return (
    <aside className="w-56 min-h-screen bg-[#0d0d0d] border-r border-[var(--border)] flex flex-col py-4 px-3 shrink-0">
      <div className="flex items-center gap-2 px-2 pb-4 mb-2 border-b border-[var(--border)]">
        <div className="w-6 h-6 bg-[var(--brand)] rounded-md shrink-0" />
        <div>
          <div className="text-sm font-bold text-white leading-none">Vyrul HQ</div>
          <div className="text-[10px] text-[var(--muted)] mt-0.5">Client Portal</div>
        </div>
      </div>

      <nav className="flex-1 flex flex-col gap-4 mt-2">
        {sections.map((section) => (
          <div key={section.label}>
            <div className="px-2 mb-1 text-[10px] font-bold uppercase tracking-widest text-[#333]">
              {section.label}
            </div>
            {section.items.map(({ href, label, icon: Icon, badge }: { href: string; label: string; icon: typeof LayoutDashboard; badge?: number }) => {
              const active = pathname === href || pathname.startsWith(href + '/')
              return (
                <Link
                  key={href}
                  href={href}
                  className={clsx(
                    'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors',
                    active
                      ? 'bg-[#1a2a10] text-[var(--brand)]'
                      : 'text-[var(--muted)] hover:text-white hover:bg-white/5'
                  )}
                >
                  <Icon size={15} />
                  <span className="flex-1">{label}</span>
                  {badge != null && badge > 0 && (
                    <span className="w-5 h-5 rounded-full bg-[var(--brand)] text-black text-xs font-bold flex items-center justify-center shrink-0">
                      {badge > 9 ? '9+' : badge}
                    </span>
                  )}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <button
        onClick={handleSignOut}
        className="flex items-center gap-2.5 px-2.5 py-2 mt-2 rounded-lg text-sm text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors w-full"
      >
        <LogOut size={15} />
        Sign Out
      </button>
    </aside>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 3: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add components/portal-sidebar.tsx
git commit -m "feat: unread message badge in portal sidebar"
```

---

## Task 5: Stripe billing integration

**Files:**
- Create: `lib/stripe.ts`
- Create: `app/api/billing/portal/route.ts`
- Create: `app/api/webhooks/stripe/route.ts`
- Modify: `app/(portal)/billing/page.tsx`

- [ ] **Step 1: Install stripe**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && npm install stripe
```

- [ ] **Step 2: Create `lib/stripe.ts`**

```typescript
import Stripe from 'stripe'

if (!process.env.STRIPE_SECRET_KEY) {
  console.warn('STRIPE_SECRET_KEY is not set — Stripe features will be disabled')
}

export const stripe = process.env.STRIPE_SECRET_KEY
  ? new Stripe(process.env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' })
  : null
```

- [ ] **Step 3: Create `app/api/billing/portal/route.ts`**

Creates a Stripe Customer Portal session for the authenticated client to manage payment method.

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getCurrentClient } from '@/lib/client'
import { stripe } from '@/lib/stripe'

export async function POST(request: NextRequest) {
  if (!stripe) {
    return NextResponse.json({ error: 'Billing not configured' }, { status: 503 })
  }

  const client = await getCurrentClient()
  if (!client) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const clientData = await import('@/lib/supabase/admin').then(m =>
    m.supabaseAdmin.from('clients').select('stripe_customer_id').eq('id', client.id).single()
  )

  const stripeCustomerId = clientData.data?.stripe_customer_id
  if (!stripeCustomerId) {
    return NextResponse.json({ error: 'No billing account linked' }, { status: 400 })
  }

  const origin = request.headers.get('origin') ?? 'https://hub.vyrulhq.com'

  const session = await stripe.billingPortal.sessions.create({
    customer: stripeCustomerId,
    return_url: `${origin}/billing`,
  })

  return NextResponse.json({ url: session.url })
}
```

- [ ] **Step 4: Create `app/api/webhooks/stripe/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { stripe } from '@/lib/stripe'
import { supabaseAdmin } from '@/lib/supabase/admin'

export async function POST(request: NextRequest) {
  if (!stripe) return NextResponse.json({ error: 'Not configured' }, { status: 503 })

  const body = await request.text()
  const signature = request.headers.get('stripe-signature')

  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    return NextResponse.json({ error: 'Missing signature' }, { status: 400 })
  }

  let event: import('stripe').Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET)
  } catch {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  switch (event.type) {
    case 'customer.subscription.updated':
    case 'customer.subscription.created': {
      const subscription = event.data.object as import('stripe').Stripe.Subscription
      const customerId = subscription.customer as string
      const status = subscription.status === 'active' ? 'active'
        : subscription.status === 'canceled' ? 'churned'
        : 'paused'

      await supabaseAdmin
        .from('clients')
        .update({ stripe_subscription_id: subscription.id, status })
        .eq('stripe_customer_id', customerId)
      break
    }
    case 'customer.subscription.deleted': {
      const subscription = event.data.object as import('stripe').Stripe.Subscription
      const customerId = subscription.customer as string
      await supabaseAdmin
        .from('clients')
        .update({ status: 'churned' })
        .eq('stripe_customer_id', customerId)
      break
    }
  }

  return NextResponse.json({ received: true })
}
```

- [ ] **Step 5: Update `app/(portal)/billing/page.tsx`** to add "Manage payment method" button when Stripe is configured

In the existing billing page, after the plan card and before the contact CTA, add a conditional button that POSTs to `/api/billing/portal` and redirects to the portal URL. Keep the rest of the page unchanged.

Read the current file first. Then add this section between the plan card and the contact CTA:

```typescript
      {/* Stripe portal button — shown when client has a stripe_customer_id */}
      {hasStripe && (
        <ManagePaymentButton />
      )}
```

And add a client component file `app/(portal)/billing/manage-payment-button.tsx`:

```typescript
'use client'

import { useState } from 'react'

export function ManagePaymentButton() {
  const [loading, setLoading] = useState(false)

  async function handleClick() {
    setLoading(true)
    try {
      const res = await fetch('/api/billing/portal', { method: 'POST' })
      const data = await res.json()
      if (data.url) window.location.href = data.url
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] flex items-center justify-between">
      <div>
        <div className="text-sm font-semibold text-white">Payment method</div>
        <div className="text-xs text-[var(--muted)] mt-0.5">Update your card or billing details</div>
      </div>
      <button
        onClick={handleClick}
        disabled={loading}
        className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm text-white hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:opacity-40 transition-colors shrink-0"
      >
        {loading ? 'Loading…' : 'Manage →'}
      </button>
    </div>
  )
}
```

To check whether the client has a Stripe customer ID, add a query in the billing server component:

```typescript
// After getCurrentClient()
const { data: clientData } = await supabase
  .from('clients')
  .select('stripe_customer_id')
  .eq('id', client.id)
  .single()

const hasStripe = !!clientData?.stripe_customer_id
```

Import `ManagePaymentButton` conditionally.

- [ ] **Step 6: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

Fix any type errors in the Stripe types.

- [ ] **Step 7: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add lib/stripe.ts app/api/billing/ app/api/webhooks/ app/\(portal\)/billing/
git commit -m "feat: Stripe billing portal and webhook handler"
```

---

## Task 6: Social stats cron scaffold

**Files:**
- Create: `vercel.json`
- Create: `app/api/cron/sync-stats/route.ts`

The cron fetches stats from TikTok, Meta, and YouTube for managed accounts stored in `social_accounts` and writes to `performance_snapshots`. Actual API calls are TODO stubs that need credentials — the structure is complete.

- [ ] **Step 1: Create `vercel.json`**

```json
{
  "crons": [
    {
      "path": "/api/cron/sync-stats",
      "schedule": "0 6 * * *"
    }
  ]
}
```

- [ ] **Step 2: Create `app/api/cron/sync-stats/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabase/admin'

// Called daily at 6am UTC by Vercel cron
// Authorization: Vercel cron sends CRON_SECRET in Authorization header
// Set CRON_SECRET env var in Vercel to a random string

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get('authorization')
  const expectedToken = process.env.CRON_SECRET
    ? `Bearer ${process.env.CRON_SECRET}`
    : null

  if (expectedToken && authHeader !== expectedToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const today = new Date().toISOString().split('T')[0]

  // Fetch all active social accounts
  const { data: accounts } = await supabaseAdmin
    .from('social_accounts')
    .select('id, platform, account_id, access_token, refresh_token, token_expires_at')

  if (!accounts || accounts.length === 0) {
    return NextResponse.json({ ok: true, message: 'No social accounts configured' })
  }

  const results: Array<{ platform: string; account_id: string; status: string; error?: string }> = []

  for (const account of accounts) {
    try {
      let stats: {
        views: number
        likes: number
        comments: number
        shares: number
        followers: number
        posts_count: number
      } | null = null

      if (account.platform === 'tiktok') {
        // TODO: Implement TikTok Business Content API fetch
        // Requires: TIKTOK_APP_ID, TIKTOK_APP_SECRET env vars
        // OAuth token stored in account.access_token
        // Docs: https://business-api.tiktok.com/portal/docs
        // stats = await fetchTikTokStats(account)
        results.push({ platform: 'tiktok', account_id: account.account_id, status: 'skipped', error: 'TikTok credentials not configured' })
        continue
      }

      if (account.platform === 'instagram') {
        // TODO: Implement Meta Graph API fetch
        // Requires: META_APP_ID, META_APP_SECRET env vars
        // OAuth token stored in account.access_token
        // Endpoint: https://graph.facebook.com/v19.0/{ig-user-id}/insights
        // stats = await fetchInstagramStats(account)
        results.push({ platform: 'instagram', account_id: account.account_id, status: 'skipped', error: 'Instagram credentials not configured' })
        continue
      }

      if (account.platform === 'youtube') {
        // TODO: Implement YouTube Data API v3 fetch
        // Requires: YOUTUBE_API_KEY env var (or OAuth for authenticated data)
        // Endpoint: https://www.googleapis.com/youtube/v3/channels
        // Docs: https://developers.google.com/youtube/v3/docs/channels/list
        // stats = await fetchYouTubeStats(account)
        results.push({ platform: 'youtube', account_id: account.account_id, status: 'skipped', error: 'YouTube credentials not configured' })
        continue
      }

      if (stats) {
        // Find clients that use this platform (all active clients for now — refine when multi-client accounts needed)
        const { data: clients } = await supabaseAdmin
          .from('clients')
          .select('id')
          .eq('status', 'active')

        for (const client of clients ?? []) {
          await supabaseAdmin
            .from('performance_snapshots')
            .upsert({
              client_id: client.id,
              platform: account.platform,
              snapshot_date: today,
              ...stats,
            }, { onConflict: 'client_id,platform,snapshot_date' })
        }

        results.push({ platform: account.platform, account_id: account.account_id, status: 'synced' })
      }
    } catch (err) {
      results.push({
        platform: account.platform,
        account_id: account.account_id,
        status: 'error',
        error: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  return NextResponse.json({ ok: true, date: today, results })
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 4: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add vercel.json app/api/cron/
git commit -m "feat: social stats cron scaffold (credentials required to activate)"
```

---

## Task 7: Run all tests + deploy

**Files:** No new files — validation and deploy only.

- [ ] **Step 1: Run the full Jest test suite**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && npx jest --no-coverage 2>&1 | tail -30
```

Expected: 37+ tests passing (all Plan 2 + Plan 3 tests).

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 3: Next.js build check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && npm run build 2>&1 | tail -40
```

Common issues:
- `no-unused-vars`: add `// eslint-disable-next-line @typescript-eslint/no-unused-vars` above offending line
- `@next/next/no-img-element` on admin clips tab: add eslint disable comment
- Type errors from Stripe SDK — check against `lib/stripe.ts` nullable stripe instance

- [ ] **Step 4: Deploy**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal && npx vercel --prod 2>&1 | grep -E "(Aliased|Error|hub\.)"
```

- [ ] **Step 5: Report**

Report: test count, TypeScript status, build status, deploy URL, any fixes made.

---

## Self-Review

| Spec requirement | Task |
|---|---|
| Admin client detail — tabbed view | Task 2 |
| Admin — edit plan/status | Task 3 (client update API) |
| Admin — footage list + download | Task 3 |
| Admin — clip upload | Task 3 |
| Admin — strategy editor | Task 3 |
| Admin — Billing Stripe IDs | Task 2 (billing tab) |
| Unread badge in sidebar | Task 4 |
| Stripe Customer Portal | Task 5 |
| Stripe webhook (subscription events) | Task 5 |
| Social stats cron scaffold | Task 6 |
| Daily cron schedule | Task 6 (vercel.json) |

**Deferred / requires manual setup:**
- Social API credentials (TikTok, Instagram, YouTube) — cron is scaffolded, won't run until credentials added
- Stripe keys — billing portal works once `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` set in Vercel
- Supabase migration 003 + 004 — must be run manually in Supabase SQL Editor
- Social account OAuth connection admin UI — deferred to Plan 5
