"""
Step 2: reads constraints.json, asks Gemini for structured recipe JSON that
respects those constraints and avoids repeating recent history.

Email sending (step 3) and history-writing (step 4) aren't wired in yet -
this script currently just prints the generated recipes so you can sanity
check the output locally or in a manual Actions run.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS_PATH = REPO_ROOT / "data" / "constraints.json"
HISTORY_PATH = REPO_ROOT / "data" / "history.json"

MODEL = "gemini-3.1-flash-lite"  # stable, free-tier as of Sept 2026


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


def generate_recipes(prompt, api_key):
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.9,  # a bit of variety week to week
        ),
    )
    return json.loads(response.text)


def main():
    api_key = os.environ["GEMINI_API_KEY"]
    constraints = load_json(CONSTRAINTS_PATH)
    history = load_json(HISTORY_PATH)

    avoid_titles = recent_titles(history)
    prompt = build_prompt(constraints, avoid_titles)
    recipes = generate_recipes(prompt, api_key)

    print(json.dumps(recipes, indent=2))
    print(f"\nGenerated {len(recipes)} recipes (email sending comes in step 3).")


if __name__ == "__main__":
    main()
