# Weekly recipe emailer

Sends you weekly lunch/dinner recipe ideas by email, based on constraints you set, running entirely on free tiers.

## Structure

```
.github/workflows/weekly-recipes.yml   GitHub Actions cron job — runs weekly
scripts/generate_recipes.py            Reads constraints, calls LLM, sends email, updates history
data/constraints.json                  Your dietary/cooking constraints — edit anytime
data/history.json                      Log of past recipes, so it doesn't repeat itself
requirements.txt                       Python dependencies
```

## Setup

1. Create a new **private GitHub repo** and push this folder to it.
2. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/) (free tier). The script uses `gemini-3.1-flash-lite`.
   - `BREVO_API_KEY` — from your [Brevo](https://www.brevo.com/) account (free tier, 300 emails/day)
   - `RECIPIENT_EMAIL` — the email address you want recipes sent to
3. Edit `data/constraints.json` to match your diet, cooking time, equipment, etc.
4. Go to the **Actions** tab and manually trigger "Weekly recipe emailer" once (via `workflow_dispatch`) to test it before waiting for the Sunday schedule.

## Testing locally

Copy `.env.example` to `.env` and fill in your real keys (this file is gitignored, so it never gets committed):

```
cp .env.example .env
pip install -r requirements.txt
python scripts/generate_recipes.py
```

## Status

- [x] Step 1: repo structure + GitHub Actions workflow
- [x] Step 2: constraints schema + Gemini prompt for structured recipe JSON
- [ ] Step 3: email HTML rendering + Brevo sending
- [ ] Step 4: history/dedup logic (write results back to history.json)
