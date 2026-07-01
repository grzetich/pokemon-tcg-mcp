"""Pokémon TCG MCP server.

A single-process Model Context Protocol server that exposes the Pokémon TCG API
(https://pokemontcg.io) as a set of MCP tools. Each tool is a thin bridge that
maps its arguments onto an HTTP request to https://api.pokemontcg.io/v2 and
returns the JSON straight through. There is no hosted backend and no second
process — the LLM client launches this file over stdio and that is the whole
server.

Set POKEMONTCG_API_KEY in the environment (or a local .env) to raise the API's
rate limits. The key is optional; without it the public, lower-rate tier is used.
"""

import difflib
import os

import requests
from mcp.server.fastmcp import FastMCP

try:
    # Optional: load a local .env so POKEMONTCG_API_KEY can live in a file
    # during development. Not required at runtime.
    from dotenv import load_dotenv

    # Load a .env sitting next to this file, regardless of the working
    # directory the MCP client launches us from.
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

API_BASE = "https://api.pokemontcg.io/v2"
REQUEST_TIMEOUT = 30

mcp = FastMCP("pokemon-tcg")


# --- HTTP helper -----------------------------------------------------------
def _api_get(path, params=None):
    """GET {API_BASE}{path} and return the parsed JSON body.

    Raises requests.HTTPError on a non-2xx response so callers can convert it
    into a structured error. The Pokémon TCG API already returns JSON, so this
    is the entire translation layer — no SDK objects, no re-serialization.
    """
    headers = {}
    api_key = os.environ.get("POKEMONTCG_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key

    response = requests.get(
        f"{API_BASE}{path}",
        params=params or {},
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _build_query(fields):
    """Build a Lucene-style `q` string from {api_field: value} pairs.

    Values containing whitespace are quoted so multi-word names (e.g. set
    "Base Set") match as a phrase. Empty values are skipped.
    """
    parts = []
    for field, value in fields.items():
        if value is None or value == "":
            continue
        value = str(value)
        if " " in value:
            parts.append(f'{field}:"{value}"')
        else:
            parts.append(f"{field}:{value}")
    return " ".join(parts)


def _suggestions(supplied):
    """Return {param: "Did you mean 'X'?"} for misspelled search parameters.

    Ported from the original Flask app: when a search returns nothing, fetch the
    list of valid values for each supplied parameter and use difflib to find the
    closest match. Best-effort — any lookup that fails is silently skipped.
    """
    out = {}

    def closest(param, valid_values):
        user_value = supplied.get(param)
        if not user_value or not valid_values:
            return
        match = difflib.get_close_matches(user_value, valid_values, n=1, cutoff=0.6)
        if match:
            out[param] = f"Did you mean '{match[0]}'?"

    try:
        if supplied.get("set_name"):
            sets = _api_get("/sets").get("data", [])
            closest("set_name", [s["name"] for s in sets if s.get("name")])
    except requests.RequestException:
        pass

    for param, endpoint in (
        ("type", "/types"),
        ("rarity", "/rarities"),
        ("subtype", "/subtypes"),
        ("supertype", "/supertypes"),
    ):
        if not supplied.get(param):
            continue
        try:
            closest(param, _api_get(endpoint).get("data", []))
        except requests.RequestException:
            pass

    return out


# --- Tools -----------------------------------------------------------------
@mcp.tool()
def search_cards(
    name: str = "",
    set_name: str = "",
    type: str = "",
    rarity: str = "",
    subtype: str = "",
    supertype: str = "",
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Search for Pokémon cards by any combination of criteria.

    Args:
        name: Full or partial card name, e.g. "Charizard".
        set_name: Name of the set the card belongs to, e.g. "Base Set".
        type: Energy type, e.g. "Fire", "Water", "Grass".
        rarity: Card rarity, e.g. "Rare Holo", "Common".
        subtype: Card subtype, e.g. "Stage 2", "V", "VMAX".
        supertype: "Pokémon", "Trainer", or "Energy".
        page: 1-based page number for pagination.
        limit: Number of results per page (the API caps this at 250).

    Returns the matching cards plus pagination info. If nothing matches, returns
    a not_found status that may include "Did you mean ...?" suggestions for
    misspelled parameters.
    """
    if page < 1 or limit < 1:
        return {"status": "error", "message": "page and limit must be positive integers."}

    query = _build_query(
        {
            "name": name,
            "set.name": set_name,
            "types": type,
            "rarity": rarity,
            "subtypes": subtype,
            "supertypes": supertype,
        }
    )

    params = {"page": page, "pageSize": limit}
    if query:
        params["q"] = query

    try:
        body = _api_get("/cards", params)
    except requests.HTTPError as e:
        return {"status": "server_error", "message": f"API returned {e.response.status_code}."}
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}

    cards = body.get("data", [])
    if not cards:
        supplied = {
            "name": name, "set_name": set_name, "type": type,
            "rarity": rarity, "subtype": subtype, "supertype": supertype,
        }
        result = {"status": "not_found", "query": {k: v for k, v in supplied.items() if v},
                  "message": "No Pokémon cards found."}
        suggestions = _suggestions(supplied)
        if suggestions:
            result["suggestions"] = suggestions
        return result

    return {
        "status": "success",
        "results": cards,
        "pagination": {
            "total_items": body.get("totalCount"),
            "current_page": body.get("page"),
            "items_per_page": body.get("pageSize"),
            "count": body.get("count"),
        },
    }


@mcp.tool()
def get_card_by_id(card_id: str) -> dict:
    """Get a single Pokémon card by its unique ID, e.g. "base1-4"."""
    try:
        body = _api_get(f"/cards/{card_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {"status": "not_found", "card_id": card_id,
                    "message": f"No card found with ID '{card_id}'."}
        return {"status": "server_error", "message": f"API returned {e.response.status_code}."}
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}

    return {"status": "success", "card": body.get("data")}


@mcp.tool()
def get_card_price(card_name: str) -> dict:
    """Get current TCGPlayer market prices for a card by name, e.g. "Charizard".

    Returns the market price for each available print variant (e.g. holofoil,
    normal, reverseHolofoil) for the first matching card.
    """
    if not card_name:
        return {"status": "error", "message": "card_name is required."}

    try:
        body = _api_get("/cards", {"q": _build_query({"name": card_name}), "pageSize": 1})
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}

    cards = body.get("data", [])
    if not cards:
        return {"status": "not_found", "card_name": card_name,
                "message": f"No card found with name '{card_name}'."}

    card = cards[0]
    tcgplayer = card.get("tcgplayer") or {}
    prices = tcgplayer.get("prices") or {}
    market = {variant: data.get("market") for variant, data in prices.items()
              if isinstance(data, dict) and data.get("market") is not None}

    if not market:
        return {"status": "no_price_data", "card_name": card.get("name"),
                "message": "No TCGPlayer price data available for this card."}

    return {
        "status": "success",
        "card_name": card.get("name"),
        "prices": market,
        "url": tcgplayer.get("url"),
        "updatedAt": tcgplayer.get("updatedAt"),
    }


@mcp.tool()
def search_sets(name: str = "", page: int = 1, limit: int = 50) -> dict:
    """Get Pokémon TCG sets, optionally filtered by name, e.g. "Base"."""
    if page < 1 or limit < 1:
        return {"status": "error", "message": "page and limit must be positive integers."}

    params = {"page": page, "pageSize": limit}
    query = _build_query({"name": name})
    if query:
        params["q"] = query

    try:
        body = _api_get("/sets", params)
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}

    return {
        "status": "success",
        "results": body.get("data", []),
        "pagination": {
            "total_items": body.get("totalCount"),
            "current_page": body.get("page"),
            "items_per_page": body.get("pageSize"),
            "count": body.get("count"),
        },
    }


@mcp.tool()
def get_set_by_id(set_id: str) -> dict:
    """Get a single Pokémon TCG set by its ID, e.g. "base1"."""
    try:
        body = _api_get(f"/sets/{set_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {"status": "not_found", "set_id": set_id,
                    "message": f"No set found with ID '{set_id}'."}
        return {"status": "server_error", "message": f"API returned {e.response.status_code}."}
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}

    return {"status": "success", "set": body.get("data")}


def _simple_list(endpoint, key):
    try:
        body = _api_get(endpoint)
    except requests.RequestException as e:
        return {"status": "server_error", "message": f"Could not reach the Pokémon TCG API: {e}"}
    return {"status": "success", key: body.get("data", [])}


@mcp.tool()
def get_types() -> dict:
    """List all card energy types, e.g. "Fire", "Water", "Grass"."""
    return _simple_list("/types", "types")


@mcp.tool()
def get_supertypes() -> dict:
    """List all card supertypes: "Pokémon", "Trainer", "Energy"."""
    return _simple_list("/supertypes", "supertypes")


@mcp.tool()
def get_subtypes() -> dict:
    """List all card subtypes, e.g. "Basic", "Stage 1", "V", "VMAX"."""
    return _simple_list("/subtypes", "subtypes")


@mcp.tool()
def get_rarities() -> dict:
    """List all card rarities, e.g. "Common", "Rare Holo", "Rare Ultra"."""
    return _simple_list("/rarities", "rarities")


if __name__ == "__main__":
    # Default transport is stdio: the MCP client launches this process and
    # speaks JSON-RPC over stdin/stdout.
    mcp.run()
