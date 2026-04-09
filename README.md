# Echo

Reddit research aggregator. Reads public posts from AI-related subreddits for personal research and analysis.

## What it does

Monitors these feeds:

| Subreddit | Mode | What it catches |
|-----------|------|-----------------|
| r/ClaudeAI | new posts | Claude product discussions, bugs, tips |
| r/ClaudeCode | new posts | Claude Code workflows, configs |
| r/ChatGPTCoding | search "claude" | Claude mentions in GPT community |
| r/LocalLLaMA | search "claude" | Claude in local model discussions |
| r/openclaw | new posts | OpenClaw community |

## Usage

```bash
pip install -r requirements.txt

# RSS mode — no auth needed, works anywhere
python echo.py rss --limit 5

# Save to JSONL file
python echo.py rss --limit 10 --output data/reddit.jsonl

# Search for a specific topic across all feeds
python echo.py rss --query "MCP servers" --limit 3

# API mode — full data (score, comments, full text)
# Requires Reddit app credentials in .env
python echo.py api --limit 5
```

## Modes

**RSS** — No authentication required. Works from datacenter IPs. Gets title, author, content preview, URL, timestamp. No scores or comment counts.

**API** — Requires Reddit OAuth2 credentials. Gets full post body, scores, comment counts, flair, and more. Set up credentials:

```bash
cp .env.example .env
# Fill in your Reddit app credentials
```

## Output format

Each record includes:

```json
{
  "title": "...",
  "author": "...",
  "subreddit": "ClaudeAI",
  "url": "https://reddit.com/r/...",
  "content": "...",
  "score": 42,
  "num_comments": 15,
  "post_id": "1sgybvl",
  "content_hash": "a1b2c3d4e5f6g7h8",
  "source": "reddit",
  "feed_url": "...",
  "feed_type": "subreddit_new",
  "query": "feed",
  "published_at": "2026-04-09T18:41:18+00:00",
  "scraped_at": "2026-04-09T18:54:25+00:00",
  "scraped_by": "cipher",
  "scraper_version": "1.0"
}
```

Records are deduplicated by `content_hash`.

## License

MIT
