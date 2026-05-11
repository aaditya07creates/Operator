# OPERATOR Development Guide

Guide for developers who want to contribute to or extend OPERATOR.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Architecture](#project-architecture)
- [Code Style Guidelines](#code-style-guidelines)
- [Adding New Features](#adding-new-features)
- [Testing](#testing)
- [Common Development Tasks](#common-development-tasks)
- [Debugging Tips](#debugging-tips)
- [Contributing](#contributing)

---

## Development Setup

### Prerequisites

- Python 3.8+ (3.10+ recommended)
- Git
- Virtual environment tool (venv)
- Text editor or IDE (VS Code, PyCharm, etc.)

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd operatorone
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   ```

3. **Activate virtual environment**
   ```bash
   # Windows
   .venv\Scripts\activate

   # Linux/Mac
   source .venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up API keys**
   ```bash
   copy .env.example .env
   # Edit .env and add your API keys
   ```

6. **Verify installation**
   ```bash
   python operatorone/setup.py
   ```

---

## Project Architecture

### Directory Structure

```
operatorone/
├── operatorone/            # Main package
│   ├── __init__.py
│   ├── config.py          # Configuration constants
│   ├── logger_config.py   # Logging setup
│   │
│   ├── main.py            # GUI entry point
│   ├── operator.py        # CLI entry point
│   │
│   ├── ai_brain.py        # Core orchestration
│   ├── ai_engine.py       # AI communication
│   ├── ai_provider.py     # Provider abstraction
│   │
│   ├── executor.py        # Command execution
│   ├── validator.py       # Safety validation
│   ├── memory.py          # Memory interface
│   ├── learning_system.py # Persistent learning
│   │
│   ├── gui.py             # Tkinter GUI
│   ├── gui_utils.py       # GUI helpers
│   ├── voice_input.py     # Whisper integration
│   ├── key_ops.py         # Keyboard automation
│   ├── file_ops.py        # File operations
│   │
│   ├── utils.py           # Shared utilities
│   └── setup.py           # Installation check
│
├── README.md              # User documentation
├── COMMANDS.md            # Command syntax reference
├── DEVELOPMENT.md         # This file
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── .gitignore            # Git ignore rules
└── start.bat             # Quick start (Windows)
```

### Core Components

#### 1. AI Layer

**ai_provider.py** - Multi-provider abstraction
- `AIProviderFactory`: Creates provider instances
- `MistralProvider`: Mistral AI implementation
- `GeminiProvider`: Google Gemini implementation
- Easy to extend with new providers

**ai_engine.py** - AI communication orchestrator
- Manages conversation history
- Extracts commands from AI responses
- Handles streaming callbacks
- Processes learning blocks

**ai_brain.py** - Core business logic
- Coordinates all components
- Implements retry strategies
- Manages command flow

#### 2. Execution Layer

**executor.py** - Command execution engine
- Auto-detects command types
- Handles file operations, keyboard ops, shell commands
- Integrates with learning system
- Multi-strategy retry logic

**validator.py** - Safety validation
- Blocks destructive commands
- Validates file paths
- Prevents command injection

**file_ops.py** - File creation and execution
- Creates files with content
- Opens files with default apps
- Handles different file types

**key_ops.py** - Keyboard automation
- Uses pynput for cross-platform support
- Press, combo, type, sequence operations
- Key name mapping

#### 3. Memory Layer

**learning_system.py** - Persistent storage
- JSON-based data structure
- Tracks apps, patterns, fixes, tasks
- Version migration support
- Automatic cleanup

**memory.py** - High-level interface
- Typed Python objects
- Clean API over LearningSystem
- Error categorization

#### 4. UI Layer

**gui.py** - Tkinter interface
- Floating capsule design
- Global hotkeys (Alt double-tap)
- Voice input (Page Down push-to-talk)
- Real-time streaming display

**voice_input.py** - Speech recognition
- OpenAI Whisper (offline)
- Push-to-talk recording
- Audio streaming

---

## Code Style Guidelines

### General Principles

1. **Follow PEP 8** for Python code style
2. **Use type hints** for all public methods and functions
3. **Write docstrings** for all modules and public APIs (Google style)
4. **Use descriptive names** for variables and functions
5. **Keep functions focused** - one responsibility per function
6. **Avoid premature optimization** - clarity over cleverness

### Type Hints

```python
# Good
def execute_command(self, command: str, timeout: int = 30) -> ExecutionResult:
    """Execute a command with optional timeout."""
    pass

# Bad
def execute_command(self, command, timeout=30):
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def categorize_error(error: str) -> str:
    """
    Categorize error message by type.

    Analyzes error text and returns a standardized category string
    for pattern matching and fixing.

    Args:
        error: Error message text from command output or exceptions

    Returns:
        str: Error category identifier (not_found, access_denied, etc.)

    Example:
        >>> categorize_error("'spotify' is not recognized")
        'not_found'
    """
    pass
```

### Logging

Use `op_logger` instead of `print()`:

```python
from logger_config import op_logger

# Good
op_logger.logger.info("Starting voice recording")
op_logger.logger.warning("API key not configured")
op_logger.logger.error(f"Failed to execute: {e}")

# Bad
print("Starting voice recording")
print(f"Error: {e}")
```

### Constants

Extract magic numbers to `config.py`:

```python
# config.py
class GUI:
    WINDOW_WIDTH = 600
    WINDOW_HEIGHT = 45
    CAPSULE_RADIUS = 25

# gui.py - Good
self.canvas.create_rounded_rectangle(0, 0, Config.GUI.WINDOW_WIDTH, ...)

# gui.py - Bad
self.canvas.create_rounded_rectangle(0, 0, 600, ...)
```

### Error Handling

Catch specific exceptions:

```python
# Good
try:
    result = self.execute(command)
except FileNotFoundError as e:
    op_logger.logger.error(f"File not found: {e}")
except PermissionError as e:
    op_logger.logger.error(f"Permission denied: {e}")

# Bad
try:
    result = self.execute(command)
except:
    pass
```

---

## Adding New Features

### Adding a New AI Provider

1. **Create provider class** in `ai_provider.py`:

```python
class ClaudeProvider(BaseAIProvider):
    def __init__(self):
        # Initialize Claude client
        pass

    def generate(self, messages, stream_callback=None):
        # Implement Claude API call
        pass
```

2. **Register in factory**:

```python
class AIProviderFactory:
    @staticmethod
    def create_provider(provider_name: str):
        if provider_name == 'claude':
            return ClaudeProvider()
        # ... existing providers
```

3. **Add configuration** to `config.py`:

```python
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY', '')
CLAUDE_MODEL = "claude-3-opus-20240229"
```

4. **Update documentation** in README.md and .env.example

### Adding a New Command Type

1. **Add detection logic** in `executor.py`:

```python
def _detect_command_type(self, command: str) -> CommandType:
    # ... existing checks
    if command.startswith('http:'):
        return CommandType.HTTP_REQUEST
```

2. **Add execution handler**:

```python
def execute(self, command: str) -> ExecutionResult:
    cmd_type = self._detect_command_type(command)

    if cmd_type == CommandType.HTTP_REQUEST:
        return self._execute_http_request(command)
```

3. **Implement the handler**:

```python
def _execute_http_request(self, command: str) -> ExecutionResult:
    import requests
    # ... implementation
```

4. **Update COMMANDS.md** with syntax documentation

### Adding GUI Customization

1. **Add constants** to `config.py`:

```python
class GUI:
    THEME_DARK = True
    BG_COLOR_DARK = "#1e1e1e"
    BG_COLOR_LIGHT = "#ffffff"
```

2. **Use in gui.py**:

```python
bg_color = Config.GUI.BG_COLOR_DARK if Config.GUI.THEME_DARK else Config.GUI.BG_COLOR_LIGHT
```

---

## Testing

### Manual Testing

Run the setup check:
```bash
python operatorone/setup.py
```

Test basic commands:
```bash
# CLI mode
python operatorone/main.py --cli

# Test commands:
open notepad
screenshot
create a simple webpage
```

### Debug Mode

Enable verbose logging:
```bash
python operatorone/main.py --debug
```

### Testing Checklist

- [ ] GUI opens with Alt double-tap
- [ ] Voice input works (hold Page Down)
- [ ] Text commands execute correctly
- [ ] File operations create and open files
- [ ] Keyboard operations work as expected
- [ ] Learning system saves and retrieves data
- [ ] Error handling displays appropriate messages
- [ ] No crashes or unhandled exceptions

---

## Common Development Tasks

### Modify System Prompt

Edit `config.py`, method `get_system_prompt()`:

```python
@staticmethod
def get_system_prompt() -> str:
    return """
    You are OPERATOR, an AI assistant...
    [Your custom prompt here]
    """
```

### Change Default AI Model

Edit `config.py`:

```python
MISTRAL_MODEL = "mistral-large-latest"  # or other model
GEMINI_MODEL = "gemini-2.0-flash-thinking-exp"
```

### Adjust Command Timeout

Edit `config.py`:

```python
COMMAND_TIMEOUT = 60  # seconds
```

### Clear Learning Data

```bash
# Delete the learning file
del operatorone\operator_learnings.json

# OPERATOR will create a fresh one on next run
```

### Reset Configuration

```bash
# Remove environment variables
set MISTRAL_API_KEY=
set GEMINI_API_KEY=

# Or delete .env file
del .env
```

---

## Debugging Tips

### Enable Verbose Logging

```python
# In logger_config.py, change log level
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Learning Data

```python
import json
with open('operator_learnings.json') as f:
    data = json.load(f)
    print(json.dumps(data, indent=2))
```

### Test AI Responses

```python
from ai_engine import AIEngine
from learning_system import LearningSystem

learning = LearningSystem()
engine = AIEngine('mistral', learning)
response = engine.generate_commands("open spotify")
print(response.commands)
```

### Debug GUI Issues

1. Check if Tkinter is installed:
   ```bash
   python -m tkinter
   ```

2. Test without global hotkeys:
   ```bash
   python operatorone/main.py --cli
   ```

3. Check Windows focus issues:
   ```python
   # In gui.py, add debug logging to _force_focus()
   op_logger.logger.debug("Forcing window focus...")
   ```

### Common Issues

**Voice input not working**:
- Check dependencies: `pip list | findstr whisper`
- Test microphone: Check Windows sound settings
- Verify Page Down key works

**Commands not executing**:
- Check learning system logs
- Verify Windows permissions
- Try simpler commands first (e.g., "open notepad")

**GUI not appearing**:
- Check for Alt key conflicts
- Try `--cli` mode first
- Verify Tkinter installation

---

## Contributing

### Before Submitting

1. **Test thoroughly** - Run setup.py and test basic functionality
2. **Follow code style** - Use type hints, docstrings, logging
3. **Update documentation** - README, COMMANDS, or DEVELOPMENT as needed
4. **No hardcoded secrets** - Use environment variables
5. **Clean commit history** - Descriptive commit messages

### Commit Message Format

```
[Type] Brief description

Longer explanation if needed

- Bullet points for details
- Reference issue numbers if applicable
```

Types: `[Feature]`, `[Fix]`, `[Docs]`, `[Refactor]`, `[Test]`

Example:
```
[Feature] Add OpenAI provider support

Implements OpenAI GPT-4 as a new AI provider option.

- Added OpenAIProvider class to ai_provider.py
- Updated config.py with OpenAI settings
- Added documentation to README.md
```

### Pull Request Checklist

- [ ] Code follows style guidelines
- [ ] All functions have docstrings
- [ ] Type hints are used
- [ ] Logging instead of print statements
- [ ] No hardcoded secrets
- [ ] Documentation updated
- [ ] Tested manually
- [ ] No breaking changes (or documented if necessary)

---

## Architecture Decisions

### Why JSON for Learning System?

- **Simple**: Easy to read and edit manually
- **Portable**: Works across platforms
- **Human-readable**: Can inspect and debug easily
- **No dependencies**: No database setup required

Future: May migrate to SQLite for larger datasets.

### Why Tkinter for GUI?

- **Built-in**: Ships with Python, no extra dependencies
- **Lightweight**: Small footprint, fast startup
- **Cross-platform**: Works on Windows, Linux, Mac
- **Sufficient**: Meets current GUI needs

### Why Two Entry Points (main.py and operator.py)?

- `main.py`: GUI mode with voice and hotkeys
- `operator.py`: CLI mode for terminal-only usage
- Allows users to choose based on environment

### Why Both Mistral and Gemini?

- **Choice**: Different models for different needs
- **Fallback**: If one provider has issues
- **Comparison**: Users can test which works better
- **Future-proof**: Easy to add more providers

---

## Future Development Ideas

### High Priority

- [ ] Add unit tests (pytest)
- [ ] Linux/Mac GUI support improvements
- [ ] SQLite backend for learning system
- [ ] More AI providers (OpenAI, Claude)
- [ ] Plugin system for custom commands

### Medium Priority

- [ ] GUI configuration editor
- [ ] Command history search
- [ ] Async learning system
- [ ] Better error recovery
- [ ] Performance optimizations

### Low Priority

- [ ] Multi-language support
- [ ] Cloud sync for learning data
- [ ] Mobile companion app
- [ ] Advanced analytics dashboard

---

## Resources

- **Python Docs**: https://docs.python.org/3/
- **Tkinter Docs**: https://docs.python.org/3/library/tkinter.html
- **Mistral API**: https://docs.mistral.ai/
- **Gemini API**: https://ai.google.dev/docs
- **Whisper**: https://github.com/openai/whisper
- **pynput**: https://pynput.readthedocs.io/

---

## Getting Help

- **Issues**: Check existing issues or create a new one
- **Documentation**: See README.md and COMMANDS.md
- **Setup Problems**: Run `python operatorone/setup.py`
- **Debugging**: Enable debug mode with `--debug` flag

---

**Happy coding! 🚀**
