"""Main module for lean-docker-mcp package.

This allows running the package directly with python -m lean_docker_mcp
"""

from lean_docker_mcp.server import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 