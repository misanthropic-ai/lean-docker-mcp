"""Main module for lean-docker-mcp package.

This allows running the package directly with python -m lean_docker_mcp
"""

import asyncio
import logging
import os
import sys
import traceback

from lean_docker_mcp.server import main

if __name__ == "__main__":
    # Configure basic logging to stdout
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("lean-docker-mcp-main")
    
    # Check for debug flag
    debug_mode = "--debug" in sys.argv or os.environ.get("LEAN_DOCKER_MCP_DEBUG", "").lower() in ["true", "1", "yes"]
    
    if debug_mode:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    try:
        logger.info("Starting lean-docker-mcp server")
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error in lean-docker-mcp: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1) 