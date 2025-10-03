"""
LLM client for semi-agentic review.
Provides async API integration for secure LLM services.
"""

import asyncio
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import json

# Try to import local config for API key fallback (not in git)
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from local_config import MCHP_LLM_API_KEY as LOCAL_API_KEY
except ImportError:
    LOCAL_API_KEY = None


@dataclass
class LLMResponse:
    """Response from LLM API."""
    content: str
    confidence: float
    reasoning: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMClient:
    """Async client for LLM API integration."""

    def __init__(self, config: Dict):
        self.config = config
        self.llm_config = config.get('llm', {})
        self.enabled = self.llm_config.get('enabled', False)

        # API configuration
        self.api_url = self.llm_config.get('api_url', '')
        # Try environment variable first, then fall back to local_config.py
        self.api_key = os.getenv(self.llm_config.get('api_key_env', 'LLM_API_KEY'), '') or LOCAL_API_KEY or ''
        self.model = self.llm_config.get('model', 'gpt-4')
        self.temperature = self.llm_config.get('temperature', 0.3)
        self.max_tokens = self.llm_config.get('max_tokens', 2000)
        self.timeout = self.llm_config.get('timeout', 30)

        # Streaming configuration
        self.stream = self.llm_config.get('stream', False)
        self.stream_timeout = self.llm_config.get('stream_timeout', 60)

        # SSL verification
        self.verify_ssl = self.llm_config.get('verify_ssl', True)

        # Rate limiting
        self.rate_limit = self.llm_config.get('rate_limit', {})
        self.requests_per_minute = self.rate_limit.get('requests_per_minute', 20)
        self.concurrent_requests = self.rate_limit.get('concurrent_requests', 5)

        # Semaphore for concurrent request limiting
        self.semaphore = asyncio.Semaphore(self.concurrent_requests)

        # HTTP client
        self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        # Use tuple timeout format: (connect_timeout, read_timeout, write_timeout, pool_timeout)
        # Based on colleague's implementation: 5s to connect, stream_timeout for reading
        timeout_config = httpx.Timeout(
            connect=5.0,  # Quick connect timeout
            read=self.stream_timeout,  # Long timeout for streaming
            write=10.0,
            pool=5.0
        )
        self.client = httpx.AsyncClient(timeout=timeout_config, verify=self.verify_ssl)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def review_text(self, text: str, context: Optional[str] = None) -> LLMResponse:
        """
        Send text for LLM review.

        Args:
            text: Text to review
            context: Optional context (surrounding text, section info, etc.)

        Returns:
            LLMResponse with reviewed text and metadata
        """
        if not self.enabled:
            raise RuntimeError("LLM client is not enabled")

        prompt = self._build_review_prompt(text, context)

        async with self.semaphore:
            response = await self._call_api(prompt)

        return self._parse_response(response)

    async def review_batch(self, texts: List[str],
                          contexts: Optional[List[str]] = None) -> List[LLMResponse]:
        """
        Review multiple texts in parallel (within rate limits).

        Args:
            texts: List of texts to review
            contexts: Optional list of contexts

        Returns:
            List of LLMResponse objects
        """
        if not contexts:
            contexts = [None] * len(texts)

        tasks = [
            self.review_text(text, context)
            for text, context in zip(texts, contexts)
        ]

        return await asyncio.gather(*tasks, return_exceptions=True)

    def _build_review_prompt(self, text: str, context: Optional[str] = None) -> str:
        """Build prompt for text review."""
        prompt = f"""You are a technical documentation reviewer. Review the following text for:
1. Grammar and spelling errors
2. Technical accuracy
3. Clarity and consistency
4. Formatting issues

Text to review:
{text}
"""

        if context:
            prompt += f"\nContext:\n{context}\n"

        prompt += """
Please provide:
1. Corrected text
2. List of changes made
3. Confidence score (0-1)
4. Brief reasoning for major changes

Format your response as JSON:
{
  "corrected_text": "...",
  "changes": [...],
  "confidence": 0.95,
  "reasoning": "..."
}
"""

        return prompt

    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """
        Make API call to LLM service (with streaming support).

        Args:
            prompt: Prompt to send

        Returns:
            API response as dictionary
        """
        # Use streaming if enabled
        if self.stream:
            return await self._call_api_stream(prompt)

        # Non-streaming mode (fallback)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "api-key": self.api_key  # Microchip API uses 'api-key' header, not 'Authorization'
        }

        # Microchip API only accepts: messages, temperature, stream
        # Do NOT include model or max_tokens (causes 302 redirect)
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a technical documentation reviewer specializing in datasheets and technical specifications."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.temperature,
            "stream": False
        }

        response = await self.client.post(
            self.api_url,
            headers=headers,
            json=payload
        )

        response.raise_for_status()
        return response.json()

    async def _call_api_stream(self, prompt: str) -> Dict[str, Any]:
        """
        Make streaming API call to LLM service.

        Args:
            prompt: Prompt to send

        Returns:
            API response as dictionary (accumulated from stream)
        """
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "api-key": self.api_key  # Microchip API uses 'api-key' header, not 'Authorization'
        }

        # Microchip API only accepts: messages, temperature, stream
        # Do NOT include model or max_tokens (causes 302 redirect)
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a technical documentation reviewer specializing in datasheets and technical specifications."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.temperature,
            "stream": True
        }

        full_content = ""
        finish_reason = None

        try:
            async with self.client.stream(
                "POST",
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.stream_timeout
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # Check for end of stream
                    if line == "data: [DONE]":
                        break

                    # Parse SSE format: "data: {json}"
                    if line.startswith("data: "):
                        try:
                            data_str = line[6:]  # Remove "data: " prefix
                            chunk = json.loads(data_str)

                            # Extract content delta from chunk
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                choice = chunk["choices"][0]

                                # Handle delta format (streaming)
                                if "delta" in choice:
                                    delta = choice["delta"]
                                    content_delta = delta.get("content", "")
                                    full_content += content_delta

                                    # Check for finish reason
                                    if "finish_reason" in choice:
                                        finish_reason = choice["finish_reason"]

                        except json.JSONDecodeError as e:
                            # Skip malformed JSON chunks
                            print(f"Warning: Failed to parse stream chunk: {e}")
                            continue

            # Return accumulated response in standard format
            return {
                "choices": [{
                    "message": {
                        "content": full_content,
                        "role": "assistant"
                    },
                    "finish_reason": finish_reason or "stop"
                }]
            }

        except httpx.TimeoutException:
            raise RuntimeError(f"Stream timeout after {self.stream_timeout}s")
        except Exception as e:
            raise RuntimeError(f"Streaming API error: {e}")

    def _parse_response(self, api_response: Dict[str, Any]) -> LLMResponse:
        """
        Parse API response into LLMResponse.

        Args:
            api_response: Raw API response

        Returns:
            Parsed LLMResponse object
        """
        # This is a generic parser - adjust based on actual API format
        try:
            # Extract content from response
            content = api_response.get('choices', [{}])[0].get('message', {}).get('content', '')

            # Try to parse as JSON
            try:
                parsed_content = json.loads(content)
                return LLMResponse(
                    content=parsed_content.get('corrected_text', content),
                    confidence=parsed_content.get('confidence', 0.8),
                    reasoning=parsed_content.get('reasoning'),
                    metadata={
                        'changes': parsed_content.get('changes', []),
                        'raw_response': api_response
                    }
                )
            except json.JSONDecodeError:
                # If not JSON, return raw content
                return LLMResponse(
                    content=content,
                    confidence=0.7,
                    metadata={'raw_response': api_response}
                )

        except Exception as e:
            raise ValueError(f"Failed to parse API response: {e}")

    async def validate_cross_reference(self, reference: str,
                                      available_targets: List[str]) -> Dict[str, Any]:
        """
        Use LLM to validate/suggest cross-reference corrections.

        Args:
            reference: The reference to validate
            available_targets: List of valid reference targets

        Returns:
            Dictionary with validation result and suggestions
        """
        if not self.enabled:
            return {'valid': False, 'suggestions': []}

        prompt = f"""Validate this cross-reference: "{reference}"

Available valid targets:
{', '.join(available_targets[:20])}

Is this reference valid? If not, suggest the most likely correct target.
Respond in JSON format:
{{
  "valid": true/false,
  "suggested_target": "...",
  "confidence": 0.95
}}
"""

        async with self.semaphore:
            response = await self._call_api(prompt)

        try:
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
            return json.loads(content)
        except:
            return {'valid': False, 'suggestions': []}

    def is_available(self) -> bool:
        """Check if LLM client is available and configured."""
        return self.enabled and bool(self.api_url) and bool(self.api_key)


class MockLLMClient(LLMClient):
    """Mock LLM client for testing without actual API."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.enabled = True  # Always enabled for testing

    async def review_text(self, text: str, context: Optional[str] = None) -> LLMResponse:
        """Mock review that returns the original text."""
        # Simulate processing delay
        await asyncio.sleep(0.1)

        return LLMResponse(
            content=text,
            confidence=0.85,
            reasoning="Mock review - no changes made",
            metadata={'mock': True}
        )

    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """Mock API call."""
        return {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'corrected_text': 'Mock corrected text',
                        'changes': [],
                        'confidence': 0.85,
                        'reasoning': 'Mock reasoning'
                    })
                }
            }]
        }
