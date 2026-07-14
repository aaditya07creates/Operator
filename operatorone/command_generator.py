"""AIEngine: the conversation layer between OPERATOR and the LLM.

Builds the system prompt (identity + core memory + learned knowledge),
injects per-query Tier-2 context, and exchanges tool-enabled turns with
the provider. Command extraction is native tool-calling — there is no
tag parsing here anymore.
"""

from typing import List, Optional

from config import Config
from context_retrieval import ContextRetriever
from core_memory import CoreMemory
from llm_providers import AIProviderFactory, ChatResponse, ToolResultMessage
from logger_config import op_logger
from memory import MemoryManager
from tool_specs import TOOL_SPECS


class AIEngine:
    def __init__(self, provider_name: str, memory: MemoryManager, core_memory: CoreMemory = None):
        self.provider_name = provider_name
        self.memory = memory
        self.core_memory = core_memory
        self.context_retriever = ContextRetriever(memory.learning_system)

        self.provider = AIProviderFactory.create_provider(provider_name)
        self.provider.add_system_message(self._build_system_prompt())

        op_logger.kv("AI Provider", provider_name)

    def _build_system_prompt(self) -> str:
        """Base prompt + Tier-1 core memory + learned command knowledge."""
        system_prompt = Config.get_system_prompt()

        if self.core_memory:
            core_section = self.core_memory.get_core_prompt_section()
            if core_section:
                system_prompt += f"\n\n{core_section}"

        command_context = self.memory.get_context_for_ai()
        if command_context:
            system_prompt += f"\n\n## Your Learned Knowledge\n{command_context}"

        return system_prompt

    def refresh_context(self):
        """Re-inject core memory into the system prompt (conversation kept).

        Called once per turn so facts OPERATOR saves mid-session (remember /
        update_core_memory / forget) become visible immediately.
        """
        self.provider.refresh_system_prompt(self._build_system_prompt())

    def _contextual_prefix(self, user_input: str) -> str:
        """Current date/time + relevant Tier-2 facts, prepended to the query.

        The timestamp goes on every message (not the cached system prompt) so
        relative dates — "2 months from now", "next Friday" — resolve
        correctly mid-session.
        """
        from datetime import datetime

        prefix = f"[Now: {datetime.now().strftime('%A, %d %B %Y, %H:%M')}]\n"
        smart_context = self.context_retriever.get_relevant_context_for_ai(
            query=user_input,
            limit=5,
        )
        if smart_context:
            prefix += f"[Context: {smart_context.strip()}]\n"
        return prefix + "\n"

    async def chat(
        self,
        user_input: Optional[str] = None,
        tool_results: Optional[List[ToolResultMessage]] = None,
    ) -> ChatResponse:
        """One tool-enabled turn. Pass user_input to start, tool_results to continue."""
        import asyncio

        self.provider.trim_history(Config.MAX_CHAT_HISTORY)

        if user_input is not None:
            self.refresh_context()
            user_input = self._contextual_prefix(user_input) + user_input
            return await asyncio.to_thread(
                self.provider.chat, user_message=user_input, tools=TOOL_SPECS
            )

        return await asyncio.to_thread(
            self.provider.chat, tool_results=tool_results, tools=TOOL_SPECS
        )

    async def generate_vision_response(self, prompt: str, image_base64: str) -> str:
        """Analyze a screenshot within the running conversation."""
        import asyncio

        op_logger.logger.info("Sending vision request to AI...")
        self.provider.trim_history(Config.MAX_CHAT_HISTORY)
        return await asyncio.to_thread(
            self.provider.send_vision_message, prompt, image_base64
        )
