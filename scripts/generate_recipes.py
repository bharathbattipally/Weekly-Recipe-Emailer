"""
Reads constraints.json, asks Gemini for structured recipe JSON that respects
those constraints and avoids repeating recent history, saves the result into
history.json (capped to the last 12 weeks), and emails it via Brevo.

The GitHub Actions workflow commits the updated history.json back to the
repo after this script runs, so next week's run sees this week's recipes.
"""

import json
import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS_PATH = REPO_ROOT / "data" / "constraints.json"
HISTORY_PATH = REPO_ROOT / "data" / "history.json"

MODEL = "gemini-3.1-flash-lite"  # stable, free-tier as of Sept 2026
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def recent_titles(history, lookback_weeks=4):
    """Flatten the last few weeks' recipe titles so we can tell the model
    what to avoid repeating."""
    titles = []
    for week in history[-lookback_weeks:]:
        for recipe in week.get("recipes", []):
            titles.append(recipe.get("title"))
    return [t for t in titles if t]


def build_prompt(constraints, avoid_titles):
    return f"""
You are a home cooking assistant. Generate {constraints['meals_per_week']} recipes
for the upcoming week based on these constraints:

Diet: {', '.join(constraints['diet'])}
Avoid ingredients: {', '.join(constraints['avoid_ingredients']) or 'none'}
Preferred cuisines: {', '.join(constraints['cuisines_preferred'])}
Max cook time: {constraints['max_cook_time_minutes']} minutes
Available equipment: {', '.join(constraints['equipment_available'])}
Meal types to cover: {', '.join(constraints['meal_types'])}
Notes: {constraints.get('notes', 'none')}

Do not repeat any of these recently-used recipe titles: {', '.join(avoid_titles) or 'none'}

Return ONLY a JSON array (no markdown fences, no commentary) where each item has:
- "title": string
- "meal_type": one of {constraints['meal_types']}
- "cuisine": string
- "cook_time_minutes": integer
- "ingredients": array of strings (include quantities)
- "steps": array of strings (short, numbered instructions)
""".strip()


def generate_recipes(prompt, api_key, max_attempts=4):
    client = genai.Client(api_key=api_key)

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.9,  # a bit of variety week to week
                ),
            )
            return json.loads(response.text)
        except genai_errors.ServerError as e:
            # 503 = model temporarily overloaded on Google's side, not our bug.
            # Retry with exponential backoff: 10s, 20s, 40s...
            if attempt == max_attempts:
                raise
            wait_seconds = 10 * (2 ** (attempt - 1))
            print(
                f"Gemini returned a server error (attempt {attempt}/{max_attempts}): {e}\n"
                f"Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)


def render_email_html(recipes):
    """Turn the recipe JSON into a simple, readable HTML email body."""
    cards = []
    for r in recipes:
        ingredients_html = "".join(f"<li>{i}</li>" for i in r.get("ingredients", []))
        steps_html = "".join(f"<li>{s}</li>" for s in r.get("steps", []))
        cards.append(f"""
        <div style="border:1px solid #e0e0e0; border-radius:8px; padding:16px; margin-bottom:20px;">
          <h2 style="margin:0 0 4px 0;">{r.get('title', 'Untitled recipe')}</h2>
          <p style="color:#666; margin:0 0 12px 0;">
            {r.get('meal_type', '').title()} &middot; {r.get('cuisine', '')} &middot; {r.get('cook_time_minutes', '?')} min
          </p>
          <h3 style="margin:12px 0 4px 0;">Ingredients</h3>
          <ul>{ingredients_html}</ul>
          <h3 style="margin:12px 0 4px 0;">Steps</h3>
          <ol>{steps_html}</ol>
        </div>
        """)

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width:600px; margin:0 auto;">
        <h1>This week's recipes</h1>
        <p style="color:#666;">{date.today().strftime('%B %d, %Y')}</p>
        {''.join(cards)}
      </body>
    </html>
    """


def send_email(recipes, brevo_api_key, sender_email, recipient_email):
    html_content = render_email_html(recipes)

    payload = {
        "sender": {"email": sender_email, "name": "Recipe Bot"},
        "to": [{"email": recipient_email}],
        "subject": f"Your recipes for the week of {date.today().strftime('%B %d')}",
        "htmlContent": html_content,
    }
    headers = {
        "api-key": brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(BREVO_SEND_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()  # raises an exception on 4xx/5xx so failures aren't silent
    print(f"Email sent - Brevo message id: {response.json().get('messageId')}")


def save_history(history, recipes, path, max_weeks=12):
    """Append this week's recipes to history and trim to the last max_weeks
    entries, so the file doesn't grow forever."""
    history.append({
        "week_of": date.today().isoformat(),
        "recipes": recipes,
    })
    history = history[-max_weeks:]

    with open(path, "w") as f:
        json.dump(history, f, indent=2)

    return history


def main():
    api_key = os.environ["GEMINI_API_KEY"]
    constraints = load_json(CONSTRAINTS_PATH)
    history = load_json(HISTORY_PATH)

    avoid_titles = recent_titles(history)
    prompt = build_prompt(constraints, avoid_titles)
    recipes = generate_recipes(prompt, api_key)

    print(json.dumps(recipes, indent=2))
    print(f"\nGenerated {len(recipes)} recipes.")

    save_history(history, recipes, HISTORY_PATH)
    print(f"Saved this week's recipes to {HISTORY_PATH.relative_to(REPO_ROOT)}")

    brevo_api_key = os.environ.get("BREVO_API_KEY")
    sender_email = os.environ.get("SENDER_EMAIL")
    recipient_email = os.environ.get("RECIPIENT_EMAIL")

    if brevo_api_key and sender_email and recipient_email:
        send_email(recipes, brevo_api_key, sender_email, recipient_email)
    else:
        print(
            "\nSkipping email send - BREVO_API_KEY, SENDER_EMAIL, or RECIPIENT_EMAIL "
            "not set."
        )


if __name__ == "__main__":
    main()
