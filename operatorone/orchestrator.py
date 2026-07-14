"""OperatorCore: wires the AI engine, executor, safety, and memory together.

The task workflow is a standard agentic loop: the model responds with tool
calls, each call is safety-checked and executed, the results go back to the
model, and the loop continues until it answers in plain text (or the
iteration cap is hit). Failed calls flow back too, so the model retries
naturally — there is no separate re-evaluate/smart-retry machinery.
"""

from typing import Callable, List, Optional
from dataclasses import dataclass
from enum import Enum

from config import Config
from command_generator import AIEngine
from executor import CommandExecutor, ExecutionResult, ConfirmCallback
from llm_providers import ProviderError, ToolResultMessage
from memory import MemoryManager
from conversation_memory import ConversationMemory
from data_management import DataManager
from core_memory import CoreMemory
from logger_config import op_logger
from tools import process_tool_command


class TaskStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    status: TaskStatus
    message: str
    commands_executed: List[str]
    ai_reasoning: Optional[str] = None
    execution_details: Optional[List[ExecutionResult]] = None

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.SUCCESS


class OperatorCore:
    def __init__(
        self,
        provider_name: Optional[str] = None,
        confirm_callback: Optional[ConfirmCallback] = None,
        on_tool_event: Optional[Callable[[str, Optional[bool]], None]] = None,
    ):
        """
        Args:
            provider_name: 'mistral' or 'gemini' (defaults to config)
            confirm_callback: async callback approving CAUTION/DANGEROUS tool
                calls; without one, those calls are denied.
            on_tool_event: optional UI hook, called with (display, None) when a
                tool starts and (display, success) when it finishes.
        """
        op_logger.header("INITIALIZING OPERATOR CORE")

        self.memory = MemoryManager()
        self.core_memory = CoreMemory(self.memory.learning_system)
        self.ai_engine = AIEngine(provider_name or Config.DEFAULT_AI_PROVIDER, self.memory, self.core_memory)
        self.executor = CommandExecutor(
            memory=self.memory,
            core_memory=self.core_memory,
            confirm_callback=confirm_callback,
        )
        self.conversation_memory = ConversationMemory(self.memory.learning_system)
        self.data_manager = DataManager(self.memory.learning_system)
        self.on_tool_event = on_tool_event

        # Start the extension bridge now (not lazily on first browser call) so
        # the extension has connected long before the first browser request.
        try:
            from browser_bridge import BrowserBridge
            BrowserBridge.get().start()
        except Exception:
            op_logger.logger.exception("Browser bridge failed to start")

        session_id = self.conversation_memory.start_session()
        op_logger.logger.info(f"Session started: {session_id}")

        self.current_task: Optional[str] = None
        self.is_busy = False

        from tools import set_operator_core
        set_operator_core(self)

        op_logger.success("Core initialized")

    async def process_task(self, user_input: str) -> TaskResult:
        if self.is_busy:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="OPERATOR is busy with another task.",
                commands_executed=[]
            )

        try:
            self.is_busy = True
            self.current_task = user_input

            op_logger.header(f"TASK: {user_input[:80]}{'...' if len(user_input) > 80 else ''}")

            is_tool, tool_result, _ = process_tool_command(user_input)
            if is_tool:
                if not tool_result.success:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        message=tool_result.error,
                        commands_executed=[]
                    )

                if tool_result.context_data and tool_result.context_data.get('tool') == 'vision':
                    return await self._execute_vision_workflow(
                        tool_result.context_data,
                        user_context=user_input
                    )
                return TaskResult(
                    status=TaskStatus.SUCCESS,
                    message=tool_result.output,
                    commands_executed=[]
                )

            return await self._execute_task_workflow(user_input)

        except ProviderError as e:
            op_logger.logger.error(f"AI provider error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"AI provider error: {e}",
                commands_executed=[]
            )
        except Exception as e:
            op_logger.logger.exception(f"Task failed: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"System error: {str(e)}",
                commands_executed=[]
            )
        finally:
            self.is_busy = False
            self.current_task = None
            # Single debounced write per turn instead of one per mutation
            self.memory.learning_system.flush()

    async def _execute_task_workflow(self, user_input: str) -> TaskResult:
        response = await self.ai_engine.chat(user_input=user_input)

        execution_results: List[ExecutionResult] = []
        executed_display: List[str] = []
        last_failed_shell: Optional[str] = None

        for _ in range(Config.MAX_TOOL_ITERATIONS):
            if not response.tool_calls:
                break

            tool_results: List[ToolResultMessage] = []
            for call in response.tool_calls:
                if self.on_tool_event:
                    self.on_tool_event(f"{call.name}", None)

                result = await self.executor.execute_tool_call(call.name, call.arguments)
                execution_results.append(result)
                executed_display.append(result.command)

                if self.on_tool_event:
                    self.on_tool_event(result.command, result.success)

                # Learn shell fixes: a failed command followed by a working one
                if call.name == "run_shell":
                    command = str(call.arguments.get("command", ""))
                    if not result.success:
                        last_failed_shell = command
                    elif last_failed_shell and last_failed_shell != command:
                        self.memory.record_fix(
                            original_command=last_failed_shell,
                            fixed_command=command,
                            error="",
                            context=user_input,
                        )
                        last_failed_shell = None

                content = result.output if result.success else f"ERROR: {result.error}"
                tool_results.append(ToolResultMessage(
                    tool_call_id=call.id,
                    name=call.name,
                    content=content or ("OK" if result.success else "Failed"),
                ))

            response = await self.ai_engine.chat(tool_results=tool_results)
        else:
            if response.tool_calls:
                op_logger.logger.warning(
                    f"Tool iteration cap ({Config.MAX_TOOL_ITERATIONS}) reached; stopping loop"
                )

        all_succeeded = all(r.success for r in execution_results) if execution_results else True
        final_text = response.text.strip() or (
            "Done." if all_succeeded else "The task could not be completed."
        )

        await self._learn_from_execution(user_input, execution_results)

        self.conversation_memory.add_interaction(
            user_message=user_input,
            ai_response=final_text,
            commands=executed_display,
            success=all_succeeded
        )

        if self.conversation_memory.is_significant_interaction(user_input, executed_display, all_succeeded):
            self.conversation_memory.add_significant_interaction(
                user_message=user_input,
                ai_response=final_text,
                significance="high" if len(executed_display) >= 3 else "medium"
            )

        return TaskResult(
            status=TaskStatus.SUCCESS if all_succeeded else TaskStatus.FAILED,
            message=final_text,
            commands_executed=executed_display,
            execution_details=execution_results
        )

    async def _execute_vision_workflow(
        self,
        vision_data: dict,
        user_context: str = ""
    ) -> TaskResult:
        try:
            ai_response = await self.ai_engine.generate_vision_response(
                prompt=vision_data['prompt'],
                image_base64=vision_data['image_base64']
            )

            self.conversation_memory.add_interaction(
                user_message=user_context or vision_data['prompt'],
                ai_response=ai_response,
                commands=[],
                success=True
            )

            return TaskResult(
                status=TaskStatus.SUCCESS,
                message=f"Vision Analysis:\n\n{ai_response}",
                commands_executed=[]
            )

        except ProviderError as e:
            op_logger.logger.error(f"Vision analysis failed: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"Vision analysis failed: {str(e)}",
                commands_executed=[]
            )

    async def _learn_from_execution(
        self,
        user_intent: str,
        results: List[ExecutionResult]
    ):
        """Update success/failure stats. Facts about the user are NOT captured
        automatically here — OPERATOR decides what to remember in first person
        via its remember / update_core_memory / forget tools."""
        for result in results:
            self.memory.update_stats(result.success)
