import os
from typing import List, Optional

from app.models import MenuItem
from app.services.menu import search_items, list_items

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AI_PERSONA_PROMPT = os.getenv(
	"AI_PERSONA_PROMPT",
	"You are a highly professional, cheerful restaurant waiter. Be respectful, concise, and helpful. "
	"Greet by name when available. Offer clear options and 2–3 tailored recommendations with prices and brief reasons. "
	"Confirm dietary notes, suggest safe alternatives, and ask a friendly follow-up. Use short sentences and WhatsApp-friendly formatting. Keep it warm but efficient.",
)


def suggest_items_for_preferences(user_text: str) -> List[tuple[int, str, float, str]]:
	"""Return list of (number, name, price, rationale). Fallback to rule-based if AI not configured."""
	items = list_items(limit=50)
	if not items:
		return []

	prefs = user_text.lower()
	use_openai = AI_PROVIDER == "openai" and OPENAI_API_KEY
	use_gemini = AI_PROVIDER == "gemini" and GEMINI_API_KEY

	if use_openai:
		try:
			from openai import OpenAI  # type: ignore
			client = OpenAI(api_key=OPENAI_API_KEY)
			menu_text = "\n".join([f"#{m.number} {m.name} — {m.price:.2f} [{m.tags or ''}]" for m in items])
			prompt = (
				f"{AI_PERSONA_PROMPT}\n\n"
				"Task: Based on the user's dietary preferences, pick 1–3 items from the menu. "
				"Return JSON array of objects with keys: number, rationale. Keep rationale to one short, friendly phrase.\n\n"
				f"User: {user_text}\nMenu:\n{menu_text}"
			)
			resp = client.responses.create(
				model="gpt-4o-mini",
				input=prompt,
			)
			text = resp.output_text or "[]"
			import json
			choices = json.loads(text)
			return _merge_choices_with_menu(choices, items)
		except Exception:
			pass

	if use_gemini:
		try:
			import google.generativeai as genai  # type: ignore
			genai.configure(api_key=GEMINI_API_KEY)
			model = genai.GenerativeModel("gemini-1.5-flash")
			menu_text = "\n".join([f"#{m.number} {m.name} — {m.price:.2f} [{m.tags or ''}]" for m in items])
			prompt = (
				f"{AI_PERSONA_PROMPT}\n\n"
				"Task: Based on the user's dietary preferences, pick 1–3 items from the menu. "
				"Return JSON array of objects with keys: number, rationale. Keep rationale to one short, friendly phrase.\n\n"
				f"User: {user_text}\nMenu:\n{menu_text}"
			)
			resp = model.generate_content(prompt)
			text = resp.text or "[]"
			import json
			choices = json.loads(text)
			return _merge_choices_with_menu(choices, items)
		except Exception:
			pass

	# Rule-based fallback using tags
	results: List[tuple[int, str, float, str]] = []
	rules = []
	if "vegan" in prefs or "plant" in prefs:
		rules.append("vegan")
	if "vegetarian" in prefs:
		rules.append("vegetarian")
	if "high protein" in prefs or "protein" in prefs:
		rules.append("high-protein")
	if "low carb" in prefs or "keto" in prefs:
		rules.append("low-carb")
	if "gluten" in prefs:
		rules.append("gluten-free")

	for m in items:
		mtags = (m.tags or "").lower()
		score = sum(1 for r in rules if r and r in mtags)
		if score > 0:
			rationale = "matches your preferences"
			results.append((m.number, m.name, m.price, rationale))
	if results:
		return results[:3]

	# Last resort: top 3 cheapest items
	items_sorted = sorted(items, key=lambda x: x.price)[:3]
	return [(m.number, m.name, m.price, "popular pick") for m in items_sorted]


def _merge_choices_with_menu(choices: list, items: List[MenuItem]) -> List[tuple[int, str, float, str]]:
	index = {m.number: m for m in items}
	results: List[tuple[int, str, float, str]] = []
	for ch in choices[:3]:
		num = ch.get("number") if isinstance(ch, dict) else None
		if not isinstance(num, int):
			continue
		m = index.get(num)
		if not m:
			continue
		rationale = ch.get("rationale") if isinstance(ch, dict) else "good fit"
		results.append((m.number, m.name, m.price, str(rationale)[:80]))
	return results
