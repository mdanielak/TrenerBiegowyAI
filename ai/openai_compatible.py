# -*- coding: utf-8 -*-
"""
OpenAI-compatible AI provider implementation.

Works with: OpenAI, DeepSeek, Ollama (OpenAI mode), vLLM, LM Studio,
and any other API compatible with OpenAI Chat Completions format.

Import as: from ai.openai_compatible import OpenAICompatibleProvider
"""
import json
from typing import Union

from ai.base import AIProvider

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class AIProviderError(Exception):
    """Raised on AI API errors."""
    pass


class AIResponseError(Exception):
    """Raised when structured output cannot be parsed/validated."""
    pass


class OpenAICompatibleProvider(AIProvider):
    """AI provider using the OpenAI SDK (works with any compatible endpoint)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        """Initialize the provider.

        Args:
            base_url: API base URL (e.g. "https://api.openai.com/v1",
                      "http://localhost:11434/v1" for Ollama).
            api_key: API key (can be dummy for local models).
            model: Model name (e.g. "gpt-4o", "deepseek-chat", "llama3").
        """
        if OpenAI is None:
            raise AIProviderError(
                "openai package not installed. Run: pip install openai"
            )

        self.base_url = base_url
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def chat(self, system_prompt: str, user_message: str,
             response_model=None) -> Union[str, dict]:
        """Send a chat completion request.

        If response_model is a Pydantic BaseModel class, requests JSON output
        and validates the response into an instance of that model.
        """
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        # Request JSON output for structured responses
        if response_model is not None:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise AIProviderError(f"AI API error: {e}") from e

        content = response.choices[0].message.content
        if content is None:
            raise AIProviderError("AI returned empty response")

        # Parse structured output
        if response_model is not None:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise AIResponseError(
                    f"AI returned invalid JSON: {e}\nRaw response: {content[:500]}"
                ) from e

            try:
                return response_model.model_validate(data)
            except Exception as e:
                raise AIResponseError(
                    f"AI response validation failed: {e}\nData: {data}"
                ) from e

        return content
