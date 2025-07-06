from flask import Flask, request, jsonify
import os
import sys # Import sys for path manipulation
import importlib # For lazy import
import traceback # For printing full tracebacks

# Initialize the Flask application
app = Flask(__name__)

# --- Global variable to hold tcg_service module and initialization status ---
_tcg_service_module = None
_tcg_service_initialized = False

def initialize_tcg_service():
    """
    Imports and initializes the tcg_service module.
    This function will be called on the first request to ensure the app is fully up.
    """
    global _tcg_service_module
    global _tcg_service_initialized

    if not _tcg_service_initialized:
        print("INFO: Attempting to LAZY IMPORT and INITIALIZE tcg_service...")
        try:
            # Add current directory to sys.path to allow importing tcg_service
            # This is important for Heroku where current dir might not be in path
            if os.getcwd() not in sys.path:
                sys.path.insert(0, os.getcwd())
                print(f"DEBUG: Added {os.getcwd()} to sys.path.")

            # Import tcg_service only when needed
            _tcg_service_module = importlib.import_module('tcg_service')
            print("INFO: tcg_service module imported successfully.")

            api_key = os.environ.get('POKEMONTCG_API_KEY')
            _tcg_service_module.set_sdk_api_key(api_key) # Pass API key to the service module
            
            _tcg_service_initialized = True
            print("INFO: tcg_service initialization complete.")
        except Exception as e:
            print(f"CRITICAL ERROR: Exception during tcg_service import or initialization: {str(e)}")
            traceback.print_exc() # Print full traceback for this critical error
            _tcg_service_initialized = False # Mark as not initialized on failure
            _tcg_service_module = None # Ensure it's None if init failed
            raise # Re-raise the exception to indicate a critical failure
    else:
        print("INFO: tcg_service already initialized for this worker.")


@app.before_request
def before_any_request():
    """
    Ensures tcg_service is initialized before handling any request.
    This runs once per worker process.
    """
    try:
        initialize_tcg_service()
        print("INFO: before_request hook executed. tcg_service check complete.")
    except Exception as e:
        print(f"CRITICAL ERROR: Exception in before_request hook during tcg_service initialization: {str(e)}")
        # If service init fails, we cannot proceed. Return a 500 error.
        return jsonify({
            "status": "server_error",
            "message": f"Critical server error: Service initialization failed. Please check server logs. Error: {str(e)}"
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

    try:
        paginated_response = _tcg_service_module.get_cards_service(query_params, page, limit)

        if not paginated_response['data'] and query_params:
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
        card_data = _tcg_service_module.get_card_by_id_service(card_id)
        if not card_data:
            return jsonify({
                "status": "not_found",
                "card_id": card_id,
                "message": f"No Pokémon card found with ID '{card_id}'."
            }), 404
        return jsonify({
            "status": "success",
            "card": card_data
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /cards/<id>: {str(e)}")
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
        return jsonify({"status": "error", "message": "Missing 'card_name' query parameter."}), 400

    try:
        card_data, status_type, price_data = _tcg_service_module.get_card_price_service(card_name)

        if status_type == "not_found":
            return jsonify({
                "status": "not_found",
                "card_name": card_name,
                "message": f"No Pokémon card found with the name '{card_name}'."
            }), 404
        elif status_type == "no_price_data":
            return jsonify({
                "status": "no_price_data",
                "card_name": card_data.get('name'),
                "card_id": card_data.get('id'),
                "card_image": card_data.get('images', {}).get('small'),
                "message": f"No TCGPlayer price data available for '{card_data.get('name')}'."
            }), 200
        else: # success
            return jsonify({
                "status": "success",
                "card_name": card_data.get('name'),
                "card_id": card_data.get('id'),
                "set_name": card_data.get('set', {}).get('name'),
                "rarity": card_data.get('rarity'),
                "card_image": card_data.get('images', {}).get('small'),
                "prices": price_data,
                "message": f"Price data retrieved for '{card_data.get('name')}'."
            }), 200

    except Exception as e:
        print(f"ERROR: An error occurred in /card_price: {str(e)}")
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

    if limit <= 0:
        return jsonify({"status": "error", "message": "Page and limit must be positive integers."}), 400
    if page <= 0:
        return jsonify({"status": "error", "message": "Page and limit must be positive integers."}), 400

    try:
        paginated_response = _tcg_service_module.get_sets_service(set_name, page, limit)

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
        set_data = _tcg_service_module.get_set_by_id_service(set_id)
        if not set_data:
            return jsonify({
                "status": "not_found",
                "set_id": set_id,
                "message": f"No Pokémon set found with ID '{set_id}'."
            }), 404
        return jsonify({
            "status": "success",
            "set": set_data
        }), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /sets/<id>: {str(e)}")
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
        types = _tcg_service_module.get_types_service()
        return jsonify({"status": "success", "types": types}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /types: {str(e)}")
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
        supertypes = _tcg_service_module.get_supertypes_service()
        return jsonify({"status": "success", "supertypes": supertypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /supertypes: {str(e)}")
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
        subtypes = _tcg_service_module.get_subtypes_service()
        return jsonify({"status": "success", "subtypes": subtypes}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /subtypes: {str(e)}")
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
        rarities = _tcg_service_module.get_rarities_service()
        return jsonify({"status": "success", "rarities": rarities}), 200
    except Exception as e:
        print(f"ERROR: An error occurred in /rarities: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "status": "server_error",
            "message": f"An error occurred: {str(e)}"
        }), 500

# This block is for local development only and is NOT executed by Gunicorn on Heroku.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)