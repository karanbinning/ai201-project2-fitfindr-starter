# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset and returns matching items. Must handle the case where no matches are found.

**Input parameters:**
- `description` (str): description of the listing
- `size` (str):  size user is looking for
- `max_price` (float): max price user would pay for the item

**What it returns:**
Retuns top 3 matches and includes all details of the listings

**What happens if it fails or returns nothing:**
it tells the user to try looking for something different but it doesn't call any other tool
---

### Tool 2: suggest_outfit

**What it does:**
Suggests outfit for the user based on their wardrobe and the item they got from their results from the function search_listings

**Input parameters:**

- `new_item` (dict): results[0] from search_listings
- `wardrobe` (dict): current wardrobe of the user

**What it returns:**
Returns a full outfit description

**What happens if it fails or returns nothing:**
tells user to look up a different listing if it fails. 

---

### Tool 3: create_fit_card

**What it does:**
If there is search_listings and suggest_outfit work, then a fit card is created

**Input parameters:**
- `outfit` (str): the outfit suggestion string returned by `suggest_outfit`
- `new_item` (dict): the listing dict for the thrifted find

**What it returns:**
Generates a short, shareable description of a complete outfit — the kind of thing someone would caption an Instagram post with. Must produce something different each time for different inputs.

**What happens if it fails or returns nothing:**
it should tell the user not enough data/info to generate a fit card

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
search_listings is called and if it succeeds then it goes to suggest_outfit and if it succeeds then it runs create_fit card
---

## State Management

**How does information from one tool get passed to the next?**
All state lives in one `session` dict created by `_new_session()`. It holds `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`, `outfit_suggestion`, `fit_card`, and `error`. Each step reads what it needs from the dict and writes its output back, so the output of one tool becomes the input to the next (e.g. `selected_item` from search feeds into `suggest_outfit`). The `error` field is the single signal that ends the interaction early.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to a helpful "try a different search" message, return early, and don't call any other tool |
| suggest_outfit | Wardrobe is empty | Fall back to general styling advice for the item instead of named-piece combinations |
| create_fit_card | Outfit input is missing or incomplete | Return a descriptive error string; don't raise an exception |

---

## Architecture

![FitFindr agent architecture diagram](img.png)

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude. For each tool I'll give it that tool's planning.md spec (inputs, return value, failure mode) plus the `tools.py` docstring, and ask it to implement the function using `load_listings()` from the data loader. I'll verify each tool against 3 test queries (including a no-match / empty-wardrobe case) before trusting it.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Planning Loop and State Management sections above plus the `run_agent` TODO in `agent.py`, and ask it to wire the loop using the `session` dict. I'll verify with the happy-path and no-results CLI tests already in `agent.py`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query into `{description: "vintage graphic tee", size: None, max_price: 30.0}`, stores it in `session["parsed"]`, and calls `search_listings("vintage graphic tee", None, 30.0)`.

**Step 2:**
`search_listings` returns the top 3 matches. The agent stores them in `session["search_results"]`, selects the top result as `session["selected_item"]`, and calls `suggest_outfit(selected_item, wardrobe)`.

**Step 3:**
`suggest_outfit` returns an outfit description (pairing the tee with the user's baggy jeans and chunky sneakers). The agent stores it in `session["outfit_suggestion"]` and calls `create_fit_card(outfit_suggestion, selected_item)`, storing the result in `session["fit_card"]`.

**Final output to user:**
The user sees the found item (title, price, platform), the styled outfit suggestion, and a shareable OOTD-style caption from the fit card.
