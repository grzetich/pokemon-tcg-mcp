from flask import Flask, request, jsonify
import pokemontcgsdk
from pokemontcgsdk import Card, Set, Type, Supertype, Subtype, Rarity
import math
import os
from dotenv import load_dotenv
import traceback
import difflib # Import the library for finding close matches

# Load .env variables for local testing
load_dotenv()

# Set API key from environment variables
pokemontcgsdk.api_key = os.environ.get('POKEMONTCG_API_KEY')

# Initialize Flask app
app = Flask(__name__)

def serialize_tcg_object(obj):
    """Recursively converts pokemontcgsdk objects to dictionaries."""
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

def paginate_results(results, page, limit):
    """Paginates a list of results."""
    if not isinstance(results, list):
        return results
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
    """A simple home route to confirm the server is running."""
    return "Pokémon TCG MCP Server is running!"

@app.route('/cards', methods=['GET'])
def get_cards():
    """Searches for cards with various query parameters and provides suggestions."""
    query_params = {k: v for k, v in request.args.items() if k not in ['page', 'limit']}
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    if limit <= 0 or page <= 0:
        return jsonify({"status": "error", "message": "Page and limit must be positive integers."}), 400
    
    q_string = [f'{key}:"{value}"' for key, value in query_params.items()]
    
    try:
        all_cards = Card.where(q=' '.join(q_string)) if q_string else Card.all()
        
        # If no cards are found, check for suggestions on specified parameters
        if not all_cards and query_params:
            suggestions = {}
            
            # Helper function to get suggestions for a given parameter
            def find_suggestion(param_name, all_values_func):
                if param_name in query_params:
                    user_value = query_params[param_name]
                    try:
                        all_values = all_values_func()
                        # If the values are objects (like Sets), extract their names
                        if all_values and not isinstance(all_values[0], str):
                            all_names = [v.name for v in all_values]
                        else:
                            all_names = all_values
                        
                        close_matches = difflib.get_close_matches(user_value, all_names, n=1, cutoff=0.6)
                        if close_matches:
                            suggestions[param_name] = f"Did you mean '{close_matches[0]}'?"
                    except Exception:
                        # If the API call to get all values fails, just skip suggestions for this param
                        pass

            # Check each parameter for potential suggestions
            find_suggestion('set', Set.all)
            find_suggestion('type', Type.all)
            find_suggestion('rarity', Rarity.all)
            find_suggestion('supertype', Supertype.all)
            find_suggestion('subtype', Subtype.all)

            if suggestions:
                return jsonify({
                    "status": "not_found",
                    "query": query_params,
                    "message": "No Pokémon cards found.",
                    "suggestions": suggestions
                }), 404

        cards_data = [serialize_tcg_object(card) for card in all_cards]
        paginated_response = paginate_results(cards_data, page, limit)
        
        if not paginated_response['data'] and q_string:
            return jsonify({"status": "not_found", "query": query_params, "message": "No Pokémon cards found."}), 404
            
        return jsonify({"status": "success", "results": paginated_response['data'], "pagination": paginated_response['pagination']}), 200
        
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/cards/<string:card_id>', methods=['GET'])
def get_card_by_id(card_id):
    """Gets a specific card by its ID."""
    try:
        card = Card.find(card_id)
        if not card:
            return jsonify({"status": "not_found", "message": f"No card found with ID '{card_id}'."}), 404
        return jsonify({"status": "success", "card": serialize_tcg_object(card)}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/card_price', methods=['GET'])
def get_card_price():
    """Finds the price of a Pokémon TCG card by name."""
    card_name = request.args.get('card_name')
    if not card_name:
        return jsonify({"status": "error", "message": "Missing 'card_name' query parameter."}), 400
    try:
        cards = Card.where(q=f'name:"{card_name}"')
        if not cards:
            return jsonify({"status": "not_found", "card_name": card_name, "message": f"No card found with name '{card_name}'."}), 404
        card = cards[0]
        price_data = {}
        if hasattr(card, 'tcgplayer') and card.tcgplayer and hasattr(card.tcgplayer, 'prices'):
            for price_type, prices in card.tcgplayer.prices.__dict__.items():
                if prices and hasattr(prices, 'market'):
                    price_data[price_type] = prices.market
        if not price_data:
            return jsonify({"status": "no_price_data", "card_name": card.name, "message": "No TCGPlayer price data available."}), 200
        return jsonify({"status": "success", "card_name": card.name, "prices": price_data}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/sets', methods=['GET'])
def get_sets():
    """Gets all Pokémon TCG sets."""
    try:
        all_sets = Set.all()
        sets_data = [serialize_tcg_object(s) for s in all_sets]
        return jsonify({"status": "success", "results": sets_data}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/types', methods=['GET'])
def get_types():
    """Gets all Pokémon TCG card types."""
    try:
        types = Type.all()
        return jsonify({"status": "success", "types": types}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/supertypes', methods=['GET'])
def get_supertypes():
    """Gets all Pokémon TCG card supertypes."""
    try:
        supertypes = Supertype.all()
        return jsonify({"status": "success", "supertypes": supertypes}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/subtypes', methods=['GET'])
def get_subtypes():
    """Gets all Pokémon TCG card subtypes."""
    try:
        subtypes = Subtype.all()
        return jsonify({"status": "success", "subtypes": subtypes}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

@app.route('/rarities', methods=['GET'])
def get_rarities():
    """Gets all Pokémon TCG card rarities."""
    try:
        rarities = Rarity.all()
        return jsonify({"status": "success", "rarities": rarities}), 200
    except Exception as e:
        return jsonify({"status": "server_error", "message": str(e)}), 500

# This block is for local development testing only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)