# lean-docker-mcp

Dockerized Lean4 execution environment for AI agents.

## Overview

This MCP server provides a safe, sandboxed Lean4 execution environment for LLM-powered agents. It allows agents to:

- Execute Lean4 code in isolated Docker containers
- Choose between transient or persistent execution environments
- Maintain state between execution steps

## Installation

### Requirements

- Docker must be installed and running on the host system
- Python 3.11 or later
- `uv` for package management (recommended)

### Install from PyPI

```bash
# Using uv (recommended)
uv pip install lean-docker-mcp

# Using pip
pip install lean-docker-mcp
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/artivus/lean-docker-mcp.git
cd lean-docker-mcp

# Install with uv
uv pip install -e .

# Or with pip
pip install -e .
```

## Quick Start

### Running the Server

The lean-docker-mcp server can be started directly using the module:

```bash
python -m lean_docker_mcp
```

This will start the MCP server and listen for JSONRPC requests on stdin/stdout.

## Components

### Docker Execution Environment

The server implements two types of execution environments:

1. **Transient Environment**
   - Each execution is isolated in a fresh container
   - State isn't maintained between calls
   - Safer for one-off code execution

2. **Persistent Environment**
   - Maintains state between executions
   - Variables and functions defined in one execution are available in subsequent executions
   - Suitable for interactive, stateful REPL-like sessions

### Tools

The server provides the following tools:

- **execute-transient**: Run Lean4 code in a transient Docker container
  - Takes `code` (required) parameter
  - Returns execution results

- **execute-persistent**: Run Lean4 code in a persistent Docker container
  - Takes `code` (required) and `session_id` (optional) parameters
  - Returns execution results
  - Maintains state between calls

- **cleanup-session**: Clean up a persistent session
  - Takes `session_id` (required) parameter
  - Stops and removes the associated Docker container

## Configuration

The server can be configured via a YAML configuration file. By default, it looks for a file at `~/.lean-docker-mcp/config.yaml`.

### Configuration File Structure

Example configuration:

```yaml
docker:
  image: lean-docker-mcp:latest
  working_dir: /home/leanuser/project
  memory_limit: 256m
  cpu_limit: 0.5
  timeout: 30
  network_disabled: true
  read_only: false

lean:
  allowed_imports:
    - Lean
    - Init
    - Std
    - Mathlib
  blocked_imports:
    - System.IO.Process
    - System.FilePath
```

### Docker Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `image` | Docker image to use for execution | `lean-docker-mcp:latest` |
| `working_dir` | Working directory inside container | `/home/leanuser/project` |
| `memory_limit` | Memory limit for container | `256m` |
| `cpu_limit` | CPU limit (0.0-1.0) | `0.5` |
| `timeout` | Execution timeout in seconds | `30` |
| `network_disabled` | Disable network access | `true` |
| `read_only` | Run container in read-only mode | `false` |

## Integration with Claude and Anthropic Products

### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>

  ```json
  "mcpServers": {
    "lean-docker-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/lean-docker-mcp",
        "run",
        "lean-docker-mcp"
      ]
    }
  }
  ```
</details>

<details>
  <summary>Published Servers Configuration</summary>

  ```json
  "mcpServers": {
    "lean-docker-mcp": {
      "command": "uvx",
      "args": [
        "lean-docker-mcp"
      ]
    }
  }
  ```
</details>

## Example MCP Usage

### Transient Execution

```
# Define and use a simple function
result = await call_tool("execute-transient", {
  "code": "def hello (name : String) : String := s!\"Hello, {name}\"\n\ndef main : IO Unit := IO.println (hello \"Lean4!\")"
})
```

### Persistent Session

```
# Create a persistent session and define a function
result = await call_tool("execute-persistent", {
  "code": "def add (a b : Nat) : Nat := a + b\n\ndef main : IO Unit := IO.println \"Function defined\""
})

# Use the function in a subsequent call with the same session
result = await call_tool("execute-persistent", {
  "session_id": "previous_session_id",
  "code": "def main : IO Unit := IO.println (toString (add 10 20))"
})
```

## Development

### Development Setup

1. Clone the repository:
```bash
git clone https://github.com/artivus/lean-docker-mcp.git
cd lean-docker-mcp
```

2. Set up development environment:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

3. Install pre-commit hooks:
```bash
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/lean_docker_mcp

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
```

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

3. Publish to PyPI:
```bash
uv publish
```

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/lean-docker-mcp run lean-docker-mcp
```

## License

[License information]

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
