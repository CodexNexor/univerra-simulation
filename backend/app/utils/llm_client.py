"""
LLM Client Wrapper
Unified OpenAI-format API calls
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .llm_base import normalize_openai_base_url
from .llm_rate_limiter import wait_for_llm_slot


class LLMClient:
    """LLM client"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = normalize_openai_base_url(base_url or Config.LLM_BASE_URL)
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (e.g., JSON mode)

        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        wait_for_llm_slot()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if response_format and self._should_retry_without_response_format(exc):
                kwargs.pop("response_format", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise
        content = response.choices[0].message.content
        # Some models (e.g., MiniMax M2.5) include <think> reasoning content that needs to be removed
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count

        Returns:
            Parsed JSON object
        """
        try:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            return json.loads(self._clean_json_response(response))
        except Exception:
            fallback_messages = list(messages)
            fallback_messages.append({
                "role": "user",
                "content": (
                    "Return only one valid JSON object. "
                    "Do not include markdown fences, explanations, or extra text."
                )
            })
            response = self.chat(
                messages=fallback_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            cleaned_response = self._clean_json_response(response)

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                extracted_json = self._extract_first_json_object(cleaned_response)
                if extracted_json is not None:
                    return extracted_json
                raise ValueError(f"Invalid JSON format returned by LLM: {cleaned_response}")

    def _should_retry_without_response_format(self, exc: Exception) -> bool:
        """Retry providers that claim OpenAI compatibility but reject JSON mode."""
        message = str(exc).lower()
        indicators = [
            "response_format",
            "json_object",
            "json mode",
            "unsupported",
            "not supported",
            "invalid_request_error",
            "extra inputs are not permitted",
        ]
        return any(indicator in message for indicator in indicators)

    def _clean_json_response(self, response: str) -> str:
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        return cleaned_response.strip()

    def _extract_first_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:index + 1]
                    return json.loads(candidate)

        return None
