# VyrulHQ Client Portal — Plan 2: Onboarding, Dashboard, Footage & Clip Library

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 3-step onboarding wizard, a real data dashboard, footage upload to Supabase Storage, and the clip library.

**Architecture:** Plan 1 (auth, invite system, layouts) is complete. This plan adds four client-facing features inside the existing `app/(portal)` route group. Each feature is a server component wrapper feeding data to a client component where interactivity is needed. Supabase Storage handles footage file storage with RLS policies scoped to each client's folder.

**Tech Stack:** Next.js 14 App Router, Supabase (DB + Storage), @supabase/ssr v0.10.3, Tailwind CSS, lucide-react, clsx, TypeScript

---

## File Structure

```
supabase/migrations/002_storage.sql           — footage-submissions bucket + storage policies
lib/client.ts                                  — getCurrentClient() server helper (reused everywhere)
__tests__/lib/client.test.ts                  — unit tests for getCurrentClient
app/api/onboarding/complete/route.ts          — POST: set onboarding_completed=true, status=active
__tests__/api/onboarding.test.ts              — unit tests for onboarding complete API
app/api/footage/route.ts                      — POST: write footage_submissions record after upload
__tests__/api/footage.test.ts                 — unit tests for footage API
app/onboarding/page.tsx                       — server wrapper (checks auth + onboarding state)
app/onboarding/onboarding-wizard.tsx          — 'use client' 3-step wizard component
app/(portal)/dashboard/page.tsx               — MODIFY existing stub → real data dashboard
app/(portal)/submit/page.tsx                  — server wrapper (fetches submission history)
app/(portal)/submit/uploader.tsx              — 'use client' drag-drop uploader with progress
app/(portal)/clips/page.tsx                   — server component (fetch all client clips)
app/(portal)/clips/clip-grid.tsx              — 'use client' platform filter + grid
app/(portal)/clips/clip-modal.tsx             — 'use client' clip detail modal
```

---

## Task 1: Supabase Storage Migration

**Files:**
- Create: `supabase/migrations/002_storage.sql`

This task creates the footage-submissions storage bucket and RLS policies. Must be run in Supabase → SQL Editor before footage upload will work.

- [ ] **Step 1: Create `supabase/migrations/002_storage.sql`**

```sql
-- Create footage-submissions bucket (private, 4GB max per file)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'footage-submissions',
  'footage-submissions',
  false,
  4294967296,
  array[
    'video/mp4', 'video/quicktime', 'video/x-msvideo',
    'video/webm', 'video/x-matroska', 'video/mpeg',
    'video/3gpp', 'video/x-flv'
  ]
)
on conflict (id) do nothing;

-- Storage RLS: clients can upload files to their own client_id folder
create policy "footage_upload_own"
on storage.objects for insert
to authenticated
with check (
  bucket_id = 'footage-submissions'
  and (storage.foldername(name))[1] = (
    select id::text from public.clients where user_id = auth.uid() limit 1
  )
);

-- Storage RLS: clients can read their own uploaded files
create policy "footage_read_own"
on storage.objects for select
to authenticated
using (
  bucket_id = 'footage-submissions'
  and (storage.foldername(name))[1] = (
    select id::text from public.clients where user_id = auth.uid() limit 1
  )
);

-- Storage RLS: clients can delete their own files (for future use)
create policy "footage_delete_own"
on storage.objects for delete
to authenticated
using (
  bucket_id = 'footage-submissions'
  and (storage.foldername(name))[1] = (
    select id::text from public.clients where user_id = auth.uid() limit 1
  )
);
```

- [ ] **Step 2: Run the migration in Supabase**

Go to Supabase Dashboard → SQL Editor → paste the SQL above → Run.

Expected: "Success. No rows returned."

Check: Supabase → Storage → Buckets — you should see `footage-submissions` listed as private.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/002_storage.sql
git commit -m "feat: add footage-submissions storage bucket and RLS policies"
```

---

## Task 2: Client Helper Library

**Files:**
- Create: `lib/client.ts`
- Create: `__tests__/lib/client.test.ts`

Server-side helper that fetches the authenticated user's client record. Used by every portal page to get plan tier, onboarding state, etc.

- [ ] **Step 1: Write the failing test at `__tests__/lib/client.test.ts`**

```typescript
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(),
}))

import { createClient } from '@/lib/supabase/server'
import { getCurrentClient } from '@/lib/client'

const mockSelect = jest.fn()
const mockEq = jest.fn()
const mockSingle = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()
  mockSelect.mockReturnValue({ eq: mockEq })
  mockEq.mockReturnValue({ single: mockSingle })
})

describe('getCurrentClient', () => {
  it('returns null when no user is authenticated', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const result = await getCurrentClient()
    expect(result).toBeNull()
  })

  it('returns null when client record not found', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
      from: jest.fn().mockReturnValue({ select: mockSelect }),
    })
    mockSingle.mockResolvedValue({ data: null, error: null })
    const result = await getCurrentClient()
    expect(result).toBeNull()
  })

  it('returns client record when found', async () => {
    const fakeClient = {
      id: 'c1', email: 'a@a.com', name: 'Alex', company: 'Acme',
      plan_tier: 'growth', status: 'active', onboarding_completed: true,
      account_manager_name: 'Marko N.', stripe_customer_id: null, stripe_subscription_id: null,
    }
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
      from: jest.fn().mockReturnValue({ select: mockSelect }),
    })
    mockSingle.mockResolvedValue({ data: fakeClient, error: null })
    const result = await getCurrentClient()
    expect(result).toEqual(fakeClient)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npm test -- --testPathPattern="lib/client" --no-coverage
```

Expected: FAIL — `Cannot find module '@/lib/client'`

- [ ] **Step 3: Create `lib/client.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'

export interface ClientRecord {
  id: string
  email: string
  name: string
  company: string | null
  plan_tier: 'starter' | 'growth' | 'scale'
  status: 'invited' | 'onboarding' | 'active' | 'paused' | 'churned'
  onboarding_completed: boolean
  account_manager_name: string
  stripe_customer_id: string | null
  stripe_subscription_id: string | null
}

export async function getCurrentClient(): Promise<ClientRecord | null> {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return null

  const { data } = await supabase
    .from('clients')
    .select('id, email, name, company, plan_tier, status, onboarding_completed, account_manager_name, stripe_customer_id, stripe_subscription_id')
    .eq('user_id', user.id)
    .single()

  return data ?? null
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- --testPathPattern="lib/client" --no-coverage
```

Expected: PASS — 3 tests passing

- [ ] **Step 5: Commit**

```bash
git add lib/client.ts __tests__/lib/client.test.ts
git commit -m "feat: add getCurrentClient server helper"
```

---

## Task 3: Onboarding Complete API Route

**Files:**
- Create: `app/api/onboarding/complete/route.ts`
- Create: `__tests__/api/onboarding.test.ts`

POST endpoint that marks a client's onboarding as complete and sets status to `active`.

- [ ] **Step 1: Write the failing test at `__tests__/api/onboarding.test.ts`**

```typescript
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(),
}))
jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: { from: jest.fn() },
}))

import { NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { POST } from '@/app/api/onboarding/complete/route'

const mockUpdate = jest.fn()
const mockEq = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()
  mockEq.mockResolvedValue({ error: null })
  mockUpdate.mockReturnValue({ eq: mockEq })
  ;(supabaseAdmin.from as jest.Mock).mockReturnValue({ update: mockUpdate })
})

function makeRequest() {
  return new NextRequest('http://localhost/api/onboarding/complete', { method: 'POST' })
}

describe('POST /api/onboarding/complete', () => {
  it('returns 401 when not authenticated', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const res = await POST(makeRequest())
    expect(res.status).toBe(401)
  })

  it('returns 200 and updates client record when authenticated', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
    })
    const res = await POST(makeRequest())
    expect(res.status).toBe(200)
    expect(mockUpdate).toHaveBeenCalledWith({ onboarding_completed: true, status: 'active' })
    expect(mockEq).toHaveBeenCalledWith('user_id', 'u1')
  })

  it('returns 500 when DB update fails', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
    })
    mockEq.mockResolvedValue({ error: new Error('DB error') })
    const res = await POST(makeRequest())
    expect(res.status).toBe(500)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- --testPathPattern="api/onboarding" --no-coverage
```

Expected: FAIL — `Cannot find module '@/app/api/onboarding/complete/route'`

- [ ] **Step 3: Create `app/api/onboarding/complete/route.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(_request: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { error } = await supabaseAdmin
    .from('clients')
    .update({ onboarding_completed: true, status: 'active' })
    .eq('user_id', user.id)

  if (error) return NextResponse.json({ error: 'Failed to complete onboarding' }, { status: 500 })
  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- --testPathPattern="api/onboarding" --no-coverage
```

Expected: PASS — 3 tests passing

- [ ] **Step 5: Commit**

```bash
git add app/api/onboarding/ __tests__/api/onboarding.test.ts
git commit -m "feat: add onboarding complete API route"
```

---

## Task 4: Onboarding Wizard

**Files:**
- Create: `app/onboarding/page.tsx`
- Create: `app/onboarding/onboarding-wizard.tsx`

3-step wizard: confirm details → what's included → how to submit footage. Completing step 3 calls the API and redirects to dashboard.

- [ ] **Step 1: Create `app/onboarding/page.tsx`**

```typescript
import { getCurrentClient } from '@/lib/client'
import { redirect } from 'next/navigation'
import { OnboardingWizard } from './onboarding-wizard'

export default async function OnboardingPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/auth/login')
  if (client.onboarding_completed) redirect('/dashboard')

  return (
    <div className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-6">
      <OnboardingWizard client={{
        name: client.name,
        email: client.email,
        company: client.company,
        planTier: client.plan_tier,
        accountManagerName: client.account_manager_name,
      }} />
    </div>
  )
}
```

- [ ] **Step 2: Create `app/onboarding/onboarding-wizard.tsx`**

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  client: {
    name: string
    email: string
    company: string | null
    planTier: 'starter' | 'growth' | 'scale'
    accountManagerName: string
  }
}

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter — $997/mo',
  growth: 'Growth — $1,997/mo',
  scale: 'Scale — $3,497/mo',
}

const PLAN_FEATURES: Record<string, string[]> = {
  starter: [
    '1 clip/day posted to your chosen platform',
    'Dedicated account manager',
    'Monthly performance report',
    'Footage submission portal',
  ],
  growth: [
    '2 clips/day across TikTok, Instagram & YouTube',
    'Dedicated account manager',
    'Monthly performance report',
    'Strategy board — current content direction',
    'Footage submission portal',
  ],
  scale: [
    '3 clips/day across all 3 platforms',
    'Dedicated account manager',
    'Weekly performance reports',
    'Monthly strategy session',
    'Strategy board & hook coaching',
    'Trend integration',
  ],
}

const STEP_LABELS = ['Your details', "What's included", 'How to submit']

export function OnboardingWizard({ client }: Props) {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()

  async function handleComplete() {
    setLoading(true)
    setError('')
    const res = await fetch('/api/onboarding/complete', { method: 'POST' })
    if (!res.ok) {
      setError('Something went wrong. Please try again.')
      setLoading(false)
      return
    }
    router.push('/dashboard')
  }

  return (
    <div className="w-full max-w-lg">
      {/* Step indicator */}
      <div className="flex items-center gap-0 mb-8">
        {STEP_LABELS.map((label, i) => {
          const n = i + 1
          const done = step > n
          const active = step === n
          return (
            <div key={n} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                  done ? 'bg-[var(--brand)] text-black' :
                  active ? 'bg-transparent border-2 border-[var(--brand)] text-[var(--brand)]' :
                  'bg-[#1a1a1a] text-[#444]'
                }`}>
                  {done ? '✓' : n}
                </div>
                <span className={`text-[10px] font-medium ${active ? 'text-[var(--brand)]' : 'text-[#333]'}`}>
                  {label}
                </span>
              </div>
              {i < STEP_LABELS.length - 1 && (
                <div className={`flex-1 h-px mx-2 mb-4 ${done ? 'bg-[var(--brand)]/40' : 'bg-[#1e1e1e]'}`} />
              )}
            </div>
          )
        })}
      </div>

      <div className="p-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
        {/* Step 1: Confirm details */}
        {step === 1 && (
          <div>
            <div className="w-9 h-9 bg-[var(--brand)] rounded-lg mb-6" />
            <h1 className="text-xl font-bold text-white mb-1">Welcome, {client.name}.</h1>
            <p className="text-[var(--muted)] text-sm mb-6">Let's confirm your details before we get started.</p>
            <div className="space-y-3 mb-6">
              {[
                { label: 'Name', value: client.name },
                { label: 'Email', value: client.email },
                { label: 'Company', value: client.company ?? '—' },
                { label: 'Account Manager', value: client.accountManagerName },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-[var(--surface-2)] border border-[var(--border)]">
                  <span className="text-xs text-[var(--muted)]">{label}</span>
                  <span className="text-sm text-white font-medium">{value}</span>
                </div>
              ))}
            </div>
            <button
              onClick={() => setStep(2)}
              className="w-full py-3 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors"
            >
              Looks right, continue →
            </button>
          </div>
        )}

        {/* Step 2: What's included */}
        {step === 2 && (
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-[var(--brand)] mb-1">Your Plan</div>
            <h2 className="text-xl font-bold text-white mb-1">{PLAN_LABELS[client.planTier]}</h2>
            <p className="text-[var(--muted)] text-sm mb-6">Here's what we're delivering for you every month.</p>
            <ul className="space-y-3 mb-6">
              {PLAN_FEATURES[client.planTier].map(feature => (
                <li key={feature} className="flex items-start gap-2.5 text-sm text-[var(--text)]">
                  <span className="text-[var(--brand)] font-bold shrink-0 mt-0.5">✓</span>
                  {feature}
                </li>
              ))}
            </ul>
            <div className="flex gap-3">
              <button
                onClick={() => setStep(1)}
                className="flex-1 py-3 rounded-lg border border-[var(--border)] text-[var(--muted)] text-sm font-medium hover:text-white transition-colors"
              >
                ← Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="flex-1 py-3 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors"
              >
                Got it →
              </button>
            </div>
          </div>
        )}

        {/* Step 3: How to submit footage */}
        {step === 3 && (
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-[var(--brand)] mb-1">Step 3 of 3</div>
            <h2 className="text-xl font-bold text-white mb-1">How to submit footage</h2>
            <p className="text-[var(--muted)] text-sm mb-6">
              Your workflow is simple — you film, we handle everything else.
            </p>
            <div className="space-y-4 mb-6">
              {[
                { n: '1', title: 'Film your content', body: 'Raw footage, podcast recordings, talking head videos — whatever you create.' },
                { n: '2', title: 'Upload via Submit Footage', body: 'Drag and drop your files. Add a title and any notes for our team.' },
                { n: '3', title: 'We edit, caption, and post', body: 'Your account manager handles the rest. Clips appear in your library once they\'re live.' },
              ].map(({ n, title, body }) => (
                <div key={n} className="flex gap-4">
                  <div className="w-7 h-7 rounded-full bg-[#1a2a10] border border-[var(--brand)]/30 flex items-center justify-center text-xs font-bold text-[var(--brand)] shrink-0 mt-0.5">
                    {n}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white mb-0.5">{title}</div>
                    <div className="text-xs text-[var(--muted)] leading-relaxed">{body}</div>
                  </div>
                </div>
              ))}
            </div>
            {error && <p className="text-red-400 text-xs mb-3">{error}</p>}
            <div className="flex gap-3">
              <button
                onClick={() => setStep(2)}
                disabled={loading}
                className="flex-1 py-3 rounded-lg border border-[var(--border)] text-[var(--muted)] text-sm font-medium hover:text-white transition-colors disabled:opacity-50"
              >
                ← Back
              </button>
              <button
                onClick={handleComplete}
                disabled={loading}
                className="flex-1 py-3 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-50 transition-colors"
              >
                {loading ? 'Setting up…' : 'Enter portal →'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add app/onboarding/
git commit -m "feat: add 3-step onboarding wizard"
```

---

## Task 5: Dashboard with Real Data

**Files:**
- Modify: `app/(portal)/dashboard/page.tsx` (replace stub)

Replaces the stub with a real server component that fetches clips, views, unread messages, and recent clips.

- [ ] **Step 1: Replace `app/(portal)/dashboard/page.tsx`**

```typescript
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import Link from 'next/link'

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter',
  growth: 'Growth',
  scale: 'Scale',
}

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
      <div className="text-xs text-[var(--muted)] mb-2">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  )
}

export default async function DashboardPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/auth/login')
  if (!client.onboarding_completed) redirect('/onboarding')

  const supabase = createClient()
  const now = new Date()
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString()
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
    .toISOString().split('T')[0]

  const [
    { count: clipsThisMonth },
    { data: snapshots },
    { count: unreadMessages },
    { data: recentClips },
    { data: platformRows },
  ] = await Promise.all([
    supabase
      .from('clips')
      .select('*', { count: 'exact', head: true })
      .eq('client_id', client.id)
      .gte('created_at', startOfMonth),
    supabase
      .from('performance_snapshots')
      .select('views')
      .eq('client_id', client.id)
      .gte('snapshot_date', thirtyDaysAgo),
    supabase
      .from('messages')
      .select('*', { count: 'exact', head: true })
      .eq('client_id', client.id)
      .is('read_at', null)
      .eq('sender_role', 'admin'),
    supabase
      .from('clips')
      .select('id, title, platform, thumbnail_url, posted_at, created_at')
      .eq('client_id', client.id)
      .order('created_at', { ascending: false })
      .limit(5),
    supabase
      .from('clips')
      .select('platform')
      .eq('client_id', client.id),
  ])

  const totalViews = snapshots?.reduce((sum, s) => sum + (s.views ?? 0), 0) ?? 0
  const platformsActive = new Set(platformRows?.map(r => r.platform)).size

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-1">Dashboard</h1>
      <p className="text-[var(--muted)] text-sm mb-8">
        Welcome back, {client.name}. Here's how your content is performing.
      </p>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Clips this month" value={clipsThisMonth ?? 0} />
        <StatCard label="Total views (30d)" value={formatNumber(totalViews)} />
        <StatCard label="Platforms active" value={platformsActive} />
        <StatCard label="Your plan" value={PLAN_LABELS[client.plan_tier]} />
      </div>

      {/* Unread message alert */}
      {(unreadMessages ?? 0) > 0 && (
        <Link
          href="/messages"
          className="flex items-center gap-3 p-4 mb-6 rounded-xl bg-[#0e1a08] border border-[var(--brand)]/30 text-sm text-white hover:border-[var(--brand)]/60 transition-colors"
        >
          <span className="text-[var(--brand)] text-base">◎</span>
          <span>
            {unreadMessages} unread message{(unreadMessages ?? 0) > 1 ? 's' : ''} from {client.account_manager_name}
          </span>
          <span className="ml-auto text-[var(--muted)] text-xs">View →</span>
        </Link>
      )}

      {/* Recent clips */}
      {recentClips && recentClips.length > 0 ? (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest">Recent Clips</h2>
            <Link href="/clips" className="text-xs text-[var(--brand)] hover:underline">View all →</Link>
          </div>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {recentClips.map(clip => (
              <Link
                key={clip.id}
                href="/clips"
                className="shrink-0 w-36 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--surface)] hover:border-white/20 transition-colors"
              >
                {clip.thumbnail_url ? (
                  <img
                    src={clip.thumbnail_url}
                    alt={clip.title}
                    className="w-full aspect-[9/16] object-cover"
                  />
                ) : (
                  <div className="w-full aspect-[9/16] bg-[var(--surface-2)] flex items-center justify-center">
                    <span className="text-2xl opacity-30">▶</span>
                  </div>
                )}
                <div className="p-2">
                  <div className="text-xs font-medium text-white truncate">{clip.title}</div>
                  <div className="text-[10px] text-[var(--muted)] mt-0.5">
                    {PLATFORM_LABELS[clip.platform] ?? clip.platform}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="p-10 rounded-xl border border-[var(--border)] bg-[var(--surface)] text-center">
          <div className="text-3xl mb-3 opacity-20">▶</div>
          <p className="text-sm text-[var(--muted)] mb-4">Your clips will appear here once they're ready.</p>
          <Link
            href="/submit"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors"
          >
            Submit footage →
          </Link>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Run TypeScript check**

```bash
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/\(portal\)/dashboard/page.tsx
git commit -m "feat: replace dashboard stub with real data"
```

---

## Task 6: Footage API Route

**Files:**
- Create: `app/api/footage/route.ts`
- Create: `__tests__/api/footage.test.ts`

POST endpoint called after a successful storage upload — creates the `footage_submissions` DB record.

- [ ] **Step 1: Write the failing test at `__tests__/api/footage.test.ts`**

```typescript
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(),
}))
jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: { from: jest.fn() },
}))

import { NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { POST } from '@/app/api/footage/route'

const mockInsert = jest.fn()
const mockSelect = jest.fn()
const mockSingle = jest.fn()
const mockClientFrom = jest.fn()
const mockClientSelect = jest.fn()
const mockClientEq = jest.fn()
const mockClientSingle = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()
  mockSingle.mockResolvedValue({ data: { id: 'sub-1', title: 'Test' }, error: null })
  mockSelect.mockReturnValue({ single: mockSingle })
  mockInsert.mockReturnValue({ select: mockSelect })
  ;(supabaseAdmin.from as jest.Mock).mockReturnValue({ insert: mockInsert })

  mockClientSingle.mockResolvedValue({ data: { id: 'client-1' }, error: null })
  mockClientEq.mockReturnValue({ single: mockClientSingle })
  mockClientSelect.mockReturnValue({ eq: mockClientEq })
  mockClientFrom.mockReturnValue({ select: mockClientSelect })
})

function makeRequest(body: unknown) {
  return new NextRequest('http://localhost/api/footage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('POST /api/footage', () => {
  it('returns 401 when not authenticated', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const res = await POST(makeRequest({ fileUrl: 'path', fileName: 'a.mp4', fileSizeBytes: 100, title: 'T' }))
    expect(res.status).toBe(401)
  })

  it('returns 400 when required fields are missing', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
      from: mockClientFrom,
    })
    const res = await POST(makeRequest({ fileUrl: 'path', fileName: 'a.mp4' })) // missing fileSizeBytes, title
    expect(res.status).toBe(400)
  })

  it('returns 201 with submission on success', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
      from: mockClientFrom,
    })
    const res = await POST(makeRequest({
      fileUrl: 'client-1/file.mp4',
      fileName: 'file.mp4',
      fileSizeBytes: 1024,
      title: 'My footage',
      notes: 'Episode 5',
    }))
    expect(res.status).toBe(201)
    const body = await res.json()
    expect(body.submission).toBeDefined()
  })

  it('returns 500 when DB insert fails', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }) },
      from: mockClientFrom,
    })
    mockSingle.mockResolvedValue({ data: null, error: new Error('DB error') })
    const res = await POST(makeRequest({
      fileUrl: 'client-1/file.mp4',
      fileName: 'file.mp4',
      fileSizeBytes: 1024,
      title: 'My footage',
    }))
    expect(res.status).toBe(500)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- --testPathPattern="api/footage" --no-coverage
```

Expected: FAIL — `Cannot find module '@/app/api/footage/route'`

- [ ] **Step 3: Create `app/api/footage/route.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'

const schema = z.object({
  fileUrl: z.string().min(1),
  fileName: z.string().min(1),
  fileSizeBytes: z.number().int().positive(),
  title: z.string().min(1).max(200),
  notes: z.string().max(1000).nullable().optional(),
})

export async function POST(request: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await request.json()
  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const { data: clientRecord } = await supabase
    .from('clients')
    .select('id')
    .eq('user_id', user.id)
    .single()

  if (!clientRecord) return NextResponse.json({ error: 'Client not found' }, { status: 404 })

  const { fileUrl, fileName, fileSizeBytes, title, notes } = parsed.data

  const { data: submission, error } = await supabaseAdmin
    .from('footage_submissions')
    .insert({
      client_id: clientRecord.id,
      file_url: fileUrl,
      file_name: fileName,
      file_size_bytes: fileSizeBytes,
      title,
      notes: notes ?? null,
    })
    .select()
    .single()

  if (error) {
    console.error('Failed to create footage submission:', error)
    return NextResponse.json({ error: 'Failed to save submission' }, { status: 500 })
  }

  return NextResponse.json({ submission }, { status: 201 })
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- --testPathPattern="api/footage" --no-coverage
```

Expected: PASS — 4 tests passing

- [ ] **Step 5: Commit**

```bash
git add app/api/footage/ __tests__/api/footage.test.ts
git commit -m "feat: add footage submission API route"
```

---

## Task 7: Submit Footage Page

**Files:**
- Create: `app/(portal)/submit/page.tsx`
- Create: `app/(portal)/submit/uploader.tsx`

Server wrapper fetches the client ID and submission history. Client component handles drag-drop, upload, and progress.

- [ ] **Step 1: Create `app/(portal)/submit/page.tsx`**

```typescript
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { Uploader } from './uploader'

export default async function SubmitPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/auth/login')
  if (!client.onboarding_completed) redirect('/onboarding')

  const supabase = createClient()
  const { data: submissions } = await supabase
    .from('footage_submissions')
    .select('id, title, file_name, file_size_bytes, notes, uploaded_at')
    .eq('client_id', client.id)
    .order('uploaded_at', { ascending: false })
    .limit(20)

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-white mb-1">Submit Footage</h1>
      <p className="text-[var(--muted)] text-sm mb-8">
        Upload your raw recordings. We'll handle the rest.
      </p>
      <Uploader clientId={client.id} initialSubmissions={submissions ?? []} />
    </div>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/submit/uploader.tsx`**

```typescript
'use client'

import { useState, useCallback, useRef } from 'react'
import { createClient } from '@/lib/supabase/client'
import { clsx } from 'clsx'

interface Submission {
  id: string
  title: string
  file_name: string
  file_size_bytes: number
  notes: string | null
  uploaded_at: string
}

interface Props {
  clientId: string
  initialSubmissions: Submission[]
}

function formatBytes(bytes: number): string {
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function Uploader({ clientId, initialSubmissions }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submissions, setSubmissions] = useState<Submission[]>(initialSubmissions)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const supabase = createClient()

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) {
      setFile(dropped)
      if (!title) setTitle(dropped.name.replace(/\.[^/.]+$/, ''))
    }
  }, [title])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0]
    if (picked) {
      setFile(picked)
      if (!title) setTitle(picked.name.replace(/\.[^/.]+$/, ''))
    }
  }

  const handleUpload = async () => {
    if (!file || !title.trim()) return
    setUploading(true)
    setProgress(0)
    setError('')
    setSuccess('')

    // Animate progress during upload (indeterminate)
    const interval = setInterval(() => {
      setProgress(prev => prev < 85 ? prev + Math.random() * 8 : prev)
    }, 400)

    const ext = file.name.split('.').pop() ?? 'mp4'
    const storagePath = `${clientId}/${Date.now()}.${ext}`

    const { data: uploadData, error: uploadError } = await supabase.storage
      .from('footage-submissions')
      .upload(storagePath, file, { cacheControl: '3600', upsert: false })

    clearInterval(interval)

    if (uploadError) {
      setError(uploadError.message)
      setUploading(false)
      setProgress(0)
      return
    }

    setProgress(95)

    const res = await fetch('/api/footage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fileUrl: uploadData.path,
        fileName: file.name,
        fileSizeBytes: file.size,
        title: title.trim(),
        notes: notes.trim() || null,
      }),
    })

    if (!res.ok) {
      setError('File uploaded but failed to save record. Contact your account manager.')
      setUploading(false)
      return
    }

    const { submission } = await res.json()
    setProgress(100)
    setSubmissions(prev => [submission, ...prev])
    setFile(null)
    setTitle('')
    setNotes('')
    setSuccess('Footage submitted! We\'ll get started on your clips.')
    setTimeout(() => {
      setUploading(false)
      setProgress(0)
      setSuccess('')
    }, 3000)
  }

  return (
    <div>
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors mb-6',
          dragging ? 'border-[var(--brand)] bg-[#0e1a08]' : 'border-[var(--border)] hover:border-[#333]',
          uploading && 'pointer-events-none opacity-60'
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={handleFileChange}
          disabled={uploading}
        />
        {file ? (
          <div>
            <div className="text-2xl mb-2">🎬</div>
            <div className="text-sm font-semibold text-white">{file.name}</div>
            <div className="text-xs text-[var(--muted)] mt-1">{formatBytes(file.size)}</div>
          </div>
        ) : (
          <div>
            <div className="text-3xl mb-3 opacity-30">↑</div>
            <div className="text-sm text-white font-medium mb-1">Drop your video here</div>
            <div className="text-xs text-[var(--muted)]">or click to browse — MP4, MOV, WebM up to 4GB</div>
          </div>
        )}
      </div>

      {/* Form fields */}
      {file && (
        <div className="space-y-4 mb-6">
          <div>
            <label className="block text-xs text-[var(--muted)] mb-1.5">Title <span className="text-red-400">*</span></label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Podcast Episode 12 — Raw"
              disabled={uploading}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-[#333] focus:outline-none focus:border-[var(--brand)] disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--muted)] mb-1.5">Notes <span className="text-[#444]">(optional)</span></label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Any context for our team — timestamps, topics, preferences…"
              rows={3}
              disabled={uploading}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-[#333] focus:outline-none focus:border-[var(--brand)] disabled:opacity-50 resize-none"
            />
          </div>
        </div>
      )}

      {/* Progress bar */}
      {uploading && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs text-[var(--muted)] mb-1.5">
            <span>Uploading…</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--brand)] rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
      {success && <p className="text-[var(--brand)] text-sm mb-4">{success}</p>}

      {file && (
        <button
          onClick={handleUpload}
          disabled={uploading || !title.trim()}
          className="w-full py-3 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-50 disabled:cursor-not-allowed transition-colors mb-8"
        >
          {uploading ? 'Uploading…' : 'Submit Footage →'}
        </button>
      )}

      {/* Submission history */}
      {submissions.length > 0 && (
        <div>
          <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest mb-4">Past Submissions</h2>
          <div className="divide-y divide-[var(--border)] border border-[var(--border)] rounded-xl overflow-hidden">
            {submissions.map(sub => (
              <div key={sub.id} className="flex items-start gap-4 px-5 py-4 bg-[var(--surface)]">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-white truncate">{sub.title}</div>
                  <div className="text-xs text-[var(--muted)] mt-0.5 truncate">
                    {sub.file_name} · {formatBytes(sub.file_size_bytes)}
                  </div>
                  {sub.notes && (
                    <div className="text-xs text-[#555] mt-1 truncate">{sub.notes}</div>
                  )}
                </div>
                <div className="text-xs text-[var(--muted)] shrink-0 mt-0.5">
                  {formatDate(sub.uploaded_at)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add app/\(portal\)/submit/
git commit -m "feat: add footage submission page with drag-drop uploader"
```

---

## Task 8: Clip Library

**Files:**
- Create: `app/(portal)/clips/page.tsx`
- Create: `app/(portal)/clips/clip-grid.tsx`
- Create: `app/(portal)/clips/clip-modal.tsx`

Server component fetches all clips; client component handles platform filter and modal.

- [ ] **Step 1: Create `app/(portal)/clips/clip-modal.tsx`**

```typescript
'use client'

import { useEffect } from 'react'

interface Clip {
  id: string
  title: string
  platform: 'tiktok' | 'instagram' | 'youtube'
  video_url: string
  thumbnail_url: string | null
  caption: string | null
  posted_at: string | null
  created_at: string
}

interface Props {
  clip: Clip
  onClose: () => void
}

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
}

const PLATFORM_COLORS: Record<string, string> = {
  tiktok: 'bg-black text-white',
  instagram: 'bg-gradient-to-r from-purple-600 to-pink-500 text-white',
  youtube: 'bg-red-600 text-white',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

export function ClipModal({ clip, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-lg bg-[var(--surface)] border border-[var(--border)] rounded-2xl overflow-hidden">
        {/* Thumbnail / video preview */}
        {clip.thumbnail_url ? (
          <img
            src={clip.thumbnail_url}
            alt={clip.title}
            className="w-full aspect-video object-cover"
          />
        ) : (
          <div className="w-full aspect-video bg-[var(--surface-2)] flex items-center justify-center">
            <span className="text-4xl opacity-20">▶</span>
          </div>
        )}

        <div className="p-6">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 className="text-lg font-bold text-white mb-1">{clip.title}</h2>
              <span className={`inline-block text-xs font-bold px-2.5 py-1 rounded-full ${PLATFORM_COLORS[clip.platform]}`}>
                {PLATFORM_LABELS[clip.platform]}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-[var(--muted)] hover:text-white transition-colors text-xl leading-none mt-1"
            >
              ✕
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-[var(--muted)]">Posted</span>
              <span className="text-white">{formatDate(clip.posted_at)}</span>
            </div>
            {clip.caption && (
              <div>
                <div className="text-xs text-[var(--muted)] mb-1">Caption</div>
                <p className="text-sm text-[var(--text)] leading-relaxed">{clip.caption}</p>
              </div>
            )}
          </div>

          <a
            href={clip.video_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-[var(--border)] text-sm text-white hover:border-white/30 transition-colors"
          >
            Open video ↗
          </a>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/clips/clip-grid.tsx`**

```typescript
'use client'

import { useState } from 'react'
import { ClipModal } from './clip-modal'
import { clsx } from 'clsx'

type Platform = 'tiktok' | 'instagram' | 'youtube'

interface Clip {
  id: string
  title: string
  platform: Platform
  video_url: string
  thumbnail_url: string | null
  caption: string | null
  posted_at: string | null
  created_at: string
}

interface Props {
  clips: Clip[]
}

const PLATFORM_LABELS: Record<Platform, string> = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
}

const PLATFORM_BADGE: Record<Platform, string> = {
  tiktok: 'bg-black text-white',
  instagram: 'bg-gradient-to-r from-purple-600 to-pink-500 text-white',
  youtube: 'bg-red-600 text-white',
}

const FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'youtube', label: 'YouTube' },
] as const

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function ClipGrid({ clips }: Props) {
  const [filter, setFilter] = useState<'all' | Platform>('all')
  const [selected, setSelected] = useState<Clip | null>(null)

  const visible = filter === 'all' ? clips : clips.filter(c => c.platform === filter)

  return (
    <div>
      {/* Platform filter tabs */}
      <div className="flex gap-2 mb-6">
        {FILTER_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              filter === opt.value
                ? 'bg-[var(--brand)] text-black'
                : 'bg-[var(--surface)] border border-[var(--border)] text-[var(--muted)] hover:text-white'
            )}
          >
            {opt.label}
          </button>
        ))}
        <span className="ml-auto text-sm text-[var(--muted)] self-center">
          {visible.length} clip{visible.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Grid */}
      {visible.length === 0 ? (
        <div className="py-20 text-center">
          <div className="text-3xl mb-3 opacity-20">▶</div>
          <p className="text-sm text-[var(--muted)]">
            {filter === 'all' ? 'No clips yet — they'll appear here once they're live.' : `No ${PLATFORM_LABELS[filter as Platform]} clips yet.`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {visible.map(clip => (
            <button
              key={clip.id}
              onClick={() => setSelected(clip)}
              className="group text-left rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--surface)] hover:border-white/20 transition-colors"
            >
              {/* Thumbnail */}
              <div className="relative aspect-[9/16] bg-[var(--surface-2)]">
                {clip.thumbnail_url ? (
                  <img
                    src={clip.thumbnail_url}
                    alt={clip.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-2xl opacity-20">▶</span>
                  </div>
                )}
                {/* Platform badge */}
                <span className={clsx(
                  'absolute top-2 left-2 text-[10px] font-bold px-2 py-0.5 rounded-full',
                  PLATFORM_BADGE[clip.platform]
                )}>
                  {PLATFORM_LABELS[clip.platform]}
                </span>
              </div>
              {/* Info */}
              <div className="p-2.5">
                <div className="text-xs font-semibold text-white leading-tight truncate">{clip.title}</div>
                <div className="text-[10px] text-[var(--muted)] mt-0.5">{formatDate(clip.posted_at)}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Modal */}
      {selected && (
        <ClipModal clip={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create `app/(portal)/clips/page.tsx`**

```typescript
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { ClipGrid } from './clip-grid'

export default async function ClipsPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/auth/login')
  if (!client.onboarding_completed) redirect('/onboarding')

  const supabase = createClient()
  const { data: clips } = await supabase
    .from('clips')
    .select('id, title, platform, video_url, thumbnail_url, caption, posted_at, created_at')
    .eq('client_id', client.id)
    .order('created_at', { ascending: false })

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-1">Clip Library</h1>
      <p className="text-[var(--muted)] text-sm mb-8">
        Every clip we've made for you, organized by platform.
      </p>
      <ClipGrid clips={clips ?? []} />
    </div>
  )
}
```

- [ ] **Step 4: Run TypeScript check**

```bash
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add app/\(portal\)/clips/
git commit -m "feat: add clip library with platform filter and detail modal"
```

---

## Task 9: Run All Tests + Deploy

**Files:** None (verification + deploy)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npm test
```

Expected: all tests pass (should be 25+ tests across 5 test files)

- [ ] **Step 2: TypeScript check**

```bash
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Push and deploy**

```bash
git push
vercel --prod
```

Expected: build succeeds, deployment aliased to `https://hub.vyrulhq.com`

- [ ] **Step 4: Smoke test on hub.vyrulhq.com**

Manual checks:
- Sign in → if first time client, should hit `/onboarding`
- Complete onboarding → lands on `/dashboard`
- Dashboard shows stat cards (zeros if no data yet)
- `/submit` shows drop zone, can select a file
- `/clips` shows empty state if no clips

---

## Self-Review

**Spec coverage:**
- ✅ Onboarding wizard: 3-step (confirm details → plan features → how to submit), completion sets `onboarding_completed=true` and `status=active`
- ✅ Dashboard: clips this month, total views (30d), platforms active, plan tier, recent clips strip, unread message alert
- ✅ Submit Footage: drag-drop zone, title (required), notes (optional), progress bar, history of past submissions
- ✅ Clip Library: platform filter (All/TikTok/Instagram/YouTube), grid of clip cards (thumbnail, title, platform badge, posted date), click → modal (caption, posted date, platform, video link)
- ✅ RLS: footage upload uses service role only for DB write (API route), storage policies use `my_client_id()` pattern
- ✅ Deferred: per-clip metrics are not included (deferred to V2 per spec)

**Gaps check:**
- Dashboard "next billing date" — spec mentions this but requires Stripe integration (Plan 3). Replaced with plan tier which is available now.
- Storage bucket must be created in Supabase before footage upload works — Task 1 covers this.

**Type consistency:**
- `ClientRecord` defined in `lib/client.ts`, used as prop type in `onboarding-wizard.tsx` (passed as plain object, no import needed)
- `Clip` interface defined inline in `clip-grid.tsx` and `clip-modal.tsx` — same fields, consistent
- `Submission` interface defined in `uploader.tsx` — matches `footage_submissions` table columns exactly
