# LangGraph Coding Agent

A LangGraph-based intelligent coding agent that generates, verifies, executes Python code, and validates output artifacts using a graph-of-thought paradigm.

## Features

- **Multi-LLM Support**: Works with any OpenAI-compatible API (OpenAI, Azure OpenAI, local models via Ollama, etc.)
- **Session Management**: SQLite-backed session management for multi-user support
- **Context Management**: Organized work directories with input, generated code, and artifacts subdirectories
- **Code Verification**: Multi-layer verification including:
  - Syntax checking
  - Linting (pylint)
  - Type checking (mypy)
  - Security analysis
  - LLM-based code review
- **Artifact Validation**: LLM-based evaluation of generated outputs
- **Retry Logic**: Automatic retry with feedback (up to 10 attempts by default)
- **LangGraph Workflow**: State-machine based workflow with conditional routing

## Project Structure

```
langgraph/
├── __init__.py              # Package initialization
├── agent/
│   ├── __init__.py
│   ├── llm_service.py       # LLM interaction for code generation & verification
│   ├── code_executor.py     # Code execution and static verification
│   ├── nodes.py             # LangGraph node definitions
│   └── graph.py             # Main agent graph workflow
├── models/
│   ├── __init__.py
│   ├── session.py           # Session, Task, and state models
│   ├── user_management.py   # User and session management with SQLite
│   └── context.py           # Context directory management
├── configs/
│   ├── __init__.py
│   └── config.yaml          # Configuration file
└── tests/
    ├── __init__.py
    └── test_agent.py        # Unit tests
```

## Installation

### Using pip

```bash
pip install langgraph langchain langchain-openai python-dotenv pyyaml
```

### Optional: Enhanced verification

```bash
pip install pylint mypy
```

### Using Poetry

```bash
poetry install
poetry install --extras verification  # With linting and type checking
```

## Configuration

Set the following environment variables:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional, for custom endpoints
```

Or create a `.env` file:

```
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
```

## Usage

### Basic Example

```python
from langgraph import UserManager, CodingAgentGraph

# Initialize user manager and create session
user_manager = UserManager()
session = user_manager.create_session_for_user(
    username="john_doe",
    work_directory="./workspaces/john"
)

# Create and run the agent
agent = CodingAgentGraph(session=session)

result = agent.run(
    task_description="Create a Python script that calculates the Fibonacci sequence up to n terms and saves it to a file"
)

if result["success"]:
    print(f"Task completed! Artifact: {result.get('artifact_path')}")
else:
    print(f"Task failed: {result.get('errors')}")
```

### Working with Context Files

Users can place files in the `input/` subdirectory of their work directory. The agent will automatically read these files as context:

```
workspaces/john/
├── input/
│   ├── data.csv      # User-provided input
│   └── config.json   # Configuration file
├── generated_code/   # Agent-generated code
└── artifacts/        # Generated output files
```

### Custom LLM Configuration

```python
from langgraph import LLMService, CodingAgentGraph

# Configure custom LLM
llm_service = LLMService(
    api_key="your-key",
    base_url="https://custom-llm-api.com/v1",
    model="custom-model-name",
    temperature=0.5,
)

# Use with agent
agent = CodingAgentGraph(session=session, llm_service=llm_service)
```

## How It Works

The agent follows a graph-of-thought workflow:

1. **Generate Code**: LLM generates Python code based on task description and context
2. **Verify Code**: Multi-layer verification (syntax, linting, security, LLM review)
3. **Execute Code**: Run the verified code in a sandboxed environment
4. **Verify Artifact**: LLM evaluates if output meets requirements
5. **Generate Response**: Create user-friendly summary with artifact path

If any step fails, the agent retries with feedback (up to 10 times).

```
generate_code → verify_code → execute_code → verify_artifact → generate_response
       ↑              ↑              ↑              ↑
       └──────────────┴──────────────┴──────────────┘ (retry loop)
```

## Running Tests

```bash
pytest langgraph/tests -v
```

## Development

### Code Style

This project follows PEP 8 guidelines. Format code with:

```bash
black langgraph/
isort langgraph/
```

### Adding New Nodes

To add new workflow steps:

1. Define the node function in `agent/nodes.py`
2. Add the node to the graph in `agent/graph.py`
3. Define routing logic for the new node

## License

MIT License
