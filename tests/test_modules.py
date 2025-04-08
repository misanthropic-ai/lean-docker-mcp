"""Tests for the main module and initialization."""

import pytest
import sys
import subprocess
from unittest.mock import MagicMock, patch

import lean_docker_mcp
from lean_docker_mcp.__main__ import main as main_entry
from lean_docker_mcp import (
    check_docker_image_exists,
    get_docker_images,
    ensure_docker_image,
    main as init_main
)


class TestInit:
    """Test the module initialization."""
    
    def test_version(self):
        """Test the version attribute exists."""
        assert hasattr(lean_docker_mcp, "__version__")
        assert isinstance(lean_docker_mcp.__version__, str)
        
    def test_package_metadata(self):
        """Test the package metadata."""
        assert hasattr(lean_docker_mcp, "__title__")
        assert hasattr(lean_docker_mcp, "__description__")
        assert hasattr(lean_docker_mcp, "__author__")
        assert hasattr(lean_docker_mcp, "__license__")
        
    def test_check_docker_image_exists_success(self):
        """Test check_docker_image_exists when image exists."""
        with patch("subprocess.run") as mock_run:
            # Mock successful subprocess run
            mock_run.return_value = MagicMock(returncode=0)
            
            # Call the function
            result = check_docker_image_exists("test-image:latest")
            
            # Check result and subprocess call
            assert result is True
            mock_run.assert_called_once_with(
                ["docker", "image", "inspect", "test-image:latest"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
    def test_check_docker_image_exists_failure(self):
        """Test check_docker_image_exists when image doesn't exist."""
        with patch("subprocess.run") as mock_run:
            # Mock failed subprocess run
            mock_run.return_value = MagicMock(returncode=1)
            
            # Call the function
            result = check_docker_image_exists("non-existent-image")
            
            # Check result
            assert result is False
            
    def test_check_docker_image_exists_exception(self):
        """Test check_docker_image_exists when exception occurs."""
        with patch("subprocess.run", side_effect=Exception("Test error")):
            # Call the function
            result = check_docker_image_exists("test-image")
            
            # Check result
            assert result is False
            
    def test_get_docker_images_success(self):
        """Test get_docker_images when images exist."""
        with patch("subprocess.run") as mock_run:
            # Mock successful subprocess run with output
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = "lean-docker-mcp:latest\nlean-docker-mcp:0.1.0\n"
            mock_run.return_value = mock_process
            
            # Call the function
            result = get_docker_images("lean-docker-mcp")
            
            # Check result
            assert result == ["lean-docker-mcp:latest", "lean-docker-mcp:0.1.0"]
            
    def test_get_docker_images_failure(self):
        """Test get_docker_images when command fails."""
        with patch("subprocess.run") as mock_run:
            # Mock failed subprocess run
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_run.return_value = mock_process
            
            # Call the function
            result = get_docker_images("lean-docker-mcp")
            
            # Check result
            assert result == []
            
    def test_get_docker_images_exception(self):
        """Test get_docker_images when exception occurs."""
        with patch("subprocess.run", side_effect=Exception("Test error")):
            # Call the function
            result = get_docker_images("lean-docker-mcp")
            
            # Check result
            assert result == []
            
    def test_ensure_docker_image_exists(self):
        """Test ensure_docker_image when image exists."""
        with patch("lean_docker_mcp.check_docker_image_exists", return_value=True):
            with patch("lean_docker_mcp.logger.info") as mock_info:
                # Call the function
                ensure_docker_image("test-image:latest")
                
                # Check logger call
                mock_info.assert_called_once_with("Docker image test-image:latest already exists.")
                
    def test_ensure_docker_image_not_exists(self):
        """Test ensure_docker_image when image doesn't exist."""
        with patch("lean_docker_mcp.check_docker_image_exists", return_value=False):
            with patch("lean_docker_mcp.logger.info") as mock_info:
                # Call the function
                ensure_docker_image("test-image:latest")
                
                # Check logger calls (there should be 2)
                assert mock_info.call_count == 2
                mock_info.assert_any_call("Docker image test-image:latest not found. Please build it manually using the provided Dockerfile.")
                
    def test_ensure_docker_image_default(self):
        """Test ensure_docker_image with default image name."""
        with patch("lean_docker_mcp.check_docker_image_exists") as mock_check:
            # Call the function with no arguments
            ensure_docker_image()
            
            # Check that it used the default image name
            mock_check.assert_called_once_with("lean-docker-mcp:latest")
            
    def test_init_main_success(self):
        """Test the init main function on success."""
        with patch("lean_docker_mcp.ensure_docker_image") as mock_ensure:
            with patch("asyncio.run") as mock_run:
                # Run the main function
                init_main()
                
                # Verify functions were called
                mock_ensure.assert_called_once()
                mock_run.assert_called_once()
                
    def test_init_main_exception(self):
        """Test the init main function with an exception."""
        with patch("lean_docker_mcp.ensure_docker_image", side_effect=Exception("Test error")):
            with patch("lean_docker_mcp.logger.error") as mock_error:
                # Run the main function and expect exception
                with pytest.raises(Exception, match="Test error"):
                    init_main()
                
                # Verify logger.error was called
                assert mock_error.call_count == 1


class TestMain:
    """Test the main entry point."""
    
    @pytest.mark.asyncio
    async def test_main_calls_server_main(self):
        """Test that main calls the server main function."""
        # Since main_entry is an async function, we need to test it correctly
        with patch("lean_docker_mcp.__main__.server_main") as mock_server_main:
            # Run the async main function
            await main_entry()
                
            # Verify server_main was called
            mock_server_main.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_main_handles_keyboard_interrupt(self):
        """Test that main properly handles KeyboardInterrupt."""
        with patch("lean_docker_mcp.__main__.server_main", side_effect=KeyboardInterrupt()):
            with patch("sys.exit") as mock_exit:
                with patch("lean_docker_mcp.__main__.print") as mock_print:
                    # Run the main function - it should handle the KeyboardInterrupt
                    await main_entry()
                    
                    # Verify sys.exit was called with code 0
                    mock_exit.assert_called_once_with(0)
                    # Verify message was printed
                    mock_print.assert_called_with("\nShutting down gracefully...")
    
    @pytest.mark.asyncio
    async def test_main_handles_exceptions(self):
        """Test that main properly handles exceptions."""
        with patch("lean_docker_mcp.__main__.server_main", side_effect=Exception("Test exception")):
            with patch("sys.exit") as mock_exit:
                with patch("lean_docker_mcp.__main__.print") as mock_print:
                    # Run the main function - it should handle the exception
                    await main_entry()
                    
                    # Verify sys.exit was called with code 1
                    mock_exit.assert_called_once_with(1)
                    # Verify error was printed
                    mock_print.assert_called_with("Error: Test exception")