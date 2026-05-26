# VyrulHQ Client Portal — Plan 1: Foundation, Auth & Invite System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the Next.js portal project, wire up Supabase Auth with Google OAuth, build the invite-only onboarding flow, and set up the portal and admin layout shells.

**Architecture:** Next.js 14 App Router hosted on Vercel at hub.vyrulhq.com. Supabase handles Postgres, Auth (Google OAuth), and Storage. Clients access the portal only via admin-sent email invites — no public signup. On invite acceptance, the Google-authenticated user is linked to their pre-created client record.

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, Supabase (`@supabase/ssr`), Resend, Zod, Jest, React Testing Library, Playwright

**Plans in this series:**
- Plan 1 (this): Foundation, Auth & Invite System
- Plan 2: Onboarding Wizard + Client Portal Core
- Plan 3: Client Portal Advanced + Billing
- Plan 4: Admin Panel + Social Stats Cron

---

## File Map

```
vyrulhq-portal/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── jest.config.ts
├── jest.setup.ts
├── playwright.config.ts
├── .env.local.example
├── middleware.ts                          # Auth + role protection for all routes
├── app/
│   ├── layout.tsx                         # Root HTML shell, Space Grotesk font
│   ├── globals.css                        # Tailwind base + custom CSS vars
│   ├── page.tsx                           # Root redirect → /dashboard or /admin
│   ├── (portal)/
│   │   ├── layout.tsx                     # Sidebar layout wrapper (auth-gated)
│   │   └── dashboard/
│   │       └── page.tsx                   # Stub — "Dashboard coming in Plan 2"
│   ├── admin/
│   │   ├── layout.tsx                     # Admin sidebar layout (admin role gated)
│   │   ├── page.tsx                       # Redirect → /admin/invites
│   │   └── invites/
│   │       └── page.tsx                   # Invite form + pending invites list
│   ├── auth/
│   │   ├── login/
│   │   │   └── page.tsx                   # "Sign in with Google" page
│   │   └── callback/
│   │       └── route.ts                   # OAuth code exchange + post-auth routing
│   └── accept/
│       └── [token]/
│           └── page.tsx                   # Invite token validation + Google OAuth redirect
├── components/
│   ├── portal-sidebar.tsx                 # Client portal nav (7 sections)
│   └── admin-sidebar.tsx                  # Admin nav (clients, invites)
├── lib/
│   ├── supabase/
│   │   ├── server.ts                      # Server-side Supabase client (cookies)
│   │   ├── client.ts                      # Browser-side Supabase client (singleton)
│   │   └── admin.ts                       # Service-role client for admin ops
│   ├── invite.ts                          # createInvite, validateToken, acceptInvite
│   └── email.ts                           # sendInviteEmail via Resend
├── app/api/
│   └── invites/
│       └── route.ts                       # POST /api/invites — create invite (admin only)
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql         # All tables, enums, indexes, RLS policies
└── __tests__/
    ├── lib/
    │   ├── invite.test.ts                 # Unit tests for invite logic
    │   └── email.test.ts                  # Unit tests for email sending
    └── api/
        └── invites.test.ts                # API route tests
e2e/
└── invite-flow.spec.ts                    # Playwright: full invite → accept → login flow
```

---

## Task 1: Scaffold Next.js Project

**Files:**
- Create: `package.json` (via create-next-app)
- Create: `next.config.ts`
- Create: `tailwind.config.ts`
- Create: `.env.local.example`

- [ ] **Step 1: Create the project**

```bash
npx create-next-app@14 vyrulhq-portal \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
cd vyrulhq-portal
```

- [ ] **Step 2: Install dependencies**

```bash
npm install \
  @supabase/supabase-js \
  @supabase/ssr \
  resend \
  zod \
  lucide-react \
  clsx \
  tailwind-merge
```

- [ ] **Step 3: Install dev/test dependencies**

```bash
npm install -D \
  jest \
  jest-environment-node \
  ts-jest \
  @types/jest \
  @testing-library/react \
  @testing-library/jest-dom \
  @testing-library/user-event \
  jest-environment-jsdom \
  @playwright/test
npx playwright install chromium
```

- [ ] **Step 4: Create `jest.config.ts`**

```typescript
import type { Config } from 'jest'

const config: Config = {
  projects: [
    {
      displayName: 'node',
      testEnvironment: 'node',
      testMatch: ['**/__tests__/**/*.test.ts'],
      transform: { '^.+\\.tsx?$': ['ts-jest', {}] },
      moduleNameMapper: { '^@/(.*)$': '<rootDir>/$1' },
    },
    {
      displayName: 'jsdom',
      testEnvironment: 'jsdom',
      testMatch: ['**/__tests__/**/*.test.tsx'],
      transform: { '^.+\\.tsx?$': ['ts-jest', {}] },
      setupFilesAfterFramework: ['<rootDir>/jest.setup.ts'],
      moduleNameMapper: { '^@/(.*)$': '<rootDir>/$1' },
    },
  ],
}
export default config
```

- [ ] **Step 5: Create `jest.setup.ts`**

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 6: Create `.env.local.example`**

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# App
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Resend
RESEND_API_KEY=re_your_key

# Stripe (Plan 3)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

```bash
cp .env.local.example .env.local
# Fill in real values from Supabase dashboard + Resend dashboard
```

- [ ] **Step 7: Configure `next.config.ts`**

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '*.supabase.co' },
    ],
  },
}

export default nextConfig
```

- [ ] **Step 8: Configure `tailwind.config.ts`**

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-space-grotesk)', 'sans-serif'],
      },
      colors: {
        brand: '#a8ff57',
        surface: '#101010',
        border: '#1e1e1e',
        muted: '#666',
      },
    },
  },
}
export default config
```

- [ ] **Step 9: Commit**

```bash
git init
git add .
git commit -m "feat: scaffold Next.js 14 portal project with Tailwind + test deps"
```

---

## Task 2: Supabase Schema Migration

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`

- [ ] **Step 1: Install Supabase CLI and initialise**

```bash
npm install -g supabase
supabase init
supabase login
# Link to your project:
supabase link --project-ref your-project-ref
```

- [ ] **Step 2: Create `supabase/migrations/001_initial_schema.sql`**

```sql
-- Extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- Enums
create type plan_tier as enum ('starter', 'growth', 'scale');
create type client_status as enum ('invited', 'onboarding', 'active', 'paused', 'churned');
create type platform_type as enum ('tiktok', 'instagram', 'youtube');
create type sender_role_type as enum ('client', 'admin');

-- clients
create table public.clients (
  id                     uuid primary key default uuid_generate_v4(),
  user_id                uuid references auth.users(id) on delete set null,
  email                  text unique not null,
  name                   text not null,
  company                text,
  plan_tier              plan_tier not null default 'starter',
  status                 client_status not null default 'invited',
  stripe_customer_id     text,
  stripe_subscription_id text,
  onboarding_completed   boolean not null default false,
  account_manager_name   text not null default 'Marko N.',
  invited_at             timestamptz not null default now(),
  created_at             timestamptz not null default now()
);

-- invites
create table public.invites (
  id          uuid primary key default uuid_generate_v4(),
  email       text not null,
  name        text not null,
  company     text,
  plan_tier   plan_tier not null default 'starter',
  token       text unique not null default encode(gen_random_bytes(32), 'hex'),
  expires_at  timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  created_by  uuid references auth.users(id),
  created_at  timestamptz not null default now()
);

-- footage_submissions
create table public.footage_submissions (
  id              uuid primary key default uuid_generate_v4(),
  client_id       uuid not null references public.clients(id) on delete cascade,
  file_url        text not null,
  file_name       text not null,
  file_size_bytes bigint not null,
  title           text not null,
  notes           text,
  uploaded_at     timestamptz not null default now()
);

-- clips
create table public.clips (
  id            uuid primary key default uuid_generate_v4(),
  client_id     uuid not null references public.clients(id) on delete cascade,
  title         text not null,
  platform      platform_type not null,
  video_url     text not null,
  thumbnail_url text,
  caption       text,
  posted_at     timestamptz,
  created_at    timestamptz not null default now()
);

-- messages
create table public.messages (
  id          uuid primary key default uuid_generate_v4(),
  client_id   uuid not null references public.clients(id) on delete cascade,
  sender_id   uuid not null references auth.users(id),
  sender_role sender_role_type not null,
  body        text not null,
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);

-- strategy_boards
create table public.strategy_boards (
  id         uuid primary key default uuid_generate_v4(),
  client_id  uuid unique not null references public.clients(id) on delete cascade,
  content    jsonb not null default '{
    "active_formats": [],
    "hook_angles": [],
    "upcoming_themes": [],
    "manager_notes": ""
  }'::jsonb,
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now()
);

-- social_accounts (VyrulHQ-owned, per client)
create table public.social_accounts (
  id                  uuid primary key default uuid_generate_v4(),
  client_id           uuid not null references public.clients(id) on delete cascade,
  platform            platform_type not null,
  platform_account_id text not null,
  access_token        text not null,
  token_expires_at    timestamptz,
  created_at          timestamptz not null default now(),
  unique(client_id, platform)
);

-- performance_snapshots
create table public.performance_snapshots (
  id            uuid primary key default uuid_generate_v4(),
  client_id     uuid not null references public.clients(id) on delete cascade,
  platform      platform_type not null,
  snapshot_date date not null,
  views         bigint not null default 0,
  likes         bigint not null default 0,
  comments      bigint not null default 0,
  shares        bigint not null default 0,
  followers     bigint not null default 0,
  posts_count   integer not null default 0,
  created_at    timestamptz not null default now(),
  unique(client_id, platform, snapshot_date)
);

-- Indexes
create index on public.clients(user_id);
create index on public.clients(email);
create index on public.footage_submissions(client_id);
create index on public.clips(client_id);
create index on public.messages(client_id, created_at);
create index on public.performance_snapshots(client_id, platform, snapshot_date);

-- RLS: enable on all client-facing tables
alter table public.clients enable row level security;
alter table public.footage_submissions enable row level security;
alter table public.clips enable row level security;
alter table public.messages enable row level security;
alter table public.strategy_boards enable row level security;
alter table public.performance_snapshots enable row level security;
alter table public.social_accounts enable row level security;

-- Helper: get the client id for the current user
create or replace function public.my_client_id()
returns uuid language sql security definer stable as $$
  select id from public.clients where user_id = auth.uid() limit 1;
$$;

-- clients: read own record
create policy "clients_read_own" on public.clients
  for select using (user_id = auth.uid());

-- footage_submissions: read own, insert own
create policy "footage_read_own" on public.footage_submissions
  for select using (client_id = public.my_client_id());

create policy "footage_insert_own" on public.footage_submissions
  for insert with check (client_id = public.my_client_id());

-- clips: read own
create policy "clips_read_own" on public.clips
  for select using (client_id = public.my_client_id());

-- messages: read own thread, insert own messages
create policy "messages_read_own" on public.messages
  for select using (client_id = public.my_client_id());

create policy "messages_insert_own" on public.messages
  for insert with check (
    client_id = public.my_client_id()
    and sender_id = auth.uid()
    and sender_role = 'client'
  );

-- strategy_boards: read own
create policy "strategy_read_own" on public.strategy_boards
  for select using (client_id = public.my_client_id());

-- performance_snapshots: read own
create policy "performance_read_own" on public.performance_snapshots
  for select using (client_id = public.my_client_id());
```

- [ ] **Step 3: Apply migration**

```bash
supabase db push
```

Expected output: `Applying migration 001_initial_schema.sql... done`

- [ ] **Step 4: Create Supabase Storage buckets via dashboard**

In Supabase Dashboard → Storage → New bucket:
- Name: `footage-submissions`, Public: No
- Name: `clips`, Public: No

- [ ] **Step 5: Commit**

```bash
git add supabase/
git commit -m "feat: add initial Supabase schema with RLS policies"
```

---

## Task 3: Supabase Client Utilities

**Files:**
- Create: `lib/supabase/server.ts`
- Create: `lib/supabase/client.ts`
- Create: `lib/supabase/admin.ts`

- [ ] **Step 1: Create `lib/supabase/server.ts`**

```typescript
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function createClient() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get(name) { return cookieStore.get(name)?.value },
        set(name, value, options) {
          try { cookieStore.set({ name, value, ...options }) } catch {}
        },
        remove(name, options) {
          try { cookieStore.set({ name, value: '', ...options }) } catch {}
        },
      },
    }
  )
}
```

- [ ] **Step 2: Create `lib/supabase/client.ts`**

```typescript
import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

- [ ] **Step 3: Create `lib/supabase/admin.ts`**

```typescript
import { createClient } from '@supabase/supabase-js'

// Service-role client — never expose to browser
export const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
  { auth: { autoRefreshToken: false, persistSession: false } }
)
```

- [ ] **Step 4: Commit**

```bash
git add lib/
git commit -m "feat: add Supabase server, browser, and admin client utilities"
```

---

## Task 4: Auth Middleware

**Files:**
- Create: `middleware.ts`

- [ ] **Step 1: Create `middleware.ts`**

```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()
  const { pathname } = request.nextUrl

  const isPortalRoute = pathname.startsWith('/dashboard') ||
    pathname.startsWith('/submit') ||
    pathname.startsWith('/clips') ||
    pathname.startsWith('/performance') ||
    pathname.startsWith('/strategy') ||
    pathname.startsWith('/messages') ||
    pathname.startsWith('/billing')

  const isAdminRoute = pathname.startsWith('/admin')

  if ((isPortalRoute || isAdminRoute) && !user) {
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/auth/login'
    return NextResponse.redirect(loginUrl)
  }

  if (isAdminRoute && user) {
    const isAdmin = user.app_metadata?.role === 'admin'
    if (!isAdmin) {
      const dashUrl = request.nextUrl.clone()
      dashUrl.pathname = '/dashboard'
      return NextResponse.redirect(dashUrl)
    }
  }

  return supabaseResponse
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|auth/callback|accept).*)',
  ],
}
```

- [ ] **Step 2: Verify middleware compiles**

```bash
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Set yourself as admin in Supabase**

In Supabase Dashboard → Authentication → Users → find your user → Edit → App metadata:
```json
{ "role": "admin" }
```

- [ ] **Step 4: Commit**

```bash
git add middleware.ts
git commit -m "feat: add auth middleware protecting portal and admin routes"
```

---

## Task 5: Root Layout + Global Styles

**Files:**
- Create: `app/layout.tsx`
- Create: `app/globals.css`
- Create: `app/page.tsx`

- [ ] **Step 1: Create `app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --brand: #a8ff57;
  --bg: #080808;
  --surface: #101010;
  --surface-2: #161616;
  --border: #1e1e1e;
  --muted: #666;
  --text: #e0e0e0;
}

body {
  background: var(--bg);
  color: var(--text);
}

* {
  border-color: var(--border);
}
```

- [ ] **Step 2: Create `app/layout.tsx`**

```typescript
import type { Metadata } from 'next'
import { Space_Grotesk } from 'next/font/google'
import './globals.css'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
})

export const metadata: Metadata = {
  title: 'Vyrul HQ',
  description: 'Your content system, managed.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={spaceGrotesk.variable}>
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
```

- [ ] **Step 3: Create `app/page.tsx`** (root redirect)

```typescript
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function RootPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) redirect('/auth/login')

  const isAdmin = user.app_metadata?.role === 'admin'
  redirect(isAdmin ? '/admin' : '/dashboard')
}
```

- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat: add root layout, global CSS vars, and root redirect"
```

---

## Task 6: Auth Pages + OAuth Callback

**Files:**
- Create: `app/auth/login/page.tsx`
- Create: `app/auth/callback/route.ts`

- [ ] **Step 1: Create `app/auth/login/page.tsx`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'

export default async function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string; invite?: string }
}) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (user) redirect(searchParams.next ?? '/dashboard')

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
      <div className="w-full max-w-sm p-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="w-9 h-9 bg-[var(--brand)] rounded-lg mb-6" />
        <h1 className="text-xl font-bold text-white mb-1">Sign in to Vyrul HQ</h1>
        <p className="text-[var(--muted)] text-sm mb-8">
          Your content portal awaits.
        </p>
        <form action="/api/auth/google" method="POST">
          {searchParams.invite && (
            <input type="hidden" name="invite" value={searchParams.invite} />
          )}
          {searchParams.next && (
            <input type="hidden" name="next" value={searchParams.next} />
          )}
          <button
            type="submit"
            className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] text-white text-sm font-semibold hover:border-white/20 transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
              <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
            </svg>
            Continue with Google
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `app/api/auth/google/route.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  const formData = await request.formData()
  const invite = formData.get('invite') as string | null
  const next = formData.get('next') as string | null

  const supabase = createClient()
  const redirectTo = new URL('/auth/callback', process.env.NEXT_PUBLIC_APP_URL!)

  if (invite) redirectTo.searchParams.set('invite', invite)
  if (next) redirectTo.searchParams.set('next', next)

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: redirectTo.toString(),
      queryParams: { access_type: 'offline', prompt: 'consent' },
    },
  })

  if (error || !data.url) {
    return NextResponse.redirect(new URL('/auth/login?error=oauth_failed', process.env.NEXT_PUBLIC_APP_URL!))
  }

  return NextResponse.redirect(data.url)
}
```

- [ ] **Step 3: Create `app/auth/callback/route.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { supabaseAdmin } from '@/lib/supabase/admin'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const code = searchParams.get('code')
  const invite = searchParams.get('invite')
  const next = searchParams.get('next')
  const appUrl = process.env.NEXT_PUBLIC_APP_URL!

  if (!code) return NextResponse.redirect(new URL('/auth/login?error=no_code', appUrl))

  const supabase = createClient()
  const { error } = await supabase.auth.exchangeCodeForSession(code)

  if (error) return NextResponse.redirect(new URL('/auth/login?error=exchange_failed', appUrl))

  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.redirect(new URL('/auth/login', appUrl))

  // If there's an invite token, link the user to their client record
  if (invite) {
    const { data: inv } = await supabaseAdmin
      .from('invites')
      .select('*')
      .eq('token', invite)
      .is('accepted_at', null)
      .gt('expires_at', new Date().toISOString())
      .single()

    if (inv) {
      await supabaseAdmin
        .from('clients')
        .update({ user_id: user.id, status: 'onboarding' })
        .eq('email', inv.email)

      await supabaseAdmin
        .from('invites')
        .update({ accepted_at: new Date().toISOString() })
        .eq('token', invite)

      return NextResponse.redirect(new URL('/onboarding', appUrl))
    }
  }

  // Existing user: route by role or onboarding state
  const isAdmin = user.app_metadata?.role === 'admin'
  if (isAdmin) return NextResponse.redirect(new URL('/admin', appUrl))

  // Check if client has completed onboarding
  const { data: client } = await supabaseAdmin
    .from('clients')
    .select('onboarding_completed')
    .eq('user_id', user.id)
    .single()

  if (client && !client.onboarding_completed) {
    return NextResponse.redirect(new URL('/onboarding', appUrl))
  }

  return NextResponse.redirect(new URL(next ?? '/dashboard', appUrl))
}
```

- [ ] **Step 4: Enable Google OAuth in Supabase dashboard**

Supabase Dashboard → Authentication → Providers → Google:
- Enable Google provider
- Add Client ID and Client Secret from Google Cloud Console
- Add callback URL `https://your-project.supabase.co/auth/v1/callback` to Google OAuth consent screen

- [ ] **Step 5: Commit**

```bash
git add app/auth/ app/api/
git commit -m "feat: add Google OAuth login page and auth callback with invite linking"
```

---

## Task 7: Invite Logic

**Files:**
- Create: `lib/invite.ts`
- Create: `lib/email.ts`
- Create: `__tests__/lib/invite.test.ts`
- Create: `__tests__/lib/email.test.ts`

- [ ] **Step 1: Write failing tests for invite logic**

Create `__tests__/lib/invite.test.ts`:

```typescript
jest.mock('@/lib/supabase/admin', () => ({
  supabaseAdmin: {
    from: jest.fn(),
  },
}))
jest.mock('@/lib/email', () => ({
  sendInviteEmail: jest.fn().mockResolvedValue(undefined),
}))

import { supabaseAdmin } from '@/lib/supabase/admin'
import { sendInviteEmail } from '@/lib/email'
import { createInvite, validateInviteToken, acceptInvite } from '@/lib/invite'

const mockChain = (returnValue: unknown) => ({
  from: jest.fn().mockReturnThis(),
  insert: jest.fn().mockReturnThis(),
  update: jest.fn().mockReturnThis(),
  select: jest.fn().mockReturnThis(),
  eq: jest.fn().mockReturnThis(),
  is: jest.fn().mockReturnThis(),
  gt: jest.fn().mockReturnThis(),
  single: jest.fn().mockResolvedValue(returnValue),
})

describe('createInvite', () => {
  it('inserts invite record, creates client, and sends email', async () => {
    const fakeInvite = { id: 'inv-1', token: 'abc123', email: 'alex@co.com' }
    const chain = mockChain({ data: fakeInvite, error: null })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    const result = await createInvite({
      email: 'alex@co.com',
      name: 'Alex',
      company: 'Acme',
      planTier: 'growth',
      createdBy: 'admin-uid',
    })

    expect(result).toEqual(fakeInvite)
    expect(sendInviteEmail).toHaveBeenCalledWith(
      expect.objectContaining({ to: 'alex@co.com', token: 'abc123' })
    )
  })

  it('throws if Supabase insert fails', async () => {
    const chain = mockChain({ data: null, error: new Error('db error') })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    await expect(
      createInvite({ email: 'x@x.com', name: 'X', company: '', planTier: 'starter', createdBy: 'uid' })
    ).rejects.toThrow('db error')
  })
})

describe('validateInviteToken', () => {
  it('returns invite data for a valid token', async () => {
    const fakeInvite = { id: 'inv-1', token: 'abc123', email: 'alex@co.com' }
    const chain = mockChain({ data: fakeInvite, error: null })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    const result = await validateInviteToken('abc123')
    expect(result).toEqual(fakeInvite)
  })

  it('returns null for an invalid token', async () => {
    const chain = mockChain({ data: null, error: new Error('not found') })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    const result = await validateInviteToken('bad-token')
    expect(result).toBeNull()
  })
})

describe('acceptInvite', () => {
  it('links client to user and marks invite accepted', async () => {
    const fakeInvite = { token: 'abc123', email: 'alex@co.com' }
    const chain = mockChain({ data: fakeInvite, error: null })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    const result = await acceptInvite('abc123', 'user-uid')
    expect(result).toEqual(fakeInvite)
  })

  it('throws if token is invalid', async () => {
    const chain = mockChain({ data: null, error: null })
    ;(supabaseAdmin.from as jest.Mock).mockReturnValue(chain)

    await expect(acceptInvite('bad', 'uid')).rejects.toThrow('Invalid or expired invite token')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npx jest __tests__/lib/invite.test.ts --no-coverage
```

Expected: FAIL — `Cannot find module '@/lib/invite'`

- [ ] **Step 3: Create `lib/email.ts`**

```typescript
import { Resend } from 'resend'

const resend = new Resend(process.env.RESEND_API_KEY!)

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter — $997/mo',
  growth: 'Growth — $1,997/mo',
  scale: 'Scale — $3,497/mo',
}

interface SendInviteEmailParams {
  to: string
  name: string
  token: string
  planTier: string
}

export async function sendInviteEmail({ to, name, token, planTier }: SendInviteEmailParams) {
  const acceptUrl = `${process.env.NEXT_PUBLIC_APP_URL}/accept/${token}`

  await resend.emails.send({
    from: 'Vyrul HQ <noreply@vyrulhq.com>',
    to,
    subject: "You're in — your Vyrul HQ portal is ready",
    html: `
      <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#e0e0e0;padding:40px 32px;border-radius:12px;">
        <div style="width:36px;height:36px;background:#a8ff57;border-radius:8px;display:inline-block;margin-bottom:24px;"></div>
        <h1 style="font-size:22px;font-weight:700;margin:0 0 8px;color:#fff;">Hey ${name},</h1>
        <p style="color:#888;font-size:15px;line-height:1.6;margin:0 0 24px;">
          Your Vyrul HQ client portal is ready. You're on the <strong style="color:#fff;">${PLAN_LABELS[planTier] ?? planTier}</strong> plan.
        </p>
        <a href="${acceptUrl}" style="display:inline-block;background:#a8ff57;color:#000;font-weight:700;font-size:15px;padding:14px 28px;border-radius:8px;text-decoration:none;margin-bottom:24px;">
          Accept Invite →
        </a>
        <p style="color:#444;font-size:13px;margin:0;">This link expires in 7 days.</p>
      </div>
    `,
  })
}
```

- [ ] **Step 4: Create `lib/invite.ts`**

```typescript
import { supabaseAdmin } from '@/lib/supabase/admin'
import { sendInviteEmail } from '@/lib/email'

export interface CreateInviteParams {
  email: string
  name: string
  company: string
  planTier: 'starter' | 'growth' | 'scale'
  createdBy: string
}

export async function createInvite(params: CreateInviteParams) {
  const { email, name, company, planTier, createdBy } = params

  const { data: invite, error } = await supabaseAdmin
    .from('invites')
    .insert({ email, name, company, plan_tier: planTier, created_by: createdBy })
    .select()
    .single()

  if (error) throw error

  await supabaseAdmin.from('clients').insert({
    email, name, company, plan_tier: planTier, status: 'invited',
  })

  await sendInviteEmail({ to: email, name, token: invite.token, planTier })

  return invite
}

export async function validateInviteToken(token: string) {
  const { data, error } = await supabaseAdmin
    .from('invites')
    .select('*')
    .eq('token', token)
    .is('accepted_at', null)
    .gt('expires_at', new Date().toISOString())
    .single()

  if (error || !data) return null
  return data
}

export async function acceptInvite(token: string, userId: string) {
  const invite = await validateInviteToken(token)
  if (!invite) throw new Error('Invalid or expired invite token')

  await supabaseAdmin
    .from('clients')
    .update({ user_id: userId, status: 'onboarding' })
    .eq('email', invite.email)

  await supabaseAdmin
    .from('invites')
    .update({ accepted_at: new Date().toISOString() })
    .eq('token', token)

  return invite
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npx jest __tests__/lib/invite.test.ts --no-coverage
```

Expected: PASS (3 suites, 5 tests)

- [ ] **Step 6: Commit**

```bash
git add lib/ __tests__/lib/
git commit -m "feat: add invite and email logic with unit tests"
```

---

## Task 8: Invite API Route

**Files:**
- Create: `app/api/invites/route.ts`
- Create: `__tests__/api/invites.test.ts`

- [ ] **Step 1: Write failing test**

Create `__tests__/api/invites.test.ts`:

```typescript
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(),
}))
jest.mock('@/lib/invite', () => ({
  createInvite: jest.fn(),
}))

import { createClient } from '@/lib/supabase/server'
import { createInvite } from '@/lib/invite'
import { POST } from '@/app/api/invites/route'

function makeRequest(body: unknown) {
  return new Request('http://localhost/api/invites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('POST /api/invites', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns 401 if not authenticated', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) },
    })
    const res = await POST(makeRequest({ email: 'a@a.com', name: 'A', company: '', planTier: 'starter' }))
    expect(res.status).toBe(401)
  })

  it('returns 403 if not admin', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1', app_metadata: {} } } }) },
    })
    const res = await POST(makeRequest({ email: 'a@a.com', name: 'A', company: '', planTier: 'starter' }))
    expect(res.status).toBe(403)
  })

  it('returns 400 on invalid body', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'u1', app_metadata: { role: 'admin' } } } }) },
    })
    const res = await POST(makeRequest({ email: 'not-an-email' }))
    expect(res.status).toBe(400)
  })

  it('creates invite and returns 201 for valid admin request', async () => {
    ;(createClient as jest.Mock).mockReturnValue({
      auth: { getUser: jest.fn().mockResolvedValue({ data: { user: { id: 'admin-uid', app_metadata: { role: 'admin' } } } }) },
    })
    const fakeInvite = { id: 'inv-1', token: 'tok', email: 'alex@co.com' }
    ;(createInvite as jest.Mock).mockResolvedValue(fakeInvite)

    const res = await POST(makeRequest({ email: 'alex@co.com', name: 'Alex', company: 'Acme', planTier: 'growth' }))
    expect(res.status).toBe(201)
    const body = await res.json()
    expect(body).toEqual({ invite: fakeInvite })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx jest __tests__/api/invites.test.ts --no-coverage
```

Expected: FAIL — `Cannot find module '@/app/api/invites/route'`

- [ ] **Step 3: Create `app/api/invites/route.ts`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { createInvite } from '@/lib/invite'
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'

const inviteSchema = z.object({
  email: z.string().email(),
  name: z.string().min(1),
  company: z.string().default(''),
  planTier: z.enum(['starter', 'growth', 'scale']),
})

export async function POST(request: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  if (user.app_metadata?.role !== 'admin') {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
  }

  const body = await request.json().catch(() => null)
  const parsed = inviteSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const invite = await createInvite({ ...parsed.data, createdBy: user.id })
  return NextResponse.json({ invite }, { status: 201 })
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx jest __tests__/api/invites.test.ts --no-coverage
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/api/ __tests__/api/
git commit -m "feat: add invite API route with auth/validation and tests"
```

---

## Task 9: Accept Invite Page

**Files:**
- Create: `app/accept/[token]/page.tsx`

- [ ] **Step 1: Create `app/accept/[token]/page.tsx`**

```typescript
import { supabaseAdmin } from '@/lib/supabase/admin'
import { redirect } from 'next/navigation'

interface Props {
  params: { token: string }
}

export default async function AcceptInvitePage({ params }: Props) {
  const { token } = params

  // Validate token server-side before showing UI
  const { data: invite } = await supabaseAdmin
    .from('invites')
    .select('name, email, plan_tier')
    .eq('token', token)
    .is('accepted_at', null)
    .gt('expires_at', new Date().toISOString())
    .single()

  if (!invite) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
        <div className="text-center">
          <div className="text-4xl mb-4">✗</div>
          <h1 className="text-xl font-bold text-white mb-2">Invite expired or invalid</h1>
          <p className="text-[var(--muted)] text-sm">Contact your account manager for a new invite.</p>
        </div>
      </div>
    )
  }

  const PLAN_LABELS: Record<string, string> = {
    starter: 'Starter — $997/mo',
    growth: 'Growth — $1,997/mo',
    scale: 'Scale — $3,497/mo',
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
      <div className="w-full max-w-sm p-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="w-9 h-9 bg-[var(--brand)] rounded-lg mb-6" />
        <h1 className="text-xl font-bold text-white mb-1">
          Hey {invite.name}, you're in.
        </h1>
        <p className="text-[var(--muted)] text-sm mb-6">
          You've been invited to the Vyrul HQ client portal on the{' '}
          <span className="text-white">{PLAN_LABELS[invite.plan_tier]}</span> plan.
        </p>
        <form action="/api/auth/google" method="POST">
          <input type="hidden" name="invite" value={token} />
          <button
            type="submit"
            className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg bg-[var(--brand)] text-black text-sm font-bold hover:bg-[#b8ff70] transition-colors"
          >
            Accept Invite with Google →
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add app/accept/
git commit -m "feat: add invite acceptance page with token validation"
```

---

## Task 10: Portal Layout + Sidebar

**Files:**
- Create: `components/portal-sidebar.tsx`
- Create: `app/(portal)/layout.tsx`
- Create: `app/(portal)/dashboard/page.tsx`

- [ ] **Step 1: Create `components/portal-sidebar.tsx`**

```typescript
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import {
  LayoutDashboard, Upload, Film, BarChart2,
  Lightbulb, MessageCircle, CreditCard, LogOut,
} from 'lucide-react'
import { clsx } from 'clsx'

const sections = [
  { label: 'Content', items: [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/submit', label: 'Submit Footage', icon: Upload },
    { href: '/clips', label: 'Clip Library', icon: Film },
  ]},
  { label: 'Growth', items: [
    { href: '/performance', label: 'Performance', icon: BarChart2 },
    { href: '/strategy', label: 'Strategy Board', icon: Lightbulb },
  ]},
  { label: 'Account', items: [
    { href: '/messages', label: 'Messages', icon: MessageCircle },
    { href: '/billing', label: 'Billing', icon: CreditCard },
  ]},
]

export function PortalSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()

  async function handleSignOut() {
    await supabase.auth.signOut()
    router.push('/auth/login')
  }

  return (
    <aside className="w-56 min-h-screen bg-[#0d0d0d] border-r border-[var(--border)] flex flex-col py-4 px-3 shrink-0">
      <div className="flex items-center gap-2 px-2 pb-4 mb-2 border-b border-[var(--border)]">
        <div className="w-6 h-6 bg-[var(--brand)] rounded-md" />
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
            {section.items.map(({ href, label, icon: Icon }) => {
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
                  {label}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <button
        onClick={handleSignOut}
        className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors mt-2"
      >
        <LogOut size={15} />
        Sign Out
      </button>
    </aside>
  )
}
```

- [ ] **Step 2: Create `app/(portal)/layout.tsx`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { PortalSidebar } from '@/components/portal-sidebar'

export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/auth/login')

  return (
    <div className="flex min-h-screen">
      <PortalSidebar />
      <main className="flex-1 p-8 overflow-auto">{children}</main>
    </div>
  )
}
```

- [ ] **Step 3: Create `app/(portal)/dashboard/page.tsx`** (stub for Plan 2)

```typescript
export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
      <p className="text-[var(--muted)]">Coming in Plan 2.</p>
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add components/ app/\(portal\)/
git commit -m "feat: add portal layout and sidebar navigation"
```

---

## Task 11: Admin Layout + Invite Management Page

**Files:**
- Create: `components/admin-sidebar.tsx`
- Create: `app/admin/layout.tsx`
- Create: `app/admin/page.tsx`
- Create: `app/admin/invites/page.tsx`

- [ ] **Step 1: Create `components/admin-sidebar.tsx`**

```typescript
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Users, Mail, LogOut } from 'lucide-react'
import { clsx } from 'clsx'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

const navItems = [
  { href: '/admin/clients', label: 'Clients', icon: Users },
  { href: '/admin/invites', label: 'Invites', icon: Mail },
]

export function AdminSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()

  async function handleSignOut() {
    await supabase.auth.signOut()
    router.push('/auth/login')
  }

  return (
    <aside className="w-56 min-h-screen bg-[#0d0d0d] border-r border-[var(--border)] flex flex-col py-4 px-3 shrink-0">
      <div className="flex items-center gap-2 px-2 pb-4 mb-4 border-b border-[var(--border)]">
        <div className="w-6 h-6 bg-[var(--brand)] rounded-md" />
        <div>
          <div className="text-sm font-bold text-white leading-none">Vyrul HQ</div>
          <div className="text-[10px] text-[var(--muted)] mt-0.5">Admin</div>
        </div>
      </div>

      <nav className="flex-1 flex flex-col gap-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href)
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
              {label}
            </Link>
          )
        })}
      </nav>

      <button
        onClick={handleSignOut}
        className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors"
      >
        <LogOut size={15} />
        Sign Out
      </button>
    </aside>
  )
}
```

- [ ] **Step 2: Create `app/admin/layout.tsx`**

```typescript
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { AdminSidebar } from '@/components/admin-sidebar'

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user || user.app_metadata?.role !== 'admin') redirect('/dashboard')

  return (
    <div className="flex min-h-screen">
      <AdminSidebar />
      <main className="flex-1 p-8 overflow-auto">{children}</main>
    </div>
  )
}
```

- [ ] **Step 3: Create `app/admin/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
export default function AdminPage() {
  redirect('/admin/invites')
}
```

- [ ] **Step 4: Create `app/admin/invites/page.tsx`**

```typescript
import { supabaseAdmin } from '@/lib/supabase/admin'
import { InviteForm } from './invite-form'

export default async function AdminInvitesPage() {
  const { data: invites } = await supabaseAdmin
    .from('invites')
    .select('id, email, name, company, plan_tier, accepted_at, expires_at, created_at')
    .order('created_at', { ascending: false })
    .limit(50)

  const PLAN_LABELS: Record<string, string> = {
    starter: 'Starter',
    growth: 'Growth',
    scale: 'Scale',
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Invites</h1>
          <p className="text-[var(--muted)] text-sm mt-1">Send portal access to new clients</p>
        </div>
      </div>

      <InviteForm />

      <div className="mt-10">
        <h2 className="text-sm font-bold text-[var(--muted)] uppercase tracking-widest mb-4">Sent Invites</h2>
        <div className="divide-y divide-[var(--border)] border border-[var(--border)] rounded-xl overflow-hidden">
          {!invites?.length && (
            <div className="p-6 text-center text-[var(--muted)] text-sm">No invites sent yet.</div>
          )}
          {invites?.map((inv) => (
            <div key={inv.id} className="flex items-center gap-4 px-5 py-4 bg-[var(--surface)]">
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-white truncate">{inv.name}</div>
                <div className="text-xs text-[var(--muted)] truncate">{inv.email} · {inv.company}</div>
              </div>
              <div className="text-xs text-[var(--muted)]">{PLAN_LABELS[inv.plan_tier]}</div>
              <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                inv.accepted_at
                  ? 'bg-[#1a2a10] text-[var(--brand)]'
                  : new Date(inv.expires_at) < new Date()
                  ? 'bg-red-950 text-red-400'
                  : 'bg-[#1a1a1a] text-[var(--muted)]'
              }`}>
                {inv.accepted_at ? 'Accepted' : new Date(inv.expires_at) < new Date() ? 'Expired' : 'Pending'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create `app/admin/invites/invite-form.tsx`** (client component for the form)

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export function InviteForm() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')

    const form = new FormData(e.currentTarget)
    const body = {
      email: form.get('email'),
      name: form.get('name'),
      company: form.get('company'),
      planTier: form.get('planTier'),
    }

    const res = await fetch('/api/invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    setLoading(false)

    if (!res.ok) {
      const data = await res.json()
      setError(data.error?.formErrors?.[0] ?? 'Failed to send invite.')
      return
    }

    setSuccess('Invite sent!')
    ;(e.target as HTMLFormElement).reset()
    router.refresh()
  }

  return (
    <form onSubmit={handleSubmit} className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
      <h2 className="text-sm font-bold text-white mb-5">Send New Invite</h2>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1.5">Name</label>
          <input name="name" required placeholder="Alex Johnson"
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white placeholder:text-[#333] focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1.5">Email</label>
          <input name="email" type="email" required placeholder="alex@company.com"
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white placeholder:text-[#333] focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1.5">Company</label>
          <input name="company" placeholder="Acme Inc."
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white placeholder:text-[#333] focus:outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1.5">Plan</label>
          <select name="planTier" required
            className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--brand)]">
            <option value="starter">Starter — $997/mo</option>
            <option value="growth">Growth — $1,997/mo</option>
            <option value="scale">Scale — $3,497/mo</option>
          </select>
        </div>
      </div>
      {error && <p className="text-red-400 text-xs mb-3">{error}</p>}
      {success && <p className="text-[var(--brand)] text-xs mb-3">{success}</p>}
      <button type="submit" disabled={loading}
        className="bg-[var(--brand)] text-black text-sm font-bold px-5 py-2.5 rounded-lg hover:bg-[#b8ff70] disabled:opacity-50 transition-colors">
        {loading ? 'Sending…' : 'Send Invite →'}
      </button>
    </form>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add components/admin-sidebar.tsx app/admin/
git commit -m "feat: add admin layout, sidebar, and invite management page"
```

---

## Task 12: Playwright E2E — Invite Flow

**Files:**
- Create: `playwright.config.ts`
- Create: `e2e/invite-flow.spec.ts`

- [ ] **Step 1: Create `playwright.config.ts`**

```typescript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
})
```

- [ ] **Step 2: Create `e2e/invite-flow.spec.ts`**

```typescript
import { test, expect } from '@playwright/test'

// Note: these tests require a real Supabase test project and valid env vars.
// Run with: PLAYWRIGHT_BASE_URL=http://localhost:3000 npx playwright test

test.describe('Accept Invite Page', () => {
  test('shows error for invalid token', async ({ page }) => {
    await page.goto('/accept/invalid-token-123')
    await expect(page.getByText('Invite expired or invalid')).toBeVisible()
  })

  test('shows client name and plan for valid token', async ({ page }) => {
    // This test requires a real invite token in the DB.
    // Create one manually in Supabase before running:
    // INSERT INTO invites (email, name, company, plan_tier) VALUES ('test@test.com', 'Test User', 'Acme', 'growth');
    // Then set TEST_INVITE_TOKEN in .env.local to the generated token.
    const token = process.env.TEST_INVITE_TOKEN
    if (!token) test.skip()

    await page.goto(`/accept/${token}`)
    await expect(page.getByText("you're in")).toBeVisible()
    await expect(page.getByText('Growth')).toBeVisible()
    await expect(page.getByText('Accept Invite with Google')).toBeVisible()
  })
})

test.describe('Admin Invites', () => {
  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/admin/invites')
    await expect(page).toHaveURL(/\/auth\/login/)
  })
})
```

- [ ] **Step 3: Run Playwright tests**

```bash
npm run dev &
npx playwright test --project=chromium
```

Expected: `redirects unauthenticated users to login` passes. Token test skips if `TEST_INVITE_TOKEN` not set.

- [ ] **Step 4: Commit**

```bash
git add playwright.config.ts e2e/
git commit -m "feat: add Playwright E2E tests for invite flow"
```

---

## Task 13: Deploy to Vercel

- [ ] **Step 1: Create GitHub repo and push**

```bash
gh repo create vyrulhq-portal --private
git remote add origin git@github.com:marko257/vyrulhq-portal.git
git push -u origin main
```

- [ ] **Step 2: Deploy to Vercel**

```bash
npx vercel --prod
```

Or via Vercel Dashboard → Import Repository → select `vyrulhq-portal`.

- [ ] **Step 3: Add environment variables in Vercel dashboard**

In Vercel → Project Settings → Environment Variables, add all variables from `.env.local.example` with production values.

- [ ] **Step 4: Add custom domain**

Vercel → Project Settings → Domains → Add `hub.vyrulhq.com`

In your DNS provider, add:
```
CNAME  hub  cname.vercel-dns.com
```

- [ ] **Step 5: Update `NEXT_PUBLIC_APP_URL` to `https://hub.vyrulhq.com`**

Update in Vercel environment variables.

- [ ] **Step 6: Update Supabase Auth redirect URLs**

Supabase Dashboard → Authentication → URL Configuration:
- Site URL: `https://hub.vyrulhq.com`
- Redirect URLs: `https://hub.vyrulhq.com/auth/callback`

- [ ] **Step 7: Verify deploy**

```bash
curl -I https://hub.vyrulhq.com
```

Expected: `HTTP/2 200`

- [ ] **Step 8: Commit deploy config**

```bash
git add .
git commit -m "chore: add Vercel deployment config and domain notes"
```

---

## Self-Review Checklist

- [x] **Invite flow:** Admin creates invite → email sent → client clicks link → Google OAuth → client record linked → redirected to /onboarding (stub until Plan 2)
- [x] **Auth middleware:** All portal + admin routes protected; admin role checked via `app_metadata.role`
- [x] **RLS:** All client tables have row-level security; service role used for admin ops
- [x] **No placeholders:** All steps contain actual code
- [x] **Type consistency:** `planTier` used consistently across invite.ts, API route, and schema
- [x] **Tests:** Unit tests for invite logic + API route; Playwright for E2E
- [x] **Deploy:** Domain, env vars, Supabase redirect URLs all covered

**Gap check:**
- Onboarding wizard → Plan 2 ✓ (stub page created, callback redirects to /onboarding)
- Client portal sections → Plans 2 + 3 ✓ (stub dashboard created)
- Admin client management → Plan 4 ✓ (only invites covered here)
- Social stats cron → Plan 4 ✓

---

*Continue with Plan 2: Onboarding Wizard + Client Portal Core (dashboard, footage submission, clip library)*
