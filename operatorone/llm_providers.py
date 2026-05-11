from abc import ABC, abstractmethod
from typing import Callable, Optional, List, Dict
import time

from config import Config
from logger_config import op_logger


class BaseAIProvider(ABC):
    """Abstract base class for AI providers"""

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name
        self.conversation_history: List[Dict] = []

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the AI client. Returns True if successful."""
        pass

    @abstractmethod
    def send_message(self, message: str, stream_callback: Optional[Callable] = None) -> str:
        """
        Send a message to the AI and get response.

        Args:
            message: User message to send
            stream_callback: Optional callback(chunk: str, is_complete: bool)

        Returns:
            Complete response text
        """
        pass

    @abstractmethod
    def add_system_message(self, message: str):
        """Add a system message to conversation history"""
        pass

    @abstractmethod
    def trim_history(self, max_messages: int):
        """Trim conversation history to max_messages"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider name for logging"""
        pass

    @abstractmethod
    def send_vision_message(self, prompt: str, image_base64: str, stream_callback: Optional[Callable] = None) -> str:
        """
        Send a message with image for vision analysis.

        Args:
            prompt: User's question about the image
            image_base64: Base64-encoded image data
            stream_callback: Optional callback for streaming

        Returns:
            AI's response about the image
        """
        pass


class MistralProvider(BaseAIProvider):
    """Mistral AI provider implementation"""

    def __init__(self, api_key: str, model_name: str = Config.MISTRAL_MODEL):
        super().__init__(api_key, model_name)
        self.client = None

    def get_provider_name(self) -> str:
        return "Mistral"

    def initialize(self) -> bool:
        """Initialize Mistral client"""
        try:
            from mistralai import Mistral

            self.client = Mistral(api_key=self.api_key)
            op_logger.logger.info(f"✓ Mistral initialized | Model: {self.model_name}")
            return True

        except ImportError:
            op_logger.logger.error("✗ Mistral SDK not installed (pip install mistralai)")
            return False
        except Exception as e:
            op_logger.logger.error(f"✗ Mistral initialization failed: {e}")
            return False

    def add_system_message(self, message: str):
        """Add system message to conversation history"""
        self.conversation_history = [
            {"role": "system", "content": message}
        ]
        op_logger.logger.debug(f"System prompt set ({len(message)} chars)")

    def trim_history(self, max_messages: int):
        """Trim conversation history, preserving system message"""
        if len(self.conversation_history) <= max_messages + 1:
            return

        # Keep system message + recent messages
        system_msg = self.conversation_history[0]
        recent = self.conversation_history[-(max_messages):]
        self.conversation_history = [system_msg] + recent

        op_logger.logger.debug(f"History trimmed to {len(self.conversation_history)} messages")

    def send_message(self, message: str, stream_callback: Optional[Callable] = None) -> str:
        """Send message to Mistral"""
        start_time = time.time()

        # Add user message
        self.conversation_history.append({
            "role": "user",
            "content": message
        })

        op_logger.ai_request(
            provider=self.get_provider_name(),
            message_length=len(message),
            streaming=stream_callback is not None
        )

        try:
            response_text = ""

            if stream_callback:
                # Streaming mode
                response_text = self._send_streaming(stream_callback)
            else:
                # Non-streaming mode
                response_text = self._send_non_streaming()

            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })

            duration_ms = int((time.time() - start_time) * 1000)
            op_logger.ai_response(
                provider=self.get_provider_name(),
                response_length=len(response_text),
                duration_ms=duration_ms
            )

            return response_text

        except Exception as e:
            op_logger.logger.error(f"✗ Mistral API error: {e}")

            # Remove failed user message
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()

            return f"Error communicating with Mistral: {str(e)}"

    def _send_streaming(self, callback: Callable) -> str:
        """Send message with streaming response"""
        response_text = ""

        try:
            stream_response = self.client.chat.stream(
                model=self.model_name,
                messages=self.conversation_history
            )

            for chunk in stream_response:
                if hasattr(chunk, 'data') and hasattr(chunk.data, 'choices'):
                    if len(chunk.data.choices) > 0:
                        delta = chunk.data.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            response_text += content
                            callback(content, is_complete=False)

            callback("", is_complete=True)

        except Exception as stream_error:
            op_logger.logger.warning(f"⚠ Streaming failed, falling back to non-streaming: {stream_error}")

            # Fallback to non-streaming
            response_text = self._send_non_streaming()
            callback(response_text, is_complete=False)
            callback("", is_complete=True)

        return response_text

    def _send_non_streaming(self) -> str:
        """Send message without streaming"""
        response = self.client.chat.complete(
            model=self.model_name,
            messages=self.conversation_history
        )
        return response.choices[0].message.content

    def send_vision_message(self, prompt: str, image_base64: str, stream_callback: Optional[Callable] = None) -> str:
        """
        Send vision analysis request to Mistral with vision capabilities.
        Works exactly like send_message but with image content.
        Automatically maintains conversation history.

        Args:
            prompt: User's question about the image
            image_base64: Base64-encoded image
            stream_callback: Optional streaming callback

        Returns:
            AI's analysis of the image
        """
        start_time = time.time()

        try:
            # Use Pixtral for vision (dedicated vision model)
            # Falls back to mistral-small-latest if pixtral not available
            vision_model = "pixtral-12b-2409"

            # Build user message with image content (multimodal format)
            user_message = {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{image_base64}"
                    }
                ]
            }

            # Add to conversation history (same as normal messages)
            self.conversation_history.append(user_message)

            op_logger.logger.info(f"Sending vision request to {vision_model}...")

            # Send request with full conversation history (includes system prompt, context, memory)
            # Pixtral has access to the same 3-stage memory system via system prompt
            response = self.client.chat.complete(
                model=vision_model,
                messages=self.conversation_history
            )

            response_text = response.choices[0].message.content

            # Add assistant response to history (same as normal messages)
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })

            duration_ms = int((time.time() - start_time) * 1000)
            op_logger.ai_response(
                provider=f"{self.get_provider_name()} Vision",
                response_length=len(response_text),
                duration_ms=duration_ms
            )

            # Stream to callback if provided
            if stream_callback:
                stream_callback(response_text, is_complete=False)
                stream_callback("", is_complete=True)

            return response_text

        except Exception as e:
            op_logger.logger.error(f"✗ Vision analysis failed: {e}")
            # Remove failed user message from history (same error handling as normal)
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            return f"Vision analysis failed: {str(e)}"


class GeminiProvider(BaseAIProvider):
    """Google Gemini provider implementation"""

    def __init__(self, api_key: str, model_name: str = Config.GEMINI_MODEL):
        super().__init__(api_key, model_name)
        self.model = None
        self.chat = None

    def get_provider_name(self) -> str:
        return "Gemini"

    def initialize(self) -> bool:
        """Initialize Gemini client"""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)

            op_logger.logger.info(f"✓ Gemini initialized | Model: {self.model_name}")
            return True

        except ImportError:
            op_logger.logger.error("✗ Google Generative AI SDK not installed (pip install google-generativeai)")
            return False
        except Exception as e:
            op_logger.logger.error(f"✗ Gemini initialization failed: {e}")
            return False

    def add_system_message(self, message: str):
        """Add system message by starting chat and sending it"""
        self.chat = self.model.start_chat(history=[])
        self.chat.send_message(message)
        op_logger.logger.debug(f"System prompt sent ({len(message)} chars)")

    def trim_history(self, max_messages: int):
        """Trim Gemini chat history"""
        if not self.chat:
            return

        if len(self.chat.history) > max_messages:
            self.chat.history = self.chat.history[-max_messages:]
            op_logger.logger.debug(f"History trimmed to {len(self.chat.history)} messages")

    def send_message(self, message: str, stream_callback: Optional[Callable] = None) -> str:
        """Send message to Gemini"""
        start_time = time.time()

        op_logger.ai_request(
            provider=self.get_provider_name(),
            message_length=len(message),
            streaming=stream_callback is not None
        )

        try:
            response_text = ""

            if stream_callback:
                # Streaming mode
                response = self.chat.send_message(message, stream=True)

                for chunk in response:
                    if chunk.text:
                        response_text += chunk.text
                        stream_callback(chunk.text, is_complete=False)

                stream_callback("", is_complete=True)
            else:
                # Non-streaming mode
                response = self.chat.send_message(message)
                response_text = response.text

            duration_ms = int((time.time() - start_time) * 1000)
            op_logger.ai_response(
                provider=self.get_provider_name(),
                response_length=len(response_text),
                duration_ms=duration_ms
            )

            return response_text

        except Exception as e:
            op_logger.logger.error(f"✗ Gemini API error: {e}")
            return f"Error communicating with Gemini: {str(e)}"

    def send_vision_message(self, prompt: str, image_base64: str, stream_callback: Optional[Callable] = None) -> str:
        """
        Vision analysis not yet implemented for Gemini.
        """
        raise NotImplementedError("Vision analysis is currently only supported with Mistral AI. Please use Mistral provider for /img tool.")


class AIProviderFactory:
    """Factory for creating AI provider instances"""

    @staticmethod
    def create_provider(provider_name: str = None) -> BaseAIProvider:
        """
        Create an AI provider instance.

        Args:
            provider_name: 'mistral' or 'gemini'. If None, uses Config.DEFAULT_AI_PROVIDER

        Returns:
            Initialized AI provider instance

        Raises:
            ValueError: If provider is unknown or API key is missing
            Exception: If provider initialization fails
        """
        if provider_name is None:
            provider_name = Config.DEFAULT_AI_PROVIDER

        provider_name = provider_name.lower()

        op_logger.header(f"AI PROVIDER: {provider_name.upper()}")

        if provider_name == 'mistral':
            config = Config.get_provider_config('mistral')

            if not config['api_key']:
                raise ValueError("Mistral API key not configured!")

            op_logger.kv("API Key", f"{config['api_key'][:10]}...{config['api_key'][-4:]}")

            provider = MistralProvider(
                api_key=config['api_key'],
                model_name=config['model']
            )

        elif provider_name == 'gemini':
            config = Config.get_provider_config('gemini')

            if not config['api_key']:
                raise ValueError("Gemini API key not configured!")

            op_logger.kv("API Key", f"{config['api_key'][:10]}...{config['api_key'][-4:]}")

            provider = GeminiProvider(
                api_key=config['api_key'],
                model_name=config['model']
            )

        else:
            raise ValueError(f"Unknown AI provider: {provider_name}")

        # Initialize the provider
        if not provider.initialize():
            raise Exception(f"Failed to initialize {provider_name} provider")

        return provider