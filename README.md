# Pokémon TCG Model Context Protocol (MCP) Server
This repository contains a lightweight Model Context Protocol (MCP) server built with Python Flask. It exposes the full functionality of the Pokémon TCG API (pokemontcg.io) as a set of accessible HTTP endpoints, designed to be easily consumed by LLM (Large Language Model) clients (via an orchestrator), custom applications, or other services requiring Pokémon TCG data.

For detailed information on all available endpoints, parameters, and response formats, please see the [**API Reference**](https://grzetich.github.io/pokemon-tcg-mcp/).

## Features
* Comprehensive Card Data: Retrieve detailed information for individual Pokémon cards or search for cards based on various criteria (name, set, type, rarity).Real-time 
* Pricing: Fetch current TCGPlayer market prices for specific cards.
* Set Information: Access details about Pokémon TCG sets.
* Categorical Data: Query lists of all available card types, supertypes, subtypes, and rarities.
* Pagination: Supports pagination for list endpoints (/cards, /sets) to manage large datasets.
* RESTful API: Standard HTTP methods (GET) and JSON responses.
<!-- * Lazy SDK Initialization: The pokemontcgsdk is now lazily imported and initialized on the first request, optimizing startup time and resource usage.-->
* API EndpointsThe server exposes the following main endpoints:
  * / (GET): Home route, returns a welcome message.
  * /cards (GET): Search for cards. Query Parameters: name, set, type, rarity, page, limit (for example, `/cards?name=Pikachu&set=Base&limit=10&page=1`)
  * /cards/<string:card_id> (GET): Get a specific card by its ID (for example, `/cards/base1-4`)
  * /card_price (GET): Get the TCGPlayer market price for a card by name (for example, `/card_price?card_name=Charizard`)
  * /sets (GET): Get all sets, or search by name. Query Parameters: name, page, limit (for example, `/sets?name=Base&limit=5`)
  * /sets/<string:set_id> (GET): Get a specific set by its ID (for example, `/sets/base1`)
  * /types (GET): Get all card types.
  * /supertypes (GET): Get all card supertypes.
  * /subtypes (GET): Get all card subtypes.
  * /rarities (GET): Get all card rarities.

## Integration and installation
This server is designed to work in conjunction with a local orchestrator script (orchestrator_app.py) that handles the Model Context Protocol (MCP) communication with LLM clients (like Claude). The orchestrator acts as a local proxy, translating LLM tool calls into HTTP requests to this deployed server.

### To install: 
1. Download the appropriate compressed file for your operating system ([install.tar.gz](https://github.com/grzetich/pokemon-tcg-mcp/blob/ebfe93e220bd6e7fbd2cfe0cb693e6b43a6e20da/install.tar.gz) or [install.zip](https://github.com/grzetich/pokemon-tcg-mcp/blob/ebfe93e220bd6e7fbd2cfe0cb693e6b43a6e20da/install.zip)) from this repository.
2. Extract *orchestrator_app.py* to your hard drive. Note the path to the file, you'll need it later.
3. Install the [**Requests**](https://pypi.org/project/requests/) Python library. It's required by *orchestrator_app.py*.
4. Depending on your configuration, extract *mcp.json* to an appropriate location. Or, copy the following lines and paste them into your configuration file.

```{
    "mcpServers": {
        "pokemon-tcg-mcp": {
            "command": "python",
            "args": ["orchestrator_app.py"]
        }
    }
}
```

**[Note]**
>>In the value for `args`, include the full path to *orchestrater_app.py* from step 2.

## Contributing
Contributions are welcome! If you have suggestions for improvements, bug fixes, or new features, please open an issue or submit a pull request.

## License
This project is open source and available under the MIT License.