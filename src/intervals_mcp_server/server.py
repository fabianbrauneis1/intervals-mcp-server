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

# von Claude
import os
import time
import secrets
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(title="Intervals.icu MCP Server Remote")

# ---- In-memory "Datenbank" für den OAuth-Stub ----
# Reicht für Single-User-Betrieb völlig aus
_clients: dict[str, dict] = {}
_auth_codes: dict[str, dict] = {}
_tokens: set[str] = set()

BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://intervals-mcp-server-production-d65b.up.railway.app")


@app.get("/health")
async def health():
    return {"status": "ok", "message": "Intervals.icu MCP Server is running"}


# 1. Claude fragt hier nach, wie die Anmeldung funktioniert
@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata():
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/token",
        "registration_endpoint": f"{BASE_URL}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
    })


@app.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    return JSONResponse({
        "resource": BASE_URL,
        "authorization_servers": [BASE_URL],
    })


# 2. Claude registriert sich selbst als Client
@app.post("/register")
async def register(request: Request):
    body = await request.json()
    client_id = secrets.token_hex(16)
    _clients[client_id] = {
        "redirect_uris": body.get("redirect_uris", []),
        "client_name": body.get("client_name", "claude"),
    }
    return JSONResponse({
        "client_id": client_id,
        "redirect_uris": body.get("redirect_uris", []),
        "client_name": body.get("client_name", "claude"),
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
    })


# 3. "Login"-Schritt - hier winken wir automatisch durch, da nur du der Nutzer bist
@app.get("/authorize")
async def authorize(
    client_id: str,
    redirect_uri: str,
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
):
    code = secrets.token_hex(16)
    _auth_codes[code] = {
        "client_id": client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "created": time.time(),
    }
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}")


# 4. Claude tauscht den Code gegen ein Access Token
@app.post("/token")
async def token(request: Request):
    form = await request.form()
    code = form.get("code")
    entry = _auth_codes.pop(code, None)
    if entry is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    access_token = secrets.token_hex(32)
    _tokens.add(access_token)
    return JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 31536000,  # 1 Jahr, damit du nicht ständig neu verbinden musst
    })


# MCP-Traffic selbst - FastMCP übernimmt SSE korrekt
app.mount("/", mcp.sse_app())


if __name__ == "__main__":
    validate_athlete_id(config.athlete_id)
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starte Remote-MCP-Server auf Port {port} via SSE...")
    uvicorn.run(app, host="0.0.0.0", port=port)
