import json
import logging
import os
import subprocess
import sys
import time
import requests

# --- Configuration ---
LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orchestrator.log')
APP_URL = "https://pocket-monster-tcg-mcp.onrender.com/"
REQUIRED_PACKAGES = ['requests']

# --- Setup Logging ---
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)

class StreamToLogger:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())
    def flush(self):
        pass

sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

# --- Dependency Check ---
def check_and_install_packages():
    logging.info("Checking for required packages...")
    try:
        for package in REQUIRED_PACKAGES:
            subprocess.check_call([sys.executable, "-m", "pip", "show", package], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("All required packages are installed.")
        return True
    except subprocess.CalledProcessError:
        logging.warning(f"Required packages are missing. Attempting to install from requirements.txt...")
        try:
            req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
            logging.info("Successfully installed packages from requirements.txt.")
            return True
        except Exception as e:
            logging.critical(f"Failed to install packages: {e}", exc_info=True)
            return False

# --- MCP Communication Functions ---
def read_message(stream):
    header_buffer = bytearray()
    while True:
        b = stream.read(1)
        if not b: return None
        header_buffer.extend(b)
        if header_buffer.endswith(b'\r\n\r\n'): break
    header_str = header_buffer.decode('utf-8')
    headers = {k.strip(): v.strip() for k, v in (line.split(':', 1) for line in header_str.strip().split('\r\n'))}
    content_length = int(headers.get('Content-Length', 0))
    if not content_length: return None
    content_bytes = stream.read(content_length)
    logging.info(f"Request from client: {content_bytes.decode('utf-8')}")
    return json.loads(content_bytes)

def write_message(stream, message):
    logging.info(f"Response to client: {json.dumps(message)}")
    payload_bytes = json.dumps(message).encode('utf-8')
    stream.write(f"Content-Length: {len(payload_bytes)}\r\n".encode('utf-8'))
    stream.write(b"Content-Type: application/json\r\n\r\n")
    stream.write(payload_bytes)
    stream.flush()

# --- Tool Execution ---
def execute_tool_call(tool_name, params):
    logging.info(f"Executing tool '{tool_name}' with params: {params}")
    
    # Simplified endpoint mapping
    endpoint = f"/{tool_name.replace('_', '-')}"
    if tool_name in ["get_pokemon_card_by_id", "get_pokemon_set_by_id"]:
        item_id = params.get('card_id') or params.get('set_id', '')
        endpoint = f"{endpoint}/{item_id}"
        
    url = f"{APP_URL}{endpoint}"
    
    try:
        logging.info(f"Making GET request to {url} with params {params}")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        # Defensive JSON parsing
        if 'application/json' not in response.headers.get('Content-Type', ''):
            logging.error(f"Response from server was not JSON. Content: {response.text[:200]}")
            return {"status": "error", "message": "The server returned a non-JSON response."}
            
        logging.info(f"Response from public server ({response.status_code})")
        return {"status": "success", "data": response.json()}

    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP Error from public server: {e.response.status_code} {e.response.text[:200]}", exc_info=True)
        return {"status": "error", "message": f"Server returned an error: {e.response.status_code}"}
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to public server failed: {e}", exc_info=True)
        return {"status": "error", "message": f"Could not connect to the public server: {e}"}
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from public server: {e}", exc_info=True)
        return {"status": "error", "message": "The server sent an invalid JSON response."}

# --- Main Loop ---
def main():
    logging.info("--- Orchestrator Starting ---")
    
    if not check_and_install_packages():
        logging.critical("Could not verify/install dependencies. Exiting.")
        return

    sys.stdin = sys.stdin.buffer
    sys.stdout = sys.stdout.buffer

    while True:
        try:
            request_obj = read_message(sys.stdin)
            if request_obj is None:
                logging.warning("Received no data from client, exiting loop.")
                break

            method = request_obj.get("method")
            params = request_obj.get("params", {})
            req_id = request_obj.get("id")
            
            response = {"jsonrpc": "2.0", "id": req_id}

            if method == 'initialize':
                response['result'] = {"capabilities": {}, "serverInfo": {"name": "Hardened Pokémon TCG Orchestrator"}}
            elif method == 'shutdown':
                response['result'] = None
                write_message(sys.stdout, response)
                break
            else:
                result = execute_tool_call(method, params)
                if result['status'] == 'success':
                    response['result'] = result['data']
                else:
                    response['error'] = {"code": -32000, "message": result['message']}
            
            write_message(sys.stdout, response)
        except Exception as e:
            logging.critical(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            # Attempt to send an error response if possible
            if 'req_id' in locals():
                error_response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": f"Internal error: {e}"}}
                write_message(sys.stdout, error_response)
            break # Exit the loop on unhandled errors

if __name__ == "__main__":
    try:
        main()
    finally:
        logging.info("--- Orchestrator Shutting Down ---")