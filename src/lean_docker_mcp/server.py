"""MCP server implementation for the Lean Docker MCP."""

import asyncio
import json
import logging
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from .config import Configuration, load_config
from .docker_manager import DockerExecutionError, DockerManager, LeanCompilationError, LeanValidationError

# Set up logging
logger = logging.getLogger(__name__)


class JsonRpcError(Exception):
    """JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        """Initialize the error.

        Args:
            code: The error code
            message: The error message
            data: Optional additional data
        """
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class Server:
    """MCP JSON-RPC server."""

    def __init__(self, config: Optional[Configuration] = None):
        """Initialize the server.

        Args:
            config: Optional configuration override
        """
        self.config = config or load_config()
        self.docker_manager = DockerManager(self.config)

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request.

        Args:
            request: The JSON-RPC request

        Returns:
            The JSON-RPC response
        """
        # Extract request information
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        logger.debug(f"Received request: {request}")

        # Prepare response structure
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
        }

        try:
            # Validate the request
            if not isinstance(request_id, (str, int, type(None))):
                raise JsonRpcError(-32600, "Invalid request: id must be a string, number, or null")
            if not method:
                raise JsonRpcError(-32600, "Invalid request: method is required")
            if not isinstance(params, dict):
                raise JsonRpcError(-32602, "Invalid params: params must be an object")

            # Dispatch the method
            if method == "execute-lean":
                result = await self._handle_execute_lean(params)
            elif method == "execute-lean-persistent":
                result = await self._handle_execute_lean_persistent(params)
            elif method == "cleanup-session":
                result = await self._handle_cleanup_session(params)
            else:
                raise JsonRpcError(-32601, f"Method not found: {method}")

            # Add the result to the response
            response["result"] = result

        except JsonRpcError as e:
            # Handle JSON-RPC errors
            response["error"] = {
                "code": e.code,
                "message": e.message,
            }
            if e.data:
                response["error"]["data"] = e.data
        except LeanValidationError as e:
            # Handle Lean validation errors
            response["error"] = {
                "code": -32001,
                "message": str(e),
                "data": {
                    "error_type": "validation_error"
                }
            }
        except LeanCompilationError as e:
            # Handle Lean compilation errors
            response["error"] = {
                "code": -32002,
                "message": str(e),
                "data": e.to_dict()
            }
        except DockerExecutionError as e:
            # Handle Docker execution errors
            response["error"] = {
                "code": -32000,
                "message": str(e),
            }
        except Exception as e:
            # Handle all other errors
            logger.exception(f"Unexpected error: {e}")
            response["error"] = {
                "code": -32603,
                "message": f"Internal error: {str(e)}",
            }

        return response

    async def _handle_execute_lean(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the execute-lean method.

        Args:
            params: The method parameters

        Returns:
            The result with stdout, error information, and status
        """
        # Validate parameters
        code = params.get("code")
        if not code:
            raise JsonRpcError(-32602, "Invalid params: code is required")
        if not isinstance(code, str):
            raise JsonRpcError(-32602, "Invalid params: code must be a string")

        # Execute the code in a transient container
        result = await self.docker_manager.execute_transient(code)
        return result

    async def _handle_execute_lean_persistent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the execute-lean-persistent method.

        Args:
            params: The method parameters

        Returns:
            The result with stdout, error information, status, and session ID
        """
        # Validate parameters
        code = params.get("code")
        if not code:
            raise JsonRpcError(-32602, "Invalid params: code is required")
        if not isinstance(code, str):
            raise JsonRpcError(-32602, "Invalid params: code must be a string")

        # Get or generate a session ID
        session_id = params.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())

        # Execute the code in a persistent container
        result = await self.docker_manager.execute_persistent(session_id, code)
        
        # Ensure the session ID is included in the result (should already be there)
        if "session_id" not in result:
            result["session_id"] = session_id
        
        return result

    async def _handle_cleanup_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the cleanup-session method.

        Args:
            params: The method parameters

        Returns:
            The result
        """
        # Validate parameters
        session_id = params.get("session_id")
        if not session_id:
            raise JsonRpcError(-32602, "Invalid params: session_id is required")
        if not isinstance(session_id, str):
            raise JsonRpcError(-32602, "Invalid params: session_id must be a string")

        # Clean up the session
        result = await self.docker_manager.cleanup_session(session_id)
        return result


async def read_request() -> Optional[Dict[str, Any]]:
    """Read a JSON-RPC request from stdin.

    Returns:
        The parsed request, or None if EOF is reached
    """
    try:
        # Read the Content-Length header
        content_length = None
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                return None  # EOF
            line = line.strip()
            if not line:
                break  # Empty line - end of headers
            if line.startswith("Content-Length: "):
                content_length = int(line[16:])

        if content_length is None:
            logger.error("Missing Content-Length header")
            return None

        # Read the request body
        request_body = await asyncio.get_event_loop().run_in_executor(
            None, lambda: sys.stdin.buffer.read(content_length).decode("utf-8")
        )
        if not request_body:
            return None  # EOF

        # Parse the request
        return json.loads(request_body)
    except Exception as e:
        logger.error(f"Error reading request: {e}")
        return None


async def write_response(response: Dict[str, Any]) -> None:
    """Write a JSON-RPC response to stdout.

    Args:
        response: The response to write
    """
    try:
        # Convert the response to JSON
        response_json = json.dumps(response)
        response_bytes = response_json.encode("utf-8")

        # Write the Content-Length header
        header = f"Content-Length: {len(response_bytes)}\r\n\r\n"
        sys.stdout.buffer.write(header.encode("utf-8"))

        # Write the response body
        sys.stdout.buffer.write(response_bytes)
        sys.stdout.buffer.flush()
    except Exception as e:
        logger.error(f"Error writing response: {e}")


async def main() -> None:
    """Start the MCP server."""
    # Initialize the server
    server = Server()

    try:
        # Process requests until EOF
        while True:
            request = await read_request()
            if request is None:
                break

            # Handle the request
            response = await server.handle_request(request)

            # Write the response
            await write_response(response)

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        sys.exit(1)


# If this module is run directly, start the server
if __name__ == "__main__":
    asyncio.run(main()) 