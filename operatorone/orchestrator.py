import re
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from config import Config
from command_generator import AIEngine
from executor import CommandExecutor, ExecutionResult
from memory import MemoryManager
from validator import CommandValidator
from implicit_learning import ImplicitLearner
from user_profiler import UserProfileBuilder
from conversation_memory import ConversationMemory
from data_management import DataManager
from core_memory import CoreMemory
from memory_curator import MemoryCurator
from paths import Paths
from logger_config import op_logger
from tools import process_tool_command, ToolRegistry


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
    def __init__(self, provider_name: Optional[str] = None):
        op_logger.header("INITIALIZING OPERATOR CORE")

        self.memory = MemoryManager()
        self.core_memory = CoreMemory(self.memory.learning_system)
        self.memory_curator = MemoryCurator(self.memory.learning_system, self.core_memory)
        self.ai_engine = AIEngine(provider_name or Config.DEFAULT_AI_PROVIDER, self.memory, self.core_memory)
        self.executor = CommandExecutor(self.memory)
        self.validator = CommandValidator(self.memory)
        self.implicit_learner = ImplicitLearner(self.memory)
        self.user_profiler = UserProfileBuilder(self.memory)
        self.conversation_memory = ConversationMemory(self.memory.learning_system)
        self.data_manager = DataManager(self.memory.learning_system)

        session_id = self.conversation_memory.start_session()
        op_logger.logger.info(f"Session started: {session_id}")

        self.current_task: Optional[str] = None
        self.is_busy = False

        from tools import set_operator_core
        set_operator_core(self)

        op_logger.success("Core initialized")

    async def process_task(
        self,
        user_input: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> TaskResult:
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

            is_tool, tool_result, remaining_text = process_tool_command(user_input)
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
                        stream_callback,
                        user_context=user_input
                    )
                else:
                    return TaskResult(
                        status=TaskStatus.SUCCESS,
                        message=tool_result.output,
                        commands_executed=[]
                    )

            return await self._execute_task_workflow(user_input, stream_callback)

        except Exception as e:
            op_logger.logger.error(f"Task failed: {e}")
            import traceback
            traceback.print_exc()
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"System error: {str(e)}",
                commands_executed=[]
            )
        finally:
            self.is_busy = False
            self.current_task = None

    async def _execute_task_workflow(
        self,
        user_input: str,
        stream_callback: Optional[Callable]
    ) -> TaskResult:
        ai_response = await self.ai_engine.generate_commands(
            user_input=user_input,
            stream_callback=stream_callback
        )

        if not ai_response.commands:
            return TaskResult(
                status=TaskStatus.SUCCESS,
                message=ai_response.explanation,
                commands_executed=[],
                ai_reasoning=ai_response.reasoning
            )

        op_logger.kv("Commands", f"{len(ai_response.commands)} generated")

        valid_commands = []
        validation_results = []

        for cmd in ai_response.commands:
            is_valid, reason = self.validator.validate(cmd)
            validation_results.append((cmd, is_valid, reason))
            if is_valid:
                valid_commands.append(cmd)
            else:
                op_logger.logger.warning(f"Blocked: {cmd[:50]}... ({reason})")

        if not valid_commands:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="All commands blocked by safety validator:\n" +
                        "\n".join([f"- {cmd}: {reason}" for cmd, _, reason in validation_results if not _]),
                commands_executed=[]
            )

        execution_results = []
        output_lines = []
        all_succeeded = True
        wants_reevaluation = ai_response.wants_reevaluation

        if ai_response.explanation:
            output_lines.append(ai_response.explanation)

        for idx, cmd in enumerate(valid_commands, 1):
            op_logger.kv("Executing", f"{idx}/{len(valid_commands)}")

            result = await self.executor.execute(cmd)
            execution_results.append(result)

            if result.success:
                output_lines.append(f"\n[OK] {cmd}")
                if result.output and not result.output.startswith("OK"):
                    output_lines.append(f"   {result.output[:500]}")
            else:
                output_lines.append(f"\n[FAILED] {cmd}")
                output_lines.append(f"   Error: {result.error}")
                all_succeeded = False

                retry_result = await self._attempt_smart_retry(
                    original_command=cmd,
                    error=result.error,
                    user_intent=user_input
                )

                if retry_result:
                    output_lines.append(f"\n[RETRY OK] {retry_result.command}")
                    execution_results.append(retry_result)
                    all_succeeded = True
                else:
                    break

            if wants_reevaluation and idx == len(valid_commands):
                op_logger.logger.info("Re-evaluating after execution...")

                exec_summary = "\n".join(output_lines[1:])
                reevaluate_prompt = (
                    f"Based on the execution results below, decide the next action.\n\n"
                    f"Results:\n{exec_summary}\n\n"
                    f"Original request: {user_input}\n\n"
                    f"What should we do next? Generate commands or explain if complete."
                )

                reevaluation_response = await self.ai_engine.generate_commands(
                    reevaluate_prompt,
                    stream_callback=stream_callback
                )

                if reevaluation_response.commands:
                    new_valid_commands = []
                    for cmd in reevaluation_response.commands:
                        is_valid, reason = self.validator.validate(cmd)
                        if is_valid:
                            new_valid_commands.append(cmd)
                        else:
                            op_logger.logger.warning(f"Blocked: {cmd[:50]}... ({reason})")

                    for new_cmd in new_valid_commands:
                        new_result = await self.executor.execute(new_cmd)
                        execution_results.append(new_result)

                        if new_result.success:
                            output_lines.append(f"\n[OK] {new_cmd}")
                            if new_result.output and not new_result.output.startswith("OK"):
                                output_lines.append(f"   {new_result.output[:500]}")
                        else:
                            output_lines.append(f"\n[FAILED] {new_cmd}")
                            output_lines.append(f"   Error: {new_result.error}")
                            all_succeeded = False
                            break
                elif reevaluation_response.explanation:
                    output_lines.append(f"\n{reevaluation_response.explanation}")

        await self._learn_from_execution(user_input, execution_results)

        self.conversation_memory.add_interaction(
            user_message=user_input,
            ai_response=ai_response.explanation,
            commands=valid_commands,
            success=all_succeeded
        )

        if self.conversation_memory.is_significant_interaction(user_input, valid_commands, all_succeeded):
            self.conversation_memory.add_significant_interaction(
                user_message=user_input,
                ai_response=ai_response.explanation,
                significance="high" if len(valid_commands) >= 3 else "medium"
            )

        self.memory_curator.queue_interaction(
            user_message=user_input,
            ai_response=ai_response.explanation,
            commands=valid_commands,
            success=all_succeeded
        )

        return TaskResult(
            status=TaskStatus.SUCCESS if all_succeeded else TaskStatus.FAILED,
            message="\n".join(output_lines),
            commands_executed=valid_commands,
            ai_reasoning=ai_response.reasoning,
            execution_details=execution_results
        )

    async def _execute_vision_workflow(
        self,
        vision_data: dict,
        stream_callback: Optional[Callable],
        user_context: str = ""
    ) -> TaskResult:
        try:
            ai_response = await self.ai_engine.generate_vision_response(
                prompt=vision_data['prompt'],
                image_base64=vision_data['image_base64'],
                stream_callback=stream_callback
            )

            self.conversation_memory.add_interaction(
                user_message=user_context or vision_data['prompt'],
                ai_response=ai_response,
                commands=[],
                success=True
            )

            self.memory_curator.queue_interaction(
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

        except Exception as e:
            op_logger.logger.error(f"Vision analysis failed: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                message=f"Vision analysis failed: {str(e)}",
                commands_executed=[]
            )

    async def _attempt_smart_retry(
        self,
        original_command: str,
        error: str,
        user_intent: str
    ) -> Optional[ExecutionResult]:
        op_logger.logger.info("Attempting smart retry...")

        attempted_commands = [original_command]
        attempted_fixes = []
        last_error = error

        similar_fixes = self.memory.find_similar_fixes(original_command, error)

        if similar_fixes:
            op_logger.kv("Memory", f"Found {len(similar_fixes)} similar fix(es)")
            best_fix = similar_fixes[0]

            result = await self.executor.execute(best_fix.fixed_command)
            attempted_commands.append(best_fix.fixed_command)

            if result.success:
                return result
            else:
                last_error = result.error
                attempted_fixes.append({'fix': best_fix.fixed_command, 'error': result.error})

        for retry_attempt in range(1, Config.MAX_RETRIES + 1):
            op_logger.logger.info(f"Retry attempt {retry_attempt}/{Config.MAX_RETRIES}")

            retry_response = await self.ai_engine.suggest_fix(
                failed_command=original_command,
                error=last_error,
                original_intent=user_intent,
                attempted_fixes=attempted_fixes + similar_fixes
            )

            if not retry_response.commands:
                continue

            retry_cmd = retry_response.commands[0]

            if retry_cmd in attempted_commands:
                continue

            attempted_commands.append(retry_cmd)
            result = await self.executor.execute(retry_cmd)

            if result.success:
                should_learn = True
                if original_command.startswith(('window:', 'clipboard:', 'process:')):
                    if retry_cmd.startswith('powershell'):
                        should_learn = False

                if should_learn:
                    self.memory.record_fix(
                        original_command=original_command,
                        fixed_command=retry_cmd,
                        error=error,
                        context=user_intent
                    )

                return result
            else:
                last_error = result.error
                attempted_fixes.append({'fix': retry_cmd, 'error': result.error})

        op_logger.logger.error(f"All {Config.MAX_RETRIES} retry attempts failed")
        return None

    async def _learn_from_execution(
        self,
        user_intent: str,
        results: List[ExecutionResult]
    ):
        from datetime import datetime

        successful_commands = [r.command for r in results if r.success]
        if successful_commands:
            self.memory.record_successful_pattern(
                intent=user_intent,
                commands=successful_commands
            )

        for result in results:
            self.memory.update_stats(result.success)

        if self.implicit_learner.should_learn_from_interaction(user_intent, {'success': len(successful_commands) > 0}):
            learned = self.implicit_learner.analyze_message(
                user_msg=user_intent,
                ai_response=None,
                result={
                    'success': len(successful_commands) > 0,
                    'commands': successful_commands
                }
            )

            if learned['total_learned'] > 0:
                op_logger.logger.info(f"Learned {learned['total_learned']} new fact(s)")

        self.user_profiler.update_profile({
            'user_message': user_intent,
            'commands': successful_commands,
            'timestamp': datetime.now().isoformat(),
            'success': len(successful_commands) > 0
        })

        detected_name = self.user_profiler.detect_name_from_message(user_intent)
        if detected_name:
            current_name = self.memory.get_user_profile().get('name')
            if not current_name:
                self.memory.update_profile('name', detected_name)
                op_logger.logger.info(f"Learned user name: {detected_name}")
