"""Configuration module for Lean Docker MCP."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Default configuration directory
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.lean-docker-mcp")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "config.yaml")


@dataclass
class DockerConfig:
    """Docker container configuration."""

    image: str = "lean-docker-mcp:latest"
    working_dir: str = "/home/leanuser/project"
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    timeout: int = 30
    network_disabled: bool = True
    read_only: bool = False
    # Container pooling configuration
    pool_size: int = 32  # Number of containers to keep in the pool; set to 0 to disable pooling
    pool_max_age: int = 300  # Maximum age of a container in seconds (5 minutes)
    max_concurrent_creations: int = 5  # Maximum number of containers to create concurrently
    pool_enabled: bool = True  # Enable/disable container pooling overall


@dataclass
class LeanConfig:
    """Lean4 specific configuration."""

    allowed_imports: List[str] = field(default_factory=lambda: ["Lean", "Init", "Std", "Mathlib"])
    blocked_imports: List[str] = field(default_factory=lambda: ["System.IO.Process", "System.FilePath"])


@dataclass
class Configuration:
    """Main configuration class."""

    docker: DockerConfig
    lean: LeanConfig

    @classmethod
    def from_dict(cls, config_dict: Dict) -> "Configuration":
        """Create a Configuration object from a dictionary."""
        docker_config = DockerConfig(**config_dict.get("docker", {}))
        lean_config = LeanConfig(**config_dict.get("lean", {}))
        
        return cls(
            docker=docker_config,
            lean=lean_config,
        )


def load_config(config_path: Optional[str] = None) -> Configuration:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the configuration file. If None, the default path is used.

    Returns:
        A Configuration object with the loaded configuration.
    """
    # If no config path is provided, use the default
    if config_path is None:
        config_path = os.environ.get("LEAN_DOCKER_MCP_CONFIG", DEFAULT_CONFIG_PATH)

    # Load configuration from file if it exists
    config_dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config_dict = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.warning(f"Error loading configuration from {config_path}: {e}")
            logger.warning("Using default configuration")
    else:
        logger.info(f"Configuration file {config_path} not found. Using default configuration.")
        # Try to load the bundled default configuration
        default_config_file = os.path.join(os.path.dirname(__file__), "default_config.yaml")
        if os.path.exists(default_config_file):
            try:
                with open(default_config_file, "r") as f:
                    config_dict = yaml.safe_load(f) or {}
                logger.info(f"Loaded default configuration from {default_config_file}")
            except Exception as e:
                logger.warning(f"Error loading default configuration from {default_config_file}: {e}")
    
    # Check for environment variables to override configuration
    # Docker container pooling settings
    if "docker" not in config_dict:
        config_dict["docker"] = {}
        
    # Pool size
    env_pool_size = os.environ.get("LEAN_DOCKER_MCP_POOL_SIZE")
    if env_pool_size:
        try:
            config_dict["docker"]["pool_size"] = int(env_pool_size)
            logger.info(f"Using pool_size={env_pool_size} from environment variable")
        except ValueError:
            logger.warning(f"Invalid value for LEAN_DOCKER_MCP_POOL_SIZE: {env_pool_size}")
    
    # Pool enabled
    env_pool_enabled = os.environ.get("LEAN_DOCKER_MCP_POOL_ENABLED")
    if env_pool_enabled is not None:
        try:
            config_dict["docker"]["pool_enabled"] = env_pool_enabled.lower() in ("true", "1", "yes")
            logger.info(f"Using pool_enabled={config_dict['docker']['pool_enabled']} from environment variable")
        except Exception as e:
            logger.warning(f"Error parsing LEAN_DOCKER_MCP_POOL_ENABLED: {e}")
    
    # Pool max age
    env_pool_max_age = os.environ.get("LEAN_DOCKER_MCP_POOL_MAX_AGE")
    if env_pool_max_age:
        try:
            config_dict["docker"]["pool_max_age"] = int(env_pool_max_age)
            logger.info(f"Using pool_max_age={env_pool_max_age} from environment variable")
        except ValueError:
            logger.warning(f"Invalid value for LEAN_DOCKER_MCP_POOL_MAX_AGE: {env_pool_max_age}")
    
    # Max concurrent creations
    env_max_concurrent = os.environ.get("LEAN_DOCKER_MCP_MAX_CONCURRENT_CREATIONS")
    if env_max_concurrent:
        try:
            config_dict["docker"]["max_concurrent_creations"] = int(env_max_concurrent)
            logger.info(f"Using max_concurrent_creations={env_max_concurrent} from environment variable")
        except ValueError:
            logger.warning(f"Invalid value for LEAN_DOCKER_MCP_MAX_CONCURRENT_CREATIONS: {env_max_concurrent}")
            
    # Other Docker settings from environment
    env_memory_limit = os.environ.get("LEAN_DOCKER_MCP_MEMORY_LIMIT")
    if env_memory_limit:
        config_dict["docker"]["memory_limit"] = env_memory_limit
        
    env_cpu_limit = os.environ.get("LEAN_DOCKER_MCP_CPU_LIMIT")
    if env_cpu_limit:
        try:
            config_dict["docker"]["cpu_limit"] = float(env_cpu_limit)
        except ValueError:
            logger.warning(f"Invalid value for LEAN_DOCKER_MCP_CPU_LIMIT: {env_cpu_limit}")
            
    env_timeout = os.environ.get("LEAN_DOCKER_MCP_TIMEOUT")
    if env_timeout:
        try:
            config_dict["docker"]["timeout"] = int(env_timeout)
        except ValueError:
            logger.warning(f"Invalid value for LEAN_DOCKER_MCP_TIMEOUT: {env_timeout}")

    # Create the configuration object
    return Configuration.from_dict(config_dict) 