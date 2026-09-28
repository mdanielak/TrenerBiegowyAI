# -*- coding: utf-8 -*-
"""Tests for ai/base.py and ai/openai_compatible.py — AI provider abstraction."""
import sys
import os
import json
from unittest.mock import MagicMock, patch
from typing import Optional

import pytest
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.base import AIProvider
from ai.openai_compatible import OpenAICompatibleProvider, AIProviderError, AIResponseError


class TestAIProviderABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            AIProvider()

    def test_subclass_must_implement_chat(self):
        class IncompleteProvider(AIProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()


class TestOpenAICompatibleProvider:
    @patch('ai.openai_compatible.OpenAI')
    def test_init(self, mock_openai_cls):
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        mock_openai_cls.assert_called_once_with(
            base_url="https://api.example.com/v1",
            api_key="test-key",
        )
        assert provider.model == "test-model"

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_returns_string(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from AI"
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        result = provider.chat("You are a coach", "What should I do?")

        assert result == "Hello from AI"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "model"
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_with_structured_output(self, mock_openai_cls):
        class TestModel(BaseModel):
            readiness: str
            score: int

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "readiness": "ready", "score": 8
        })
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        result = provider.chat("System", "User", response_model=TestModel)

        assert isinstance(result, TestModel)
        assert result.readiness == "ready"
        assert result.score == 8

        # Verify JSON response format was requested
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_structured_invalid_json(self, mock_openai_cls):
        class TestModel(BaseModel):
            readiness: str

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        with pytest.raises(AIResponseError, match="invalid JSON"):
            provider.chat("System", "User", response_model=TestModel)

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_structured_validation_error(self, mock_openai_cls):
        class TestModel(BaseModel):
            readiness: str
            score: int

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        # Missing required field 'score'
        mock_response.choices[0].message.content = json.dumps({
            "readiness": "ready"
        })
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        with pytest.raises(AIResponseError, match="validation failed"):
            provider.chat("System", "User", response_model=TestModel)

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_api_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("Rate limited")

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        with pytest.raises(AIProviderError, match="AI API error"):
            provider.chat("System", "User")

    @patch('ai.openai_compatible.OpenAI')
    def test_chat_empty_response(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider("http://localhost/v1", "key", "model")
        with pytest.raises(AIProviderError, match="empty response"):
            provider.chat("System", "User")
