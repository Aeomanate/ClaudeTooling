#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""AI provider interface — abstracts the AI backend so steps don't depend
on a specific SDK.  Default: AnthropicProvider (uses the anthropic SDK).
Fallback: MockProvider for tests.
"""

import base64
import os

try:
    import anthropic
    from anthropic import AsyncAnthropic
except ImportError:
    anthropic = None
    AsyncAnthropic = None

from git_hooks_impl.logger import dbg, log, warn


class AIProvider:
    """Abstract interface for AI completions."""

    def text_completion(self, prompt, system='', model_override=None):
        """Send a text prompt, return the response text."""
        raise NotImplementedError

    def vision_completion(self, prompt, images, system='', model_override=None):
        """Send text + images, return the response text.

        images: list of (bytes, mime_type) tuples.
        """
        raise NotImplementedError

    def is_available(self):
        """Return True if the provider is configured and ready."""
        raise NotImplementedError


class AnthropicProvider(AIProvider):
    """Production provider using the anthropic Python SDK.

    Reads ANTHROPIC_AUTH_TOKEN from env.
    """

    _MODEL = 'claude-opus-4-6'
    _MODEL_VISION = 'claude-sonnet-4-6'

    def __init__(self):
        self._client = None
        self._api_key = os.environ.get('ANTHROPIC_AUTH_TOKEN', '')

    def _get_async_client(self):
        # AsyncAnthropic.messages.create() returns a coroutine (empirically verified:
        # asyncio.iscoroutine(client.messages.create(...)) == True, SDK v0.86.0)
        if self._client is None:
            if AsyncAnthropic is None:
                warn('anthropic package not installed — AI features unavailable')
                return None
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                timeout=600.0,
            )
        return self._client

    def is_available(self):
        """Check if SDK is importable and API key is set."""
        if not self._api_key:
            warn(
                'AI provider unavailable: '
                'ANTHROPIC_AUTH_TOKEN env var is empty or unset'
            )
            return False
        if anthropic is None:
            warn('AI provider unavailable: anthropic SDK not importable')
            return False
        return True

    async def text_completion(self, prompt, system='', model_override=None):
        """Send text prompt to Claude, return response text."""
        client = self._get_async_client()
        if not client:
            return ''

        model = model_override or self._MODEL
        dbg(f'AI call: model={model}, prompt={len(prompt)} chars')

        messages = [{'role': 'user', 'content': prompt}]
        kwargs = {'model': model, 'max_tokens': 16384, 'messages': messages}
        if system:
            kwargs['system'] = system

        # AsyncAnthropic.messages.create returns a coroutine — must await
        response = await client.messages.create(**kwargs)
        result = response.content[0].text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
        cache_write = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
        log(f'AI response: {len(result)} chars '
            f'(in={input_tokens}, out={output_tokens} tokens, '
            f'cache_read={cache_read}, cache_write={cache_write})')

        return result

    async def vision_completion(self, prompt, images, system='', model_override=None):
        """Send text + images to Claude, return response text.

        images: list of (bytes, mime_type) tuples.
        """
        client = self._get_async_client()
        if not client:
            return ''

        model = model_override or self._MODEL_VISION
        dbg(f'AI vision call: model={model}, {len(images)} images')

        content = []
        for image_bytes, mime_type in images:
            content.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': mime_type,
                    'data': base64.b64encode(image_bytes).decode(),
                },
            })
        content.append({'type': 'text', 'text': prompt})

        kwargs = {
            'model': model,
            'max_tokens': 4096,
            'messages': [{'role': 'user', 'content': content}],
        }
        if system:
            kwargs['system'] = system

        response = await client.messages.create(**kwargs)
        result = response.content[0].text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        log(f'AI vision response: {len(result)} chars '
            f'(in={input_tokens}, out={output_tokens} tokens)')

        return result


class MockProvider(AIProvider):
    """Test provider — returns canned responses in order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def is_available(self):
        return True

    async def text_completion(self, prompt, system='', model_override=None):
        self.calls.append({
            'type': 'text',
            'prompt': prompt,
            'system': system,
            'model_override': model_override,
        })
        if self.responses:
            return self.responses.pop(0)
        return ''

    async def vision_completion(self, prompt, images, system='', model_override=None):
        self.calls.append({
            'type': 'vision',
            'prompt': prompt,
            'images_count': len(images),
            'system': system,
            'model_override': model_override,
        })
        if self.responses:
            return self.responses.pop(0)
        return ''
