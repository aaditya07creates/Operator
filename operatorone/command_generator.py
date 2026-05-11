
from typing import List, Optional, Callable
from dataclasses import dataclass
import re

from config import Config
from learning_system import LearningSystem
from context_retrieval import ContextRetriever
from core_memory import CoreMemory
from logger_config import op_logger


@dataclass
class AIResponse:
    """Structured AI response"""
    explanation: str  # AI's natural language explanation
    commands: List[str]  # Extracted commands to execute
    reasoning: Optional[str] = None  # AI's reasoning (if verbose)
    wants_reevaluation: bool = False  # Whether AI requested re-evaluation after execution


class AIEngine:
    """
    Manages AI communication with clean separation of concerns.
    No more JSON parsing from text - just extract commands cleanly.
    """

    def __init__(self, provider_name: str, memory: LearningSystem, core_memory: CoreMemory = None):
        self.provider_name = provider_name
        self.memory = memory
        self.core_memory = core_memory
        self.conversation_history = []

        # Initialize smart context retrieval
        self.context_retriever = ContextRetriever(memory.learning_system)

        # Import the actual AI provider
        from llm_providers import AIProviderFactory
        self.provider = AIProviderFactory.create_provider(provider_name)

        # Initialize with system prompt
        self._initialize_system_prompt()

        op_logger.kv("AI Provider", provider_name)

    def _initialize_system_prompt(self):
        """Initialize AI with system prompt including learned knowledge and core memory"""
        # Build base system prompt
        system_prompt = Config.get_system_prompt()

        # Inject core memory (Tier 1 - always present)
        if self.core_memory:
            core_section = self.core_memory.get_core_prompt_section()
            if core_section:
                system_prompt += f"\n\n{core_section}"

        # Add command memory context (apps, tasks, fixes)
        command_context = self.memory.get_context_for_ai()
        if command_context:
            system_prompt += f"\n\n## Your Learned Knowledge\n{command_context}"

        # Add to provider
        self.provider.add_system_message(system_prompt)

        op_logger.kv("System Prompt", f"{len(system_prompt)} chars")

    def _get_contextual_prefix(self, user_input: str) -> str:
        """
        Get relevant context to prepend to user query.

        Returns context string to help AI make better decisions.
        Does NOT modify system message (preserves conversation history).
        """
        # Get smart context based on user query
        smart_context = self.context_retriever.get_relevant_context_for_ai(
            query=user_input,
            limit=5  # Reduced to 5 for less token usage
        )

        if smart_context:
            # Return as context hint, not as system message replacement
            return f"[Context: {smart_context.strip()}]\n\n"

        return ""

    async def generate_commands(
        self,
        user_input: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> AIResponse:
        """
        Generate commands for user's task.

        Args:
            user_input: User's natural language request
            stream_callback: Optional callback for streaming responses

        Returns:
            AIResponse with explanation and commands
        """

        # Trim history if needed
        self.provider.trim_history(Config.MAX_CHAT_HISTORY)

        # Prepend relevant context from Tier 2 active knowledge
        contextual_prefix = self._get_contextual_prefix(user_input)
        if contextual_prefix:
            user_input = contextual_prefix + user_input

        # Send message to AI
        response_text = self.provider.send_message(user_input, stream_callback)

        # Check if AI wants re-evaluation after command execution
        wants_reevaluation = '<re-evaluate>' in response_text

        # Process learning blocks (if any)
        self._process_learning_blocks(response_text)

        # Extract commands
        commands = self._extract_commands(response_text)

        # Get explanation (text before first command or all text if no commands)
        explanation = self._extract_explanation(response_text, commands)

        return AIResponse(
            explanation=explanation,
            commands=commands,
            reasoning=None,  # Could add reasoning extraction if needed
            wants_reevaluation=wants_reevaluation
        )

    async def generate_vision_response(
        self,
        prompt: str,
        image_base64: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Generate vision analysis response with image.
        Uses the existing conversation history system automatically.

        Args:
            prompt: User's question about the image
            image_base64: Base64-encoded image data
            stream_callback: Optional callback for streaming responses

        Returns:
            str with AI's analysis of the image
        """
        op_logger.logger.info("Sending vision request to AI...")

        # Trim history if needed (same as normal messages)
        self.provider.trim_history(Config.MAX_CHAT_HISTORY)

        # Send vision message - provider handles history automatically
        response_text = self.provider.send_vision_message(
            prompt=prompt,
            image_base64=image_base64,
            stream_callback=stream_callback
        )

        return response_text

    async def suggest_fix(
        self,
        failed_command: str,
        error: str,
        original_intent: str,
        attempted_fixes: List = None
    ) -> AIResponse:
        """
        Ask AI to suggest fix for failed command.

        Args:
            failed_command: The command that failed
            error: Error message from execution
            original_intent: User's original request
            attempted_fixes: List of fixes already tried (with errors)

        Returns:
            AIResponse with alternative approach
        """

        # Build context-rich fix request with full history
        fix_request = f"""The command failed. I need your help to find an alternative approach.

ORIGINAL TASK: {original_intent}

INITIAL COMMAND THAT FAILED:
Command: {failed_command}
Error: {error}
"""

        # Include all attempted fixes with their errors
        if attempted_fixes and len(attempted_fixes) > 0:
            fix_request += f"\n\nATTEMPTED FIXES (all failed):\n"
            for i, fix in enumerate(attempted_fixes[:5], 1):  # Show up to 5 attempts
                # Handle both dict and CommandFix object
                if isinstance(fix, dict):
                    fix_cmd = fix.get('fix', fix.get('fixed_command', 'unknown'))
                    fix_error = fix.get('error', 'No error recorded')
                else:  # CommandFix object
                    fix_cmd = fix.fixed_command
                    fix_error = 'No error recorded'  # CommandFix doesn't store error message
                fix_request += f"{i}. Command: {fix_cmd}\n"
                fix_request += f"   Error: {fix_error}\n\n"

        fix_request += """
IMPORTANT: You must suggest a COMPLETELY DIFFERENT approach that I haven't tried yet.

Think through these possibilities:
1. Is the app name/path correct? Maybe try the full path
2. Should I use PowerShell with Get-AppxPackage for UWP apps?
3. Does the app need to be started from a specific directory?
4. Is there an alias or shortcut I should use?
5. Should I try 'explorer.exe' to open a file/folder?
6. Does this require administrator privileges?

Provide ONE alternative command in a <command> tag. Make it significantly different from what I've already tried.
If you genuinely cannot think of another approach, explain why in your response without providing a command."""

        # Get AI's suggestion
        response_text = self.provider.send_message(fix_request)

        # Extract commands
        commands = self._extract_commands(response_text)
        explanation = self._extract_explanation(response_text, commands)

        return AIResponse(
            explanation=explanation,
            commands=commands
        )

    def _extract_commands(self, response: str) -> List[str]:
        """Extract commands from <command>...</command> tags"""
        commands = re.findall(r'<command>(.*?)</command>', response, re.DOTALL)
        clean_commands = [cmd.strip() for cmd in commands if cmd.strip()]

        # Safety check: If we get an unreasonable number of commands, something went wrong
        if len(clean_commands) > 10:
            op_logger.logger.warning(f"⚠️  AI generated {len(clean_commands)} commands - this seems wrong!")
            op_logger.logger.warning("   Truncating to first 3 commands for safety")
            clean_commands = clean_commands[:3]

        return clean_commands

    def _extract_explanation(self, response: str, commands: List[str]) -> str:
        """Extract explanation text (everything before first command or all text)"""
        if not commands:
            # No commands, return cleaned response
            cleaned = self._clean_response_text(response)
            return cleaned

        # Find position of first command tag
        first_cmd_match = re.search(r'<command>', response)
        if first_cmd_match:
            # Get text before first command
            explanation = response[:first_cmd_match.start()].strip()
            return self._clean_response_text(explanation)

        return self._clean_response_text(response)

    def _clean_response_text(self, text: str) -> str:
        """Remove all XML-like tags from response text"""
        # Remove learning tags
        text = re.sub(r'<learn>.*?</learn>', '', text, flags=re.DOTALL)
        text = re.sub(r'<unlearn>.*?</unlearn>', '', text, flags=re.DOTALL)
        text = re.sub(r'<update>.*?</update>', '', text, flags=re.DOTALL)
        text = re.sub(r'<re-evaluate>.*?</re-evaluate>', '', text, flags=re.DOTALL)

        return text.strip()

    def _process_learning_blocks(self, response: str):
        """
        Process learning blocks from AI response.
        This is kept separate from command execution.
        """

        # Extract learning blocks
        learn_blocks = re.findall(r'<learn>(.*?)</learn>', response, re.DOTALL)
        for block in learn_blocks:
            try:
                import json
                learning_data = json.loads(block.strip())

                if self.memory.add_learning_from_ai(learning_data):
                    op_logger.learning_action(
                        "Learned",
                        learning_data.get("type", "unknown"),
                        learning_data.get("note", "")
                    )
            except json.JSONDecodeError as e:
                op_logger.logger.warning(f"Failed to parse learning block: {e}")
            except Exception as e:
                op_logger.logger.error(f"Error processing learning: {e}")

        # Extract unlearn blocks
        unlearn_blocks = re.findall(r'<unlearn>(.*?)</unlearn>', response, re.DOTALL)
        for block in unlearn_blocks:
            try:
                import json
                unlearn_data = json.loads(block.strip())

                if self.memory.remove_learning_from_ai(unlearn_data):
                    op_logger.learning_action(
                        "Unlearned",
                        unlearn_data.get("type", "unknown"),
                        unlearn_data.get("note", "")
                    )
            except Exception as e:
                op_logger.logger.error(f"Error processing unlearn: {e}")

        # Extract update blocks
        update_blocks = re.findall(r'<update>(.*?)</update>', response, re.DOTALL)
        for block in update_blocks:
            try:
                import json
                update_data = json.loads(block.strip())

                if self.memory.update_learning_from_ai(update_data):
                    op_logger.learning_action(
                        "Updated",
                        update_data.get("type", "unknown"),
                        update_data.get("note", "")
                    )
            except Exception as e:
                op_logger.logger.error(f"Error processing update: {e}")