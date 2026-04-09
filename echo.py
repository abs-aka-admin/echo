#!/usr/bin/env python3
"""
Echo — Reddit research aggregator.

Reads public posts from AI-related subreddits via RSS feeds and the Reddit API.
Stores results for personal research and analysis. Non-commercial.

Usage:
    # RSS mode (no auth needed, works from datacenter IPs)
    python echo.py rss --limit 5

    # API mode (requires Reddit app credentials)
    python echo.py api --limit 5

    # Single query
    python echo.py rss --query "claude code" --limit 3
"""

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Configuration ────────────────────────────────────────────

FEEDS = [
    {"subreddit": "ClaudeAI", "mode": "new"},
    {"subreddit": "ClaudeCode", "mode": "new"},
    {"subreddit": "ChatGPTCoding", "mode": "search", "query": "claude"},
    {"subreddit": "LocalLLaMA", "mode": "search", "query": "claude"},
    {"subreddit": "openclaw", "mode": "new"},
]

USER_AGENT = "Echo/1.0 (Canopy research lab; github.com/abs-aka-admin/echo)"

# Reddit API credentials (from env or .env file)
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")


# ── Utilities ────────────────────────────────────────────────


def content_hash(text: str) -> str:
    """SHA-256 hash for dedup."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def extract_post_id(url: str) -> str:
    """Extract Reddit post ID from URL."""
    match = re.search(r"/comments/([a-z0-9]+)/", url)
    return match.group(1) if match else ""


def make_record(
    title: str,
    author: str,
    subreddit: str,
    url: str,
    content: str,
    score: int | None,
    num_comments: int | None,
    published_at: str,
    query: str,
    feed_url: str,
    feed_type: str,
) -> dict:
    """Create a standardised record with full metadata."""
    return {
        "title": title,
        "author": author,
        "subreddit": subreddit,
        "url": url,
        "content": content,
        "score": score,
        "num_comments": num_comments,
        "post_id": extract_post_id(url),
        "content_hash": content_hash(f"{title}{author}{url}"),
        "source": "reddit",
        "feed_url": feed_url,
        "feed_type": feed_type,
        "query": query,
        "published_at": published_at,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "scraped_by": "cipher",
        "scraper_version": "1.0",
    }


# ── RSS Mode ─────────────────────────────────────────────────


def fetch_rss(subreddit: str, mode: str = "new", query: str = "", limit: int = 5) -> list[dict]:
    """Fetch posts via Reddit RSS feeds. No auth needed."""
    if mode == "search" and query:
        url = f"https://www.reddit.com/r/{subreddit}/search.rss?q={query}&restrict_sr=on&sort=new&t=week"
        feed_type = "subreddit_search"
    else:
        url = f"https://www.reddit.com/r/{subreddit}/{mode}.rss?limit={limit}"
        feed_type = f"subreddit_{mode}"

    print(f"  r/{subreddit} ({mode}) ", end="", flush=True)

    resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True)
    if resp.status_code != 200:
        print(f"✗ {resp.status_code}")
        return []

    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)

    results = []
    for entry in entries[:limit]:
        title = entry.findtext("atom:title", "", ns)
        link = entry.find("atom:link", ns)
        href = link.attrib.get("href", "") if link is not None else ""
        author = entry.findtext("atom:author/atom:name", "", ns).replace("/u/", "")
        updated = entry.findtext("atom:updated", "", ns)
        raw_content = entry.findtext("atom:content", "", ns) or ""
        clean_content = re.sub(r"<[^>]+>", "", raw_content).strip()
        category = entry.find("atom:category", ns)
        cat_label = category.attrib.get("label", "") if category is not None else subreddit

        results.append(
            make_record(
                title=title,
                author=author,
                subreddit=cat_label,
                url=href,
                content=clean_content[:2000],
                score=None,  # RSS doesn't provide scores
                num_comments=None,
                published_at=updated,
                query=query or "feed",
                feed_url=url,
                feed_type=feed_type,
            )
        )

    print(f"✓ {len(results)} posts")
    return results


# ── API Mode ─────────────────────────────────────────────────


def get_api_token() -> str | None:
    """Authenticate with Reddit OAuth2 and return bearer token."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        print("  ✗ Missing Reddit API credentials (set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD)")
        return None

    resp = httpx.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"  ✗ Auth failed: {resp.status_code}")
        return None

    token = resp.json().get("access_token")
    print(f"  ✓ Authenticated as {REDDIT_USERNAME}")
    return token


def fetch_api(
    token: str, subreddit: str, mode: str = "new", query: str = "", limit: int = 5
) -> list[dict]:
    """Fetch posts via Reddit API. Requires OAuth token."""
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}

    if mode == "search" and query:
        url = f"https://oauth.reddit.com/r/{subreddit}/search"
        params = {"q": query, "restrict_sr": "on", "sort": "new", "t": "week", "limit": limit}
        feed_type = "api_search"
    else:
        url = f"https://oauth.reddit.com/r/{subreddit}/{mode}"
        params = {"limit": limit}
        feed_type = f"api_{mode}"

    print(f"  r/{subreddit} ({mode}) ", end="", flush=True)

    resp = httpx.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        print(f"✗ {resp.status_code}")
        return []

    posts = resp.json().get("data", {}).get("children", [])
    results = []

    for post in posts[:limit]:
        p = post["data"]
        results.append(
            make_record(
                title=p.get("title", ""),
                author=p.get("author", ""),
                subreddit=p.get("subreddit", subreddit),
                url=f"https://reddit.com{p.get('permalink', '')}",
                content=p.get("selftext", "")[:2000],
                score=p.get("score"),
                num_comments=p.get("num_comments"),
                published_at=datetime.fromtimestamp(
                    p.get("created_utc", 0), tz=timezone.utc
                ).isoformat(),
                query=query or "feed",
                feed_url=url,
                feed_type=feed_type,
            )
        )

    print(f"✓ {len(results)} posts")
    return results


# ── Output ───────────────────────────────────────────────────


def save_results(results: list[dict], output: str = "stdout"):
    """Save results to stdout or JSONL file."""
    if output == "stdout":
        print(json.dumps(results, indent=2))
    else:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"\n  Appended {len(results)} records to {path}")


# ── Main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Echo — Reddit research aggregator")
    parser.add_argument("mode", choices=["rss", "api"], help="Fetch mode: rss (no auth) or api (OAuth)")
    parser.add_argument("--limit", type=int, default=5, help="Posts per feed (default: 5)")
    parser.add_argument("--query", type=str, default="", help="Override: search for a specific query across all feeds")
    parser.add_argument("--output", type=str, default="stdout", help="Output: stdout or path to JSONL file")
    args = parser.parse_args()

    print(f"\n{'─'*50}")
    print(f"Echo — {args.mode.upper()} mode, {args.limit} per feed")
    print(f"{'─'*50}\n")

    all_results = []

    if args.mode == "rss":
        for feed in FEEDS:
            query = args.query or feed.get("query", "")
            mode = "search" if args.query else feed["mode"]
            results = fetch_rss(feed["subreddit"], mode, query, limit=args.limit)
            all_results.extend(results)

    elif args.mode == "api":
        token = get_api_token()
        if not token:
            sys.exit(1)
        for feed in FEEDS:
            query = args.query or feed.get("query", "")
            mode = "search" if args.query else feed["mode"]
            results = fetch_api(token, feed["subreddit"], mode, query, limit=args.limit)
            all_results.extend(results)

    # Dedup by content_hash
    seen = set()
    unique = []
    for r in all_results:
        if r["content_hash"] not in seen:
            seen.add(r["content_hash"])
            unique.append(r)
    dupes = len(all_results) - len(unique)

    print(f"\n{'─'*50}")
    print(f"Total: {len(unique)} unique records ({dupes} duplicates removed)")
    print(f"{'─'*50}\n")

    save_results(unique, args.output)


if __name__ == "__main__":
    main()
