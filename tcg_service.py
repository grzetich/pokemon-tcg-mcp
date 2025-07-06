import os
import pokemontcgsdk
from pokemontcgsdk import Card, Set, Type, Supertype, Subtype, Rarity
import math
import traceback

# --- Configuration ---
# API key will be set by the calling application (app.py)
# pokemontcgsdk.api_key = os.environ.get('POKEMONTCG_API_KEY') # This will be set externally

# --- Helper Function for Object Serialization ---
def serialize_tcg_object(obj):
    """
    Recursively converts pokemontcgsdk objects and their nested attributes
    into a dictionary suitable for JSON serialization.
    Handles potential byte strings by decoding them to UTF-8.
    """
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return f"<binary_data: {len(obj)} bytes>"
    if isinstance(obj, list):
        return [serialize_tcg_object(item) for item in obj]
    if isinstance(obj, dict):
        return {key: serialize_tcg_object(value) for key, value in obj.items()}

    if hasattr(obj, '__dict__'):
        data = {}
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                data[key] = serialize_tcg_object(value)
        return data
    
    return str(obj)


# --- Helper Function for Pagination ---
def paginate_results(results, page, limit):
    """
    Helper function to paginate a list of results.
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
    q_string = []
    for key, value in query_params.items():
        q_string.append(f'{key}:"{value}"')

    if q_string:
        all_cards = Card.where(q=' '.join(q_string))
    else:
        all_cards = Card.all()

    cards_data = [serialize_tcg_object(card) for card in all_cards]
    paginated_response = paginate_results(cards_data, page, limit)
    return paginated_response

def get_card_by_id_service(card_id):
    """Service function for /cards/<id> endpoint."""
    card = Card.find(card_id)
    return serialize_tcg_object(card) if card else None

def get_card_price_service(card_name):
    """Service function for /card_price endpoint."""
    cards = Card.where(q=f'name:"{card_name}"')
    if not cards:
        return None, "not_found"

    card = cards[0]
    price_data = {}
    if hasattr(card, 'tcgplayer') and card.tcgplayer and hasattr(card.tcgplayer, 'prices'):
        for price_type, prices in card.tcgplayer.prices.__dict__.items():
            if prices and hasattr(prices, 'market'):
                price_data[price_type] = prices.market
            elif prices and hasattr(prices, 'averageSellPrice'):
                price_data[price_type] = prices.averageSellPrice

    if not price_data:
        return serialize_tcg_object(card), "no_price_data"
    
    return serialize_tcg_object(card), "success", price_data

def get_sets_service(set_name, page, limit):
    """Service function for /sets endpoint."""
    if set_name:
        all_sets = Set.where(q=f'name:"{set_name}"')
    else:
        all_sets = Set.all()
    
    sets_data = [serialize_tcg_object(s) for s in all_sets]
    paginated_response = paginate_results(sets_data, page, limit)
    return paginated_response

def get_set_by_id_service(set_id):
    """Service function for /sets/<id> endpoint."""
    set_obj = Set.find(set_id)
    return serialize_tcg_object(set_obj) if set_obj else None

def get_types_service():
    """Service function for /types endpoint."""
    return Type.all()

def get_supertypes_service():
    """Service function for /supertypes endpoint."""
    return Supertype.all()

def get_subtypes_service():
    """Service function for /subtypes endpoint."""
    return Subtype.all()

def get_rarities_service():
    """Service function for /rarities endpoint."""
    return Rarity.all()

# --- SDK Initialization function (called by app.py) ---
def set_sdk_api_key(api_key):
    """Sets the API key for pokemontcgsdk."""
    if api_key:
        pokemontcgsdk.api_key = api_key
        print("INFO: pokemontcgsdk API key set in tcg_service.")
    else:
        print("ERROR: API key not provided to tcg_service. SDK functionality may be limited.")