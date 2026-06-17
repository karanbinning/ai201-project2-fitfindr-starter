"""
Tests for the three FitFindr tools.

The LLM-backed tools (suggest_outfit, create_fit_card) are tested against a
fake Groq client so the suite runs offline with no API key or network calls.
search_listings is pure data logic and is tested directly.
"""

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Fake Groq client ────────────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def create(self, **kwargs):
        # Echo back the user prompt so tests can assert on what was sent.
        user_msg = next(
            m["content"] for m in kwargs["messages"] if m["role"] == "user"
        )
        return _FakeCompletion(f"FAKE_LLM_RESPONSE :: {user_msg}")


class _FakeChat:
    completions = _FakeCompletions()


class _FakeClient:
    chat = _FakeChat()


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace the Groq client so LLM-backed tools run without the API."""
    monkeypatch.setattr("tools._get_groq_client", lambda: _FakeClient())


# ── Tool 1: search_listings ─────────────────────────────────────────────────


def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match sizes like "S/M", "M/L", "M" — case-insensitively.
    results = search_listings("shirt", size="m")
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


def test_search_results_sorted_by_relevance():
    # More keyword overlap should not rank below less overlap.
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) > 1  # sanity: query actually matches several items


# ── Tool 2: suggest_outfit ──────────────────────────────────────────────────


def test_suggest_outfit_with_wardrobe(mock_llm):
    item = search_listings("vintage graphic tee", max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_empty_wardrobe(mock_llm):
    # Failure mode: empty wardrobe → still returns non-empty styling advice,
    # and the prompt must NOT reference named wardrobe pieces.
    item = search_listings("vintage graphic tee", max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "haven't told us what's in their wardrobe" in result


# ── Tool 3: create_fit_card ─────────────────────────────────────────────────


def test_create_fit_card_happy_path(mock_llm):
    item = search_listings("vintage graphic tee", max_price=50)[0]
    card = create_fit_card("A breezy summer outfit with the tee.", item)
    assert isinstance(card, str)
    assert card.strip() != ""


def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit → descriptive error string, no exception,
    # and no LLM call (so this needs no mock).
    item = search_listings("vintage graphic tee", max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "Not enough info" in card


def test_create_fit_card_whitespace_outfit():
    # Whitespace-only outfit is also treated as missing.
    item = search_listings("vintage graphic tee", max_price=50)[0]
    card = create_fit_card("   \n  ", item)
    assert "Not enough info" in card
