"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Default Groq-hosted model used for all LLM calls in this module.
_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Keywords to match against — lowercased, short noise words dropped.
    stop_words = {"a", "an", "the", "for", "with", "and", "or", "of", "in", "to"}
    keywords = [
        word
        for word in description.lower().split()
        if word not in stop_words and len(word) > 1
    ]

    size_query = size.lower().strip() if size else None

    matches = []
    for listing in listings:
        # Price filter (inclusive).
        if max_price is not None and listing["price"] > max_price:
            continue

        # Size filter — case-insensitive substring match so "M" matches "S/M".
        if size_query is not None and size_query not in listing["size"].lower():
            continue

        # Build a searchable text blob from the listing's text fields.
        haystack = " ".join(
            [
                listing["title"],
                listing["description"],
                listing["category"],
                " ".join(listing["style_tags"]),
                " ".join(listing["colors"]),
                listing["brand"] or "",
            ]
        ).lower()

        # Score by how many query keywords appear in the listing.
        score = sum(1 for word in keywords if word in haystack)
        if score == 0:
            continue

        matches.append((score, listing))

    # Sort by score, highest first.
    matches.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in matches]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    # Describe the thrifted item the user is considering.
    item_desc = (
        f"{new_item['title']} — a {new_item.get('condition', '')} "
        f"{new_item['category']} ({', '.join(new_item.get('colors', []))}; "
        f"tags: {', '.join(new_item.get('style_tags', []))}). "
        f"${new_item['price']} on {new_item.get('platform', 'a resale app')}."
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty wardrobe → general styling advice for the item.
        prompt = (
            f"A user is considering buying this thrifted item:\n{item_desc}\n\n"
            "They haven't told us what's in their wardrobe yet. Give friendly, "
            "general styling advice: what kinds of pieces pair well with it, what "
            "vibe or occasion it suits, and how to dress it up or down. Suggest "
            "1–2 example outfits using generic pieces (not specific brands)."
        )
    else:
        # Format the wardrobe into named pieces the LLM can reference.
        wardrobe_lines = []
        for it in items:
            note = f" ({it['notes']})" if it.get("notes") else ""
            wardrobe_lines.append(
                f"- {it['name']} [{it['category']}, "
                f"{', '.join(it.get('colors', []))}]{note}"
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A user is considering buying this thrifted item:\n{item_desc}\n\n"
            f"Here is what's already in their wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfits that pair the thrifted item with "
            "specific named pieces from their wardrobe above. Refer to the "
            "wardrobe pieces by name, explain why each outfit works, and keep "
            "the tone friendly and concrete."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are FitFindr, a thoughtful personal stylist who helps "
                    "people style secondhand and thrifted clothing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard against a missing or whitespace-only outfit — don't crash.
    if not outfit or not outfit.strip():
        return (
            "Not enough info to generate a fit card — no outfit suggestion was "
            "provided. Try styling an outfit first, then come back."
        )

    client = _get_groq_client()

    item_desc = (
        f"{new_item['title']}, ${new_item['price']}, "
        f"on {new_item.get('platform', 'a resale app')}"
    )

    prompt = (
        f"Thrifted item: {item_desc}\n\n"
        f"Outfit it's styled in:\n{outfit}\n\n"
        "Write a short, shareable OOTD caption (2–4 sentences) for an Instagram "
        "or TikTok post about this thrifted find. Make it sound casual and "
        "authentic — like a real person hyping their outfit, not a product "
        "listing. Mention the item name, its price, and the platform naturally "
        "(once each). Capture the specific vibe of the outfit. Output only the "
        "caption text — no quotation marks, hashtags-only lines, or labels."
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write fun, authentic social-media captions for thrifted "
                    "outfit finds."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        # High temperature so repeated calls on the same input vary.
        temperature=1.1,
    )

    return response.choices[0].message.content
