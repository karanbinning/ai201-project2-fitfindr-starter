# FitFindr 🛍️

FitFindr is an agent that helps you shop secondhand. You describe what you're
looking for in plain language; it finds a matching listing, styles it against
your wardrobe, and writes a shareable "fit card" caption for the find.

It chains **three tools** through a **planning loop** that decides what to do
next based on the result of each step — and stops early with a helpful message
when a step can't produce useful input for the next one.

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Running

**Web UI (Gradio):**
```bash
python app.py
```
Open the URL printed in your terminal (usually `http://localhost:7860`, but
check the output — the port can change).

**CLI (happy path + no-results path):**
```bash
python agent.py
```

**Tests:**
```bash
python -m pytest tests/ -v
```

---

## Tool Inventory

All three tools live in [tools.py](tools.py) and can be called and tested in
isolation. The two LLM-backed tools call Groq (`llama-3.3-70b-versatile`).

### 1. `search_listings(description, size=None, max_price=None) -> list[dict]`

- **Inputs:**
  - `description` (`str`) — keywords describing the item (e.g. `"vintage graphic tee"`)
  - `size` (`str | None`) — size filter; case-insensitive substring match, so `"M"` matches `"S/M"`
  - `max_price` (`float | None`) — inclusive price ceiling
- **Output:** `list[dict]` — matching listings sorted by relevance (best first); **empty list** if nothing matches (never raises).
- **Purpose:** Search the 40-listing mock dataset. Filters by price and size, then scores each remaining listing by how many `description` keywords appear across its title, description, category, style tags, colors, and brand. Listings with a score of 0 are dropped.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

- **Inputs:**
  - `new_item` (`dict`) — a listing dict (the item being considered)
  - `wardrobe` (`dict`) — a wardrobe dict with an `"items"` key (a list of wardrobe item dicts; may be empty)
- **Output:** `str` — a non-empty outfit suggestion.
- **Purpose:** Suggest 1–2 complete outfits. With a populated wardrobe it pairs the item with **specific named pieces** from the wardrobe. With an empty wardrobe it returns **general styling advice** instead.

### 3. `create_fit_card(outfit, new_item) -> str`

- **Inputs:**
  - `outfit` (`str`) — the outfit string from `suggest_outfit()`
  - `new_item` (`dict`) — the listing dict for the item
- **Output:** `str` — a 2–4 sentence casual OOTD caption (mentions item name, price, platform once each). Uses a high LLM temperature (`1.1`) so repeated calls on the same input vary.
- **Purpose:** Turn the outfit into a shareable social-media caption. Returns a **descriptive error string** (no exception) if `outfit` is empty or whitespace-only.

---

## Planning Loop — How the Agent Decides

The loop lives in `run_agent(query, wardrobe)` in [agent.py](agent.py). It is a
**linear pipeline with a guard**: each step's output is the next step's input,
and the agent only advances when the previous step produced something usable.

```
query
  │
  ▼
[parse] ── extract {description, size, max_price}
  │
  ▼
search_listings(description, size, max_price)
  │
  ├── results == []  ──►  set session["error"], RETURN EARLY  (skip tools 2 & 3)
  │
  ▼  (results found)
select top result  ──►  session["selected_item"]
  │
  ▼
suggest_outfit(selected_item, wardrobe)
  │   └── branches internally: empty wardrobe → general advice
  ▼
create_fit_card(outfit, selected_item)
  │
  ▼
return session
```

**The key decision the agent makes** is at the search step: *did the search
return anything?* If `search_listings` returns an empty list, there is no item
to style and no item to caption — so calling `suggest_outfit` or
`create_fit_card` would mean feeding them garbage. The agent sets a helpful
error and returns immediately. This is why the three tools are **not** called
unconditionally.

A second, smaller decision happens *inside* `suggest_outfit`: if the wardrobe is
empty it switches from "pair with your named pieces" to "general styling
advice," so a brand-new user with no wardrobe still gets a useful answer.

**Query parsing** is LLM-first with a regex fallback. `_parse_query()` asks the
LLM to extract `{description, size, max_price}` as JSON — this lets it strip
conversational noise (wardrobe details, questions) and keep just the item being
searched for. If the LLM call fails or returns malformed data, it falls back to
a deterministic regex parser so the agent still works offline.

---

## State Management

All state for one interaction lives in a single `session` dict created by
`_new_session()`:

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | entry point | parser |
| `parsed` | `_parse_query()` | `search_listings` call |
| `search_results` | `search_listings` | branch guard, item selection |
| `selected_item` | item selection | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | entry point | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `error` | branch guard | final output / UI |

Each step reads what it needs from the dict and writes its output back, so the
output of one tool literally becomes the input to the next — the **same**
`selected_item` dict object that search stores is the object passed into both
`suggest_outfit` and `create_fit_card` (verified by identity checks, not just
equality). The `error` field is the single signal that ends the interaction
early; when it's set, the downstream fields stay `None`.

---

## Error Handling (per tool, with examples)

| Tool | Failure mode | Response |
|------|-------------|----------|
| `search_listings` | No listing matches the query | Returns `[]` (no exception). The agent sets `session["error"]` to a "try a different search" message and returns early without calling the other tools. |
| `suggest_outfit` | Wardrobe is empty | Falls back to general styling advice for the item instead of named-piece combinations. |
| `create_fit_card` | `outfit` is empty / whitespace-only | Returns a descriptive error string ("Not enough info to generate a fit card…") instead of raising or calling the LLM. |

**Concrete example from testing** — the impossible query
`"designer ballgown size XXS under $5"`:

```bash
$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]

$ python agent.py
...
=== No-results path ===
Error message: Couldn't find any listings matching that. Try a different
description, a larger budget, or a different size.
```

`search_listings` returns `[]`, the agent surfaces an actionable message
(naming three things the user can change), and `session["fit_card"]` stays
`None` — `suggest_outfit` and `create_fit_card` are never called. This was
verified by spying on the tool functions during the no-results run.

---

## AI Usage

I used Claude (via Claude Code) as the primary AI tool throughout. Two concrete
instances:

**1. Implementing the three tools.**
- *Input I gave it:* the Tool 1/2/3 specs from [planning.md](planning.md)
  (inputs, return value, failure mode), the docstring TODOs in `tools.py`, and
  the `load_listings()` signature from the data loader.
- *What it produced:* implementations of all three functions — keyword-overlap
  scoring for `search_listings`, the empty-vs-populated wardrobe branch for
  `suggest_outfit`, and the empty-outfit guard for `create_fit_card`.
- *What I changed / overrode:* No model was pinned anywhere in the repo, so I
  had it factor the model name into a single `_MODEL` constant rather than
  hardcoding it in each call. I also kept `search_listings` returning **all**
  sorted matches (the docstring contract) rather than capping at top-3, and let
  the caller select `results[0]` — so the tool stays general.

**2. The query parser.**
- *Input I gave it:* the planning.md "Complete Interaction" walkthrough, which
  expects the conversational query *"I'm looking for a vintage graphic tee under
  $30. I mostly wear baggy jeans…"* to parse into
  `{description: "vintage graphic tee", size: None, max_price: 30.0}`.
- *What it produced:* first a pure-regex parser.
- *What I changed / overrode:* the regex parser left conversational noise in the
  description (the whole sentence, including the wardrobe details), which didn't
  match the walkthrough. I had it switch to an **LLM-first parser with the regex
  parser kept as a fallback**, so conversational queries parse cleanly but the
  agent still works if the LLM call fails.

---

## Spec Reflection

- **What matched the plan:** the linear search → style → caption pipeline and the
  single-`session`-dict state model from planning.md held up exactly. The
  early-return-on-empty-search decision was the right call and made the
  no-results path clean.
- **What I changed from the plan:** planning.md left the parse method open
  ("regex or LLM"); I ended up needing the LLM for conversational queries and
  added a regex fallback — worth noting since it adds one LLM call per query.
- **Trade-offs:** `search_listings` uses substring keyword matching, which is
  simple and fast but can over-match (e.g. `"tee"` inside another word). Fine for
  this 40-item dataset; a real system would tokenize or use embeddings.

---

## Repository Layout

```
ai201-project2-fitfindr-starter/
├── tools.py                  # The 3 tools
├── agent.py                  # Planning loop + query parser
├── app.py                    # Gradio UI (handle_query maps session → panels)
├── planning.md               # Design doc
├── tests/test_tools.py       # Pytest suite (per-tool, incl. failure modes)
├── data/
│   ├── listings.json         # 40 mock secondhand listings
│   └── wardrobe_schema.json  # Wardrobe format + example/empty wardrobes
└── utils/data_loader.py      # Data loading helpers
``` 
