---
name: draft-outreach
description: Draft short, friendly first messages for the top 20 Partner Finder owners with status "New", save them to partners.db and set their status to "Drafted". Use when the user asks to draft outreach, draft messages, or runs /draft-outreach. Only drafts — never sends anything.
---

# Draft outreach (drafts only — never send)

**Hard rule:** This skill only writes drafts into the local database. Never send,
post, email or DM anything to anyone. Never use Gmail, social media, messaging or
other outside tools while running this skill. Never visit or fetch the communities' URLs.

## Steps

1. Read `about-my-product.txt` in the project folder. If it still has
   `[square-bracket placeholders]`, tell the user to fill it in first and stop.

2. Get the owners to draft for:
   ```
   python3 db.py top-new
   ```
   This prints up to 20 owners with status "New", best fit score first.
   If the list is empty, tell the user there is nothing to draft and stop.

3. For each owner, write a first message:
   - 60–110 words, friendly, plain, no hype, no emojis, no ALL CAPS.
   - Open with their first name if `owner_name` is known, otherwise "Hi there".
   - Mention something specific about what their community is about, using only
     the `community_name` and `niche` fields. Don't invent facts (no made-up
     posts, wins or numbers).
   - One sentence on what the product does, one sentence on the partner offer,
     both taken from `about-my-product.txt`.
   - End with a low-pressure question (e.g. "Would you be open to a quick chat?").
   - Sign off with the sign-off name from `about-my-product.txt`.
   - Each message must be different — don't reuse a template sentence for sentence.

4. Write all messages to a JSON file in the scratchpad or a temp folder (not the
   project folder), shaped as `{"<owner id>": "<message>", ...}`, then save them:
   ```
   python3 db.py save-drafts /path/to/drafts.json
   ```
   This saves each message and changes the status from "New" to "Drafted".
   It only touches owners that are still "New".

5. Tell the user how many were drafted, show 2 of the messages as examples, and
   remind them to review, edit and Approve them on the screen at
   http://localhost:8000. Nothing has been sent.
