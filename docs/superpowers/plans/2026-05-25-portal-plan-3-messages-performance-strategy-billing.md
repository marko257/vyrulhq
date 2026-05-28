# VyrulHQ Client Portal — Plan 3: Messages, Performance, Strategy & Billing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the client messages thread (Supabase Realtime), performance snapshot dashboard, read-only strategy board, simplified billing page, and admin client list with message reply capability.

**Architecture:** All client-facing pages follow the established pattern: server component wrapper fetches initial data via `getCurrentClient()` + Supabase, passes to a `'use client'` component where interactivity is needed. Messages uses Supabase Realtime via `postgres_changes` subscription on the `messages` table. Performance reads from `performance_snapshots` (a pre-aggregated cache table). Strategy and billing are pure server components. The admin side adds a client list and per-client message thread at `/admin/clients` and `/admin/clients/[id]`.

**Tech Stack:** Next.js 14 App Router, Supabase (DB + Realtime), `@supabase/ssr` v0.10.3, `@/lib/supabase/client` (browser singleton for Realtime), Tailwind CSS, lucide-react, TypeScript

---

## File Structure

```
supabase/migrations/003_realtime.sql                    — enable Realtime on messages table
app/(portal)/dashboard/page.tsx                         — MODIFY: fix from_admin → sender_role bug
app/api/messages/route.ts                               — POST: send a message (client or admin)
app/api/messages/read/route.ts                          — PATCH: mark messages as read
__tests__/api/messages.test.ts                          — unit tests for send API
__tests__/api/messages-read.test.ts                     — unit tests for read API
app/(portal)/messages/page.tsx                          — server wrapper (fetch initial messages)
app/(portal)/messages/message-thread.tsx                — 'use client' Realtime chat component
app/(portal)/performance/page.tsx                       — server component (reads searchParams for range)
app/(portal)/performance/range-tabs.tsx                 — 'use client' time range selector
app/(portal)/strategy/page.tsx                          — server component (read-only strategy board)
app/(portal)/billing/page.tsx                           — server component (plan info, no Stripe)
app/admin/clients/page.tsx                              — server component (client list)
app/admin/clients/[id]/page.tsx                         — server wrapper (admin message thread)
app/admin/clients/[id]/admin-thread.tsx                 — 'use client' Realtime admin thread
```

---

## Context for Implementers

**Established patterns (Plans 1 & 2):**
- `getCurrentClient()` from `@/lib/client` — returns `ClientRecord | null` (uses anon key + RLS)
- `createClient()` from `@/lib/supabase/server` — SSR server client (anon key)
- `createClient()` from `@/lib/supabase/client` — browser singleton (anon key, for Realtime)
- `supabaseAdmin` from `@/lib/supabase/admin` — service role, bypasses RLS
- CSS vars: `--brand: #a8ff57`, `--bg: #080808`, `--surface: #101010`, `--surface-2: #161616`, `--border: #1e1e1e`, `--muted: #666`
- Portal routes under `app/(portal)/` are auth-protected by middleware
- Admin routes under `app/admin/` require `user.app_metadata.role === 'admin'`

**Schema (relevant tables):**
```
messages: id, client_id, sender_id, sender_role (client|admin), body, read_at, created_at
performance_snapshots: id, client_id, platform (tiktok|instagram|youtube), snapshot_date, views, likes, comments, shares, followers, posts_count, created_at
strategy_boards: id, client_id, content (jsonb: {active_formats, hook_angles, upcoming_themes, manager_notes}), updated_by, updated_at
clients: id, user_id, name, company, email, plan_tier, status, onboarding_completed, account_manager_name, created_at
```

**Known bug:** `app/(portal)/dashboard/page.tsx` queries `.eq('from_admin', true)` — column doesn't exist. Correct column is `sender_role`. Fixed in Task 1.

---

## Task 1: DB migration + fix dashboard bug

**Files:**
- Create: `supabase/migrations/003_realtime.sql`
- Modify: `app/(portal)/dashboard/page.tsx`

- [ ] **Step 1: Create `supabase/migrations/003_realtime.sql`**

```sql
-- Enable Realtime on messages table so clients and admins get live updates
alter publication supabase_realtime add table messages;

-- Optional: seed performance snapshot demo data for a client
-- Replace 'YOUR_CLIENT_ID' with a real client UUID from your clients table
-- Run this section separately after confirming a client ID exists:
--
-- insert into performance_snapshots
--   (client_id, platform, snapshot_date, views, likes, comments, shares, followers, posts_count)
-- select
--   'YOUR_CLIENT_ID'::uuid,
--   platform,
--   (current_date - (n || ' days')::interval)::date,
--   (random() * 50000 + 1000)::bigint,
--   (random() * 2000 + 50)::bigint,
--   (random() * 300 + 10)::bigint,
--   (random() * 500 + 20)::bigint,
--   (10000 + n * 50)::bigint,
--   2
-- from
--   generate_series(0, 29) as n,
--   unnest(array['tiktok', 'instagram', 'youtube']::platform_type[]) as platform
-- on conflict (client_id, platform, snapshot_date) do nothing;
```

- [ ] **Step 2: Run in Supabase SQL Editor**

Copy the file contents into Supabase → SQL Editor → Run.

Expected: "Success. No rows returned."

**Note:** The commented-out seed block is optional. To seed demo performance data: find a client UUID in the `clients` table, replace `YOUR_CLIENT_ID`, uncomment the insert block, and run it separately.

- [ ] **Step 3: Fix the dashboard `from_admin` bug**

In `app/(portal)/dashboard/page.tsx`, find this query (around line 25-30):
```typescript
    supabase
      .from('messages')
      .select('id')
      .eq('client_id', client.id)
      .eq('from_admin', true)
      .is('read_at', null),
```

Replace `.eq('from_admin', true)` with `.eq('sender_role', 'admin')`:
```typescript
    supabase
      .from('messages')
      .select('id')
      .eq('client_id', client.id)
      .eq('sender_role', 'admin')
      .is('read_at', null),
```

- [ ] **Step 4: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add supabase/migrations/003_realtime.sql app/\(portal\)/dashboard/page.tsx
git commit -m "feat: enable messages Realtime, fix dashboard sender_role query"
```

---

## Task 2: Messages send + read APIs with tests

**Files:**
- Create: `app/api/messages/route.ts`
- Create: `app/api/messages/read/route.ts`
- Create: `__tests__/api/messages.test.ts`
- Create: `__tests__/api/messages-read.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `__tests__/api/messages.test.ts`:

```typescript
import { NextRequest } from 'next/server'
import { POST } from '@/app/api/messages/route'

jest.mock('@/lib/client', () => ({ getCurrentClient: jest.fn() }))
jest.mock('@/lib/supabase/server', () => ({ createClient: jest.fn() }))
jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: { from: jest.fn() },
}))

const { getCurrentClient } = jest.requireMock('@/lib/client')
const { createClient } = jest.requireMock('@/lib/supabase/server')
const { supabaseAdmin } = jest.requireMock('@/lib/supabase/admin')

function makeRequest(body: unknown) {
  return new NextRequest('http://localhost/api/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('POST /api/messages', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns 401 when not authenticated', async () => {
    createClient.mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const res = await POST(makeRequest({ body: 'hello' }))
    expect(res.status).toBe(401)
  })

  it('returns 400 for empty body text', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'user-1', app_metadata: {} } },
        }),
      },
    })
    getCurrentClient.mockResolvedValue({ id: 'client-1' })
    const res = await POST(makeRequest({ body: '' }))
    expect(res.status).toBe(400)
  })

  it('returns 201 when client sends message', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'user-1', app_metadata: {} } },
        }),
      },
    })
    getCurrentClient.mockResolvedValue({ id: 'client-1' })
    supabaseAdmin.from.mockReturnValue({
      insert: jest.fn().mockResolvedValue({ error: null }),
    })
    const res = await POST(makeRequest({ body: 'Hello account manager!' }))
    expect(res.status).toBe(201)
    const data = await res.json()
    expect(data.ok).toBe(true)
  })

  it('returns 201 when admin sends message with clientId', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'admin-1', app_metadata: { role: 'admin' } } },
        }),
      },
    })
    supabaseAdmin.from.mockReturnValue({
      insert: jest.fn().mockResolvedValue({ error: null }),
    })
    const res = await POST(makeRequest({ body: 'Hi client!', clientId: 'client-1' }))
    expect(res.status).toBe(201)
  })

  it('returns 400 when admin omits clientId', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'admin-1', app_metadata: { role: 'admin' } } },
        }),
      },
    })
    const res = await POST(makeRequest({ body: 'Hi client!' }))
    expect(res.status).toBe(400)
  })
})
```

Create `__tests__/api/messages-read.test.ts`:

```typescript
import { NextRequest } from 'next/server'
import { PATCH } from '@/app/api/messages/read/route'

jest.mock('@/lib/client', () => ({ getCurrentClient: jest.fn() }))
jest.mock('@/lib/supabase/server', () => ({ createClient: jest.fn() }))
jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: { from: jest.fn() },
}))

const { getCurrentClient } = jest.requireMock('@/lib/client')
const { createClient } = jest.requireMock('@/lib/supabase/server')
const { supabaseAdmin } = jest.requireMock('@/lib/supabase/admin')

function makeRequest(body: unknown) {
  return new NextRequest('http://localhost/api/messages/read', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('PATCH /api/messages/read', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns 401 when not authenticated', async () => {
    createClient.mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const res = await PATCH(makeRequest({}))
    expect(res.status).toBe(401)
  })

  it('marks admin messages as read for client', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'user-1', app_metadata: {} } },
        }),
      },
    })
    getCurrentClient.mockResolvedValue({ id: 'client-1' })
    const eqMock = jest.fn().mockReturnThis()
    const isMock = jest.fn().mockResolvedValue({ error: null })
    supabaseAdmin.from.mockReturnValue({
      update: jest.fn().mockReturnValue({ eq: eqMock }),
    })
    eqMock.mockReturnValue({ eq: eqMock, is: isMock })

    const res = await PATCH(makeRequest({}))
    expect(res.status).toBe(200)
    const data = await res.json()
    expect(data.ok).toBe(true)
  })

  it('marks client messages as read for admin', async () => {
    createClient.mockReturnValue({
      auth: {
        getUser: jest.fn().mockResolvedValue({
          data: { user: { id: 'admin-1', app_metadata: { role: 'admin' } } },
        }),
      },
    })
    const eqMock = jest.fn().mockReturnThis()
    const isMock = jest.fn().mockResolvedValue({ error: null })
    supabaseAdmin.from.mockReturnValue({
      update: jest.fn().mockReturnValue({ eq: eqMock }),
    })
    eqMock.mockReturnValue({ eq: eqMock, is: isMock })

    const res = await PATCH(makeRequest({ clientId: 'client-1' }))
    expect(res.status).toBe(200)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx jest __tests__/api/messages.test.ts __tests__/api/messages-read.test.ts --no-coverage 2>&1 | tail -15
```

Expected: FAIL (cannot find module)

- [ ] **Step 3: Create `app/api/messages/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { getCurrentClient } from '@/lib/client'
import { supabaseAdmin } from '@/lib/supabase/admin'

const ClientBodySchema = z.object({ body: z.string().min(1) })
const AdminBodySchema = z.object({
  body: z.string().min(1),
  clientId: z.string().uuid(),
})

export async function POST(request: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const isAdmin = user.app_metadata?.role === 'admin'
  const rawBody = await request.json()

  if (isAdmin) {
    const parsed = AdminBodySchema.safeParse(rawBody)
    if (!parsed.success) return NextResponse.json({ error: 'Invalid request' }, { status: 400 })

    const { error } = await supabaseAdmin.from('messages').insert({
      client_id: parsed.data.clientId,
      sender_id: user.id,
      sender_role: 'admin',
      body: parsed.data.body,
    })
    if (error) return NextResponse.json({ error: 'Failed to send' }, { status: 500 })
    return NextResponse.json({ ok: true }, { status: 201 })
  }

  const client = await getCurrentClient()
  if (!client) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const parsed = ClientBodySchema.safeParse(rawBody)
  if (!parsed.success) return NextResponse.json({ error: 'Invalid request' }, { status: 400 })

  const { error } = await supabaseAdmin.from('messages').insert({
    client_id: client.id,
    sender_id: user.id,
    sender_role: 'client',
    body: parsed.data.body,
  })
  if (error) return NextResponse.json({ error: 'Failed to send' }, { status: 500 })
  return NextResponse.json({ ok: true }, { status: 201 })
}
```

- [ ] **Step 4: Create `app/api/messages/read/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { getCurrentClient } from '@/lib/client'
import { supabaseAdmin } from '@/lib/supabase/admin'

export async function PATCH(request: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const isAdmin = user.app_metadata?.role === 'admin'
  let clientId: string
  let senderRoleToMark: 'client' | 'admin'

  if (isAdmin) {
    const rawBody = await request.json().catch(() => ({}))
    const parsed = z.object({ clientId: z.string().uuid() }).safeParse(rawBody)
    if (!parsed.success) return NextResponse.json({ error: 'Invalid request' }, { status: 400 })
    clientId = parsed.data.clientId
    senderRoleToMark = 'client'
  } else {
    const client = await getCurrentClient()
    if (!client) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    clientId = client.id
    senderRoleToMark = 'admin'
  }

  await supabaseAdmin
    .from('messages')
    .update({ read_at: new Date().toISOString() })
    .eq('client_id', clientId)
    .eq('sender_role', senderRoleToMark)
    .is('read_at', null)

  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx jest __tests__/api/messages.test.ts __tests__/api/messages-read.test.ts --no-coverage 2>&1 | tail -15
```

Expected: 8 tests passing

- [ ] **Step 6: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/api/messages/ __tests__/api/messages.test.ts __tests__/api/messages-read.test.ts
git commit -m "feat: messages send and read APIs"
```

---

## Task 3: Client messages page with Realtime

**Files:**
- Create: `app/(portal)/messages/page.tsx`
- Create: `app/(portal)/messages/message-thread.tsx`

- [ ] **Step 1: Create `app/(portal)/messages/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { MessageThread } from './message-thread'

export default async function MessagesPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const supabase = createClient()
  const { data: messages } = await supabase
    .from('messages')
    .select('id, body, sender_role, read_at, created_at')
    .eq('client_id', client.id)
    .order('created_at', { ascending: true })

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col max-w-2xl mx-auto -m-8">
      <div className="px-6 py-4 border-b border-[var(--border)] shrink-0">
        <h1 className="text-lg font-bold text-white">Messages</h1>
        <p className="text-xs text-[var(--muted)] mt-0.5">
          {client.account_manager_name} · Account Manager
        </p>
      </div>
      <MessageThread
        initialMessages={messages ?? []}
        clientId={client.id}
        accountManagerName={client.account_manager_name}
      />
    </div>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/messages/message-thread.tsx`**

```typescript
'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { createClient } from '@/lib/supabase/client'

interface Message {
  id: string
  body: string
  sender_role: 'client' | 'admin'
  read_at: string | null
  created_at: string
}

interface Props {
  initialMessages: Message[]
  clientId: string
  accountManagerName: string
}

const supabase = createClient()

export function MessageThread({ initialMessages, clientId, accountManagerName }: Props) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/messages/read', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientId }),
    })
  }, [clientId])

  useEffect(() => {
    const channel = supabase
      .channel(`messages:${clientId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: `client_id=eq.${clientId}`,
        },
        (payload) => {
          setMessages((prev) => [...prev, payload.new as Message])
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [clientId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return
    const text = input.trim()
    setInput('')
    setSending(true)
    await fetch('/api/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: text }),
    })
    setSending(false)
  }, [input, sending])

  return (
    <>
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-[var(--muted)] text-sm py-12">
            <div className="text-2xl mb-2">💬</div>
            <p>No messages yet. Say hello to {accountManagerName}!</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender_role === 'client' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.sender_role === 'admin' && (
              <div className="w-6 h-6 rounded-full bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center text-xs text-[var(--muted)] shrink-0 mr-2 mt-0.5">
                M
              </div>
            )}
            <div
              className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                msg.sender_role === 'client'
                  ? 'bg-[var(--brand)] text-black rounded-br-sm font-medium'
                  : 'bg-[var(--surface-2)] text-white rounded-bl-sm border border-[var(--border)]'
              }`}
            >
              {msg.body}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 border-t border-[var(--border)] flex gap-3 shrink-0">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder={`Message ${accountManagerName}…`}
          className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-[var(--muted)] focus:outline-none focus:border-[var(--brand)] transition-colors"
          disabled={sending}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || sending}
          className="px-4 py-2.5 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-40 transition-colors shrink-0"
        >
          Send
        </button>
      </div>
    </>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

Fix any errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/\(portal\)/messages/
git commit -m "feat: client messages page with Realtime"
```

---

## Task 4: Admin client list + message thread

**Files:**
- Create: `app/admin/clients/page.tsx`
- Create: `app/admin/clients/[id]/page.tsx`
- Create: `app/admin/clients/[id]/admin-thread.tsx`

The admin sidebar already has a "Clients" nav item pointing to `/admin/clients`. These pages satisfy that link.

- [ ] **Step 1: Create `app/admin/clients/page.tsx`**

```typescript
import { supabaseAdmin } from '@/lib/supabase/admin'
import Link from 'next/link'

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter',
  growth: 'Growth',
  scale: 'Scale',
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-[#1a2a10] text-[var(--brand)]',
  onboarding: 'bg-blue-950 text-blue-400',
  invited: 'bg-[#1a1a1a] text-[var(--muted)]',
  paused: 'bg-yellow-950 text-yellow-400',
  churned: 'bg-red-950 text-red-400',
}

export default async function AdminClientsPage() {
  const [clientsResult, unreadResult] = await Promise.all([
    supabaseAdmin
      .from('clients')
      .select('id, name, company, plan_tier, status, created_at')
      .order('created_at', { ascending: false }),
    supabaseAdmin
      .from('messages')
      .select('client_id')
      .eq('sender_role', 'client')
      .is('read_at', null),
  ])

  const clients = clientsResult.data ?? []
  const unreadMap = (unreadResult.data ?? []).reduce(
    (acc, m) => { acc[m.client_id] = (acc[m.client_id] ?? 0) + 1; return acc },
    {} as Record<string, number>
  )

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-white mb-6">Clients</h1>

      {clients.length === 0 ? (
        <p className="text-[var(--muted)] text-sm">No clients yet. Send an invite to get started.</p>
      ) : (
        <div className="divide-y divide-[var(--border)] border border-[var(--border)] rounded-xl overflow-hidden">
          {clients.map((client) => (
            <Link
              key={client.id}
              href={`/admin/clients/${client.id}`}
              className="flex items-center gap-4 px-5 py-4 bg-[var(--surface)] hover:bg-[var(--surface-2)] transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-white">{client.name}</div>
                <div className="text-xs text-[var(--muted)] truncate">{client.company}</div>
              </div>
              <div className="text-xs text-[var(--muted)] shrink-0">
                {PLAN_LABELS[client.plan_tier] ?? client.plan_tier}
              </div>
              <div
                className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${
                  STATUS_STYLES[client.status] ?? 'bg-[#1a1a1a] text-[var(--muted)]'
                }`}
              >
                {client.status}
              </div>
              {unreadMap[client.id] > 0 && (
                <span className="w-5 h-5 rounded-full bg-[var(--brand)] text-black text-xs font-bold flex items-center justify-center shrink-0">
                  {unreadMap[client.id]}
                </span>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `app/admin/clients/[id]/page.tsx`**

```typescript
import { supabaseAdmin } from '@/lib/supabase/admin'
import { notFound } from 'next/navigation'
import { AdminThread } from './admin-thread'

interface Props {
  params: { id: string }
}

export default async function AdminClientPage({ params }: Props) {
  const [clientResult, messagesResult] = await Promise.all([
    supabaseAdmin
      .from('clients')
      .select('id, name, company, plan_tier, status, email, account_manager_name, created_at')
      .eq('id', params.id)
      .single(),
    supabaseAdmin
      .from('messages')
      .select('id, body, sender_role, read_at, created_at')
      .eq('client_id', params.id)
      .order('created_at', { ascending: true }),
  ])

  if (!clientResult.data) notFound()
  const client = clientResult.data
  const messages = messagesResult.data ?? []

  const PLAN_LABELS: Record<string, string> = {
    starter: 'Starter — $997/mo',
    growth: 'Growth — $1,997/mo',
    scale: 'Scale — $3,497/mo',
  }

  return (
    <div className="max-w-2xl">
      {/* Client info header */}
      <div className="mb-6 p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <h1 className="text-xl font-bold text-white">{client.name}</h1>
        <div className="flex gap-4 mt-2">
          <span className="text-xs text-[var(--muted)]">{client.company}</span>
          <span className="text-xs text-[var(--muted)]">{client.email}</span>
          <span className="text-xs text-[var(--muted)]">
            {PLAN_LABELS[client.plan_tier] ?? client.plan_tier}
          </span>
          <span className="text-xs text-[var(--muted)] capitalize">{client.status}</span>
        </div>
      </div>

      {/* Message thread */}
      <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest mb-3">
        Messages
      </h2>
      <div className="border border-[var(--border)] rounded-xl overflow-hidden flex flex-col h-[60vh]">
        <AdminThread
          initialMessages={messages}
          clientId={client.id}
          clientName={client.name}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create `app/admin/clients/[id]/admin-thread.tsx`**

```typescript
'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { createClient } from '@/lib/supabase/client'

interface Message {
  id: string
  body: string
  sender_role: 'client' | 'admin'
  read_at: string | null
  created_at: string
}

interface Props {
  initialMessages: Message[]
  clientId: string
  clientName: string
}

const supabase = createClient()

export function AdminThread({ initialMessages, clientId, clientName }: Props) {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/messages/read', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientId }),
    })
  }, [clientId])

  useEffect(() => {
    const channel = supabase
      .channel(`admin-messages:${clientId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: `client_id=eq.${clientId}`,
        },
        (payload) => {
          setMessages((prev) => [...prev, payload.new as Message])
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [clientId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return
    const text = input.trim()
    setInput('')
    setSending(true)
    await fetch('/api/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: text, clientId }),
    })
    setSending(false)
  }, [input, sending, clientId])

  return (
    <>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-[var(--muted)] text-sm py-8">
            No messages yet with {clientName}.
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender_role === 'admin' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                msg.sender_role === 'admin'
                  ? 'bg-[var(--brand)] text-black rounded-br-sm font-medium'
                  : 'bg-[var(--surface-2)] text-white rounded-bl-sm border border-[var(--border)]'
              }`}
            >
              {msg.body}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t border-[var(--border)] flex gap-2 shrink-0">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder={`Reply to ${clientName}…`}
          className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white placeholder:text-[var(--muted)] focus:outline-none focus:border-[var(--brand)] transition-colors"
          disabled={sending}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || sending}
          className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] disabled:opacity-40 transition-colors shrink-0"
        >
          Send
        </button>
      </div>
    </>
  )
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

Fix any errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/admin/clients/
git commit -m "feat: admin client list and message thread"
```

---

## Task 5: Performance page

**Files:**
- Create: `app/(portal)/performance/page.tsx`
- Create: `app/(portal)/performance/range-tabs.tsx`

The page reads `searchParams.range` (default `'30d'`) to filter snapshots. The `RangeTabs` client component updates the URL with `router.push`.

- [ ] **Step 1: Create `app/(portal)/performance/range-tabs.tsx`**

```typescript
'use client'

import { useRouter, useSearchParams } from 'next/navigation'

const RANGES = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
]

export function RangeTabs({ current }: { current: string }) {
  const router = useRouter()
  const searchParams = useSearchParams()

  function setRange(range: string) {
    const params = new URLSearchParams(searchParams.toString())
    params.set('range', range)
    router.push(`/performance?${params.toString()}`)
  }

  return (
    <div className="flex gap-2">
      {RANGES.map((r) => (
        <button
          key={r.value}
          onClick={() => setRange(r.value)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            current === r.value
              ? 'bg-[var(--brand)] text-black'
              : 'bg-[var(--surface)] text-[var(--muted)] hover:text-white border border-[var(--border)]'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/performance/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { Suspense } from 'react'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'
import { RangeTabs } from './range-tabs'

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
}

const RANGES: Record<string, number> = { '7d': 7, '30d': 30, '90d': 90 }

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

interface SearchParams { range?: string }

export default async function PerformancePage({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const range = searchParams.range && RANGES[searchParams.range] ? searchParams.range : '30d'
  const days = RANGES[range]
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000)
    .toISOString()
    .split('T')[0]

  const supabase = createClient()
  const { data: snapshots } = await supabase
    .from('performance_snapshots')
    .select('platform, snapshot_date, views, likes, comments, shares, followers, posts_count')
    .eq('client_id', client.id)
    .gte('snapshot_date', since)
    .order('snapshot_date', { ascending: true })

  const all = snapshots ?? []

  // Aggregate by platform
  const platforms = ['tiktok', 'instagram', 'youtube'] as const
  const stats = platforms.map((platform) => {
    const rows = all.filter((s) => s.platform === platform)
    const totalViews = rows.reduce((sum, s) => sum + s.views, 0)
    const totalLikes = rows.reduce((sum, s) => sum + s.likes, 0)
    const totalComments = rows.reduce((sum, s) => sum + s.comments, 0)
    const totalPosts = rows.reduce((sum, s) => sum + s.posts_count, 0)
    const firstFollowers = rows[0]?.followers ?? 0
    const lastFollowers = rows[rows.length - 1]?.followers ?? 0
    const followerGrowth = lastFollowers - firstFollowers
    return { platform, totalViews, totalLikes, totalComments, totalPosts, followerGrowth, rows }
  })

  const hasData = all.length > 0

  return (
    <div className="max-w-4xl space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Performance</h1>
          <p className="text-[var(--muted)] text-sm mt-1">
            Stats across your managed platforms
          </p>
        </div>
        <Suspense>
          <RangeTabs current={range} />
        </Suspense>
      </div>

      {!hasData ? (
        <div className="text-center py-16 text-[var(--muted)]">
          <div className="text-3xl mb-3">📊</div>
          <p className="text-sm">No stats yet for this period.</p>
          <p className="text-xs mt-1">
            Performance data is updated daily once your social accounts are connected.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {stats.map(({ platform, totalViews, totalLikes, totalComments, totalPosts, followerGrowth, rows }) => {
            if (rows.length === 0) return null
            const maxViews = Math.max(...rows.map((r) => r.views), 1)
            return (
              <div key={platform} className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
                <h2 className="text-base font-bold text-white mb-4">
                  {PLATFORM_LABELS[platform]}
                </h2>

                {/* Stat row */}
                <div className="grid grid-cols-4 gap-3 mb-6">
                  {[
                    { label: 'Views', value: formatNumber(totalViews) },
                    { label: 'Likes', value: formatNumber(totalLikes) },
                    { label: 'Comments', value: formatNumber(totalComments) },
                    {
                      label: 'Follower growth',
                      value: `${followerGrowth >= 0 ? '+' : ''}${formatNumber(followerGrowth)}`,
                    },
                  ].map((stat) => (
                    <div key={stat.label} className="p-3 rounded-lg bg-[var(--surface-2)]">
                      <div className="text-lg font-bold text-white">{stat.value}</div>
                      <div className="text-xs text-[var(--muted)] mt-0.5">{stat.label}</div>
                    </div>
                  ))}
                </div>

                {/* Simple bar chart — views per day */}
                <div>
                  <div className="text-xs text-[var(--muted)] mb-2">Views per day</div>
                  <div className="flex items-end gap-1 h-16">
                    {rows.map((row) => (
                      <div
                        key={row.snapshot_date}
                        className="flex-1 bg-[var(--brand)] rounded-sm opacity-80 hover:opacity-100 transition-opacity"
                        style={{ height: `${Math.max(4, (row.views / maxViews) * 64)}px` }}
                        title={`${row.snapshot_date}: ${formatNumber(row.views)} views`}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 4: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/\(portal\)/performance/
git commit -m "feat: performance page with platform stats and bar chart"
```

---

## Task 6: Strategy board page

**Files:**
- Create: `app/(portal)/strategy/page.tsx`

- [ ] **Step 1: Create `app/(portal)/strategy/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'
import { createClient } from '@/lib/supabase/server'

interface StrategyContent {
  active_formats: string[]
  hook_angles: string[]
  upcoming_themes: string[]
  manager_notes: string
}

const SECTIONS: { key: keyof StrategyContent; label: string; emoji: string }[] = [
  { key: 'active_formats', label: 'Active Formats', emoji: '🎬' },
  { key: 'hook_angles', label: 'Hook Angles Being Tested', emoji: '🪝' },
  { key: 'upcoming_themes', label: 'Upcoming Themes', emoji: '📅' },
]

export default async function StrategyPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const supabase = createClient()
  const { data: board } = await supabase
    .from('strategy_boards')
    .select('content, updated_at')
    .eq('client_id', client.id)
    .single()

  const content: StrategyContent = board?.content ?? {
    active_formats: [],
    hook_angles: [],
    upcoming_themes: [],
    manager_notes: '',
  }

  const hasContent =
    content.active_formats.length > 0 ||
    content.hook_angles.length > 0 ||
    content.upcoming_themes.length > 0 ||
    content.manager_notes

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Strategy Board</h1>
          <p className="text-[var(--muted)] text-sm mt-1">
            Your current content direction from your account manager
          </p>
        </div>
        {board?.updated_at && (
          <p className="text-xs text-[var(--muted)] shrink-0">
            Updated{' '}
            {new Date(board.updated_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            })}
          </p>
        )}
      </div>

      {!hasContent ? (
        <div className="text-center py-16 text-[var(--muted)]">
          <div className="text-3xl mb-3">🗺️</div>
          <p className="text-sm">Your strategy board hasn&apos;t been set up yet.</p>
          <p className="text-xs mt-1">
            Your account manager will fill this in after your first week.
          </p>
        </div>
      ) : (
        <>
          {SECTIONS.map(({ key, label, emoji }) => {
            const items = content[key] as string[]
            if (!items.length) return null
            return (
              <div
                key={key}
                className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]"
              >
                <h2 className="text-sm font-bold text-white mb-3">
                  {emoji} {label}
                </h2>
                <ul className="space-y-2">
                  {items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--muted)]">
                      <span className="text-[var(--brand)] mt-0.5 shrink-0">–</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}

          {content.manager_notes && (
            <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
              <h2 className="text-sm font-bold text-white mb-3">📝 Notes from Manager</h2>
              <p className="text-sm text-[var(--muted)] leading-relaxed whitespace-pre-wrap">
                {content.manager_notes}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 3: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/\(portal\)/strategy/page.tsx
git commit -m "feat: read-only strategy board page"
```

---

## Task 7: Billing page

**Files:**
- Create: `app/(portal)/billing/page.tsx`

Simplified — no Stripe. Shows plan tier, what's included, and a contact CTA. Stripe integration is Plan 4.

- [ ] **Step 1: Create `app/(portal)/billing/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { getCurrentClient } from '@/lib/client'

const PLANS: Record<string, {
  label: string
  price: string
  cadence: string
  features: string[]
}> = {
  starter: {
    label: 'Starter',
    price: '$997',
    cadence: '/month',
    features: [
      '1 clip per day (30/month)',
      'Posted to 1 platform of your choice',
      'Dedicated account manager',
      'Monthly performance report',
      'We handle captions, hashtags, and posting',
    ],
  },
  growth: {
    label: 'Growth',
    price: '$1,997',
    cadence: '/month',
    features: [
      '2 clips per day (60/month)',
      'Posted to TikTok, Instagram Reels & YouTube Shorts',
      'Dedicated account manager',
      'Monthly performance report',
      'Hook coaching and trend integration',
    ],
  },
  scale: {
    label: 'Scale',
    price: '$3,497',
    cadence: '/month',
    features: [
      '3 clips per day (90/month)',
      'Posted to TikTok, Instagram Reels & YouTube Shorts',
      'Dedicated account manager',
      'Weekly performance reports',
      'Monthly strategy session (30 min)',
      'Hook coaching, trend integration, priority support',
    ],
  },
}

export default async function BillingPage() {
  const client = await getCurrentClient()
  if (!client) redirect('/onboarding')

  const plan = PLANS[client.plan_tier] ?? PLANS.starter

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Billing</h1>
        <p className="text-[var(--muted)] text-sm mt-1">Your current plan and subscription details</p>
      </div>

      {/* Plan card */}
      <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-3xl font-bold text-white">{plan.price}</span>
          <span className="text-[var(--muted)] text-sm">{plan.cadence}</span>
        </div>
        <div className="text-[var(--brand)] text-sm font-semibold mb-4">{plan.label} Plan</div>
        <ul className="space-y-2">
          {plan.features.map((feature, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="text-[var(--brand)] mt-0.5 shrink-0">✓</span>
              <span className="text-white">{feature}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Contact CTA */}
      <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white">Questions about billing?</div>
          <div className="text-xs text-[var(--muted)] mt-0.5">
            Your account manager handles all billing changes
          </div>
        </div>
        <a
          href="/messages"
          className="px-4 py-2 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors shrink-0"
        >
          Message us →
        </a>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

- [ ] **Step 3: Commit**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
git add app/\(portal\)/billing/page.tsx
git commit -m "feat: billing page showing plan info"
```

---

## Task 8: Run all tests + deploy

**Files:** No new files — validation and deploy only.

- [ ] **Step 1: Run the full Jest test suite**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx jest --no-coverage 2>&1 | tail -30
```

Expected: all tests pass (was 29 tests in Plan 2 + 8 new = 37 total).

If any tests fail: read the error, fix the source or test (whichever is wrong), re-run.

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
node_modules/.bin/tsc --noEmit 2>&1
```

Fix any errors.

- [ ] **Step 3: Next.js build check**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npm run build 2>&1 | tail -30
```

Common issues:
- `no-unused-vars` ESLint: add `// eslint-disable-next-line @typescript-eslint/no-unused-vars` above the offending line
- `@next/next/no-img-element`: add `// eslint-disable-next-line @next/next/no-img-element` above `<img>` tags using external URLs (Supabase Storage)
- Missing `Suspense` boundary around `useSearchParams()` — `RangeTabs` is already wrapped in `<Suspense>` in the performance page, so this should be fine

Fix any errors, commit fixes.

- [ ] **Step 4: Deploy**

```bash
cd /Users/markonikolic/Documents/Claude/Projects/vyrulhq-portal
npx vercel --prod 2>&1 | grep -E "(Aliased|Error|hub\.)"
```

Expected: `▲ Aliased     https://hub.vyrulhq.com`

- [ ] **Step 5: Manual smoke test (Supabase migration)**

Run `supabase/migrations/003_realtime.sql` in Supabase SQL Editor if not already done:
```
alter publication supabase_realtime add table messages;
```

- [ ] **Step 6: Report results**

Report: total test count, TypeScript status, build status, and deploy URL.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Messages — client chat UI | Task 3 |
| Messages — Realtime updates | Task 3 (Supabase Realtime subscription) |
| Messages — unread count | Task 1 (dashboard fix uses sender_role) |
| Messages — admin reply | Task 4 |
| Performance — platform tabs + time range | Task 5 |
| Performance — stats: views, likes, followers | Task 5 |
| Performance — chart | Task 5 (CSS bar chart, no library) |
| Strategy board — read-only client view | Task 6 |
| Billing — plan info | Task 7 |
| Admin — client list | Task 4 |
| Admin — client message thread | Task 4 |

**Deferred (not in Plan 3):**
- Stripe billing portal (Plan 4)
- Admin client detail tabs beyond messages (Plan 4)
- Social account connections / cron sync (Plan 4)
- Unread badge in sidebar (Plan 4 — requires Realtime in layout)
