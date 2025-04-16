"""MCP server implementation for the Lean Docker MCP."""

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, cast

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import AnyUrl

from .config import Configuration, load_config
from .docker_manager import DockerExecutionError, DockerManager, LeanCompilationError, LeanValidationError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lean-docker-mcp")

# Initialize the configuration
config = load_config()

# Initialize the Docker manager
docker_manager = DockerManager(config)

# Store sessions for persistent code execution environments
sessions = {}

# Create the MCP server
server = Server("lean-docker-mcp")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available resources.

    Currently there are no resources to list.
    """
    return []


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """Read a specific resource by its URI.

    Currently there are no resources to read.
    """
    raise ValueError(f"Unsupported resource URI: {uri}")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """List available prompts.

    Currently there are no prompts defined.
    """
    return []


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
    """Generate a prompt.

    Currently there are no prompts defined.
    """
    raise ValueError(f"Unknown prompt: {name}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools that can be called by clients."""
    logger.info("Listing tools")
    return [
        types.Tool(
            name="execute-lean",
            description="Execute Lean4 code in a transient Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Lean4 code to execute"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="execute-lean-persistent",
            description="Execute Lean4 code in a persistent Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Lean4 code to execute"},
                    "session_id": {"type": "string", "description": "Session identifier"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="cleanup-session",
            description="Clean up a persistent session and its resources",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session identifier"},
                },
                "required": ["session_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests for Lean4 code execution."""
    logger.info(f"Calling tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    try:
        if name == "execute-lean":
            code = arguments.get("code")

            if not code:
                raise ValueError("Missing code")

            result = await docker_manager.execute_transient(code)

            # Format text result
            formatted_text = _format_execution_result(result)

            return [types.TextContent(type="text", text=formatted_text)]

        elif name == "execute-lean-persistent":
            code = arguments.get("code")
            session_id = arguments.get("session_id")

            if not code:
                raise ValueError("Missing code")

            # Create a new session if not provided
            if not session_id:
                session_id = str(uuid.uuid4())
                sessions[session_id] = {"created_at": asyncio.get_event_loop().time()}

            result = await docker_manager.execute_persistent(session_id, code)

            # Format text result
            formatted_text = _format_execution_result(result, session_id)

            return [types.TextContent(type="text", text=formatted_text)]

        elif name == "cleanup-session":
            session_id = arguments.get("session_id")

            if not session_id:
                raise ValueError("Missing session ID")

            result = await docker_manager.cleanup_session(session_id)

            if session_id in sessions:
                del sessions[session_id]

            return [
                types.TextContent(
                    type="text",
                    text=f"Session {session_id} cleaned up successfully: {result['message']}",
                )
            ]

        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return a properly formatted error response
        error_message = f"Error executing {name}: {str(e)}"
        return [types.TextContent(type="text", text=error_message)]


def _format_execution_result(result: Dict[str, Any], session_id: Optional[str] = None) -> str:
    """Format execution result for display."""
    # Extract relevant information from the result
    stdout = result.get("stdout", "")
    error = result.get("error", "")
    status = result.get("status", "")
    exit_code = result.get("exit_code", -1)

    # Build the response text
    session_text = f"Session ID: {session_id}\n\n" if session_id else ""
    status_text = f"Status: {status}\n"
    exit_code_text = f"Exit Code: {exit_code}\n\n" if exit_code is not None else ""
    
    output_text = f"Output:\n{stdout}" if stdout else "No output"
    
    error_text = f"\n\nError: {error}" if error else ""
    
    return f"{session_text}{status_text}{exit_code_text}{output_text}{error_text}"


async def main() -> None:
    """Start the MCP server."""
    # Configure logging based on debug flag from command line or environment
    debug_mode = "--debug" in sys.argv or os.environ.get("LEAN_DOCKER_MCP_DEBUG", "").lower() in ["true", "1", "yes"]
    
    if debug_mode:
        logging.basicConfig(level=logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    else:
        # Set info level logging by default for better diagnostics
        logging.basicConfig(level=logging.INFO)
    
    # Initialize the container pool if enabled
    if config.docker.pool_enabled:
        logger.info("Initializing container pool")
        try:
            await docker_manager.initialize_pool()
        except Exception as e:
            logger.error(f"Error initializing container pool: {e}")
            # Don't disable pooling, just log the error and continue
            # The system will fall back to creating containers on demand
    
    # Run the server using stdin/stdout streams
    logger.info("Starting MCP server using stdio transport")
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("stdio server initialized, running MCP server")
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="lean-docker-mcp",
                    server_version="0.2.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        logger.error(f"Error running MCP server: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    finally:
        # Clean up any remaining sessions when the server shuts down
        logger.info("Cleaning up sessions")
        for session_id in list(sessions.keys()):
            try:
                await docker_manager.cleanup_session(session_id)
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}")
        
        # Don't attempt pool cleanup for now
        logger.info("Server shutdown complete")


# If this module is run directly, start the server
if __name__ == "__main__":
    asyncio.run(main()) 