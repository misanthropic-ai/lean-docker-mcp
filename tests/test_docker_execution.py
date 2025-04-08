"""Test suite for Docker execution of Lean code."""

import asyncio
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from lean_docker_mcp.config import Configuration, DockerConfig, LeanConfig
from lean_docker_mcp.docker_manager import DockerManager
from lean_docker_mcp.server import Server


@pytest.fixture
def test_config():
    """Create a test configuration for Docker execution."""
    docker_config = DockerConfig(
        image="lean-docker-mcp:latest",
        working_dir="/home/leanuser/project",
        memory_limit="256m",
        cpu_limit=0.5,
        timeout=30,
        network_disabled=True,
    )
    
    lean_config = LeanConfig(
        allowed_imports=["Lean", "Init", "Std", "Mathlib"],
        blocked_imports=["System.IO.Process", "System.FilePath"],
    )
    
    return Configuration(docker=docker_config, lean=lean_config)


@pytest.fixture
def mock_container():
    """Create a mock Docker container."""
    container = MagicMock()
    container.id = "test-container-id"
    container.stop = MagicMock()
    container.remove = MagicMock()
    
    # Simple exec_run mock that will be customized in tests
    container.exec_run = MagicMock()
    return container


@pytest.fixture
def mock_docker_client(mock_container):
    """Create a mock Docker client."""
    client = MagicMock()
    client.containers = MagicMock()
    client.containers.get = MagicMock(return_value=mock_container)
    client.containers.run = MagicMock()  # Will be customized in tests
    return client


@pytest_asyncio.fixture
async def docker_manager(test_config, mock_docker_client):
    """Create a DockerManager instance with mocked Docker client."""
    with patch("lean_docker_mcp.docker_manager.docker") as mock_docker:
        mock_docker.from_env.return_value = mock_docker_client
        manager = DockerManager(test_config)
        yield manager


class TestTransientExecution:
    """Test the transient execution of Lean code."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, docker_manager, mock_docker_client):
        """Test executing valid Lean code with successful result."""
        # Set up the mock to return a successful result
        mock_docker_client.containers.run.return_value = b"""---LEAN_OUTPUT_START---
Hello, Lean4!
---LEAN_OUTPUT_END---
---LEAN_EXIT_CODE_START---
0
---LEAN_EXIT_CODE_END---"""

        # Test code that prints "Hello, Lean4!"
        code = 'def main : IO Unit := IO.println "Hello, Lean4!"'
        result = await docker_manager.execute_transient(code)
        
        # Check the result
        assert result["status"] == "success"
        assert "Hello, Lean4!" in result["stdout"]
        assert result["exit_code"] == 0
        
        # Verify Docker client was called correctly
        mock_docker_client.containers.run.assert_called_once()
        
        # Check Docker run parameters
        call_args = mock_docker_client.containers.run.call_args[1]
        assert call_args["image"] == "lean-docker-mcp:latest"
        assert call_args["mem_limit"] == "256m"
        assert call_args["network_disabled"] is True

    @pytest.mark.asyncio
    async def test_compilation_error(self, docker_manager, mock_docker_client):
        """Test executing Lean code with a compilation error."""
        # Set up the mock to return an error
        mock_docker_client.containers.run.return_value = b"""---LEAN_OUTPUT_START---
/app/Script.lean:1:22: error: type mismatch
  42
  ^
expected type
  IO Unit
but given type
  Nat
---LEAN_OUTPUT_END---
---LEAN_EXIT_CODE_START---
1
---LEAN_EXIT_CODE_END---"""

        # Test code with a type error
        code = 'def main : IO Unit := 42'  # Type error
        result = await docker_manager.execute_transient(code)
        
        # Check the result
        assert result["status"] == "error"
        assert "type mismatch" in result["stdout"]
        assert result["exit_code"] == 1
        assert "error_info" in result
        assert result["error_info"]["error_type"] == "type_mismatch"

    @pytest.mark.asyncio
    async def test_validation_error(self, docker_manager):
        """Test code that fails validation."""
        with patch("lean_docker_mcp.docker_manager.LeanCodeValidator.validate", 
                   return_value=(False, "Import 'System.IO.Process' is blocked for security reasons")):
            
            # Test code that imports a blocked module
            code = 'import System.IO.Process'
            result = await docker_manager.execute_transient(code)
            
            # Check the result
            assert result["status"] == "error"
            assert "Validation error" in result["error"]
            assert "blocked for security reasons" in result["error"]
            assert result["error_type"] == "validation_error"
            
    @pytest.mark.asyncio
    async def test_docker_exception(self, docker_manager, mock_docker_client):
        """Test handling of Docker exceptions."""
        # Simulate a Docker error during execution
        mock_docker_client.containers.run.side_effect = Exception("Docker error")
        
        # Execute code that will trigger the Docker error
        code = 'def main : IO Unit := IO.println "Hello"'
        
        # Should wrap the exception in a DockerExecutionError
        with pytest.raises(Exception) as excinfo:
            await docker_manager.execute_transient(code)
        
        # Check that the exception was properly wrapped
        assert "Error executing code in Docker" in str(excinfo.value)


class TestPersistentExecution:
    """Test the persistent execution of Lean code."""

    @pytest.mark.asyncio
    async def test_successful_persistent_execution(self, docker_manager, mock_docker_client, mock_container):
        """Test executing valid Lean code in a persistent container."""
        # Configure the exec_run mocks for the session
        exec_run_calls = []
        
        def mock_exec_run(*args, **kwargs):
            exec_run_calls.append((args, kwargs))
            call_index = len(exec_run_calls) - 1
            
            # Return different responses based on the call
            if call_index == 2:  # The call to execute the wrapper script
                return type('ExecResult', (), {
                    'exit_code': 0,
                    'output': b"""---LEAN_OUTPUT_START---
Hello from persistent container
---LEAN_OUTPUT_END---
---LEAN_EXIT_CODE_START---
0
---LEAN_EXIT_CODE_END---"""
                })()
            else:
                # Other calls (script creation, cleanup) return empty success
                return type('ExecResult', (), {'exit_code': 0, 'output': b''})()
        
        mock_container.exec_run.side_effect = mock_exec_run
        
        # Test code for persistent execution
        code = 'def main : IO Unit := IO.println "Hello from persistent container"'
        session_id = "test-session"
        result = await docker_manager.execute_persistent(session_id, code)
        
        # Check the result
        assert result["status"] == "success"
        assert "Hello from persistent container" in result["stdout"]
        assert result["exit_code"] == 0
        assert result["session_id"] == session_id
        
        # Check that container was created correctly
        mock_docker_client.containers.run.assert_called_once()
        
        # Verify the expected number of exec_run calls (create script, create wrapper, execute, cleanup)
        assert len(exec_run_calls) == 4

    @pytest.mark.asyncio
    async def test_persistent_execution_error(self, docker_manager, mock_docker_client, mock_container):
        """Test error handling in persistent execution."""
        # Configure the exec_run mocks for the session with an error
        exec_run_calls = []
        
        def mock_exec_run(*args, **kwargs):
            exec_run_calls.append((args, kwargs))
            call_index = len(exec_run_calls) - 1
            
            # Return different responses based on the call
            if call_index == 2:  # The call to execute the wrapper script
                return type('ExecResult', (), {
                    'exit_code': 1,
                    'output': b"""---LEAN_OUTPUT_START---
/home/leanuser/project/Script_abcdef.lean:1:22: error: unknown identifier 'nonexistent'
  IO.println nonexistent
            ^
---LEAN_OUTPUT_END---
---LEAN_EXIT_CODE_START---
1
---LEAN_EXIT_CODE_END---"""
                })()
            else:
                # Other calls (script creation, cleanup) return empty success
                return type('ExecResult', (), {'exit_code': 0, 'output': b''})()
        
        mock_container.exec_run.side_effect = mock_exec_run
        
        # Test code with an error
        code = 'def main : IO Unit := IO.println nonexistent'
        session_id = "test-session"
        result = await docker_manager.execute_persistent(session_id, code)
        
        # Check the result
        assert result["status"] == "error"
        assert "unknown identifier" in result["stdout"]
        assert result["exit_code"] == 1
        assert "error_info" in result
        assert result["error_info"]["error_type"] == "unknown_identifier"
        
        # Verify the expected number of exec_run calls were made
        assert len(exec_run_calls) == 4

    @pytest.mark.asyncio
    async def test_persistent_validation_error(self, docker_manager):
        """Test persistent execution with code that fails validation."""
        with patch("lean_docker_mcp.docker_manager.LeanCodeValidator.validate", 
                  return_value=(False, "Import 'System.IO.Process' is blocked for security reasons")):
            
            # Test code that imports a blocked module
            code = 'import System.IO.Process'
            session_id = "test-session"
            result = await docker_manager.execute_persistent(session_id, code)
            
            # Check the result
            assert result["status"] == "error"
            assert "Validation error" in result["error"]
            assert "blocked for security reasons" in result["error"]
            assert result["error_type"] == "validation_error"
    
    @pytest.mark.asyncio
    async def test_container_not_found(self, docker_manager, mock_docker_client):
        """Test handling of container not found during persistent execution."""
        # Import the correct exception type
        from docker.errors import NotFound
        
        # Add a fake session ID to the persistent containers
        docker_manager.persistent_containers["test-session"] = "nonexistent-id"
        
        # Make the container.get raise NotFound
        mock_docker_client.containers.get.side_effect = NotFound("Container not found")
        
        # Execute code with the session ID
        code = 'def main : IO Unit := IO.println "Hello"'
        
        # Should raise DockerExecutionError
        from lean_docker_mcp.docker_manager import DockerExecutionError
        with pytest.raises(DockerExecutionError) as excinfo:
            await docker_manager.execute_persistent("test-session", code)
        
        # Check the exception
        assert "Session test-session has expired or was deleted" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_cleanup_session(self, docker_manager, mock_docker_client, mock_container):
        """Test cleanup of a persistent session."""
        # Add a test session to the manager's persistent containers
        docker_manager.persistent_containers["test-session"] = "test-container-id"
        
        # Call cleanup
        result = await docker_manager.cleanup_session("test-session")
        
        # Check the result
        assert result["status"] == "success"
        assert "test-session" in result["message"]
        
        # Verify that the container was stopped and removed
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        
        # Verify the session was removed from tracking
        assert "test-session" not in docker_manager.persistent_containers
        
    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_session(self, docker_manager):
        """Test cleanup of a session that doesn't exist."""
        # Call cleanup on a session that doesn't exist
        result = await docker_manager.cleanup_session("nonexistent-session")
        
        # Check the result
        assert result["status"] == "not_found"
        assert "nonexistent-session" in result["message"]


class TestServerIO:
    """Test the server I/O functions."""
    
    @pytest.mark.asyncio
    async def test_server_main(self):
        """Test the server main loop."""
        from lean_docker_mcp.server import main, read_request, Server
        
        # Mock read_request to return a request and then None (to exit the loop)
        with patch("lean_docker_mcp.server.read_request") as mock_read_request:
            mock_read_request.side_effect = [
                {"jsonrpc": "2.0", "id": 1, "method": "execute-lean", "params": {"code": "test"}},
                None  # End the loop
            ]
            
            # Mock write_response to do nothing
            with patch("lean_docker_mcp.server.write_response") as mock_write_response:
                # Mock Server.handle_request to return a simple response
                with patch.object(Server, "handle_request", return_value={"jsonrpc": "2.0", "id": 1, "result": {}}) as mock_handle_request:
                    # Run the main function
                    await main()
                    
                    # Verify that read_request was called twice
                    assert mock_read_request.call_count == 2
                    # Verify that handle_request was called once
                    assert mock_handle_request.call_count == 1
                    # Verify that write_response was called once
                    assert mock_write_response.call_count == 1
                    
    @pytest.mark.asyncio
    async def test_server_main_error(self):
        """Test the server main loop with an error."""
        from lean_docker_mcp.server import main, read_request, Server, logger
        
        # Mock read_request to raise an exception
        with patch("lean_docker_mcp.server.read_request", side_effect=Exception("Test error")):
            # Mock sys.exit to prevent test from exiting
            with patch("sys.exit") as mock_exit:
                # Mock logger.error
                with patch.object(logger, "error") as mock_logger_error:
                    # Run the main function
                    await main()
                    
                    # Verify that logger.error was called
                    assert mock_logger_error.call_count == 1
                    # Verify that sys.exit was called with code 1
                    mock_exit.assert_called_once_with(1)
    
    @pytest.mark.asyncio
    async def test_read_request(self):
        """Test reading a JSON-RPC request."""
        from lean_docker_mcp.server import read_request
        
        # Mock stdin to return a JSON-RPC request
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.side_effect = [
                "Content-Length: 76\n",
                "\n",  # Empty line (end of headers)
                ""     # EOF (not used)
            ]
            mock_stdin.buffer = MagicMock()
            mock_stdin.buffer.read.return_value = b'{"jsonrpc": "2.0", "id": 1, "method": "execute-lean", "params": {"code": "test"}}'
            
            # Read the request
            result = await read_request()
            
            # Check the result
            assert result is not None
            assert result["jsonrpc"] == "2.0"
            assert result["id"] == 1
            assert result["method"] == "execute-lean"
            assert result["params"]["code"] == "test"
            
    @pytest.mark.asyncio
    async def test_read_request_missing_header(self):
        """Test reading a JSON-RPC request with missing header."""
        from lean_docker_mcp.server import read_request
        
        # Mock stdin to return a request with missing Content-Length
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.side_effect = [
                "Invalid-Header: test\n",
                "\n",  # Empty line (end of headers)
                ""     # EOF
            ]
            
            # Read the request - should return None
            result = await read_request()
            assert result is None
            
    @pytest.mark.asyncio
    async def test_read_request_eof(self):
        """Test reading a JSON-RPC request with EOF."""
        from lean_docker_mcp.server import read_request
        
        # Mock stdin to return EOF immediately
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.return_value = ""
            
            # Read the request - should return None
            result = await read_request()
            assert result is None
            
    @pytest.mark.asyncio
    async def test_write_response(self):
        """Test writing a JSON-RPC response."""
        from lean_docker_mcp.server import write_response
        
        # Mock stdout
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = MagicMock()
            
            # Write a response
            response = {"jsonrpc": "2.0", "id": 1, "result": {"status": "success"}}
            await write_response(response)
            
            # Check that stdout.buffer.write was called twice (once for headers, once for body)
            assert mock_stdout.buffer.write.call_count == 2
            assert mock_stdout.buffer.flush.call_count == 1
    
    @pytest.mark.asyncio
    async def test_write_response_error(self):
        """Test error handling in write_response."""
        from lean_docker_mcp.server import write_response
        from lean_docker_mcp.server import logger
        
        # Mock stdout to raise an exception
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = MagicMock()
            mock_stdout.buffer.write.side_effect = Exception("Test error")
            
            # Mock logger
            with patch.object(logger, "error") as mock_logger_error:
                # Write a response
                response = {"jsonrpc": "2.0", "id": 1, "result": {"status": "success"}}
                await write_response(response)
                
                # Check that logger.error was called
                mock_logger_error.assert_called_once()
                assert "Test error" in mock_logger_error.call_args[0][0]


class TestServerExecution:
    """Test the server execution interface."""

    @pytest_asyncio.fixture
    async def server(self, docker_manager):
        """Create a Server instance with mocked Docker manager."""
        with patch("lean_docker_mcp.server.DockerManager", return_value=docker_manager):
            server_instance = Server()
            yield server_instance

    @pytest.mark.asyncio
    async def test_execute_lean_request(self, server, docker_manager):
        """Test the execute-lean JSON-RPC method."""
        # Mock the Docker manager's execute_transient method
        docker_manager.execute_transient = AsyncMock(return_value={
            "status": "success",
            "stdout": "Hello, Lean4!",
            "exit_code": 0
        })
        
        # Create a test request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": {
                "code": 'def main : IO Unit := IO.println "Hello, Lean4!"'
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["status"] == "success"
        assert "Hello, Lean4!" in response["result"]["stdout"]
        
        # Verify that execute_transient was called with the correct code
        docker_manager.execute_transient.assert_called_once_with(
            'def main : IO Unit := IO.println "Hello, Lean4!"'
        )

    @pytest.mark.asyncio
    async def test_execute_lean_persistent_request(self, server, docker_manager):
        """Test the execute-lean-persistent JSON-RPC method."""
        # Mock the Docker manager's execute_persistent method
        docker_manager.execute_persistent = AsyncMock(return_value={
            "status": "success",
            "stdout": "Hello from persistent container",
            "exit_code": 0,
            "session_id": "test-session"
        })
        
        # Create a test request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean-persistent",
            "params": {
                "code": 'def main : IO Unit := IO.println "Hello from persistent container"',
                "session_id": "test-session"
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["status"] == "success"
        assert "Hello from persistent container" in response["result"]["stdout"]
        assert response["result"]["session_id"] == "test-session"
        
        # Verify that execute_persistent was called with the correct code and session ID
        docker_manager.execute_persistent.assert_called_once_with(
            "test-session",
            'def main : IO Unit := IO.println "Hello from persistent container"'
        )
        
    @pytest.mark.asyncio
    async def test_execute_lean_persistent_with_auto_session_id(self, server, docker_manager):
        """Test the execute-lean-persistent method with automatic session ID generation."""
        # Mock the Docker manager's execute_persistent method
        docker_manager.execute_persistent = AsyncMock(return_value={
            "status": "success",
            "stdout": "Hello from persistent container",
            "exit_code": 0,
            "session_id": "generated-id"  # The server should use this value in the response
        })
        
        # Create a test request without session_id
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean-persistent",
            "params": {
                "code": 'def main : IO Unit := IO.println "Hello from persistent container"'
                # No session_id, should be generated
            }
        }
        
        # Send the request to the server
        with patch("lean_docker_mcp.server.uuid.uuid4", return_value="generated-id"):
            response = await server.handle_request(request)
        
        # Check the response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["session_id"] == "generated-id"
        
        # Verify that execute_persistent was called with the generated session ID
        docker_manager.execute_persistent.assert_called_once()
        args, _ = docker_manager.execute_persistent.call_args
        assert args[0] == "generated-id"

    @pytest.mark.asyncio
    async def test_cleanup_session_request(self, server, docker_manager):
        """Test the cleanup-session JSON-RPC method."""
        # Mock the Docker manager's cleanup_session method
        docker_manager.cleanup_session = AsyncMock(return_value={
            "status": "success",
            "message": "Session test-session cleaned up successfully"
        })
        
        # Create a test request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "cleanup-session",
            "params": {
                "session_id": "test-session"
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["status"] == "success"
        
        # Verify that cleanup_session was called with the correct session ID
        docker_manager.cleanup_session.assert_called_once_with("test-session")
        
    @pytest.mark.asyncio
    async def test_invalid_cleanup_params(self, server):
        """Test handling of invalid cleanup parameters."""
        # Create a test request missing the required 'session_id' parameter
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "cleanup-session",
            "params": {}  # Missing session_id parameter
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32602  # Invalid params
        assert "session_id is required" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_error_response(self, server, docker_manager):
        """Test error handling in the server."""
        # Create a test request with an invalid method
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "invalid-method",
            "params": {}
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32601  # Method not found
        assert "Method not found" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_invalid_params(self, server):
        """Test handling of invalid parameters."""
        # Create a test request missing the required 'code' parameter
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": {}  # Missing code parameter
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32602  # Invalid params
        assert "code is required" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_invalid_code_type(self, server):
        """Test handling of invalid code type."""
        # Create a test request with non-string code
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": {
                "code": 42  # Not a string
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32602  # Invalid params
        assert "code must be a string" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_invalid_session_id_type(self, server):
        """Test handling of invalid session_id type."""
        # Create a test request with non-string session_id
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "cleanup-session",
            "params": {
                "session_id": 42  # Not a string
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32602  # Invalid params
        assert "session_id must be a string" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_invalid_request_format(self, server):
        """Test handling of invalid request format."""
        # Create a test request with invalid id type
        request = {
            "jsonrpc": "2.0",
            "id": {"invalid": "id"},  # Invalid id type
            "method": "execute-lean",
            "params": {
                "code": "def main : IO Unit := IO.println \"Hello\""
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        # The server returns the original id, even if invalid
        assert response["id"] == {"invalid": "id"}
        assert "error" in response
        assert response["error"]["code"] == -32600  # Invalid request
        assert "id must be" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_invalid_params_type(self, server):
        """Test handling of invalid params type."""
        # Create a test request with invalid params type
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": "not-an-object"  # Not a dict
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32602  # Invalid params
        assert "params must be an object" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_docker_execution_error(self, server):
        """Test handling of DockerExecutionError in the server."""
        # Create a mock DockerManager that raises an exception
        from lean_docker_mcp.docker_manager import DockerExecutionError
        
        mock_docker_manager = MagicMock()
        mock_docker_manager.execute_transient = AsyncMock(side_effect=DockerExecutionError("Docker execution error"))
        
        # Replace the server's docker_manager with our mock
        server.docker_manager = mock_docker_manager
        
        # Create a test request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": {
                "code": 'def main : IO Unit := IO.println "Hello"'
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert "Docker execution error" in response["error"]["message"]
        
    @pytest.mark.asyncio
    async def test_lean_compilation_error(self, server):
        """Test handling of LeanCompilationError in the server."""
        # Create a mock DockerManager that raises a LeanCompilationError
        from lean_docker_mcp.docker_manager import LeanCompilationError
        
        mock_docker_manager = MagicMock()
        error = LeanCompilationError(
            message="Type mismatch error",
            error_type="type_mismatch",
            line=10,
            column=5
        )
        mock_docker_manager.execute_transient = AsyncMock(side_effect=error)
        
        # Replace the server's docker_manager with our mock
        server.docker_manager = mock_docker_manager
        
        # Create a test request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "execute-lean",
            "params": {
                "code": 'def main : IO Unit := 42'
            }
        }
        
        # Send the request to the server
        response = await server.handle_request(request)
        
        # Check the error response
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "error" in response
        assert "Type mismatch error" in response["error"]["message"]
        assert response["error"]["data"]["error_type"] == "type_mismatch"