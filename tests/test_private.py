import asyncio
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from backend import config, main
from backend.image_processor import process_image, is_image, ImageLimitError

PASSWORD = "test-only-password-with-32-characters"
USERHASH = "test-only-server-userhash"
URL = "https://files.catbox.moe/audit.png"


class PrivateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config_patch = patch.object(config, "CONFIG_DIR", Path(self.directory.name))
        self.config_patch.start()
        self.env = patch.dict(os.environ, {"CATBOX_USERHASH": USERHASH, "APP_PASSWORD": PASSWORD})
        self.env.start()
        main.app.middleware_stack = None
        self.lifespan = main.app.router.lifespan_context(main.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://private.test", auth=("admin", PASSWORD))

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.config_patch.stop()
        self.env.stop()
        self.directory.cleanup()

    async def test_private_routes_and_public_health(self):
        for path in ("/", "/static/app.js", "/api/config", "/api/history", "/api/export", "/docs", "/openapi.json"):
            response = await self.client.get(path, auth=None)
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual((await self.client.get("/api/health", auth=None)).status_code, 200)
        self.assertEqual((await self.client.get("/", auth=("admin", "wrong"))).status_code, 401)
        self.assertEqual((await self.client.get("/")).status_code, 200)

    async def test_secrets_never_exported_or_present_in_frontend(self):
        for path in ("/", "/static/app.js", "/api/config", "/api/export", "/api/history"):
            response = await self.client.get(path)
            self.assertNotIn(USERHASH, response.text)
            self.assertNotIn(PASSWORD, response.text)
        page = (await self.client.get("/")).text
        self.assertNotIn('id="input-userhash"', page)

    async def test_cross_origin_and_security_headers(self):
        response = await self.client.post('/api/config', json={'theme': 'dark'}, headers={'Origin': 'https://attacker.test'})
        self.assertEqual(response.status_code, 403)
        response = await self.client.post('/api/config', json={'theme': 'dark'}, headers={'Origin': 'https://private.test'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('access-control-allow-origin', response.headers)
        self.assertIn("script-src 'self'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['cache-control'], 'no-store')

    async def test_invalid_input_and_xss_are_rejected(self):
        for data in ({'theme': []}, {'webp_quality': 101}, {'upload_concurrency': 0}, {'userhash': 'override'}):
            self.assertEqual((await self.client.post('/api/config', json=data)).status_code, 422)
        for url in ('x" onerror="alert(1)', 'javascript:alert(1)', 'https://attacker.test/a.png', URL + '?x="'):
            response = await self.client.post('/api/import', json={'history': [{'url': url}]})
            self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.client.post('/api/history/delete', json={'urls': [[]]})).status_code, 422)

    async def test_backup_strips_legacy_client_credentials(self):
        result = await self.client.post('/api/import', json={'client': {'userhash': 'legacy-secret'}, 'history': [{'url': URL}]})
        self.assertEqual(result.status_code, 200)
        exported = (await self.client.get('/api/export')).json()
        self.assertNotIn('client', exported)
        self.assertNotIn('legacy-secret', json.dumps(exported))

    async def test_upload_uses_only_server_credential_and_keeps_history(self):
        observed = []
        async def upload(body, filename, userhash, session):
            observed.append((body.read(), userhash))
            return URL
        with patch.object(main, 'upload_file', upload):
            response = await self.client.post('/api/upload', files={'files': ('audit.txt', b'hello')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed, [(b'hello', USERHASH)])
        self.assertEqual(len(config.get_history()), 1)
        response = await self.client.post('/api/upload', files={'files': ('audit.txt', b'hello')}, data={'userhash': 'override'})
        self.assertEqual(response.status_code, 400)

    async def test_global_concurrency_is_bounded_and_released(self):
        active, peak = 0, 0
        async def upload(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(.08)
            active -= 1
            return URL
        with patch.object(main, 'upload_file', upload):
            responses = await asyncio.gather(*[self.client.post('/api/upload', files={'files': (f'{i}.txt', b'hello')}) for i in range(9)])
            self.assertLessEqual(peak, 3)
            self.assertIn(503, [r.status_code for r in responses])
            self.assertEqual((await self.client.post('/api/upload', files={'files': ('after.txt', b'hello')})).status_code, 200)

    async def test_body_size_limits_with_and_without_length(self):
        response = await self.client.post('/api/import', content=b'{}', headers={'Content-Length': str(3 * 1024 * 1024), 'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        async def chunks():
            for _ in range(3):
                yield b'x' * (1024 * 1024)
        response = await self.client.post('/api/import', content=chunks(), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        with patch.object(main.app.state, 'max_size', 4):
            response = await self.client.post('/api/upload', files={'files': ('large.txt', b'12345')})
        self.assertEqual(response.status_code, 413)

    async def test_retention_counts_and_concurrent_persistence(self):
        entries = [{'url': f'https://files.catbox.moe/{i}.png'} for i in range(500)]
        response = await self.client.post('/api/import', json={'history': entries})
        self.assertEqual(response.json()['imported_history'], 500)
        response = await self.client.post('/api/import', json={'history': [{'url': URL}]})
        self.assertEqual(response.json()['imported_history'], 0)
        self.assertEqual(response.json()['skipped_history'], 1)
        await asyncio.to_thread(config.add_history_batch, [{'url': URL}])
        self.assertEqual(len(config.get_history()), 500)
        config.remove_history_batch([entry['url'] for entry in entries] + [URL])
        await asyncio.gather(*[asyncio.to_thread(config.add_history_batch, [{'url': f'https://files.catbox.moe/parallel{i}.png'}]) for i in range(20)])
        self.assertEqual(len(config.get_history()), 20)


class StandaloneTests(unittest.TestCase):
    def test_custom_password_startup(self):
        async def start():
            async with main.app.router.lifespan_context(main.app):
                pass
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'CONFIG_DIR', Path(directory)):
            with patch.dict(os.environ, {'CATBOX_USERHASH': USERHASH, 'APP_PASSWORD': 'test-pass'}):
                asyncio.run(start())
            with patch.dict(os.environ, {'CATBOX_USERHASH': USERHASH, 'APP_PASSWORD': 'short7'}):
                with self.assertRaises(RuntimeError):
                    asyncio.run(start())

    def test_missing_credentials_fail_startup(self):
        async def start():
            async with main.app.router.lifespan_context(main.app):
                pass
        with patch.dict(os.environ, {'CATBOX_USERHASH': '', 'APP_PASSWORD': ''}):
            with self.assertRaises(RuntimeError):
                asyncio.run(start())

    def test_png_modes_and_transparency_preserve_format(self):
        for mode in ('RGB', 'RGBA', 'P', 'L'):
            image = Image.new(mode, (10, 10))
            if mode == 'P':
                image.info['transparency'] = 0
            source = io.BytesIO()
            image.save(source, format='PNG')
            body, ext = process_image(source.getvalue(), False, 80)
            self.assertEqual(ext, 'png')
            self.assertEqual(Image.open(io.BytesIO(body)).format, 'PNG')
            self.assertEqual(process_image(source.getvalue(), True, 80)[1], 'webp')

    def test_pixel_limit_and_external_file_remains_open(self):
        source = io.BytesIO()
        Image.new('RGB', (11, 10)).save(source, format='PNG')
        self.assertTrue(is_image(source))
        self.assertFalse(source.closed)
        with patch('backend.image_processor.MAX_PIXELS', 100):
            with self.assertRaises(ImageLimitError):
                is_image(source)

    def test_legacy_migration_preserves_original_and_filters_bad_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'CONFIG_DIR', Path(directory)):
            legacy = {'userhash': 'secret-not-for-db', 'webp_quality': 76, 'history': [{'url': URL}, {'url': 'x" onerror="x'}]}
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps(legacy), encoding='utf-8')
            config.initialize()
            self.assertEqual(config.get_settings()['webp_quality'], 76)
            self.assertEqual(len(config.get_history()), 1)
            self.assertEqual(json.loads(path.read_text()), legacy)
            self.assertNotIn(b'secret-not-for-db', (Path(directory) / 'settings.db').read_bytes())


if __name__ == '__main__':
    unittest.main()
