# Podcast Outreach Pipeline — Design Spec

**Date:** 2026-05-26  
**Status:** Approved  
**Goal:** Build a repeatable prospect discovery pipeline that finds podcasters with YouTube video content but no Shorts, extracts their contact email, and outputs a CSV ready for GMass cold outreach.

---

## Problem

Podcasters who film their episodes have a latent content asset — long-form video sitting on YouTube with no Short-form extraction happening. They're leaving views, followers, and inbound leads on the table. This is exactly the gap VyrulHQ sells against. The pipeline automates finding people in that exact situation at scale.

---

## Targeting Criteria

A prospect qualifies if they meet **all three**:

1. Has an active podcast (50+ episodes, posted in last 90 days)
2. Has a YouTube channel with video uploads (confirmed match to podcast)
3. Has little to no YouTube Shorts activity in the last 90 days

**Disqualify if:**
- No email found in RSS feed
- No YouTube channel found or confirmed
- Already posting Shorts consistently (10+ in last 90 days)
- Podcast is clearly produced by a media company (too sophisticated, already has a team)

**Target categories:** business, entrepreneurship, self-improvement, marketing, investing, health/fitness coaching — niches where the host has a monetized business and can pay without haggling.

---

## Pipeline Architecture

Five sequential stages run as a single Python script:

### Stage 1 — Discover (Listen Notes API)
- Query Listen Notes Search API with `type=podcast`, English only, 50+ episodes, active in last 90 days
- Target categories specified via CLI flag
- Returns up to the configured `--limit` (default 500) shows per run
- Captures: podcast name, RSS feed URL, Listen Notes episode count, category

### Stage 2 — Extract Email (RSS Parser)
- Fetch each podcast's RSS feed URL
- Parse XML for `<itunes:email>` tag (required by Apple Podcasts spec)
- Fallback: `<managingEditor>` tag
- Discard show if no email found (~30–40% expected loss rate)

### Stage 3 — YouTube Match (YouTube Data API)
- Search YouTube for a channel matching the podcast name
- Confirm match by comparing podcast website URL (from Listen Notes) with channel's linked website
- Skip show if no confirmed channel match found
- Captures: channel ID, channel URL, subscriber count (informational)

### Stage 4 — Shorts Gap Check (YouTube Data API)
- Pull all uploads from the matched channel in the last 90 days
- Classify each video as a Short if: duration ≤ 60 seconds OR title contains `#Shorts`/`#shorts`
- Count total videos and Shorts separately
- Compute gap score (see below)

### Stage 5 — Output (CSV)
- Write one row per qualifying prospect
- Sort by gap score descending
- Save to `prospects.csv` in the script directory

---

## Output Schema

| Column | Source | Notes |
|---|---|---|
| `podcast_name` | Listen Notes | For personalization |
| `host_email` | RSS feed | Primary send-to address |
| `youtube_channel_url` | YouTube API | Reference in email copy |
| `yt_videos_90d` | YouTube API | Total uploads last 90 days |
| `yt_shorts_90d` | YouTube API | Shorts count last 90 days |
| `gap_score` | Calculated | 0–10, higher = better prospect |
| `category` | Listen Notes | For segmentation |
| `episode_count` | Listen Notes | Show maturity proxy |

**Gap score formula:**
```
gap_score = (yt_videos_90d / max(yt_shorts_90d, 1)) * min(episode_count / 10, 1)
```
More videos + fewer Shorts + more episodes = higher score.

---

## APIs

| API | Plan | Limits | Cost |
|---|---|---|---|
| Listen Notes | Free | 10,000 requests/month | $0 |
| YouTube Data v3 | Free | 10,000 units/day | $0 |

YouTube unit cost: ~100 units per channel search, ~1 unit per video detail call. At 10k units/day, expect ~100 full podcast lookups/day before hitting the limit. Run on consecutive days to process large batches.

---

## File Location

```
tools/podcast-prospector/
  scrape.py         # Main script
  config.py         # API keys (gitignored)
  requirements.txt  # Dependencies
  prospects.csv     # Output (gitignored)
```

---

## CLI Usage

```bash
python scrape.py --categories "business,entrepreneurship,coaching" --limit 500
```

**Flags:**
- `--categories` — comma-separated Listen Notes genre slugs
- `--limit` — max podcasts to discover (default: 500)
- `--output` — output CSV path (default: `prospects.csv`)

Runtime: ~2–3 min for 100 podcasts, ~20 min for 500. YouTube API is the bottleneck.

---

## Sending Setup

**Tool:** GMass (Gmail plugin)  
**Workflow:**
1. Import `prospects.csv` into Google Sheets
2. Connect GMass to the sheet
3. Send cold email template with `{{podcast_name}}` and `{{youtube_channel_url}}` merge fields
4. Set one follow-up at day 4 if no reply

**Note:** GMass sends from your Gmail account, which is fine for batches under ~100/day. At higher volume, migrate to Instantly.ai with a dedicated warmed-up sending domain.

---

## Cold Email Strategy

**Subject:** `[Podcast Name] — you're sitting on clips.`

**Body (template):**
- Observation: noticed they have X videos on YouTube but aren't doing Shorts
- Implication: they're leaving views and inbound on the table
- CTA: 15-minute call to show what that looks like for their show

3–4 sentences. No deck, no pitch, no pricing in the first email.

---

## Run Cadence

Weekly. Run once per week, deduplicate against previously contacted list before importing to GMass. Rotate categories each run to expand coverage across niches.
