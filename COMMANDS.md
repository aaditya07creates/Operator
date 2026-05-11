# OPERATOR Command Reference

Complete guide to OPERATOR's special command syntax and natural language capabilities.

## Table of Contents

- [Natural Language Commands](#natural-language-commands)
- [File Operations](#file-operations)
- [Keyboard Operations](#keyboard-operations)
- [Available Keys Reference](#available-keys-reference)
- [Command Examples](#command-examples)
- [Tips and Best Practices](#tips-and-best-practices)

---

## Natural Language Commands

OPERATOR understands natural language and automatically translates your intent into system commands.

### Application Launching

```
"open spotify"
"start chrome"
"launch notepad"
"run calculator"
"I want to listen to music"
```

**How it works**: OPERATOR uses AI to understand your intent and checks its learning database for successful launch strategies. If it hasn't learned how to open an app, it tries multiple strategies automatically.

### Common Actions

```
"screenshot this"           # Triggers Win+Shift+S
"screenshot"                # Same as above
"copy this"                 # Triggers Ctrl+C
"paste here"                # Triggers Ctrl+V
"close window"              # Triggers Alt+F4
"minimize window"           # Triggers Win+Down
"maximize window"           # Triggers Win+Up
```

### File Creation (Natural Language)

```
"create a button webpage"
"make a python script that prints hello world"
"create an html page with a red background"
"make a text file with my shopping list"
```

**How it works**: The AI generates appropriate file content based on your description, then uses file operations to create and open the file.

---

## File Operations

Advanced file commands using special syntax for precise control.

### Syntax Format

```
file:<operation>:<path>:<content>
```

### Create File

**Syntax**: `file:create:<filename>:<content>`

**Examples**:
```
file:create:script.py:print('Hello World')
file:create:C:\Users\aadit\Desktop\note.txt:Remember to buy milk
file:create:webpage.html:<html><body><h1>Test</h1></body></html>
```

**Default location**: If no full path is provided, files are created in:
```
C:\Users\aadit\OperatorPrograms\
```

**Behavior**: Creates the file with the specified content. Does NOT automatically open it.

### Run File

**Syntax**: `file:run:<path>`

**Examples**:
```
file:run:script.py
file:run:C:\Users\aadit\Documents\report.html
file:run:webpage.html
```

**Behavior**:
- Opens the file with the default associated application
- `.html` files open in default browser
- `.py` files may execute or open in default editor
- `.txt` files open in Notepad

### Create and Run

**Syntax**: `file:create-run:<filename>:<content>`

**Examples**:
```
file:create-run:button.html:<html><body><button>Click Me</button></body></html>
file:create-run:test.py:for i in range(10): print(i)
file:create-run:note.txt:This is a test note
```

**Behavior**: Creates the file AND immediately opens it.

**Use case**: Perfect for quick prototyping or testing code snippets.

### Supported File Types

| Extension | Behavior | Opens In |
|-----------|----------|----------|
| `.html`, `.htm` | Opens in browser | Default browser |
| `.py` | Executes or opens | Python/Editor |
| `.txt` | Opens for editing | Notepad |
| `.js` | Opens in editor | Default editor |
| `.css` | Opens in editor | Default editor |
| `.json` | Opens in editor | Default editor |
| `.bat`, `.cmd` | Executes | Command Prompt |

---

## Keyboard Operations

Automate keyboard input with precise control over keys, combinations, and sequences.

### Press Single Key

**Syntax**: `key:press:<keyname>`

**Examples**:
```
key:press:enter
key:press:escape
key:press:space
key:press:tab
key:press:a
key:press:5
```

**Behavior**: Presses and releases the specified key once.

### Key Combination (Chord)

**Syntax**: `key:combo:<modifier1>:<modifier2>:<key>`

**Description**: Holds all keys simultaneously (like Ctrl+C).

**Examples**:
```
key:combo:ctrl:c                # Copy
key:combo:ctrl:v                # Paste
key:combo:ctrl:shift:escape     # Open Task Manager
key:combo:win:shift:s           # Screenshot tool
key:combo:alt:f4                # Close window
key:combo:ctrl:alt:delete       # Security screen
key:combo:win:l                 # Lock computer
```

**Order**: Modifiers are pressed first, then the main key.

### Type Text

**Syntax**: `key:type:<text to type>`

**Examples**:
```
key:type:Hello World!
key:type:This is a test
key:type:user@example.com
key:type:C:\Users\aadit\Documents
```

**Behavior**: Types the text character by character, as if using a keyboard.

**Special characters**: Most special characters work (!, @, #, etc.)

**Limitations**:
- Very long text may be slow
- Some special Unicode characters may not work
- Typing speed depends on system

### Key Sequence

**Syntax**: `key:seq:<key1>:<key2>:<key3>...`

**Description**: Presses keys one after another (NOT simultaneously).

**Examples**:
```
key:seq:alt:f4              # Press Alt, release, then press F4, release
key:seq:win:r               # Open Run dialog (Win, then R)
key:seq:5:plus:5:enter      # Calculator: type 5, +, 5, Enter
```

**Difference from combo**:
- `key:combo:win:r` = Hold Win, press R, release both (shortcut)
- `key:seq:win:r` = Press Win, release, press R, release (two separate presses)

**Use case**: When you need keys pressed in order, not held together.

---

## Available Keys Reference

### Modifier Keys

| Key Name | Aliases | Description |
|----------|---------|-------------|
| `ctrl` | `control` | Control key |
| `shift` | - | Shift key |
| `alt` | - | Alt key |
| `win` | `windows`, `cmd` | Windows/Command key |

### Letter Keys

```
a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x, y, z
```

**Note**: Use lowercase in syntax. OPERATOR handles shift automatically for uppercase.

### Number Keys

```
0, 1, 2, 3, 4, 5, 6, 7, 8, 9
```

### Special Keys

| Key Name | Aliases | Description |
|----------|---------|-------------|
| `enter` | `return` | Enter/Return key |
| `space` | `spacebar` | Space bar |
| `tab` | - | Tab key |
| `backspace` | - | Backspace key |
| `delete` | `del` | Delete key |
| `escape` | `esc` | Escape key |
| `insert` | - | Insert key |
| `home` | - | Home key |
| `end` | - | End key |
| `pageup` | - | Page Up key |
| `pagedown` | - | Page Down key |

### Arrow Keys

```
up, down, left, right
```

### Function Keys

```
f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12
```

### Lock Keys

```
capslock, numlock, scrolllock
```

### Multimedia Keys (if supported)

```
volumeup, volumedown, volumemute
play, pause, next, previous
```

**Note**: Multimedia key support depends on your keyboard and system.

### Other Keys

```
printscreen, pause, menu
```

---

## Command Examples

### Common Workflows

#### 1. Screenshot and Open Paint
```
Natural: "take a screenshot"
OPERATOR executes: key:combo:win:shift:s
```

#### 2. Create Quick Webpage
```
Natural: "create a red button webpage"
OPERATOR executes: file:create-run:button.html:<html>...[generates HTML]...</html>
```

#### 3. Open App and Type
```
User: "open notepad and type hello world"
OPERATOR executes:
  start notepad
  timeout /t 2 /nobreak
  key:type:Hello World
```

#### 4. Calculator Workflow
```
User: "use calculator to add 25 and 17"
OPERATOR executes:
  start calc
  timeout /t 1 /nobreak
  key:seq:2:5:plus:1:7:enter
```

#### 5. Copy File Path
```
User: "type my documents path"
OPERATOR executes: key:type:C:\Users\aadit\Documents
```

### Advanced Examples

#### Multi-Step File Creation
```
file:create:script.py:import os\nprint(os.getcwd())
file:run:script.py
```

#### Custom Keyboard Shortcut
```
key:combo:ctrl:shift:alt:f12
```

#### Long Text Entry
```
key:type:Dear Sir or Madam,\nI am writing to inform you...
```

**Note**: Use `\n` for newlines in typed text (support depends on context).

---

## Tips and Best Practices

### File Operations

1. **Use full paths for important files**
   ```
   # Good
   file:create:C:\Projects\important.py:code here

   # Risky (uses default location)
   file:create:important.py:code here
   ```

2. **Escape special characters in content**
   ```
   # If content contains colons, use natural language instead
   Natural: "create a python script that prints time"
   vs
   file:create:time.py:print("Time: 12:30")  # Colon may cause parsing issues
   ```

3. **Use create-run for immediate feedback**
   ```
   file:create-run:test.html:<html>...</html>
   # Immediately see the result in browser
   ```

### Keyboard Operations

1. **Wait before typing in new windows**
   ```
   # OPERATOR automatically adds delays when needed
   # But for manual commands:
   start notepad
   timeout /t 2 /nobreak
   key:type:Hello
   ```

2. **Use combo for shortcuts, seq for separate presses**
   ```
   key:combo:ctrl:c     # Copy (Ctrl held with C)
   key:seq:win:r        # Press Win, then R separately
   ```

3. **Test keyboard commands in safe environments**
   ```
   # Test in Notepad first
   open notepad
   key:combo:ctrl:a     # Select all
   key:press:delete     # Delete
   ```

### Natural Language

1. **Be specific for complex tasks**
   ```
   # Good
   "create an html page with a red button that says Click Me"

   # Vague
   "make a website"
   ```

2. **Use simple commands for common tasks**
   ```
   "screenshot"  # Better than "take a screenshot of my screen"
   "open spotify"  # Better than "I want to launch the Spotify application"
   ```

3. **Let AI handle file content**
   ```
   # Instead of:
   file:create:page.html:<html><body>...</body></html>

   # Use:
   "create a simple webpage with a heading"
   # AI generates better HTML
   ```

### Debugging

1. **Check learning system logs**
   ```
   # Location: operator_learnings.json
   # Contains successful commands and error fixes
   ```

2. **Use CLI mode for testing**
   ```
   python operatorone/main.py --cli
   # See raw AI output and command parsing
   ```

3. **Enable debug logging**
   ```
   python operatorone/main.py --debug
   # Verbose logging to console
   ```

### Security

1. **Avoid sensitive data in commands**
   ```
   # BAD - Don't type passwords
   key:type:mySecretPassword123

   # Use clipboard manually instead
   ```

2. **Review AI-generated commands**
   ```
   # In debug mode, you see commands before execution
   # Useful for verifying intent
   ```

---

## Command Resolution Flow

When you give OPERATOR a command:

1. **Natural Language Processing**
   - AI analyzes your intent
   - Generates structured command(s)
   - May produce multiple commands for complex tasks

2. **Command Type Detection**
   - Checks for `file:`, `key:` prefixes
   - Identifies standard shell commands
   - Detects application launch requests

3. **Learning System Consultation**
   - Checks if similar command succeeded before
   - Retrieves preferred strategies for apps
   - Applies known error fixes

4. **Validation**
   - Safety check (blocks destructive commands)
   - Path validation for file operations
   - Key name validation for keyboard ops

5. **Execution**
   - Executes the command
   - Monitors for errors
   - Records result in learning system

6. **Retry Logic** (if needed)
   - Tries alternative strategies
   - Consults AI for error fixes
   - Updates learning system with solutions

---

## Syntax Summary

| Command Type | Syntax | Example |
|--------------|--------|---------|
| Create file | `file:create:path:content` | `file:create:script.py:print('hi')` |
| Run file | `file:run:path` | `file:run:webpage.html` |
| Create & run | `file:create-run:path:content` | `file:create-run:test.py:code` |
| Press key | `key:press:keyname` | `key:press:enter` |
| Key combo | `key:combo:key1:key2` | `key:combo:ctrl:c` |
| Type text | `key:type:text` | `key:type:Hello` |
| Key sequence | `key:seq:key1:key2` | `key:seq:win:r` |
| Shell command | (no prefix) | `start notepad` |
| Natural language | (plain English) | `"open spotify"` |

---

## Troubleshooting Commands

### File Operations

**Problem**: File created in wrong location
```
Solution: Use full path
file:create:C:\Users\aadit\Desktop\file.txt:content
```

**Problem**: File not opening after create-run
```
Solution: Check file association
- .html files need a browser
- .py files need Python installed
```

**Problem**: Content contains colons and breaks parsing
```
Solution: Use natural language instead
"create a python script that prints the current time"
```

### Keyboard Operations

**Problem**: Key combination not working
```
Solution: Verify key names from Available Keys Reference
Use exact names: ctrl, shift, alt, win
```

**Problem**: Typing too fast/slow
```
Note: Timing is automatic
If issues persist, use natural language:
"type hello world slowly"
```

**Problem**: Special characters not typing
```
Solution: Some Unicode chars not supported
Use standard ASCII characters
```

### General

**Problem**: Command not executing
```
1. Check syntax carefully (colons, spelling)
2. Run in --debug mode to see parsing
3. Try natural language version first
4. Check learning system logs
```

**Problem**: AI generates wrong command
```
Solution: Be more specific in natural language
"create an HTML file with a red button"
vs
"make a button"
```

---

## Getting Help

- **Setup issues**: Run `python operatorone/setup.py`
- **Syntax questions**: Refer to this document
- **AI behavior**: See `README.md` for provider configuration
- **Bug reports**: Check learning system logs first

For more information, see:
- `README.md` - General documentation
- `DEVELOPMENT.md` - Developer guide and advanced usage
