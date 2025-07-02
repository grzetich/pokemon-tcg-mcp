from flask import Flask, request, jsonify
import pokemontcgsdk # Corrected import for pokemontcgsdk.api_key
from pokemontcgsdk import Card, Set, Type, Supertype, Subtype, Rarity # Import classes directly
import math # For pagination calculations
import os # For Heroku port dynamic assignment
from dotenv import load_dotenv
load_dotenv() # This loads the variables from .env into os.environt

# Now os.environ.get will find the variable from .env
pokemontcgsdk.api_key = os.environ.get('POKEMONTCG_API_KEY')

# Initialize the Flask application
app = Flask(__name__)

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
            # If bytes cannot be decoded as UTF-8, represent them as a string
            # indicating binary data. For actual binary data (e.g., image bytes),
            # you might consider base64 encoding if needed for transfer.
            return f"<binary_data: {len(obj)} bytes>"
    if isinstance(obj, list):
        return [serialize_tcg_object(item) for item in obj]
    if isinstance(obj, dict):
        return {key: serialize_tcg_object(value) for key, value in obj.items()}

    # If it's an object from the SDK (or a similar custom object),
    # iterate through its dictionary and serialize its contents.
    if hasattr(obj, '__dict__'):
        data = {}
        for key, value in obj.__dict__.items():
            # Skip internal/private attributes that start with '_'
            if not key.startswith('_'):
                data[key] = serialize_tcg_object(value)
        return data
    
    # Fallback for other complex objects that are not directly serializable
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

@app.route('/')
def home():
    """
    A simple home route to confirm the Pokémon TCG MCP Server is running.
    """
    return "Pokémon TCG MCP Server is running! Available endpoints: /cards, /cards/<id>, /card_price, /sets, /sets/<id>, /types, /supertypes, /subtypes, /rarities."

# --- Card Endpoints ---

@app.route('/cards', methods=['GET'])
def get_cards():
    """
    API endpoint to search for Pokémon TCG cards with various query parameters.
    Supports 'name', 'set', 'type', 'rarity', 'page', and 'limit' query parameters.
    Example: /cards?name=Pikachu&set=Base&limit=10&page=1
    """
    query_params = {k: v for k, v in request.args.items() if k not in ['page', 'limit']}
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20)) # Default limit

    if limit <= 0:
        return jsonify({"status": "error", "message": "Limit must be a positive integer."}), 400
    if page <= 0:
        return jsonify({"status": "error", "message": "Page must be a positive integer."}), 400

    q_string = []
    for key, value in query_params.items():
        # Basic sanitization and query string formatting.
        # For more advanced searches (e.g., specific operator support),
        # refer to the SDK's documentation on 'q' parameter.
        q_string.append(f'{key}:"{value}"')

    try:
        if q_string:
            # Use 'where' method for filtered searches
            all_cards = Card.where(q=' '.join(q_string))
        else:
            # If no specific query, get all cards (consider large response if no limit)
            # The SDK's 'all()' method does not inherently paginate,
            # so we fetch all and paginate manually for the API response.
            all_cards = Card.all()

        # Convert Card objects to dictionaries for JSON serialization using the helper
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
            "card": serialize_tcg_object(card) # Use the helper for serialization
        }), 200
    except Exception as e:
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
    card_name = request.args.get('card_name')

    if not card_name:
        return jsonify({
            "status": "error",
            "message": "Missing 'card_name' query parameter."
        }), 400

    try:
        # Search for cards by name. The SDK returns a list of Card objects.
        cards = Card.where(q=f'name:"{card_name}"')

        if not cards:
            return jsonify({
                "status": "not_found",
                "card_name": card_name,
                "message": f"No Pokémon card found with the name '{card_name}'."
            }), 404

        card = cards[0] # Take the first card found

        price_data = {}
        if hasattr(card, 'tcgplayer') and card.tcgplayer and hasattr(card.tcgplayer, 'prices'):
            # The prices object itself needs to be serialized if it contains complex types
            # or byte strings, but typically price values are floats/ints.
            # We'll use serialize_tcg_object just in case, though it might not be strictly necessary
            # for the direct price values which are usually numbers.
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

        sets_data = [serialize_tcg_object(s) for s in all_sets] # Use the helper for serialization
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
            "set": serialize_tcg_object(set_obj) # Use the helper for serialization
        }), 200
    except Exception as e:
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
    try:
        types = Type.all()
        # Types are simple strings, so direct jsonify should be fine, but
        # serialize_tcg_object can be used for consistency if desired,
        # though it's not strictly needed here.
        return jsonify({"status": "success", "types": types}), 200
    except Exception as e:
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/supertypes', methods=['GET'])
def get_supertypes():
    """
    API endpoint to get all Pokémon TCG card supertypes.
    """
    try:
        supertypes = Supertype.all()
        return jsonify({"status": "success", "supertypes": supertypes}), 200
    except Exception as e:
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/subtypes', methods=['GET'])
def get_subtypes():
    """
    API endpoint to get all Pokémon TCG card subtypes.
    """
    try:
        subtypes = Subtype.all()
        return jsonify({"status": "success", "subtypes": subtypes}), 200
    except Exception as e:
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route('/rarities', methods=['GET'])
def get_rarities():
    """
    API endpoint to get all Pokémon TCG card rarities.
    """
    try:
        rarities = Rarity.all()
        return jsonify({"status": "success", "rarities": rarities}), 200
    except Exception as e:
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000)) # Get port from environment, default to 5000
    app.run(host='0.0.0.0', port=port, debug=False) # Listen on all interfaces, disable debug for production
