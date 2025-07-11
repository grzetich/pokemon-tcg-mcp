import requests
import json
import os
import sys
import time

# --- Configuration ---
# IMPORTANT: Replace this with the actual URL of your deployed Render MCP server.
APP_URL = "https://pocket-monster-tcg-mcp.onrender.com/"

# --- Message Framing Functions (for Model Context Protocol) ---

def read_message(stream):
    """Reads a single message from the input stream, handling Content-Length headers."""
    headers = {}
    # Read headers line by line, decoding each to string
    while True:
        line_bytes = stream.readline()
        if not line_bytes: # EOF
            return None
        line = line_bytes.decode('utf-8').strip()
        if not line: # Empty line signifies end of headers
            break
        key, value = line.split(':', 1)
        headers[key.strip()] = value.strip()

    content_length = int(headers.get('Content-Length', 0))
    if content_length == 0:
        return None # No content to read

    content_bytes = stream.read(content_length)
    return json.loads(content_bytes.decode('utf-8')) # Decode content bytes before JSON parsing

def write_message(stream, message):
    """Writes a single message to the output stream with Content-Length headers."""
    json_payload = json.dumps(message)
    json_payload_bytes = json_payload.encode('utf-8') # Encode payload to bytes
    content_length = len(json_payload_bytes)

    stream.write(f"Content-Length: {content_length}\r\n".encode('utf-8'))
    stream.write("Content-Type: application/json\r\n".encode('utf-8'))
    stream.write("\r\n".encode('utf-8')) # End of headers
    stream.write(json_payload_bytes)
    stream.flush()

# --- LLM Tool Definitions (Generic JSON Schema-like structure) ---
# These definitions describe your MCP server's endpoints to an external LLM client.
# The LLM client would use these to understand when and how to generate tool calls.

TOOLS = [
    {
        "name": "get_pokemon_card_price",
        "description": "Fetches the current market price and details for a specific Pokémon TCG card by its name. Use this tool when a user asks for a card's price.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_name": {
                    "type": "string",
                    "description": "The full name of the Pokémon card to look up (e.g., 'Charizard', 'Pikachu VMAX')."
                }
            },
            "required": ["card_name"]
        }
    },
    {
        "name": "search_pokemon_cards",
        "description": "Searches for Pokémon TCG cards based on various criteria such as name, set, type, or rarity. Supports pagination. Use this when a user asks to find cards by specific attributes.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": { "type": "string", "description": "The full or partial name of the Pokémon card." },
                "set": { "type": "string", "description": "The name of the set the card belongs to." },
                "type": { "type": "string", "description": "The card's type (e.g., 'Grass', 'Fire', 'Water')." },
                "rarity": { "type": "string", "description": "The card's rarity (e.g., 'Common', 'Rare Holo')." },
                "page": { "type": "integer", "description": "The page number for results (defaults to 1)." },
                "limit": { "type": "integer", "description": "The number of results per page (defaults to 20)." }
            }
        }
    },
    {
        "name": "get_pokemon_sets",
        "description": "Retrieves a list of all Pokémon TCG sets, with optional filtering by name. Use this when a user asks about Pokémon card sets.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": { "type": "string", "description": "The name of the set to search for." },
                "page": { "type": "integer", "description": "The page number for results (defaults to 1)."},
                "limit": { "type": "integer", "description": "The number of results per page (defaults to 20)."}
            }
        }
    },
    {
        "name": "get_pokemon_card_types",
        "description": "Retrieves a list of all available Pokémon TCG card types (e.g., 'Grass', 'Fire'). Use this when a user asks about card types.",
        "parameters": { "type": "object", "properties": {} } # No parameters
    },
    {
        "name": "get_pokemon_card_rarities",
        "description": "Retrieves a list of all available Pokémon TCG card rarities (e.g., 'Common', 'Rare Holo'). Use this when a user asks about card rarities.",
        "parameters": { "type": "object", "properties": {} } # No parameters
    },
    {
        "name": "get_pokemon_card_supertypes",
        "description": "Retrieves a list of all available Pokémon TCG card supertypes (e.g., 'Pokémon', 'Trainer'). Use this when a user asks about card supertypes.",
        "parameters": { "type": "object", "properties": {} } # No parameters
    },
    {
        "name": "get_pokemon_card_subtypes",
        "description": "Retrieves a list of all available Pokémon TCG card subtypes (e.g., 'Basic', 'V', 'EX'). Use this when a user asks about card subtypes.",
        "parameters": { "type": "object", "properties": {} } # No parameters
    },
    {
        "name": "get_pokemon_card_by_id",
        "description": "Retrieves a specific Pokémon TCG card by its unique ID. Use this when a user asks for a card by its exact ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {
                    "type": "string",
                    "description": "The unique ID of the Pokémon card (e.g., 'base1-4')."
                }
            },
            "required": ["card_id"]
        }
    },
    {
        "name": "get_pokemon_set_by_id",
        "description": "Retrieves a specific Pokémon TCG set by its unique ID. Use this when a user asks for a set by its exact ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "set_id": {
                    "type": "string",
                    "description": "The unique ID of the Pokémon set (e.g., 'base1')."
                }
            },
            "required": ["set_id"]
        }
    }
]

# --- Function to Execute Tool Calls (Makes HTTP requests to your MCP Server) ---
def execute_tool_call(tool_name: str, **kwargs) -> dict:
    """
    Executes a tool call by making an HTTP request to the Pokémon TCG MCP Server.
    This function acts as the bridge between the LLM's tool request and your server.
    """
    endpoint = ""
    params = kwargs

    # Map tool_name to the correct MCP server endpoint
    if tool_name == "get_pokemon_card_price":
        endpoint = "/card_price"
    elif tool_name == "search_pokemon_cards":
        endpoint = "/cards"
    elif tool_name == "get_pokemon_card_by_id":
        card_id = kwargs.pop("card_id")
        endpoint = f"/cards/{card_id}"
        params = {}
    elif tool_name == "get_pokemon_sets":
        endpoint = "/sets"
    elif tool_name == "get_pokemon_set_by_id":
        set_id = kwargs.pop("set_id")
        endpoint = f"/sets/{set_id}"
        params = {}
    elif tool_name == "get_pokemon_card_types":
        endpoint = "/types"
        params = {}
    elif tool_name == "get_pokemon_card_supertypes":
        endpoint = "/supertypes"
        params = {}
    elif tool_name == "get_pokemon_card_subtypes":
        endpoint = "/subtypes"
        params = {}
    elif tool_name == "get_pokemon_card_rarities":
        endpoint = "/rarities"
        params = {}
    else:
        # This case should ideally not be reached if LLM uses defined tools
        # But if it does, it's an unrecognized method, return an error that can be wrapped
        return {"status": "error", "message": f"Tool '{tool_name}' not recognized by orchestrator."}

    try:
        full_url = f"{APP_URL}{endpoint}"
        response = requests.get(full_url, params=params, timeout=15)
        response.raise_for_status()
        return {"status": "success", "data": response.json()}
    except requests.exceptions.Timeout:
        return {"status": "server_error", "message": f"Failed to connect to MCP server: Request timed out after 15 seconds."}
    except requests.exceptions.RequestException as e:
        return {"status": "server_error", "message": f"Failed to connect to MCP server or request failed: {e}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON response from MCP server."}

# --- Main Orchestrator Logic (Handles continuous tool execution) ---
def main():
    # --- WAKE-UP CALL TO RENDER BACKEND (Non-blocking for Claude's interaction) ---
    try:
        wake_up_response = requests.get(APP_URL, timeout=15)
        wake_up_response.raise_for_status()
        # Removed time.sleep(2) here to ensure orchestrator is immediately responsive to Claude
    except requests.exceptions.Timeout:
        pass
    except requests.exceptions.RequestException as e:
        pass
    # --- END WAKE-UP CALL ---

    # Set stdin/stdout to binary mode for consistent byte reading/writing
    sys.stdin = sys.stdin.buffer
    sys.stdout = sys.stdout.buffer

    # Main loop to continuously read and execute tool calls
    while True:
        try:
            request_obj = read_message(sys.stdin)
            if request_obj is None: # No content or EOF
                break

            jsonrpc_version = request_obj.get("jsonrpc")
            request_id = request_obj.get("id") # Can be None for notifications
            method_name = request_obj.get("method")
            params = request_obj.get("params", {})

            # Initialize response object only if it's a request (has an ID)
            response_obj = None
            if request_id is not None:
                response_obj = {
                    "jsonrpc": "2.0",
                    "id": request_id
                }

            # Handle JSON-RPC version check
            if jsonrpc_version != "2.0":
                if response_obj: # Only send error if it was a request
                    response_obj["error"] = {"code": -32600, "message": "Invalid JSON-RPC version. Expected '2.0'."}
            # Handle specific JSON-RPC methods (requests or notifications)
            elif method_name == "initialize":
                if response_obj: # Initialize is a request, so it needs a response
                    response_obj["result"] = {
                        "capabilities": {}, # Minimal capabilities
                        "serverInfo": {
                            "name": "Pokémon TCG MCP Orchestrator",
                            "version": "1.0.0"
                        }
                    }
            elif method_name == "initialized":
                # This is a notification from the client after initialization. No response needed.
                pass
            elif method_name == "shutdown":
                # This is a request to prepare for shutdown. Respond, then break.
                if response_obj:
                    response_obj["result"] = None
                write_message(sys.stdout, response_obj) # Write response before breaking
                break # Exit the loop after responding to shutdown
            elif method_name == "exit":
                # This is a notification to exit. No response needed, just break.
                break
            elif method_name is None:
                if response_obj: # Only send error if it was a request
                    response_obj["error"] = {"code": -32600, "message": "Invalid Request: 'method' is required."}
            # Handle all other methods (tool calls or unrecognized notifications)
            else:
                # If it's a request (has an ID), execute as a tool call and send response
                if request_id is not None:
                    tool_result = execute_tool_call(method_name, **params)
                    if tool_result.get("status") == "success":
                        response_obj["result"] = tool_result.get("data")
                    else:
                        response_obj["error"] = {
                            "code": -32000, # Generic server error code
                            "message": tool_result.get("message", "An unknown error occurred."),
                            "data": {"status": tool_result.get("status")} # Include original status for context
                        }
                else:
                    # It's an unrecognized notification (no ID). Do NOT send a response.
                    # Just ignore it.
                    pass
            
            # Write response to stdout only if a response object was created (i.e., it was a request)
            if response_obj:
                write_message(sys.stdout, response_obj)

        except json.JSONDecodeError:
            # If the incoming message is not valid JSON, send a parse error
            error_response = {
                "jsonrpc": "2.0",
                "id": None, # For parse errors, id is often null
                "error": {"code": -32700, "message": "Parse error: Invalid JSON was received by the server."}
            }
            write_message(sys.stdout, error_response)
        except Exception as e:
            # Catch any other unexpected errors and send a generic JSON-RPC error
            # Try to use request_id if it was parsed from the current message, otherwise None
            current_request_id = request_id if 'request_id' in locals() else None
            error_response = {
                "jsonrpc": "2.0",
                "id": current_request_id,
                "error": {"code": -32000, "message": f"Server error: {str(e)}"}
            }
            write_message(sys.stdout, error_response)


if __name__ == "__main__":
    main()