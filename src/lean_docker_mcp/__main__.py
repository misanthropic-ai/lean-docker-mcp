#!/usr/bin/env python3
"""Command-line entry point for the Lean Docker MCP."""

import asyncio
import sys

from .server import main as server_main

async def main():
    """Main entry point for the Lean Docker MCP."""
    try:
        await server_main()
    except KeyboardInterrupt:
        # Clean shutdown on Ctrl+C
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 