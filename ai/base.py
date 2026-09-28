# -*- coding: utf-8 -*-
"""
Abstract AI provider interface.

All AI providers must implement the chat() method.
Import as: from ai.base import AIProvider
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Union

T = TypeVar('T')


class AIProvider(ABC):
    """Abstract base class for AI providers.

    Implementations should support OpenAI-compatible chat completions.
    """

    @abstractmethod
    def chat(self, system_prompt: str, user_message: str,
             response_model=None) -> Union[str, dict]:
        """Send a chat completion request.

        Args:
            system_prompt: System message defining AI behavior.
            user_message: User's message/query.
            response_model: Optional Pydantic model class for structured output.
                If provided, the response is parsed and validated into this model.
                If None, returns raw string response.

        Returns:
            str if response_model is None, otherwise an instance of response_model.

        Raises:
            AIProviderError: On API errors.
            AIResponseError: If structured output cannot be parsed/validated.
        """
        ...
