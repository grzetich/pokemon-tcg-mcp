from flask import Flask, request, jsonify
import pokemontcgsdk
from pokemontcgsdk import Card, Set, Type, Supertype, Subtype, Rarity
import math
import os
from dotenv import load_dotenv # Assuming you still have this for local testing

# Initialize the Flask application
app = Flask(__name__)

# --- Configuration ---
# Load .env variables if present (for local testing)
# This should be at the very top, but load_dotenv() itself should be quick.
load_dotenv()

# --- Global variable to hold API key, initialized lazily ---
_pokemontcgsdk_initialized = False

def initialize_pokemontcgsdk():
    """
    Initializes the pokemontcgsdk with the API key.
    This function will be called on the first request to ensure the app is fully up.
    """
    global _pokemontcgsdk_initialized
    if not _pokemontcgsdk_initialized:
        api_key = os.environ.get('POKEMONTCG_API_KEY')
        if not api_key:
            print("ERROR: POKEMONTCG_API_KEY environment variable is not set!")
            # In a real production app, you might raise an error or return a 500 here
            # but for startup, we'll let it proceed and log the error.
        else:
            pokemontcgsdk.api_key = api_key
            print("INFO: pokemontcgsdk API key set successfully.")
        _pokemontcgsdk_initialized = True

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

@app.before_request
def before_first_request():
    """
    Ensures pokemontcgsdk is initialized before handling any request.
    This runs once per worker process.
    """
    initialize_pokemontcgsdk()
    print("INFO: Received first request, SDK initialized (or already was).")


@app.route('/')
def home():
    """
    A simple home route to confirm the Pokémon TCG MCP Server is running.
    """
    print("INFO: Home route accessed.")
    return "Pokémon TCG MCP Server is running! Available endpoints: /cards, /cards/<id>, /card_price, /sets, /sets/<id>, /types, /supertypes, /subtypes, /rarities."

# --- Card Endpoints ---

@app.route('/cards', methods=['GET'])
def get_cards():
    """
    API endpoint to search for Pokémon TCG cards with various query parameters.
    Supports 'name', 'set', 'type', 'rarity', 'page', and 'limit' query parameters.
    Example: /cards?name=Pikachu&set=Base&limit=10&page=1
    """
    print("INFO: /cards route accessed.")
    query_params = {k: v for k, v in request.args.items() if k not in ['page', 'limit']}
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20)) # Default limit

    if limit <= 0:
        return jsonify({"status": "error", "message": "Limit must be a positive integer."}), 400
    if page <= 0:
        return jsonify({"status": "error", "message": "Page must be a positive integer."}), 400

    q_string = []
    for key, value in query_params.items():
        q_string.append(f'{key}:"{value}"')

    try:
        if q_string:
            all_cards = Card.where(q=' '.join(q_string))
        else:
            all_cards = Card.all()

        cards_data = [serialize_tcg_object(card) for card in all_cards]

        paginated_response = paginate_results(cards_data, page, limit)

        if not paginated_response['data'] and q_string:
             return jsonify({
                "status": "not_found",
                "query": query_params,
                "message": "No Pokémon cards found matching your criteria."
            }), 404

        return jsonify({
            "status": "success",
            "results": paginated_response['data'],
            "pagination": paginated_response['pagination']
        }), 200

    except Exception as e:
        print(f"ERROR: An error occurred in /cards: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/cards/<string:card_id>', methods=['GET'])
def get_card_by_id(card_id):
    """
    API endpoint to get a specific Pokémon TCG card by its ID.
    Example: /cards/base1-4
    """
    print(f"INFO: /cards/{card_id} route accessed.")
    try:
        card = Card.find(card_id)
        if not card:
            return jsonify({
                "status": "not_found",
                "card_id": card_id,
                "message": f"No Pokémon card found with ID '{card_id}'."
            }), 404
        return jsonify({
            "status": "success",
            "card": serialize_tcg_object(card)
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /cards/<id>: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/card_price', methods=['GET'])
def get_card_price():
    """
    API endpoint to find the price of a Pokémon TCG card by name.
    Expects a 'card_name' query parameter.
    This route prioritizes TCGPlayer market price.
    """
    print("INFO: /card_price route accessed.")
    card_name = request.args.get('card_name')

    if not card_name:
        return jsonify({
            "status": "error",
            "message": "Missing 'card_name' query parameter."
        }), 400

    try:
        cards = Card.where(q=f'name:"{card_name}"')

        if not cards:
            return jsonify({
                "status": "not_found",
                "card_name": card_name,
                "message": f"No Pokémon card found with the name '{card_name}'."
            }), 404

        card = cards[0]

        price_data = {}
        if hasattr(card, 'tcgplayer') and card.tcgplayer and hasattr(card.tcgplayer, 'prices'):
            for price_type, prices in card.tcgplayer.prices.__dict__.items():
                if prices and hasattr(prices, 'market'):
                    price_data[price_type] = prices.market
                elif prices and hasattr(prices, 'averageSellPrice'):
                    price_data[price_type] = prices.averageSellPrice

        if not price_data:
            return jsonify({
                "status": "no_price_data",
                "card_name": card.name,
                "card_id": card.id,
                "card_image": card.images.small if hasattr(card.images, 'small') else None,
                "message": f"No TCGPlayer price data available for '{card.name}'."
            }), 200

        return jsonify({
            "status": "success",
            "card_name": card.name,
            "card_id": card.id,
            "set_name": card.set.name if hasattr(card, 'set') and hasattr(card.set, 'name') else None,
            "rarity": card.rarity if hasattr(card, 'rarity') else None,
            "card_image": card.images.small if hasattr(card.images, 'small') else None,
            "prices": price_data,
            "message": f"Price data retrieved for '{card.name}'."
        }), 200

    except Exception as e:
        print(f"ERROR: An error occurred in /card_price: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500


# --- Set Endpoints ---

@app.route('/sets', methods=['GET'])
def get_sets():
    """
    API endpoint to get all Pokémon TCG sets.
    Supports 'name', 'page', and 'limit' query parameters.
    Example: /sets?name=Base&limit=5
    """
    print("INFO: /sets route accessed.")
    set_name = request.args.get('name')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))

    if limit <= 0 or page <= 0:
        return jsonify({"status": "error", "message": "Page and limit must be positive integers."}), 400

    try:
        if set_name:
            all_sets = Set.where(q=f'name:"{set_name}"')
        else:
            all_sets = Set.all()

        sets_data = [serialize_tcg_object(s) for s in all_sets]
        paginated_response = paginate_results(sets_data, page, limit)

        if not paginated_response['data'] and set_name:
            return jsonify({
                "status": "not_found",
                "query": {"name": set_name},
                "message": "No Pokémon sets found matching your criteria."
            }), 404

        return jsonify({
            "status": "success",
            "results": paginated_response['data'],
            "pagination": paginated_response['pagination']
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /sets: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/sets/<string:set_id>', methods=['GET'])
def get_set_by_id(set_id):
    """
    API endpoint to get a specific Pokémon TCG set by its ID.
    Example: /sets/base1
    """
    print(f"INFO: /sets/{set_id} route accessed.")
    try:
        set_obj = Set.find(set_id)
        if not set_obj:
            return jsonify({
                "status": "not_found",
                "set_id": set_id,
                "message": f"No Pokémon set found with ID '{set_id}'."
            }), 404
        return jsonify({
            "status": "success",
            "set": serialize_tcg_object(set_obj)
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /sets/<id>: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

# --- Type, Supertype, Subtype, Rarity Endpoints ---

@app.route('/types', methods=['GET'])
def get_types():
    """
    API endpoint to get all Pokémon TCG card types.
    """
    print("INFO: /types route accessed.")
    try:
        types = Type.all()
        return jsonify({"status": "success", "types": types}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /types: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/supertypes', methods=['GET'])
def get_supertypes():
    """
    API endpoint to get all Pokémon TCG card supertypes.
    """
    print("INFO: /supertypes route accessed.")
    try:
        supertypes = Supertype.all()
        return jsonify({"status": "success", "supertypes": supertypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /supertypes: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/subtypes', methods=['GET'])
def get_subtypes():
    """
    API endpoint to get all Pokémon TCG card subtypes.
    """
    print("INFO: /subtypes route accessed.")
    try:
        subtypes = Subtype.all()
        return jsonify({"status": "success", "subtypes": subtypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /subtypes: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/rarities', methods=['GET'])
def get_rarities():
    """
    API endpoint to get all Pokémon TCG card rarities.
    """
    print("INFO: /rarities route accessed.")
    try:
        rarities = Rarity.all()
        return jsonify({"status": "success", "rarities": rarities}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /rarities: {str(e)}")
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

# This block is for local development only and is NOT executed by Gunicorn on Heroku.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)