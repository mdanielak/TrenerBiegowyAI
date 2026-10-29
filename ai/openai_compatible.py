# -*- coding: utf-8 -*-
"""
OpenAI-compatible AI provider implementation.

Works with: OpenAI, DeepSeek, Ollama (OpenAI mode), vLLM, LM Studio,
and any other API compatible with OpenAI Chat Completions format.

Import as: from ai.openai_compatible import OpenAICompatibleProvider
"""
import json
import logging
from typing import Union

from ai.base import AIProvider

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# A minute covers slower local models while preventing indefinitely blocked CLI runs.
AI_REQUEST_TIMEOUT = 60.0
# Two SDK-managed retries balance transient provider failures against prompt completion.
AI_MAX_RETRIES = 2


logger = logging.getLogger(__name__)


def _strip_code_fence(text: str) -> str:
    """Zdejmij blok ```json ... ```, którym niektóre modele otaczają odpowiedź."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


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
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=AI_REQUEST_TIMEOUT,
            max_retries=AI_MAX_RETRIES,
        )

    def chat(self, system_prompt: str, user_message: str, response_model=None, *,
             temperature: float | None = None, seed: int | None = None,
             top_p: float | None = None) -> Union[str, dict]:
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
        for name, value in (("temperature", temperature), ("seed", seed), ("top_p", top_p)):
            if value is not None:
                kwargs[name] = value

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            # Nie każdy dostawca zgodny z OpenAI (np. Gemini) przyjmuje tryb JSON i `seed`.
            # Prompt i tak wymaga samego JSON-a, więc jedna ponowna próba bez nich jest bezpieczna.
            optional = [name for name in ("response_format", "seed") if name in kwargs]
            if not optional or getattr(e, "status_code", None) != 400:
                raise AIProviderError(f"AI API error: {e}") from e
            logger.info("AI provider rejected %s; retrying without them", ", ".join(optional))
            for name in optional:
                kwargs.pop(name)
            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as retry_error:
                raise AIProviderError(f"AI API error: {retry_error}") from retry_error

        content = response.choices[0].message.content
        if content is None:
            raise AIProviderError("AI returned empty response")

        # Parse structured output
        if response_model is not None:
            try:
                data = json.loads(_strip_code_fence(content))
            except json.JSONDecodeError:
                logger.debug("AI returned invalid JSON response: %s", content)
                raise AIResponseError(
                    f"AI returned invalid JSON ({len(content)} characters)"
                ) from None

            try:
                return response_model.model_validate(data)
            except Exception:
                logger.debug("AI response validation failed for data: %s", data)
                raise AIResponseError(
                    f"AI response validation failed for response of {len(content)} characters"
                ) from None

        return content
