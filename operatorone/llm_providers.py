"""LLM provider abstraction with native tool-calling.

Both providers expose the same surface:

- add_system_message(text)      reset conversation with a system prompt
- refresh_system_prompt(text)   update the system prompt, keep conversation
- send_message(text) -> str     plain chat, no tools (utility for non-agentic calls)
- chat(...) -> ChatResponse     tool-enabled turn; pass either user_message
                                or tool_results (results of the previous
                                turn's tool calls)
- send_vision_message(...)      image analysis
- trim_history(n)

API failures raise ProviderError instead of returning error strings, so
callers can distinguish a failed request from a real reply.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import Config
from logger_config import op_logger
from rate_limiter import limiter, _is_rate_limit_error


@dataclass
class ToolCall:
    """A function call requested by the model."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResultMessage:
    """The outcome of one tool call, fed back to the model."""
    tool_call_id: str
    name: str
    content: str


@dataclass
class ChatResponse:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)


class ProviderError(Exception):
    """An LLM API request failed."""


class BaseAIProvider(ABC):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the AI client. Returns True if successful."""

    @abstractmethod
    def add_system_message(self, message: str):
        """Reset the conversation with this system prompt."""

    @abstractmethod
    def refresh_system_prompt(self, message: str):
        """Replace the system prompt while preserving conversation history."""

    @abstractmethod
    def send_message(self, message: str) -> str:
        """Plain chat turn without tools. Returns response text."""

    @abstractmethod
    def chat(
        self,
        user_message: Optional[str] = None,
        tool_results: Optional[List[ToolResultMessage]] = None,
        tools: Optional[List[Dict]] = None,
    ) -> ChatResponse:
        """Tool-enabled chat turn. Exactly one of user_message/tool_results."""

    @abstractmethod
    def send_vision_message(self, prompt: str, image_base64: str) -> str:
        """Analyze an image. Returns response text."""

    @abstractmethod
    def trim_history(self, max_messages: int):
        """Bound conversation history length."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Provider name for logging."""


class MistralProvider(BaseAIProvider):
    """Mistral AI provider (mistralai >= 1.x SDK)."""

    def __init__(self, api_key: str, model_name: str = None):
        super().__init__(api_key, model_name or Config.MISTRAL_MODEL)
        self.client = None
        self.conversation_history: List[Dict] = []

    def get_provider_name(self) -> str:
        return "Mistral"

    def initialize(self) -> bool:
        try:
            from mistralai import Mistral
            self.client = Mistral(api_key=self.api_key)
            op_logger.logger.info(f"Mistral initialized | Model: {self.model_name}")
            return True
        except ImportError:
            op_logger.logger.error("Mistral SDK not installed (pip install mistralai)")
            return False
        except Exception as e:
            op_logger.logger.error(f"Mistral initialization failed: {e}")
            return False

    def add_system_message(self, message: str):
        self.conversation_history = [{"role": "system", "content": message}]

    def refresh_system_prompt(self, message: str):
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            self.conversation_history[0] = {"role": "system", "content": message}
        else:
            self.conversation_history.insert(0, {"role": "system", "content": message})

    def trim_history(self, max_messages: int):
        """Trim history, preserving the system message and never splitting a
        tool exchange (a 'tool' message must follow its assistant call)."""
        if len(self.conversation_history) <= max_messages + 1:
            return

        system_msg = self.conversation_history[0]
        recent = self.conversation_history[-max_messages:]

        # Advance the cut to a user message so we never start mid-exchange
        start = 0
        for i, msg in enumerate(recent):
            if msg.get("role") == "user":
                start = i
                break
        else:
            return  # no user boundary in window; keep as-is rather than corrupt

        self.conversation_history = [system_msg] + recent[start:]

    @staticmethod
    def _to_mistral_tools(tools: Optional[List[Dict]]) -> Optional[List[Dict]]:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def _complete(self, tools: Optional[List[Dict]]) -> ChatResponse:
        start_time = time.time()
        try:
            kwargs = {"model": self.model_name, "messages": self.conversation_history}
            mistral_tools = self._to_mistral_tools(tools)
            if mistral_tools:
                kwargs["tools"] = mistral_tools
                kwargs["tool_choice"] = "auto"

            fallback = Config.MISTRAL_FALLBACK_MODEL
            try:
                # Short retry on the primary; if its burst window is
                # saturated, the fallback finishes the reply instead.
                retries = 2 if fallback and fallback != self.model_name else None
                response = limiter.call(
                    lambda: self.client.chat.complete(**kwargs),
                    provider="Mistral", max_retries=retries)
            except Exception as e:
                if not (_is_rate_limit_error(e) and fallback
                        and fallback != self.model_name):
                    raise
                op_logger.logger.warning(
                    f"{self.model_name} is rate limited — answering with "
                    f"{fallback} for this reply"
                )
                kwargs["model"] = fallback
                response = limiter.call(
                    lambda: self.client.chat.complete(**kwargs),
                    provider="Mistral fallback")
            message = response.choices[0].message
        except Exception as e:
            raise ProviderError(f"Mistral API error: {e}") from e

        text = message.content or ""
        if isinstance(text, list):  # content chunks
            text = "".join(getattr(c, "text", "") or "" for c in text)

        tool_calls: List[ToolCall] = []
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": text}

        if getattr(message, "tool_calls", None):
            raw_calls = []
            for i, tc in enumerate(message.tool_calls):
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                call_id = tc.id or f"call_{i}"
                tool_calls.append(ToolCall(id=call_id, name=tc.function.name, arguments=args))
                raw_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                        if isinstance(tc.function.arguments, str)
                        else json.dumps(tc.function.arguments),
                    },
                })
            assistant_msg["tool_calls"] = raw_calls

        self.conversation_history.append(assistant_msg)

        duration_ms = int((time.time() - start_time) * 1000)
        op_logger.logger.debug(
            f"Mistral response: {len(text)} chars, {len(tool_calls)} tool call(s), {duration_ms}ms"
        )
        return ChatResponse(text=text, tool_calls=tool_calls)

    def chat(
        self,
        user_message: Optional[str] = None,
        tool_results: Optional[List[ToolResultMessage]] = None,
        tools: Optional[List[Dict]] = None,
    ) -> ChatResponse:
        if user_message is not None:
            self.conversation_history.append({"role": "user", "content": user_message})
        elif tool_results:
            for result in tool_results:
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result.content,
                })

        try:
            return self._complete(tools)
        except ProviderError:
            # Drop the user message we just appended so a retry doesn't duplicate it
            if user_message is not None and self.conversation_history \
                    and self.conversation_history[-1].get("role") == "user":
                self.conversation_history.pop()
            raise

    def send_message(self, message: str) -> str:
        return self.chat(user_message=message).text

    def send_vision_message(self, prompt: str, image_base64: str) -> str:
        vision_model = Config.MISTRAL_VISION_MODEL

        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": f"data:image/png;base64,{image_base64}"},
            ],
        }
        self.conversation_history.append(user_message)

        try:
            response = limiter.call(
                lambda: self.client.chat.complete(
                    model=vision_model,
                    messages=self.conversation_history,
                ),
                provider="Mistral vision",
            )
            response_text = response.choices[0].message.content or ""
        except Exception as e:
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            raise ProviderError(f"Mistral vision error: {e}") from e

        self.conversation_history.append({"role": "assistant", "content": response_text})
        return response_text


class GeminiProvider(BaseAIProvider):
    """Google Gemini provider (google-generativeai 0.8.x SDK)."""

    def __init__(self, api_key: str, model_name: str = None):
        super().__init__(api_key, model_name or Config.GEMINI_MODEL)
        self.genai = None
        self.model = None
        self.chat_session = None
        self._system_prompt = ""
        self._call_counter = 0

    def get_provider_name(self) -> str:
        return "Gemini"

    def initialize(self) -> bool:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            self._rebuild(history=[])
            op_logger.logger.info(f"Gemini initialized | Model: {self.model_name}")
            return True
        except ImportError:
            op_logger.logger.error("Google Generative AI SDK not installed (pip install google-generativeai)")
            return False
        except Exception as e:
            op_logger.logger.error(f"Gemini initialization failed: {e}")
            return False

    def _rebuild(self, history):
        """(Re)create model + chat. system_instruction is a constructor arg,
        so changing the system prompt requires a rebuild."""
        self.model = self.genai.GenerativeModel(
            self.model_name,
            system_instruction=self._system_prompt or None,
        )
        self.chat_session = self.model.start_chat(history=history or [])

    def add_system_message(self, message: str):
        self._system_prompt = message
        self._rebuild(history=[])

    def refresh_system_prompt(self, message: str):
        self._system_prompt = message
        old_history = list(self.chat_session.history) if self.chat_session else []
        self._rebuild(history=old_history)

    def trim_history(self, max_messages: int):
        if not self.chat_session:
            return
        history = self.chat_session.history
        if len(history) <= max_messages:
            return
        trimmed = list(history[-max_messages:])
        # Start at a user turn so function-call/response pairs stay intact
        start = 0
        for i, content in enumerate(trimmed):
            if content.role == "user" and not any(
                getattr(p, "function_response", None) and p.function_response.name
                for p in content.parts
            ):
                start = i
                break
        self.chat_session.history = trimmed[start:]

    # ---- Schema conversion: JSON Schema -> Gemini proto schema ----

    _TYPE_MAP = {
        "object": "OBJECT", "string": "STRING", "integer": "INTEGER",
        "number": "NUMBER", "boolean": "BOOLEAN", "array": "ARRAY",
    }

    @classmethod
    def _to_gemini_schema(cls, schema: Dict) -> Dict:
        converted: Dict[str, Any] = {}
        if "type" in schema:
            converted["type"] = cls._TYPE_MAP.get(schema["type"], "STRING")
        if "description" in schema:
            converted["description"] = schema["description"]
        if "enum" in schema:
            converted["enum"] = schema["enum"]
        if "properties" in schema:
            converted["properties"] = {
                k: cls._to_gemini_schema(v) for k, v in schema["properties"].items()
            }
        if "required" in schema:
            converted["required"] = schema["required"]
        if "items" in schema:
            converted["items"] = cls._to_gemini_schema(schema["items"])
        return converted

    @classmethod
    def _to_gemini_tools(cls, tools: Optional[List[Dict]]):
        if not tools:
            return None
        return [{
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": cls._to_gemini_schema(t["parameters"]),
                }
                for t in tools
            ]
        }]

    @staticmethod
    def _proto_to_plain(value):
        """Convert proto Map/List composites from function_call.args to plain Python."""
        if hasattr(value, "items"):
            return {k: GeminiProvider._proto_to_plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)) or type(value).__name__ == "RepeatedComposite":
            return [GeminiProvider._proto_to_plain(v) for v in value]
        return value

    def _send(self, content, tools: Optional[List[Dict]]) -> ChatResponse:
        start_time = time.time()
        try:
            response = limiter.call(
                lambda: self.chat_session.send_message(
                    content, tools=self._to_gemini_tools(tools)
                ),
                provider="Gemini",
            )
        except Exception as e:
            raise ProviderError(f"Gemini API error: {e}") from e

        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []

        try:
            candidates = response.candidates
            if not candidates:
                raise ProviderError("Gemini returned no candidates (possibly safety-blocked)")
            for part in candidates[0].content.parts:
                fc = getattr(part, "function_call", None)
                if fc and fc.name:
                    self._call_counter += 1
                    tool_calls.append(ToolCall(
                        id=f"gemini_call_{self._call_counter}",
                        name=fc.name,
                        arguments=self._proto_to_plain(fc.args),
                    ))
                elif getattr(part, "text", None):
                    text_parts.append(part.text)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Gemini response parsing error: {e}") from e

        duration_ms = int((time.time() - start_time) * 1000)
        text = "".join(text_parts)
        op_logger.logger.debug(
            f"Gemini response: {len(text)} chars, {len(tool_calls)} tool call(s), {duration_ms}ms"
        )
        return ChatResponse(text=text, tool_calls=tool_calls)

    def chat(
        self,
        user_message: Optional[str] = None,
        tool_results: Optional[List[ToolResultMessage]] = None,
        tools: Optional[List[Dict]] = None,
    ) -> ChatResponse:
        if user_message is not None:
            return self._send(user_message, tools)

        if tool_results:
            parts = [
                self.genai.protos.Part(
                    function_response=self.genai.protos.FunctionResponse(
                        name=result.name,
                        response={"result": result.content},
                    )
                )
                for result in tool_results
            ]
            return self._send(parts, tools)

        raise ValueError("chat() requires user_message or tool_results")

    def send_message(self, message: str) -> str:
        return self.chat(user_message=message).text

    def send_vision_message(self, prompt: str, image_base64: str) -> str:
        import base64
        try:
            blob = {"mime_type": "image/png", "data": base64.b64decode(image_base64)}
            response = limiter.call(
                lambda: self.model.generate_content([prompt, blob]),
                provider="Gemini vision",
            )
            return response.text
        except Exception as e:
            raise ProviderError(f"Gemini vision error: {e}") from e


class AIProviderFactory:
    """Factory for creating AI provider instances."""

    @staticmethod
    def create_provider(provider_name: str = None) -> BaseAIProvider:
        if provider_name is None:
            provider_name = Config.DEFAULT_AI_PROVIDER

        provider_name = provider_name.lower()

        if provider_name == 'mistral':
            config = Config.get_provider_config('mistral')
            if not config['api_key']:
                raise ValueError("Mistral API key not configured!")
            provider = MistralProvider(api_key=config['api_key'], model_name=config['model'])

        elif provider_name == 'gemini':
            config = Config.get_provider_config('gemini')
            if not config['api_key']:
                raise ValueError("Gemini API key not configured!")
            provider = GeminiProvider(api_key=config['api_key'], model_name=config['model'])

        else:
            raise ValueError(f"Unknown AI provider: {provider_name}")

        if not provider.initialize():
            raise RuntimeError(f"Failed to initialize {provider_name} provider")

        return provider
