"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import re

from tools import search_listings, suggest_outfit, create_fit_card, _get_groq_client, _MODEL


# ── query parsing ───────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract a search description, optional size, and optional max_price from a
    natural language query.

    Uses the LLM to isolate the *item being searched for* from conversational
    noise (e.g. wardrobe details, questions), falling back to a regex parser
    if the LLM call fails or returns malformed data.

    Examples:
        "I'm looking for a vintage graphic tee under $30. I mostly wear baggy
         jeans and chunky sneakers. How would I style it?"
            → {"description": "vintage graphic tee", "size": None, "max_price": 30.0}

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    parsed = _parse_query_llm(query)
    if parsed is not None:
        return parsed
    return _parse_query_regex(query)


def _parse_query_llm(query: str) -> dict | None:
    """
    Ask the LLM to extract search parameters as JSON. Returns the parsed dict,
    or None if the call fails or the output can't be used (caller falls back).
    """
    prompt = (
        "Extract secondhand-clothing search parameters from the user's message. "
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "description": a short search phrase for the ITEM they want to buy '
        "(strip out wardrobe details, questions, and filler — keep just the item "
        "and its descriptors, e.g. \"vintage graphic tee\"),\n"
        '  "size": the size they asked for as a string, or null if none,\n'
        '  "max_price": the maximum price as a number, or null if none.\n\n'
        f"User message: {query}"
    )
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": "You extract structured search parameters as JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)

        description = data.get("description")
        if not description or not str(description).strip():
            return None  # unusable — fall back to regex

        size = data.get("size")
        size = str(size).strip() if size not in (None, "") else None

        max_price = data.get("max_price")
        max_price = float(max_price) if max_price not in (None, "") else None

        return {
            "description": str(description).strip(),
            "size": size,
            "max_price": max_price,
        }
    except Exception:
        # Network error, missing key, bad JSON, wrong types — fall back.
        return None


def _parse_query_regex(query: str) -> dict:
    """
    Deterministic fallback parser using regex (no LLM call).

    Examples:
        "vintage graphic tee under $30, size M"
            → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    text = query
    max_price = None
    size = None

    # Price: "under $30", "below 30", "$30", "under 25.50".
    price_match = re.search(
        r"(?:under|below|less than|max|<=?)?\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars|bucks)?",
        text,
        flags=re.IGNORECASE,
    )
    if price_match and ("$" in price_match.group(0) or re.search(
        r"under|below|less than|max", price_match.group(0), re.IGNORECASE
    )):
        max_price = float(price_match.group(1))
        text = text.replace(price_match.group(0), " ")

    # Size: "size M", "size W30", "size US 9".
    size_match = re.search(r"size\s+([\w/]+(?:\s+\d+)?)", text, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(1).strip()
        text = text.replace(size_match.group(0), " ")

    # Description: whatever's left, minus common filler words.
    filler = {
        "looking", "for", "a", "an", "the", "i", "want", "need", "im",
        "find", "me", "some", "something", "under", "below", "to", "buy",
    }
    words = [w for w in re.split(r"[\s,]+", text) if w and w.lower() not in filler]
    description = " ".join(words).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search the listings.
    session["search_results"] = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    if not session["search_results"]:
        # Failure mode: nothing matched. End early without calling other tools.
        session["error"] = (
            "Couldn't find any listings matching that. Try a different "
            "description, a larger budget, or a different size."
        )
        return session

    # Step 4: select the top (most relevant) result.
    session["selected_item"] = session["search_results"][0]

    # Step 5: suggest an outfit for the selected item.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], wardrobe
    )

    # Step 6: generate a shareable fit card from the outfit.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: done.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
