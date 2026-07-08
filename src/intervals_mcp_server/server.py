"""
Intervals.icu MCP Server

This module implements a Model Context Protocol (MCP) server for connecting
Claude with the Intervals.icu API. It provides tools for retrieving and managing
athlete data, including activities, events, workouts, and wellness metrics.

Main Features:
    - Activity retrieval and detailed analysis
    - Event management (races, workouts, calendar items)
    - Wellness data tracking and visualization
    - Error handling with user-friendly messages
    - Configurable parameters with environment variable support

Usage:
    This server is designed to be run as a standalone script and exposes several MCP tools
    for use with Claude Desktop or other MCP-compatible clients. The server loads configuration
    from environment variables (optionally via a .env file) and communicates with the Intervals.icu API.

    To run the server:
        $ python src/intervals_mcp_server/server.py

    MCP tools provided:
        - get_activities
        - get_activity_details
        - get_activity_intervals
        - get_activity_streams
        - get_activity_messages
        - add_activity_message
        - get_events
        - get_event_by_id
        - add_or_update_event
        - delete_event
        - delete_events_by_date_range
        - get_wellness_data
        - get_athlete_power_curves
        - get_custom_items
        - get_custom_item_by_id
        - create_custom_item
        - update_custom_item
        - delete_custom_item

    See the README for more details on configuration and usage.
"""

import logging

# Import API client and configuration
from intervals_mcp_server.api.client import (
    httpx_client,  # Re-export for backward compatibility with tests
    make_intervals_request,
)
from intervals_mcp_server.config import get_config
from intervals_mcp_server.mcp_instance import mcp

# Import types and validation
from intervals_mcp_server.server_setup import setup_transport, start_server
from intervals_mcp_server.utils.validation import validate_athlete_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("intervals_icu_mcp_server")

# Get configuration instance
config = get_config()

# Import tool modules to register them (tools register themselves via @mcp.tool() decorators)
# Import tool functions for re-export
from intervals_mcp_server.tools.activities import (  # pylint: disable=wrong-import-position  # noqa: E402
    add_activity_message,
    get_activities,
    get_activity_details,
    get_activity_intervals,
    get_activity_messages,
    get_activity_streams,
)
from intervals_mcp_server.tools.events import (  # pylint: disable=wrong-import-position  # noqa: E402
    add_or_update_event,
    delete_event,
    delete_events_by_date_range,
    get_event_by_id,
    get_events,
)
from intervals_mcp_server.tools.gear import get_gear_list  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.wellness import get_wellness_data  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.power_curves import get_athlete_power_curves  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.custom_items import (  # pylint: disable=wrong-import-position  # noqa: E402
    create_custom_item,
    delete_custom_item,
    get_custom_item_by_id,
    get_custom_items,
    update_custom_item,
)

# Re-export make_intervals_request and httpx_client for backward compatibility
# pylint: disable=duplicate-code  # This __all__ list is intentionally similar to tools/__init__.py
__all__ = [
    "make_intervals_request",
    "httpx_client",  # Re-exported for test compatibility
    "add_activity_message",
    "get_activities",
    "get_activity_details",
    "get_activity_intervals",
    "get_activity_messages",
    "get_activity_streams",
    "get_events",
    "get_event_by_id",
    "delete_event",
    "delete_events_by_date_range",
    "add_or_update_event",
    "get_wellness_data",
    "get_athlete_power_curves",
    "get_custom_items",
    "get_custom_item_by_id",
    "create_custom_item",
    "update_custom_item",
    "delete_custom_item",
]


# Run the server
#if __name__ == "__main__":
#    # Validate ATHLETE_ID when server starts (not at import time to allow tests)
#    validate_athlete_id(config.athlete_id)
#
#    # Setup transport and start server
#    selected_transport = setup_transport()
#    start_server(mcp, selected_transport)

# von Gemini
import os
from fastapi import FastAPI
from mcp.server.sse import SseServerTransport

# 1. Erstelle die FastAPI-App
app = FastAPI(title="Intervals.icu MCP Server Remote")

# 2. Initialisiere den SSE-Transport von MCP
sse_transport = SseServerTransport("/messages")

# 3. Definiere die Web-Routen für Claude Desktop
@app.get("/sse")
async def handle_sse():
    async with sse_transport.connect_consumers() as queue:
        # Öffnet den permanenten Event-Stream zu Claude
        return await sse_transport.handle_sse_request(queue)

@app.post("/messages")
async def handle_messages():
    # Verarbeitet die Nachrichten (Tool-Aufrufe), die von Claude gesendet werden
    return await sse_transport.handle_post_request()

# Run the server
if __name__ == "__main__":
    # Validate ATHLETE_ID when server starts
    validate_athlete_id(config.athlete_id)

    # Hier wechseln wir von stdio auf den Uvicorn Webserver für Railway
    import uvicorn
    
    # Railway übergibt den Port dynamisch über diese Umgebungsvariable
    port = int(os.environ.get("PORT", 8000))
    
    logger.info(f"Starte Remote-Mcp-Server auf Port {port} via SSE...")
    uvicorn.run(app, host="0.0.0.0", port=port)
