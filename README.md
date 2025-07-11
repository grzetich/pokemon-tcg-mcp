# Pokémon TCG Model Context Protocol (MCP) Server
This repository contains a lightweight Model Context Protocol (MCP) server built with Python Flask. It exposes the full functionality of the Pokémon TCG API (pokemontcg.io) as a set of accessible HTTP endpoints, designed to be easily consumed by LLM (Large Language Model) clients (via an orchestrator), custom applications, or other services requiring Pokémon TCG data.
## Features
* Comprehensive Card Data: Retrieve detailed information for individual Pokémon cards or search for cards based on various criteria (name, set, type, rarity).Real-time 
* Pricing: Fetch current TCGPlayer market prices for specific cards.
* Set Information: Access details about Pokémon TCG sets.
* Categorical Data: Query lists of all available card types, supertypes, subtypes, and rarities.
* Pagination: Supports pagination for list endpoints (/cards, /sets) to manage large datasets.
* RESTful API: Standard HTTP methods (GET) and JSON responses.
* Lazy SDK Initialization: The pokemontcgsdk is now lazily imported and initialized on the first request, optimizing startup time and resource usage.
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

## Integration (Orchestrator)
This server is designed to work in conjunction with a separate orchestrator script (like orchestrator_app.py in a companion repository) that handles the Model Context Protocol (MCP) communication with LLM clients (e.g., Claude). The orchestrator acts as a local proxy, translating LLM tool calls into HTTP requests to this deployed server.

## Contributing
Contributions are welcome! If you have suggestions for improvements, bug fixes, or new features, please open an issue or submit a pull request.

## License
This project is open source and available under the MIT License.