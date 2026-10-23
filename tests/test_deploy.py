import base64
import unittest
from unittest.mock import patch
from deploy_server import team_gate, build_app


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        def app(env, start):
            start('200 OK', [])
            return [b'protected']
        self.app = team_gate(app, 'https://demo.example', 'x' * 24)

    def call(self, **headers):
        env = dict(PATH_INFO='/', REQUEST_METHOD='GET', HTTP_HOST='demo.example')
        env.update(headers)
        response = []
        body = b''.join(self.app(env, lambda status, h: response.append(status)))
        return response[0], body

    def test_gate_and_cross_origin(self):
        self.assertTrue(self.call()[0].startswith('401'))
        auth = 'Basic ' + base64.b64encode(b'team:' + b'x' * 24).decode()
        self.assertEqual(self.call(HTTP_AUTHORIZATION=auth)[1], b'protected')
        self.assertTrue(self.call(HTTP_AUTHORIZATION=auth, HTTP_ORIGIN='https://other.example')[0].startswith('403'))
        self.assertTrue(self.call(HTTP_AUTHORIZATION=auth, HTTP_HOST='other.example')[0].startswith('403'))
        self.assertTrue(self.call(HTTP_AUTHORIZATION='Basic invalid!')[0].startswith('401'))
        self.assertEqual(self.call(PATH_INFO='/healthz')[1], b'ok')

    def test_deploy_refuses_missing_secrets_or_volume(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'PUBLIC_ORIGIN'):
                build_app()
        settings = {'PUBLIC_ORIGIN': 'https://demo.example', 'TEAM_PASSWORD': 'x' * 24,
                    'DATA_DIR': '/data', 'RAILWAY_ENVIRONMENT_ID': 'test'}
        with patch.dict('os.environ', settings, clear=True):
            with self.assertRaisesRegex(ValueError, 'volume'):
                build_app()
        with patch.dict('os.environ', {'PUBLIC_ORIGIN': 'https://demo.example'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'TEAM_PASSWORD'):
                build_app()
