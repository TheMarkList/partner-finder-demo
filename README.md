# Partner Finder v1

> **Concept demo.** Sample data only. Not affiliated with Blotato. Nothing is sent.
> Try it in your browser: https://themarklist.github.io/partner-finder-demo/

Tracks community owners who could become referral partners. You add owners by hand
or by CSV. The tool scores them, Claude drafts first messages, and you review them.
**Nothing is ever sent.** You copy approved messages and send them yourself.

## Start it
1. Open Terminal and run: `cd ~/partner-finder && python3 server.py`
2. Open http://localhost:8000 in your browser.
3. To stop it, press Control + C in Terminal.

## Files
- `partners.db`: the database (created on first start). Back it up by copying it.
- `server.py`: the small local web server.
- `db.py`: database, fit score and CSV import.
- `screen.html`: the screen for the local tool.
- `demo/index.html`: a browser-only demo with sample data (no server needed).
- `index.html`: forwards the GitHub Pages link to the demo.
- `template.csv`: blank CSV with the right columns.
- `about-my-product.txt`: not included. Create it yourself with your product name, what it does,
  the partner offer and your sign-off name. The draft skill reads it.
- `.claude/skills/draft-outreach/`: the Claude Code skill that writes drafts.

## Fit score (0–100)
- **Activity, up to 40:** posts this week. 0 posts = 0, 10 or more = 40 (4 points per post).
- **Size, up to 20:** 100–5,000 members = 20. 50–99 or 5,001–20,000 = 12. Under 50 or over 20,000 = 5. Unknown = 10.
- **Niche, up to 40:** the community name and niche are checked for these words:
  - coaches (coach, coaching, mentor): +15
  - creators (creator, YouTube, content, influencer): +15
  - small business (business, agency, entrepreneur, marketing): +15
  - "social media": +10
  - Capped at 40. Off-topic words (crypto, gaming, forex, betting, NFT) make this part 0
    and cap the whole score at 20, so off-topic communities always rank at the bottom.
- Follower counts are never used.

## CSV columns
`community_name, url, platform, owner_name, niche, member_count, price, posts_this_week`.
Only community_name is required. The same URL (or the same name and platform when there's no
URL) is saved once. Importing it again updates the numbers but keeps the status and draft.
