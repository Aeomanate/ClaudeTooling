#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for ai_provider.py — AIProvider interface and implementations.

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_ai_provider.py" -v
"""

import base64 as b64
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import git_hooks_impl.ai_provider as _ai_provider_module
from git_hooks_impl.ai_provider import AIProvider, AnthropicProvider, MockProvider

try:
    import anthropic as _anthropic_sdk
    _ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    _anthropic_sdk = None
    _ANTHROPIC_SDK_AVAILABLE = False

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.ai_provider.dbg',
        'git_hooks_impl.ai_provider.log',
        'git_hooks_impl.ai_provider.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


class TestAnthropicProviderAvailability(unittest.TestCase):
    """Check is_available() for various env/import states."""

    def setUp(self):
        _ai_provider_module.anthropic = _anthropic_sdk
        self._sdk_available = _ANTHROPIC_SDK_AVAILABLE

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    def test_available_with_auth_token(self):
        """ANTHROPIC_AUTH_TOKEN set + anthropic importable -> True."""
        if not self._sdk_available:
            self.skipTest('anthropic SDK not installed')
        provider = AnthropicProvider()
        self.assertTrue(provider.is_available())

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_key(self):
        """No API key env vars -> False."""
        provider = AnthropicProvider()
        self.assertFalse(provider.is_available())


class TestAnthropicProviderCalls(unittest.IsolatedAsyncioTestCase):
    """Verify SDK is called correctly (async methods)."""

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_text_completion_calls_sdk(self):
        """text_completion('hello') -> messages.create awaited with prompt."""
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='world')]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        # AsyncMock: messages.create must be awaitable (provider uses await)
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.text_completion('hello')

        self.assertEqual(result, 'world')
        mock_client.messages.create.assert_called_once()

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_vision_completion_sends_base64(self):
        """Image bytes -> base64 encoded in content block."""
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='I see a chart')]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 20
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.vision_completion(
            'describe this', [(b'\x89PNG', 'image/png')],
        )

        self.assertEqual(result, 'I see a chart')
        call_kwargs = mock_client.messages.create.call_args.kwargs
        content = call_kwargs['messages'][0]['content']
        self.assertEqual(content[0]['type'], 'image')
        self.assertEqual(content[1]['type'], 'text')


class TestMockProvider(unittest.IsolatedAsyncioTestCase):
    """MockProvider returns canned responses and tracks calls (async methods)."""

    async def test_returns_responses_in_order(self):
        """['a', 'b'] -> first call 'a', second call 'b'."""
        provider = MockProvider(responses=['a', 'b'])
        self.assertEqual(await provider.text_completion('q1'), 'a')
        self.assertEqual(await provider.text_completion('q2'), 'b')

    async def test_tracks_call_details(self):
        """Each call recorded with type, prompt, model_override."""
        provider = MockProvider(responses=['ok'])
        await provider.text_completion('hello', system='sys', model_override='opus')
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]['type'], 'text')
        self.assertEqual(provider.calls[0]['prompt'], 'hello')
        self.assertEqual(provider.calls[0]['model_override'], 'opus')

    async def test_vision_tracks_image_count(self):
        """Vision call records number of images."""
        provider = MockProvider(responses=['chart description'])
        await provider.vision_completion('describe', [(b'img1', 'image/png'), (b'img2', 'image/png')])
        self.assertEqual(provider.calls[0]['images_count'], 2)

    def test_always_available(self):
        """MockProvider.is_available() -> True."""
        self.assertTrue(MockProvider().is_available())

    async def test_empty_responses_returns_empty(self):
        """No responses left -> ''."""
        provider = MockProvider(responses=[])
        self.assertEqual(await provider.text_completion('q'), '')

    async def test_vision_empty_responses_returns_empty(self):
        """Vision with no responses left -> ''."""
        provider = MockProvider(responses=[])
        self.assertEqual(
            await provider.vision_completion('q', [(b'img', 'image/png')]), '',
        )


class TestAIProviderAbstract(unittest.IsolatedAsyncioTestCase):
    """Base AIProvider raises NotImplementedError for all methods."""

    def setUp(self):
        self.provider = AIProvider()

    async def test_text_completion_not_implemented(self):
        """Abstract text_completion -> NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            await self.provider.text_completion('prompt')

    async def test_vision_completion_not_implemented(self):
        """Abstract vision_completion -> NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            await self.provider.vision_completion('prompt', [])

    def test_is_available_not_implemented(self):
        """Abstract is_available -> NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.provider.is_available()


class TestAnthropicProviderImportFallback(unittest.TestCase):
    """Verify behaviour when anthropic SDK is not installed."""

    def setUp(self):
        self._original_anthropic = _ai_provider_module.anthropic
        self._original_async_anthropic = _ai_provider_module.AsyncAnthropic
        _ai_provider_module.anthropic = None
        _ai_provider_module.AsyncAnthropic = None
        os.environ['ANTHROPIC_AUTH_TOKEN'] = 'test-token'

    def tearDown(self):
        _ai_provider_module.anthropic = self._original_anthropic
        _ai_provider_module.AsyncAnthropic = self._original_async_anthropic
        os.environ.pop('ANTHROPIC_AUTH_TOKEN', None)

    def test_get_client_returns_none_when_sdk_missing(self):
        """SDK not installed -> _get_async_client returns None, AI unavailable."""
        provider = AnthropicProvider()
        self.assertIsNone(provider._get_async_client())

    def test_is_available_false_when_sdk_missing(self):
        """SDK not installed -> is_available() returns False even with key."""
        provider = AnthropicProvider()
        self.assertFalse(provider.is_available())


class TestAnthropicProviderNoClient(unittest.IsolatedAsyncioTestCase):
    """Verify graceful fallback when _get_async_client returns None."""

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_text_completion_returns_empty_when_no_client(self):
        """No SDK client -> text_completion returns empty string."""
        provider = AnthropicProvider()
        provider._get_async_client = MagicMock(return_value=None)
        self.assertEqual(await provider.text_completion('hello'), '')

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_vision_completion_returns_empty_when_no_client(self):
        """No SDK client -> vision_completion returns empty string."""
        provider = AnthropicProvider()
        provider._get_async_client = MagicMock(return_value=None)
        self.assertEqual(
            await provider.vision_completion('describe', [(b'\x89PNG', 'image/png')]),
            '',
        )


class TestAnthropicProviderSystemParam(unittest.IsolatedAsyncioTestCase):
    """Verify the system parameter is forwarded to the SDK."""

    def _make_provider_with_mock_client(self):
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='reply')]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client
        return provider, mock_client

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_text_completion_with_system(self):
        """System prompt provided -> 'system' key included in SDK call."""
        provider, mock_client = self._make_provider_with_mock_client()
        await provider.text_completion('hello', system='be helpful')
        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs['system'], 'be helpful')

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_text_completion_without_system(self):
        """No system prompt -> 'system' key absent from SDK call."""
        provider, mock_client = self._make_provider_with_mock_client()
        await provider.text_completion('hello')
        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn('system', call_kwargs)

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_vision_completion_with_system(self):
        """System prompt provided -> 'system' key included in vision SDK call."""
        provider, mock_client = self._make_provider_with_mock_client()
        await provider.vision_completion(
            'describe', [(b'\x89PNG', 'image/png')], system='be concise',
        )
        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs['system'], 'be concise')

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_vision_completion_without_system(self):
        """No system prompt -> 'system' key absent from vision SDK call."""
        provider, mock_client = self._make_provider_with_mock_client()
        await provider.vision_completion('describe', [(b'\x89PNG', 'image/png')])
        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn('system', call_kwargs)


class TestAnthropicProviderBase64Encoding(unittest.IsolatedAsyncioTestCase):
    """Verify vision_completion encodes image bytes to base64 correctly."""

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_image_bytes_encoded_as_base64(self):
        """Raw image bytes -> base64-encoded string in API content block."""
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='ok')]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 10
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        image_data = b'\x89PNG\r\n\x1a\nfake'
        await provider.vision_completion('what is this', [(image_data, 'image/png')])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        image_block = call_kwargs['messages'][0]['content'][0]
        self.assertEqual(image_block['source']['type'], 'base64')
        self.assertEqual(image_block['source']['media_type'], 'image/png')
        self.assertEqual(
            image_block['source']['data'],
            b64.b64encode(image_data).decode(),
        )

    @patch.dict(os.environ, {'ANTHROPIC_AUTH_TOKEN': 'test-token'})
    async def test_multiple_images_all_encoded(self):
        """Multiple images -> each gets its own base64 content block."""
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='two images')]
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 15
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        images = [
            (b'img1data', 'image/png'),
            (b'img2data', 'image/jpeg'),
        ]
        await provider.vision_completion('compare', images)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        content = call_kwargs['messages'][0]['content']
        self.assertEqual(len(content), 3)  # 2 images + 1 text
        self.assertEqual(content[0]['source']['media_type'], 'image/png')
        self.assertEqual(content[1]['source']['media_type'], 'image/jpeg')
        self.assertEqual(content[2]['type'], 'text')
        self.assertEqual(content[2]['text'], 'compare')
