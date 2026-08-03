#!/usr/bin/env python3
"""
poe.ninja PoE2 currency prices -> Discord (edits one pinned message in place).

Two modes, auto-detected:
  Bot mode      if DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID are set.
                Message is posted/edited by the bot account via REST API.
  Webhook mode  otherwise, if DISCORD_WEBHOOK_URL is set.

Env vars:
  DISCORD_BOT_TOKEN    bot token (secret, bot mode)
  DISCORD_CHANNEL_ID   target channel id (bot mode)
  DISCORD_WEBHOOK_URL  webhook url (secret, webhook mode)
  CURRENCIES           comma-separated names, e.g. "Divine Orb,Chaos Orb"
  LEAGUE_MATCH         substring to match league id/name, e.g. "aldur".
                       Falls back to the first (current) league if no match.

First run: posts a new message and saves its id to message_id.txt.
Later runs: edits that same message (PATCH), so no notifications spam.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_BASE = "https://poe.ninja"
DISCORD_API = "https://discord.com/api/v10"
STATE_FILE = "message_id.txt"

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
CURRENCIES = [c.strip() for c in os.environ.get("CURRENCIES", "Divine Orb,Chaos Orb").split(",") if c.strip()]
LEAGUE_MATCH = os.environ.get("LEAGUE_MATCH", "aldur").strip().lower()
# Currency to quote prices in (name or id). Prices are converted from the
# API's primary reference currency using core.rates.
QUOTE_CURRENCY = os.environ.get("QUOTE_CURRENCY", "Exalted Orb").strip()

HEADERS = {
    # poe.ninja asks for a descriptive User-Agent with a contact.
    "User-Agent": "poe2-discord-price-board/1.0 (GitHub Actions; contact: eason1305+claude@gmail.com)",
}


def http_json(url, method="GET", payload=None, extra_headers=None):
    data = None
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        return json.loads(body) if body else None


def pick_league():
    leagues = http_json(f"{API_BASE}/poe2/api/economy/leagues")
    for lg in leagues:
        text = (str(lg.get("id", "")) + " " + str(lg.get("name", ""))).lower()
        if LEAGUE_MATCH and LEAGUE_MATCH in text:
            return lg
    return leagues[0]  # first entry = current temp challenge league


def norm_items(items):
    """core.items may be a dict keyed by id or a list of objects; normalize to {id: meta}."""
    if isinstance(items, dict):
        return {str(k): v for k, v in items.items()}
    if isinstance(items, list):
        return {str(i.get("id")): i for i in items if isinstance(i, dict)}
    return {}


def id_of(x):
    """primary/secondary may be a bare id or an object."""
    if isinstance(x, dict):
        return str(x.get("id", ""))
    return str(x) if x is not None else ""


def fmt(v):
    if v is None:
        return "?"
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def fetch_overview(league_value):
    return http_json(
        f"{API_BASE}/poe2/api/economy/exchange/current/overview"
        f"?league={urllib.request.quote(str(league_value))}&type=Currency"
    )


def fetch_prices():
    league = pick_league()
    # Some league identifiers (e.g. URL slug "runesofaldur") return an empty
    # overview; the human-readable name (e.g. "Runes of Aldur") works. Try
    # id first, then name.
    data = fetch_overview(league.get("id"))
    if not (data.get("lines") or []):
        name = league.get("name")
        if name and name != league.get("id"):
            data = fetch_overview(name)

    core = data.get("core", {}) or {}
    # Item metadata (names) lives in the top-level "items" array; core.items
    # only contains the few reference currencies. Merge both.
    items = {**norm_items(data.get("items")), **norm_items(core.get("items"))}

    def name_of(iid):
        meta = items.get(str(iid)) or {}
        return meta.get("name") or str(iid)

    primary_id = id_of(core.get("primary"))
    rates = core.get("rates") or {}

    # Resolve the quote currency (by name or id); convert prices from the
    # primary reference currency using core.rates (units of X per 1 primary).
    quote_id = None
    q = QUOTE_CURRENCY.lower()
    for iid, meta in items.items():
        if iid.lower() == q or str(meta.get("name", "")).lower() == q:
            quote_id = iid
            break
    factor = 1.0
    if quote_id and quote_id != primary_id:
        r = rates.get(quote_id)
        if r:
            factor = r
        else:
            quote_id = primary_id  # no rate available; fall back to primary
    elif not quote_id:
        quote_id = primary_id
    quote_name = name_of(quote_id) if quote_id else "?"

    print(f"League: {league.get('name') or league.get('id')} | "
          f"primary={name_of(primary_id)} | quote={quote_name} (factor={factor})")

    by_name = {}
    for line in data.get("lines", []) or []:
        v = line.get("primaryValue")
        by_name[name_of(line.get("id")).lower()] = (v * factor) if v is not None else None

    rows, missing = [], []
    for want in CURRENCIES:
        v = by_name.get(want.lower())
        if v is None:
            missing.append(want)
        else:
            rows.append((want, v))
    return league, quote_name, rows, missing


def build_payload(league, primary_name, rows, missing):
    lines = [f"**{name}** : `{fmt(v)}` {primary_name}" for name, v in rows]
    if missing:
        lines.append(f"-# 查無資料:{', '.join(missing)}")
    league_label = league.get("name") or league.get("id")
    return {
        "content": "",
        "embeds": [{
            "title": f"PoE2 通貨價格 — {league_label}",
            "description": "\n".join(lines) if lines else "(無資料)",
            "color": 0xC9A227,
            "footer": {"text": "資料來源:poe.ninja · 每小時自動更新"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "allowed_mentions": {"parse": []},
    }


def discord_edit(message_id, payload):
    if BOT_TOKEN:
        http_json(
            f"{DISCORD_API}/channels/{CHANNEL_ID}/messages/{message_id}",
            method="PATCH", payload=payload,
            extra_headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
    else:
        http_json(f"{WEBHOOK_URL}/messages/{message_id}", method="PATCH", payload=payload)


def discord_post(payload):
    if BOT_TOKEN:
        resp = http_json(
            f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
            method="POST", payload=payload,
            extra_headers={"Authorization": f"Bot {BOT_TOKEN}"},
        )
    else:
        resp = http_json(f"{WEBHOOK_URL}?wait=true", method="POST", payload=payload)
    return resp["id"]


def main():
    if BOT_TOKEN and not CHANNEL_ID:
        sys.exit("DISCORD_BOT_TOKEN is set but DISCORD_CHANNEL_ID is not")
    if not BOT_TOKEN and not WEBHOOK_URL:
        sys.exit("Set DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID (bot mode) "
                 "or DISCORD_WEBHOOK_URL (webhook mode)")
    mode = "bot" if BOT_TOKEN else "webhook"

    league, primary_name, rows, missing = fetch_prices()
    payload = build_payload(league, primary_name, rows, missing)

    message_id = ""
    if os.path.exists(STATE_FILE):
        message_id = open(STATE_FILE, encoding="utf-8").read().strip()

    if message_id:
        try:
            discord_edit(message_id, payload)
            print(f"[{mode}] Edited message {message_id}")
            return
        except urllib.error.HTTPError as e:
            # 404: message deleted. 403: message belongs to another author
            # (e.g. it was created in the other mode) — post a fresh one.
            if e.code not in (403, 404):
                raise
            print(f"Cannot edit saved message ({e.code}); posting a new one.")

    new_id = discord_post(payload)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(new_id + "\n")
    print(f"[{mode}] Posted new message {new_id} (saved to {STATE_FILE})")


if __name__ == "__main__":
    main()
