import os
import requests
import math
import traceback
import json # For handling API responses

# Base URL for the Pokémon TCG API (Version 2)
# Ensure this is correct as per pokemontcg.io documentation
POKEMONTCG_API_BASE_URL = "https://api.pokemontcg.io/v2"

# API Key will be set by the calling application (app.py)
_api_key = None

def set_sdk_api_key(api_key):
    """Sets the API key for the service."""
    global _api_key
    _api_key = api_key
    if _api_key:
        print("INFO: Pokémon TCG API key set in tcg_service.")
    else:
        print("WARNING: API key not provided to tcg_service. Rate limits may apply.")

def _make_api_request(endpoint, params=None):
    """Internal helper to make authenticated API requests."""
    headers = {}
    if _api_key:
        headers['X-Api-Key'] = _api_key
    
    url = f"{POKEMONTCG_API_BASE_URL}{endpoint}"
    print(f"DEBUG: Making API request to {url} with params {params} and headers {headers}")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10) # Added timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.Timeout:
        print(f"ERROR: API request to {url} timed out.")
        raise ConnectionError(f"API request to {url} timed out.")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: API request to {url} failed: {e}")
        print(f"DEBUG: Response content: {response.text if 'response' in locals() else 'No response'}")
        raise ConnectionError(f"API request failed: {e}")
    except json.JSONDecodeError:
        print(f"ERROR: Failed to decode JSON from response for {url}. Response: {response.text}")
        raise ValueError(f"Invalid JSON response from API for {url}.")


# --- Helper Function for Object Serialization (simplified as API returns JSON directly) ---
def serialize_tcg_object(obj):
    """
    Since the API returns JSON, this function primarily ensures consistency
    and handles any specific formatting needs, or deep copies if mutable.
    For direct API responses, it might just return the object as is.
    """
    # For direct API responses, the data is usually already JSON-serializable dict/list
    return obj


# --- Helper Function for Pagination ---
def paginate_results(results, page, limit):
    """
    Helper function to paginate a list of results.
    Note: pokemontcg.io API has its own pagination. This is for client-side
    pagination if the API returns more than the desired limit or if we fetch all.
    However, the API's 'page' and 'pageSize' parameters should be preferred.
    """
    if not isinstance(results, list):
        return results # Not a list, no pagination needed

    total_items = len(results)
    total_pages = math.ceil(total_items / limit) if limit > 0 else 1

    start_index = (page - 1) * limit
    end_index = start_index + limit

    paginated_data = results[start_index:end_index]

    return {
        "data": paginated_data,
        "pagination": {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "items_per_page": limit
        }
    }

# --- Service Functions for Endpoints ---

def get_cards_service(query_params, page, limit):
    """Service function for /cards endpoint."""
    params = {
        'page': page,
        'pageSize': limit
    }
    # Map friendly query_params to API's 'q' parameter
    q_parts = []
    if 'name' in query_params:
        q_parts.append(f'name:"{query_params["name"]}"')
    if 'set' in query_params:
        q_parts.append(f'set.name:"{query_params["set"]}"')
    if 'type' in query_params:
        q_parts.append(f'types:"{query_params["type"]}"')
    if 'rarity' in query_params:
        q_parts.append(f'rarity:"{query_params["rarity"]}"')
    
    if q_parts:
        params['q'] = ' '.join(q_parts)

    response_data = _make_api_request("/cards", params=params)
    
    # pokemontcg.io API returns 'data' and 'totalCount'
    cards_data = response_data.get('data', [])
    total_count = response_data.get('totalCount', 0)
    
    return {
        "data": cards_data,
        "pagination": {
            "total_items": total_count,
            "total_pages": math.ceil(total_count / limit) if limit > 0 else 1,
            "current_page": page,
            "items_per_page": limit
        }
    }


def get_card_by_id_service(card_id):
    """Service function for /cards/<id> endpoint."""
    response_data = _make_api_request(f"/cards/{card_id}")
    return response_data.get('data') # API returns {'data': card_object}


def get_card_price_service(card_name):
    """Service function for /card_price endpoint."""
    # First, find the card by name
    search_params = {'q': f'name:"{card_name}"', 'pageSize': 1}
    search_response = _make_api_request("/cards", params=search_params)
    cards = search_response.get('data', [])

    if not cards:
        return None, "not_found", None

    card = cards[0]
    
    price_data = {}
    if card.get('tcgplayer') and card['tcgplayer'].get('prices'):
        for price_type, prices in card['tcgplayer']['prices'].items():
            if prices and prices.get('market'):
                price_data[price_type] = prices['market']
            elif prices and prices.get('averageSellPrice'): # Fallback if market not present
                price_data[price_type] = prices['averageSellPrice']

    if not price_data:
        return card, "no_price_data", None
    
    return card, "success", price_data


def get_sets_service(set_name, page, limit):
    """Service function for /sets endpoint."""
    params = {
        'page': page,
        'pageSize': limit
    }
    if set_name:
        params['q'] = f'name:"{set_name}"'

    response_data = _make_api_request("/sets", params=params)
    sets_data = response_data.get('data', [])
    total_count = response_data.get('totalCount', 0)

    return {
        "data": sets_data,
        "pagination": {
            "total_items": total_count,
            "total_pages": math.ceil(total_count / limit) if limit > 0 else 1,
            "current_page": page,
            "items_per_page": limit
        }
    }


def get_set_by_id_service(set_id):
    """Service function for /sets/<id> endpoint."""
    response_data = _make_api_request(f"/sets/{set_id}")
    return response_data.get('data')


def get_types_service():
    """Service function for /types endpoint."""
    response_data = _make_api_request("/types")
    return response_data.get('data', [])


def get_supertypes_service():
    """Service function for /supertypes endpoint."""
    response_data = _make_api_request("/supertypes")
    return response_data.get('data', [])


def get_subtypes_service():
    """Service function for /subtypes endpoint."""
    response_data = _make_api_request("/subtypes")
    return response_data.get('data', [])


def get_rarities_service():
    """Service function for /rarities endpoint."""
    response_data = _make_api_request("/rarities")
    return response_data.get('data', [])