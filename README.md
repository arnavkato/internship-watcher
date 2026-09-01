# internship-watcher

Polls community-maintained internship feeds every 15 min, filters to the roles
you want (SWE / quant / data-ML), and pings **Discord** the moment a new one
opens so you can apply first. Also writes `listings.csv` you sort in Google Sheets.

Pure Python stdlib — nothing to install. State lives in `seen.json` so it runs
the same locally or on a free GitHub Actions runner.

## Run locally

```bash
echo 'export JOBS_DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."' > .env
source .env
python3 jobs.py poll      # first run seeds a baseline (no alerts); later runs alert on new
```

`poll` also refreshes `listings.csv` — import it into Google Sheets and
sort/filter there. Columns: company, title, priority, category, season,
locations, sponsorship, date_posted, date_updated, first_seen, applicants,
active, url, source.

## Run in the cloud (free, GitHub Actions)

Public repo → Actions are free and unlimited. Nothing here is sensitive.

1. Create a **public** repo and push this folder to it (see commands you were given).
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   name `JOBS_DISCORD_WEBHOOK`, value = your webhook URL.
3. Done. `.github/workflows/poll.yml` polls every 15 min, alerts Discord, and
   commits `seen.json` / `listings.csv` back so it remembers what it's seen.

Trigger a first run manually under the **Actions** tab (workflow_dispatch) — the
first run seeds silently, the next one starts alerting.

> GitHub pauses scheduled workflows after **60 days** with no repo commits. The
> Action commits state on every run, so as long as it's finding listings it stays
> awake on its own.

## Tuning the filter (`config.toml`)

- `sources` — community feed URLs; swap in new cycles (Summer2028, …) as they appear.
- `[boards]` — direct company ATS boards (Greenhouse/Lever/Ashby), polled in
  parallel. These catch openings within **minutes** vs the feeds' hours of lag.
  Add a firm by dropping its slug in the matching list. Note: Google/Meta/Amazon/
  Apple/Microsoft (and Citadel, Two Sigma, HRT, Jane St, …) use proprietary
  portals with no public API — they can't be polled directly and arrive via the feeds.
- `seasons` — which terms to keep (Summer 2027, Fall 2026, …).
- `exclude` — title words that drop a listing outright (sales, mechanical, …).
- `priority.{quant,swe,data}` — a listing is tagged if its feed `category`
  matches **or** its title contains an `include` word. That title fallback is
  what catches odd names like "Systems Engineer". Checked quant → swe → data.

Run `python3 jobs.py selftest` after editing the lists.

## Known limits

- **No applicant count** — not in the free feeds (would need LinkedIn scraping,
  fragile + ToS-gray). Column exists but stays blank; sort on `date_posted`.
- Dedup is `company|title|season`, so the same role from two feeds alerts once.
