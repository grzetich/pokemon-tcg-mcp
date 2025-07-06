from flask import Flask, request, jsonify
import math
import os
from dotenv import load_dotenv

# Initialize the Flask application
app = Flask(__name__)

# --- Configuration ---
# Load .env variables if present (for local testing)
try:
    load_dotenv()
    print("DEBUG: .env loaded successfully (if .env file exists).")
except Exception as e:
    print(f"DEBUG: Could not load .env file: {e}")

# --- Global variable to hold SDK instance and initialization status ---
_pokemontcgsdk_initialized = False
_pokemontcgsdk = None # Will hold the imported module

def initialize_pokemontcgsdk():
    """
    Initializes the pokemontcgsdk with the API key and imports it lazily.
    This function will be called on the first request to ensure the app is fully up.
    """
    global _pokemontcgsdk_initialized
    global _pokemontcgsdk # Declare global to assign to it

    if not _pokemontcgsdk_initialized:
        print("INFO: Attempting to LAZY INITIALIZE pokemontcgsdk...")
        try:
            # Import pokemontcgsdk only when needed
            import pokemontcgsdk as imported_sdk
            _pokemontcgsdk = imported_sdk
            print("INFO: pokemontcgsdk module imported successfully.")

            api_key = os.environ.get('POKEMONTCG_API_KEY')
            if not api_key:
                print("ERROR: POKEMONTCG_API_KEY environment variable is NOT set! This will limit SDK functionality.")
            else:
                _pokemontcgsdk.api_key = api_key
                print("INFO: pokemontcgsdk API key set successfully.")
            
            _pokemontcgsdk_initialized = True
            print("INFO: pokemontcgsdk initialization complete.")
        except Exception as e:
            print(f"CRITICAL ERROR: Exception during pokemontcgsdk import or initialization: {str(e)}")
            import traceback
            traceback.print_exc() # Print full traceback for this critical error
            _pokemontcgsdk_initialized = False # Mark as not initialized on failure
            _pokemontcgsdk = None # Ensure it's None if init failed
            raise # Re-raise the exception to indicate a critical failure
    else:
        print("INFO: pokemontcgsdk already initialized for this worker.")

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
def before_any_request():
    """
    Ensures pokemontcgsdk is initialized before handling any request.
    This runs once per worker process.
    """
    try:
        initialize_pokemontcgsdk()
        print("INFO: before_request hook executed. SDK check complete.")
    except Exception as e:
        print(f"CRITICAL ERROR: Exception in before_request hook during SDK initialization: {str(e)}")
        # If SDK init fails, we cannot proceed. Return a 500 error.
        return jsonify({
            "status": "server_error",
            "message": f"Critical server error: SDK initialization failed. Please check server logs. Error: {str(e)}"
        }), 500


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
        print(f"INFO: Calling _pokemontcgsdk.Card.where with q='{' '.join(q_string)}'")
        if q_string:
            all_cards = _pokemontcgsdk.Card.where(q=' '.join(q_string))
        else:
            print("INFO: Calling _pokemontcgsdk.Card.all() - This can be a heavy operation.")
            all_cards = _pokemontcgsdk.Card.all()
        print(f"INFO: Card query returned {len(all_cards)} results.")

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
        import traceback
        traceback.print_exc()
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
        print(f"INFO: Calling _pokemontcgsdk.Card.find('{card_id}')")
        card = _pokemontcgsdk.Card.find(card_id)
        if not card:
            print(f"INFO: Card '{card_id}' not found.")
            return jsonify({
                "status": "not_found",
                "card_id": card_id,
                "message": f"No Pokémon card found with ID '{card_id}'."
            }), 404
        print(f"INFO: Card '{card_id}' found.")
        return jsonify({
            "status": "success",
            "card": serialize_tcg_object(card)
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /cards/<id>: {str(e)}")
        import traceback
        traceback.print_exc()
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
        print(f"INFO: Calling _pokemontcgsdk.Card.where for price lookup with name='{card_name}'")
        cards = _pokemontcgsdk.Card.where(q=f'name:"{card_name}"')
        print(f"INFO: _pokemontcgsdk.Card.where for price lookup returned {len(cards)} results.")

        if not cards:
            print(f"INFO: No cards found for price lookup with name='{card_name}'.")
            return jsonify({
                "status": "not_found",
                "card_name": card_name,
                "message": f"No Pokémon card found with the name '{card_name}'."
            }), 200

        card = cards[0]

        price_data = {}
        if hasattr(card, 'tcgplayer') and card.tcgplayer and hasattr(card.tcgplayer, 'prices'):
            print("INFO: TCGPlayer data found.")
            for price_type, prices in card.tcgplayer.prices.__dict__.items():
                if prices and hasattr(prices, 'market'):
                    price_data[price_type] = prices.market
                elif prices and hasattr(prices, 'averageSellPrice'):
                    price_data[price_type] = prices.averageSellPrice
            print(f"INFO: Extracted price data: {price_data}")

        if not price_data:
            print("INFO: No TCGPlayer price data available for the card.")
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
        import traceback
        traceback.print_exc()
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
        print(f"INFO: Calling _pokemontcgsdk.Set.where with name='{set_name}' (if provided).")
        if set_name:
            all_sets = _pokemontcgsdk.Set.where(q=f'name:"{set_name}"')
        else:
            print("INFO: Calling _pokemontcgsdk.Set.all() - This can be a heavy operation.")
            all_sets = _pokemontcgsdk.Set.all()
        print(f"INFO: Set query returned {len(all_sets)} results.")

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
        import traceback
        traceback.print_exc()
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
        print(f"INFO: Calling _pokemontcgsdk.Set.find('{set_id}')")
        set_obj = _pokemontcgsdk.Set.find(set_id)
        if not set_obj:
            print(f"INFO: Set '{set_id}' not found.")
            return jsonify({
                "status": "not_found",
                "set_id": set_id,
                "message": f"No Pokémon set found with ID '{set_id}'."
            }), 404
        print(f"INFO: Set '{set_id}' found.")
        return jsonify({
            "status": "success",
            "set": serialize_tcg_object(set_obj)
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /sets/<id>: {str(e)}")
        import traceback
        traceback.print_exc()
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
        print("INFO: Calling _pokemontcgsdk.Type.all()")
        types = _pokemontcgsdk.Type.all()
        print(f"INFO: _pokemontcgsdk.Type.all() returned {len(types)} results.")
        return jsonify({"status": "success", "types": types}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /types: {str(e)}")
        import traceback
        traceback.print_exc()
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
        print("INFO: Calling _pokemontcgsdk.Supertype.all()")
        supertypes = _pokemontcgsdk.Supertype.all()
        print(f"INFO: _pokemontcgsdk.Supertype.all() returned {len(supertypes)} results.")
        return jsonify({"status": "success", "supertypes": supertypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /supertypes: {str(e)}")
        import traceback
        traceback.print_exc()
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
        print("INFO: Calling _pokemontcgsdk.Subtype.all()")
        subtypes = _pokemontcgsdk.Subtype.all()
        print(f"INFO: _pokemontcgsdk.Subtype.all() returned {len(subtypes)} results.")
        return jsonify({"status": "success", "subtypes": subtypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /subtypes: {str(e)}")
        import traceback
        traceback.print_exc()
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
        print("INFO: Calling _pokemontcgsdk.Rarity.all()")
        rarities = _pokemontcgsdk.Rarity.all()
        print(f"INFO: _pokemontcgsdk.Rarity.all() returned {len(rarities)} results.")
        return jsonify({"status": "success", "rarities": rarities}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /rarities: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

# This block is for local development only and is NOT executed by Gunicorn on Heroku.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)