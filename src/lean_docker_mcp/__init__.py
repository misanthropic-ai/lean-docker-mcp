"""Lean Docker MCP package for running Lean4 code in isolated Docker containers.

This package provides a server that accepts Lean4 code execution requests and runs
them in isolated Docker containers for security.
"""

import asyncio
import logging
import os
import re
import subprocess
from typing import List, Optional

from . import config, docker_manager, server
from .config import load_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lean-docker-mcp")

# Package version
__version__ = "0.2.4"


def check_docker_image_exists(image_name: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking Docker image: {e}")
        return False


def get_docker_images(base_name: str) -> List[str]:
    """Get list of Docker images with the given base name."""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", base_name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return []
    except Exception as e:
        logger.error(f"Error listing Docker images: {e}")
        return []


def cleanup_old_images(base_name: str, current_version: str) -> None:
    """Remove old versions of the Docker image."""
    try:
        # Get all images with this base name
        images = get_docker_images(base_name)

        # Filter out the current version and 'latest' tag
        images_to_remove = [img for img in images if not img.endswith(f":{current_version}") and not img.endswith(":latest")]

        if images_to_remove:
            logger.info(f"Cleaning up {len(images_to_remove)} old image versions...")
            for img in images_to_remove:
                logger.info(f"Removing old image: {img}")
                subprocess.run(
                    ["docker", "rmi", img],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
    except Exception as e:
        logger.warning(f"Error cleaning up old images: {e}")


def ensure_docker_image(image_name: Optional[str] = None) -> None:
    """Ensure the Docker image exists with the correct version, building it if necessary."""
    if image_name is None:
        # Load configuration to get the default image name
        config_obj = load_config()
        base_image_name = config_obj.docker.image

        # Extract base name without tag
        if ":" in base_image_name:
            base_name = base_image_name.split(":")[0]
        else:
            base_name = base_image_name

        # Create versioned image name
        versioned_image_name = f"{base_name}:{__version__}"
        latest_image_name = f"{base_name}:latest"
    else:
        # If a custom image name is provided, use it as is
        versioned_image_name = image_name
        latest_image_name = image_name
        base_name = image_name.split(":")[0] if ":" in image_name else image_name

    # Check if the versioned image exists
    if not check_docker_image_exists(versioned_image_name):
        logger.info(f"Docker image {versioned_image_name} not found. Building it now...")
        
        # Build the Docker image using the build_docker_image.sh script
        # Try several possible locations for the build script
        script_paths = [
            os.path.join(os.path.dirname(__file__), "build_docker_image.sh"),  # Same directory as module
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "build_docker_image.sh"),  # 3 levels up (development)
            os.path.join(os.getcwd(), "build_docker_image.sh"),  # Current working directory
        ]
        
        script_found = False
        for script_path in script_paths:
            if os.path.exists(script_path):
                script_found = True
                try:
                    logger.info(f"Found build script at {script_path}")
                    subprocess.run(
                        [script_path, "--tag", __version__, "--name", base_name],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    logger.info(f"Successfully built Docker image: {versioned_image_name}")
                    
                    # Also tag as latest
                    try:
                        subprocess.run(
                            ["docker", "tag", versioned_image_name, latest_image_name],
                            check=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        logger.info(f"Tagged {versioned_image_name} as {latest_image_name}")
                    except Exception as e:
                        logger.warning(f"Error tagging image as latest: {e}")
                    
                    # Clean up old versions
                    cleanup_old_images(base_name, __version__)
                    break
                except Exception as e:
                    logger.warning(f"Failed to build Docker image with script {script_path}: {e}")
                    continue
        
        if not script_found:
            # If script isn't found, try to build directly using the Dockerfile in the package
            dockerfile_path = os.path.join(os.path.dirname(__file__), "Dockerfile")
            if os.path.exists(dockerfile_path):
                try:
                    logger.info(f"Building Docker image using Dockerfile at {dockerfile_path}")
                    subprocess.run(
                        ["docker", "build", "-t", versioned_image_name, "-f", dockerfile_path, os.path.dirname(dockerfile_path)],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    logger.info(f"Successfully built Docker image: {versioned_image_name}")
                    
                    # Tag as latest
                    subprocess.run(
                        ["docker", "tag", versioned_image_name, latest_image_name],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except Exception as e:
                    logger.warning(f"Failed to build Docker image from Dockerfile: {e}")
                    logger.warning(f"Please build the Docker image manually using: docker build -t {versioned_image_name} -f {dockerfile_path} .")
            else:
                logger.warning(f"Build script not found at {script_path}")
                logger.warning(f"Dockerfile not found at {dockerfile_path}")
                logger.warning(f"Please build the Docker image manually using: docker build -t {versioned_image_name} -f src/lean_docker_mcp/Dockerfile .")
    else:
        logger.info(f"Docker image {versioned_image_name} already exists.")
        
        # Check if latest tag exists and points to the correct version
        if not check_docker_image_exists(latest_image_name):
            # Tag the versioned image as latest
            try:
                subprocess.run(
                    ["docker", "tag", versioned_image_name, latest_image_name],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                logger.info(f"Tagged {versioned_image_name} as {latest_image_name}")
            except Exception as e:
                logger.warning(f"Error tagging image as latest: {e}")


def main() -> None:
    """Main entry point for the package."""
    try:
        # Ensure the Docker image exists before starting the server
        ensure_docker_image()

        # Run the server
        asyncio.run(server.main())
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise


# Expose important items at package level
__all__ = ["main", "server", "config", "docker_manager", "__version__"] 