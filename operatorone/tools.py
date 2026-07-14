
import base64
import io
from typing import Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

try:
    from PIL import ImageGrab
    import mss
    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False

from config import Config
from logger_config import op_logger

# Global reference to operator core (set by orchestrator)
_operator_core = None

def set_operator_core(core):
    """Set the global operator core reference for tools to use"""
    global _operator_core
    _operator_core = core


@dataclass
class ToolResult:
    """Result from tool execution"""
    success: bool
    output: str
    error: str
    context_data: Optional[dict] = None  # Additional data to pass to AI


@dataclass
class ToolInfo:
    """Information about a tool"""
    name: str
    handler: callable
    description: str
    usage: str
    icon: str = "🔧"


class ToolRegistry:
    """Registry of available /command tools"""

    _tools = {}  # name -> ToolInfo

    @classmethod
    def register(cls, name: str, handler, description: str = "", usage: str = "", icon: str = "🔧"):
        """Register a tool handler with metadata"""
        cls._tools[name] = ToolInfo(
            name=name,
            handler=handler,
            description=description,
            usage=usage,
            icon=icon
        )
        op_logger.logger.debug(f"Registered tool: /{name}")

    @classmethod
    def get(cls, name: str):
        """Get tool handler by name"""
        tool_info = cls._tools.get(name)
        return tool_info.handler if tool_info else None

    @classmethod
    def get_tool_info(cls, name: str) -> Optional[ToolInfo]:
        """Get full tool information"""
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> list:
        """List all registered tool names"""
        return list(cls._tools.keys())

    @classmethod
    def get_all_tools(cls) -> list:
        """Get all ToolInfo objects"""
        return list(cls._tools.values())

    @classmethod
    def search_tools(cls, query: str) -> list:
        """Search tools by prefix"""
        query_lower = query.lower()
        return [tool for tool in cls._tools.values()
                if tool.name.lower().startswith(query_lower)]

    @classmethod
    def is_tool_command(cls, text: str) -> bool:
        """Check if text is a tool command (starts with /)"""
        return text.strip().startswith('/')


class ImageTool:
    """
    /img tool - Screenshot and vision analysis
    Takes a screenshot and sends it to Mistral for analysis
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """
        Take screenshot and prepare for vision analysis.

        Args:
            user_prompt: User's question/prompt about the screenshot

        Returns:
            ToolResult with screenshot data encoded for AI
        """
        try:
            if not SCREENSHOT_AVAILABLE:
                return ToolResult(
                    success=False,
                    output="",
                    error="Screenshot tool requires PIL (Pillow) and mss libraries. Install with: pip install Pillow mss"
                )

            # Take screenshot
            op_logger.logger.info("📸 Taking screenshot...")

            # Use mss for full screen capture (faster than PIL)
            with mss.mss() as sct:
                # Capture primary monitor
                monitor = sct.monitors[1]  # Index 0 is all monitors, 1 is primary
                screenshot = sct.grab(monitor)

                # Convert to PIL Image
                from PIL import Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)

            # Resize if too large (Mistral has size limits)
            max_size = 1920
            if img.width > max_size or img.height > max_size:
                ratio = min(max_size / img.width, max_size / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                op_logger.logger.info(f"Resized screenshot to {new_size[0]}x{new_size[1]}")

            # Convert to base64
            buffered = io.BytesIO()
            img.save(buffered, format="PNG", optimize=True)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            op_logger.logger.info(f"✓ Screenshot captured ({img.width}x{img.height})")

            # Prepare prompt for AI
            if not user_prompt or not user_prompt.strip():
                prompt = "Describe what you see in this screenshot in detail."
            else:
                # User provided a question/context about the image
                prompt = user_prompt.strip()

            return ToolResult(
                success=True,
                output=f"📸 Screenshot captured ({img.width}x{img.height}). Analyzing with vision AI...",
                error="",
                context_data={
                    'image_base64': img_base64,
                    'prompt': prompt,
                    'tool': 'vision'
                }
            )

        except Exception as e:
            op_logger.logger.error(f"Screenshot failed: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to capture screenshot: {str(e)}"
            )


class HelpTool:
    """
    /help tool - Show available tools and usage
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show help for all available tools"""
        # Get all registered tools
        all_tools = ToolRegistry.get_all_tools()

        lines = ["🔧 OPERATOR Tools", "=" * 60, ""]

        # Group tools by category
        action_tools = []
        memory_tools = []
        info_tools = []
        data_tools = []

        for tool in all_tools:
            if tool.name in ['img']:
                action_tools.append(tool)
            elif tool.name in ['core', 'tiers']:
                memory_tools.append(tool)
            elif tool.name in ['stats', 'memory', 'profile', 'knowledge', 'sessions', 'storage', 'paths']:
                info_tools.append(tool)
            elif tool.name in ['forget', 'cleanup']:
                data_tools.append(tool)
            elif tool.name != 'help':  # Don't show help in help
                action_tools.append(tool)

        if action_tools:
            lines.append("📸 Action Tools:")
            for tool in action_tools:
                lines.append(f"  {tool.icon} {tool.usage}")
                lines.append(f"     {tool.description}")
                lines.append("")

        if memory_tools:
            lines.append("🧠 Memory System (v4.0):")
            for tool in memory_tools:
                lines.append(f"  {tool.icon} {tool.usage}")
                lines.append(f"     {tool.description}")
                lines.append("")

        if info_tools:
            lines.append("📊 Information Tools:")
            for tool in info_tools:
                lines.append(f"  {tool.icon} {tool.usage}")
                lines.append(f"     {tool.description}")
                lines.append("")

        if data_tools:
            lines.append("🗃️  Data Management:")
            for tool in data_tools:
                lines.append(f"  {tool.icon} {tool.usage}")
                lines.append(f"     {tool.description}")
                lines.append("")

        lines.append("=" * 60)

        return ToolResult(
            success=True,
            output="\n".join(lines),
            error=""
        )


class StatsTool:
    """
    /stats tool - Show execution statistics
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show OPERATOR execution statistics"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        stats = _operator_core.memory.get_statistics()
        message = f"""📊 OPERATOR Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Commands Executed: {stats['total_executed']}
Success Rate: {stats['success_rate']:.1%}
Learned Patterns: {stats['patterns_learned']}
Recorded Fixes: {stats['fixes_recorded']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

        return ToolResult(success=True, output=message, error="")


class MemoryTool:
    """
    /memory tool - Show learned patterns and fixes
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show memory summary with patterns and fixes"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        memory_dump = _operator_core.memory.get_memory_summary()
        return ToolResult(success=True, output=memory_dump, error="")


class ProfileTool:
    """
    /profile tool - Show user profile
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show what OPERATOR has stored about the user (self-managed memory)."""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        profile = _operator_core.memory.get_user_profile() or {}
        lines = ["=" * 60, "USER PROFILE", "=" * 60, ""]
        if not profile:
            lines.append("Nothing saved yet. OPERATOR stores what it learns about")
            lines.append("you in core memory as you talk — see /core.")
        else:
            for key, value in profile.items():
                lines.append(f"{key}: {value}")
        lines += ["", "=" * 60]
        return ToolResult(success=True, output="\n".join(lines), error="")


class KnowledgeTool:
    """
    /knowledge tool - View knowledge base facts
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show knowledge base facts, optionally filtered by category"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        # Parse category from user prompt
        category = user_prompt.strip().lower() if user_prompt.strip() else None
        if category and category not in ['personal', 'technical', 'general']:
            category = None

        facts = _operator_core.memory.get_facts(category=category)

        if not facts:
            message = f"No facts found" + (f" in category '{category}'" if category else "")
        else:
            lines = ["=" * 60, f"KNOWLEDGE BASE ({len(facts)} facts)", "=" * 60, ""]

            for fact in facts[:20]:  # Limit to 20 facts
                category_emoji = {
                    "personal": "👤",
                    "technical": "💻",
                    "general": "📝"
                }.get(fact.get("category", "general"), "📝")

                tier_label = {
                    1: "T1",
                    2: "T2",
                    3: "T3",
                    4: "T4"
                }.get(fact.get("tier", 2), "T2")

                confidence = int(fact.get("confidence", 0.5) * 100)
                content = fact.get("content", "")
                fact_id = fact.get("id", "")

                lines.append(f"{category_emoji} [{fact_id}|{tier_label}] {content} ({confidence}%)")

            if len(facts) > 20:
                lines.append(f"\n... and {len(facts) - 20} more facts")

            lines.append("")
            lines.append("=" * 60)
            lines.append("Usage: /knowledge [personal|technical|general]")
            lines.append("       /forget <fact_id>")
            message = "\n".join(lines)

        return ToolResult(success=True, output=message, error="")


class SessionsTool:
    """
    /sessions tool - View conversation sessions
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show conversation session history"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        sessions = _operator_core.memory.learning_system.learnings.get("conversation_memory", {}).get("sessions", [])

        if not sessions:
            message = "No conversation sessions recorded yet"
        else:
            lines = ["=" * 60, f"CONVERSATION SESSIONS ({len(sessions)})", "=" * 60, ""]

            for session in sessions[-10:]:  # Show last 10
                session_id = session.get("session_id", "")
                start = session.get("start_time", "")[:16]  # Trim to minutes
                summary = session.get("summary", "No summary")
                topics = ", ".join(session.get("key_topics", []))

                lines.append(f"[{session_id}] {start}")
                lines.append(f"  Summary: {summary}")
                if topics:
                    lines.append(f"  Topics: {topics}")
                lines.append("")

            lines.append("=" * 60)
            message = "\n".join(lines)

        return ToolResult(success=True, output=message, error="")


class ForgetTool:
    """
    /forget tool - Remove a fact from knowledge base
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Remove a fact by ID from knowledge base"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        fact_id = user_prompt.strip()
        if not fact_id:
            return ToolResult(
                success=False,
                output="",
                error="Usage: /forget <fact_id>\nUse /knowledge to see fact IDs"
            )

        if _operator_core.memory.forget_fact(fact_id):
            message = f"✓ Forgot fact {fact_id}"
        else:
            message = f"✗ Fact {fact_id} not found"

        return ToolResult(success=True, output=message, error="")


class StorageTool:
    """
    /storage tool - View storage statistics
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show storage statistics and health"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        stats = _operator_core.data_manager.get_storage_stats()

        lines = ["=" * 60, "STORAGE STATISTICS", "=" * 60, ""]
        lines.append(f"File Size: {stats['file_size_mb']} MB / {stats['max_file_size_mb']} MB")
        lines.append(f"Health: {stats['health'].upper()}")
        lines.append("")
        lines.append(f"Total Facts: {stats['total_facts']}")
        lines.append(f"  Tier 1 (Core):     {stats.get('tier_1_core', 0)}")
        lines.append(f"  Tier 2 (Active):   {stats.get('tier_2_active', 0)}")
        lines.append(f"  Tier 3 (Episodic): {stats.get('tier_3_episodic', 0)}")
        lines.append(f"  Tier 4 (Archive):  {stats.get('tier_4_archive', 0)}")
        lines.append("")
        lines.append(f"Sessions: {stats['total_sessions']}")
        lines.append(f"Long-term Memories: {stats['total_ltm']}")
        lines.append("")

        if stats['health'] == 'needs_cleanup':
            lines.append("⚠️  Storage is getting full. Run /cleanup to optimize.")
        else:
            lines.append("✓ Storage is healthy")

        lines.append("")
        lines.append("=" * 60)

        return ToolResult(success=True, output="\n".join(lines), error="")


class CleanupTool:
    """
    /cleanup tool - Run data maintenance
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Run data maintenance and optimization"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        lines = ["=" * 60, "RUNNING DATA MAINTENANCE...", "=" * 60, ""]

        # Create backup first
        backup_path = _operator_core.data_manager.create_backup()
        lines.append(f"✓ Created backup: {backup_path}")
        lines.append("")

        # Run maintenance
        results = _operator_core.data_manager.perform_maintenance()

        lines.append("Maintenance Results:")
        lines.append(f"  • Facts pruned: {results['facts_pruned']}")
        lines.append(f"  • Facts merged: {results['facts_merged']}")
        lines.append(f"  • Sessions archived: {results['sessions_archived']}")
        lines.append(f"  • Memories pruned: {results['ltm_pruned']}")
        lines.append("")

        # Show new stats
        stats = _operator_core.data_manager.get_storage_stats()
        lines.append(f"New file size: {stats['file_size_mb']} MB")
        lines.append(f"Health: {stats['health'].upper()}")
        lines.append("")
        lines.append("=" * 60)

        return ToolResult(success=True, output="\n".join(lines), error="")


class CoreTool:
    """
    /core tool - View core memory (Tier 1) contents
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show current core memory contents"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        core_section = _operator_core.core_memory.get_core_prompt_section()
        if not core_section:
            core_section = "(Core memory is empty)"

        total = _operator_core.core_memory.get_total_core_items()
        max_items = _operator_core.core_memory.MAX_CORE_ITEMS
        header = f"CORE MEMORY ({total}/{max_items} items)"
        lines = ["=" * 60, header, "=" * 60, "", core_section, "", "=" * 60]

        return ToolResult(success=True, output="\n".join(lines), error="")


class TiersTool:
    """
    /tiers tool - View memory tier breakdown
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show fact count breakdown by tier"""
        if not _operator_core:
            return ToolResult(success=False, output="", error="Operator core not initialized")

        stats = _operator_core.data_manager.get_storage_stats()

        lines = ["=" * 60, "MEMORY TIER BREAKDOWN", "=" * 60, ""]
        lines.append(f"Tier 1 - Core Memory:      {stats.get('tier_1_core', 0)} facts (always in prompt)")
        lines.append(f"Tier 2 - Active Knowledge:  {stats.get('tier_2_active', 0)} facts (retrieved per-query)")
        lines.append(f"Tier 3 - Episodic:          {stats.get('tier_3_episodic', 0)} facts")
        lines.append(f"Tier 4 - Archive:           {stats.get('tier_4_archive', 0)} facts (cold storage)")
        lines.append("")
        lines.append(f"Total: {stats['total_facts']} facts")
        lines.append("")
        lines.append("=" * 60)

        return ToolResult(success=True, output="\n".join(lines), error="")


class PathsTool:
    """
    /paths tool - Show data file locations
    """

    @staticmethod
    def execute(user_prompt: str = "") -> ToolResult:
        """Show where data files are stored"""
        try:
            from paths import Paths
            path_info = Paths.get_info()

            lines = ["=" * 60, "DATA FILE LOCATIONS", "=" * 60, ""]
            lines.append(f"Platform: {path_info['platform']}")
            lines.append("")
            lines.append(f"User Data Directory:")
            lines.append(f"  {path_info['user_data_dir']}")
            lines.append("")
            lines.append(f"Knowledge Base:")
            lines.append(f"  {path_info['learning_file']}")
            lines.append("")
            lines.append(f"Backups:")
            lines.append(f"  {path_info['backup_dir']}")
            lines.append("")
            lines.append(f"Logs:")
            lines.append(f"  {path_info['logs_dir']}")
            lines.append("")
            lines.append("=" * 60)
            lines.append("💡 All data is stored in user directory for app compatibility")

            return ToolResult(success=True, output="\n".join(lines), error="")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to get paths: {str(e)}")


# Register tools with metadata
ToolRegistry.register(
    name='img',
    handler=ImageTool.execute,
    description='Screenshot and AI vision analysis',
    usage='/img [question about the screen]',
    icon='📸'
)

ToolRegistry.register(
    name='help',
    handler=HelpTool.execute,
    description='Show available tools and usage',
    usage='/help',
    icon='❓'
)

# Information tools
ToolRegistry.register(
    name='stats',
    handler=StatsTool.execute,
    description='View execution statistics',
    usage='/stats',
    icon='📊'
)

ToolRegistry.register(
    name='memory',
    handler=MemoryTool.execute,
    description='View learned patterns and fixes',
    usage='/memory',
    icon='🧠'
)

ToolRegistry.register(
    name='profile',
    handler=ProfileTool.execute,
    description='View your user profile',
    usage='/profile',
    icon='👤'
)

ToolRegistry.register(
    name='knowledge',
    handler=KnowledgeTool.execute,
    description='View knowledge base facts',
    usage='/knowledge [category]',
    icon='📚'
)

ToolRegistry.register(
    name='sessions',
    handler=SessionsTool.execute,
    description='View conversation sessions',
    usage='/sessions',
    icon='💬'
)

ToolRegistry.register(
    name='storage',
    handler=StorageTool.execute,
    description='View storage statistics',
    usage='/storage',
    icon='💾'
)

ToolRegistry.register(
    name='paths',
    handler=PathsTool.execute,
    description='Show data file locations',
    usage='/paths',
    icon='📁'
)

# Memory system v4.0 tools
ToolRegistry.register(
    name='core',
    handler=CoreTool.execute,
    description='View core memory (Tier 1)',
    usage='/core',
    icon='🧠'
)

ToolRegistry.register(
    name='tiers',
    handler=TiersTool.execute,
    description='View memory tier breakdown',
    usage='/tiers',
    icon='📊'
)


# Data management tools
ToolRegistry.register(
    name='forget',
    handler=ForgetTool.execute,
    description='Remove a fact from knowledge',
    usage='/forget <fact_id>',
    icon='🗑️'
)

ToolRegistry.register(
    name='cleanup',
    handler=CleanupTool.execute,
    description='Run data maintenance',
    usage='/cleanup',
    icon='🧹'
)


def process_tool_command(text: str) -> Tuple[bool, Optional[ToolResult], str]:
    """
    Process a tool command if the input starts with /toolname.

    Only inputs that *begin* with a slash are treated as tool commands, so
    paths and URLs inside normal requests (e.g. "open C:/Users/...") are
    left for the AI.

    Returns:
        (is_tool_command, tool_result, remaining_text) tuple
    """
    import re

    match = re.match(r'^\s*/(\w+)(?:\s+(.*))?$', text, re.DOTALL)

    if not match:
        return False, None, text

    tool_name = match.group(1)
    tool_args = (match.group(2) or "").strip()

    handler = ToolRegistry.get(tool_name)

    if handler is None:
        available = ", ".join([f"/{t}" for t in ToolRegistry.list_tools()])
        return True, ToolResult(
            success=False,
            output="",
            error=f"Unknown tool: /{tool_name}\nAvailable tools: {available}\nType /help for more info."
        ), ""

    try:
        result = handler(tool_args)
        return True, result, ""
    except Exception as e:
        op_logger.logger.error(f"Tool /{tool_name} failed: {e}")
        return True, ToolResult(
            success=False,
            output="",
            error=f"Tool failed: {str(e)}"
        ), ""
