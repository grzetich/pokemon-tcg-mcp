# Pokémon TCG MCP Server
This repository contains a lightweight Model Context Protocol (MCP) server built with Flask and the pokemon-tcgsdk-python library. It exposes the full functionality of the Pokémon TCG API (pokemontcg.io) as a set of accessible HTTP endpoints, designed to be easily consumed by LLM (Large Language Model) clients, custom applications, or other services requiring Pokémon TCG data.

## Features
* Comprehensive Card Data: Retrieve detailed information for individual Pokémon cards or search for cards based on various criteria (name, set, type, rarity).
* Real-time Pricing: Fetch current TCGPlayer market prices for specific cards.
* Set Information: Access details about Pokémon TCG sets.
* Categorical Data: Query lists of all available card types, supertypes, subtypes, and rarities.
* Pagination: Supports pagination for list endpoints (/cards, /sets) to manage large datasets.
* RESTful API: Standard HTTP methods (GET) and JSON responses.
* Production-Ready Deployment: Configured for easy deployment to Heroku using Gunicorn.

## API Endpoints
The server exposes the following main endpoints:
* /GET: Home route, returns a welcome message.
* /cardsGET: Search for cards.Query Parameters: name, set, type, rarity (e.g., /cards?name=Pikachu&set=Base&limit=10&page=1)
* /cards/<string:card_id>GET: Get a specific card by its ID (e.g., /cards/base1-4)
* /card_priceGET: Get the TCGPlayer market price for a card by name (e.g., /card_price?card_name=Charizard)
* /setsGET: Get all sets, or search by name.Query Parameters: name (e.g., /sets?name=Base)/sets/<string:set_id>GET: Get a specific set by its ID (e.g., /sets/base1)
* /typesGET: Get all card types.
* /supertypesGET: Get all card supertypes.
* /subtypesGET: Get all card subtypes.
* /raritiesGET: Get all card rarities.

## Contributing
Contributions are welcome! If you have suggestions for improvements, bug fixes, or new features, please open an issue or submit a pull request.

## License
This project is open source and available under the MIT License.
