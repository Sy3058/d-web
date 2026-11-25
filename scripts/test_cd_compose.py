"""Render real Compose files with disposable, non-secret fixture settings."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComposeDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        binary = os.environ.get('DWEB_COMPOSE_BIN')
        self.command = [binary] if binary else ['docker', 'compose']

    def tearDown(self):
        self.temporary.cleanup()

    def render(self, filename, values, project):
        envfile = self.directory / f'{project}.env'
        envfile.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
        result = subprocess.run([*self.command, '-p', project, '--env-file', str(envfile), '-f', str(ROOT / filename), 'config', '--format', 'json'], env={**os.environ, **values}, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_runtime_isolates_projects_and_keeps_existing_staging_volume(self):
        for name in ['staging', 'production']:
            with self.subTest(environment=name):
                backend = self.directory / f'{name}-backend.env'
                backend.write_text('JWT_SECRET=non-secret-fixture\n')
                values = dict(COMPOSE_PROJECT_NAME=f'dweb-{name}', IMAGE_PREFIX=f'ghcr.io/example/d-web/{name}', DEPLOY_SHA='a' * 40, BACKEND_ENV_FILE=str(backend), POSTGRES_PASSWORD='a' * 64, APP_HOST=f'{name}.example.com', ADMIN_HOST=f'{name}-admin.example.com', API_HOST=f'{name}-api.example.com', PAYMENT_ENVIRONMENT='test', PAYMENTS_ACCEPT_NEW='false', EDGE_NETWORK=f'dweb-{name}-edge', EDGE_ALIAS_PREFIX=name)
                config = self.render('deploy/runtime.yml', values, f'dweb-{name}')
                self.assertEqual(set(config['services']), {'postgres', 'migrate', 'api', 'frontend', 'admin'})
                self.assertFalse(any(service.get('ports') for service in config['services'].values()))
                self.assertEqual(config['volumes']['postgres_data']['name'], f'dweb-{name}_postgres_data')
                self.assertEqual(config['networks']['edge']['name'], f'dweb-{name}-edge')
                self.assertEqual(set(config['services']['postgres']['networks']), {'default'})
                for service in ['api', 'frontend', 'admin']:
                    self.assertEqual(config['services'][service]['networks']['edge']['aliases'], [f'{name}-{service}'])
                self.assertEqual(config['services']['migrate']['image'], config['services']['api']['image'])
                self.assertEqual(config['services']['api']['environment']['ENV'], 'production')

    def test_only_common_gateway_publishes_web_ports_and_reuses_certificates(self):
        values = dict(COMPOSE_PROJECT_NAME='dweb-edge', ACME_EMAIL='ops@example.com', STAGING_APP_HOST='staging.example.com', STAGING_ADMIN_HOST='staging-admin.example.com', STAGING_API_HOST='staging-api.example.com', PRODUCTION_APP_HOST='example.com', PRODUCTION_ADMIN_HOST='admin.example.com', PRODUCTION_API_HOST='api.example.com', CADDY_DATA_VOLUME='dweb-staging_caddy_data', CADDY_CONFIG_VOLUME='dweb-staging_caddy_config')
        config = self.render('deploy/edge.yml', values, 'dweb-edge')
        self.assertEqual(set(config['services']), {'caddy'})
        ports = {str(port['published']) for port in config['services']['caddy']['ports']}
        self.assertEqual(ports, {'80', '443'})
        self.assertEqual(config['volumes']['caddy_data']['name'], 'dweb-staging_caddy_data')
        self.assertEqual(config['volumes']['caddy_config']['name'], 'dweb-staging_caddy_config')
        self.assertEqual({network['name'] for network in config['networks'].values()}, {'dweb-staging-edge', 'dweb-production-edge'})


if __name__ == '__main__':
    unittest.main()
