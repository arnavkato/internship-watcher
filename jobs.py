#!/usr/bin/env python3
"""Internship watcher: poll community listings feeds, filter to the roles you
want, alert Discord the moment a new one opens, and write a CSV you sort in Sheets.

    python jobs.py poll       # fetch, alert Discord on new, refresh listings.csv
    python jobs.py selftest   # assert the matcher behaves

State is seen.json ({dedup_key: first_seen_date}) so it works the same locally
and on an ephemeral GitHub Actions runner. Pure stdlib — no pip install needed.
Discord webhook via env JOBS_DISCORD_WEBHOOK (or the field in config.toml).
"""
import argparse, csv, json, os, time, tomllib, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
CONFIG = HERE / "config.toml"
STATE = HERE / "seen.json"
CSV = HERE / "listings.csv"


def load_config():
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def get_json(url):
    with urllib.request.urlopen(url, timeout=45) as r:
        return json.load(r)


def post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def classify(title, category, cfg):
    """Return priority tag ('quant'|'swe'|'data') or None if unwanted."""
    t = " " + (title or "").lower() + " "
    if any(x in t for x in cfg["exclude"]):
        return None
    for tag in ("quant", "swe", "data"):  # order = priority
        p = cfg["priority"][tag]
        if category in p["categories"] or any(k in t for k in p["include"]):
            return tag
    return None


def wanted_season(terms, cfg):
    for s in cfg["seasons"]:
        if s in (terms or []):
            return s
    return None


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else ""


def collect(cfg):
    """Fetch every source, return {dedup_key: listing dict} for wanted, active roles."""
    out = {}
    for url in cfg["sources"]:
        try:
            records = get_json(url)
        except Exception as e:  # one dead feed shouldn't kill the run
            print(f"! skip source {url}: {e}")
            continue
        for r in records:
            if not (r.get("active") and r.get("is_visible", True)):
                continue
            season = wanted_season(r.get("terms"), cfg)
            if not season:
                continue
            pri = classify(r.get("title"), r.get("category"), cfg)
            if not pri:
                continue
            company = (r.get("company_name") or "").strip()
            title = (r.get("title") or "").strip()
            key = f"{company}|{title}|{season}".lower()
            out.setdefault(key, dict(  # first source wins on dup key
                key=key, company=company, title=title, priority=pri,
                category=r.get("category"), season=season,
                locations=", ".join(r.get("locations") or []),
                sponsorship=r.get("sponsorship"), url=r.get("url"),
                source=r.get("source"), date_posted=r.get("date_posted"),
                date_updated=r.get("date_updated")))
    return out


def write_csv(matches, seen):
    rows = sorted(matches.values(), key=lambda m: m["date_posted"] or 0, reverse=True)
    with open(CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "title", "priority", "category", "season", "locations",
                    "sponsorship", "date_posted", "date_updated", "first_seen",
                    "applicants", "active", "url", "source"])
        for m in rows:
            w.writerow([m["company"], m["title"], m["priority"], m["category"], m["season"],
                        m["locations"], m["sponsorship"], iso(m["date_posted"]),
                        iso(m["date_updated"]), seen.get(m["key"], ""),
                        "", 1, m["url"], m["source"]])  # applicants: not in feeds, stays blank
    print(f"wrote {len(rows)} row(s) -> {CSV.name}")


def notify(new, cfg):
    hook = os.environ.get("JOBS_DISCORD_WEBHOOK") or cfg.get("discord_webhook")
    if not hook:
        print("  (no Discord webhook set — skipping alert. Set JOBS_DISCORD_WEBHOOK.)")
        return
    new.sort(key=lambda m: m["date_posted"] or 0, reverse=True)
    tag = {"quant": "🟢 QUANT", "swe": "🔵 SWE", "data": "🟣 DATA"}
    for i in range(0, len(new), 10):  # Discord: max 10 embeds/message
        batch = new[i:i + 10]
        embeds = [{
            "title": f"{m['title']} — {m['company']}"[:256],
            "url": m["url"],
            "description": f"{tag.get(m['priority'], m['priority'])} · {m['season']}"
                           f"\n📍 {m['locations'] or 'n/a'}",
        } for m in batch]
        try:
            post_json(hook, {"content": f"**{len(batch)} new internship(s)**", "embeds": embeds})
        except Exception as e:
            print(f"  ! Discord POST failed: {e}")
            return
        time.sleep(0.6)  # be gentle on the webhook rate limit
    print(f"  alerted Discord: {len(new)} listing(s).")


def poll(cfg):
    seen = json.loads(STATE.read_text()) if STATE.exists() else None
    seeding = seen is None
    if seeding:
        seen = {}
    matches = collect(cfg)
    new = [m for m in matches.values() if m["key"] not in seen]
    today = iso(int(time.time()))
    for key in matches:
        seen.setdefault(key, today)  # ponytail: seen grows unbounded; prune by age if it ever matters
    STATE.write_text(json.dumps(seen, indent=0, sort_keys=True))
    write_csv(matches, seen)
    if seeding:
        print(f"seeded {len(matches)} listing(s) — alerts start on the next poll.")
    else:
        print(f"{len(new)} new matching listing(s).")
        if new:
            notify(new, cfg)


def selftest():
    cfg = load_config()
    assert classify("Quantitative Trading Intern", "Quant", cfg) == "quant"
    assert classify("Software Engineer Intern", "Product", cfg) == "swe"
    assert classify("Systems Engineer Intern", "Hardware", cfg) == "swe"  # title rescues miscategorized
    assert classify("Intern", "Software", cfg) == "swe"                   # category-only match
    assert classify("Machine Learning Intern", "AI/ML/Data", cfg) == "data"
    assert classify("Mechanical Engineer Intern", "Hardware", cfg) is None  # excluded
    assert classify("Sales Development Intern", "Product", cfg) is None
    assert wanted_season(["Summer 2027"], cfg) == "Summer 2027"
    assert wanted_season(["Summer 2025"], cfg) is None
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("poll")
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"poll": lambda: poll(load_config()), "selftest": selftest}[a.cmd]()


if __name__ == "__main__":
    main()
