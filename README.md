# Pokémon TCG Model Context Protocol (MCP) Server

A lightweight [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the [Pokémon TCG API](https://pokemontcg.io) (pokemontcg.io) as a set of tools for LLM clients such as Claude Desktop. It runs as a single local process: the client launches it over stdio, and each tool is a thin wrapper that calls the public Pokémon TCG API directly. **There is no hosted backend to deploy or maintain.**

For the full tool reference, see the [**API Reference**](https://grzetich.github.io/pokemon-tcg-mcp/).

## Data Flow

![Data Flow Diagram](docs/pokemon-tcg-mcp-flow.png)

```
LLM client  ──(MCP / stdio)──▶  server.py  ──(HTTPS)──▶  api.pokemontcg.io
```

The client and the server speak MCP over stdin/stdout. `server.py` translates each tool call into a single HTTPS request to `api.pokemontcg.io/v2` and passes the JSON response straight back. No intermediate web service is involved.

---

## Features

* **Comprehensive card data** — search by name, set, type, rarity, subtype, or supertype, or fetch a single card by ID.
* **Real-time pricing** — current TCGPlayer market prices for a card by name.
* **Set information** — list or search sets, or fetch a single set by ID.
* **Categorical data** — list all types, supertypes, subtypes, and rarities.
* **Smart suggestions** — a search that matches nothing returns "Did you mean …?" suggestions for misspelled set/type/rarity/subtype/supertype values.
* **Pagination** — `page` and `limit` arguments on the search tools.

### Tools

| Tool | Description |
| --- | --- |
| `search_cards` | Search cards by `name`, `set_name`, `type`, `rarity`, `subtype`, `supertype`, `page`, `limit`. |
| `get_card_by_id` | Get one card by ID (e.g. `base1-4`). |
| `get_card_price` | Get TCGPlayer market prices for a card by name. |
| `search_sets` | List or search sets by `name`, with pagination. |
| `get_set_by_id` | Get one set by ID (e.g. `base1`). |
| `get_types` | List all card energy types. |
| `get_supertypes` | List all card supertypes. |
| `get_subtypes` | List all card subtypes. |
| `get_rarities` | List all card rarities. |

## Installation

1. Clone or download this repository.
2. Install the dependencies (a virtual environment is recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. (Recommended) Set your own Pokémon TCG API key to raise the rate limits. Get one free at the [Pokémon TCG Developer Portal](https://dev.pokemontcg.io/), then either export it or put it in a `.env` file next to `server.py`:

   ```bash
   export POKEMONTCG_API_KEY=your-key-here
   ```

   The server works without a key on the public, lower-rate tier.

4. Register the server with your MCP client. For most clients, add the following to the client's MCP configuration (the contents of [`mcp.json`](mcp.json)), using the **full path** to `server.py` and to the Python interpreter from your virtual environment:

   ```json
   {
       "mcpServers": {
           "pokemon-tcg-mcp": {
               "command": "/full/path/to/.venv/bin/python",
               "args": ["/full/path/to/server.py"]
           }
       }
   }
   ```

That's it — the client starts `server.py` on demand. There is nothing to host.

## Running locally

To exercise the server outside a client (sanity check):

```bash
python server.py
```

It will wait for MCP messages on stdin. In normal use you don't run it by hand — the MCP client launches it for you.

## Contributing

Contributions are welcome. Please open an issue or submit a pull request.

## License

Open source under the MIT License.
