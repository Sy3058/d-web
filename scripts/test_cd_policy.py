"""Exercise deployment identity validation without network or repository mutations."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / 'prepare-deployment.sh'


class DeploymentIdentityTests(unittest.TestCase):
    def run_policy(self, **changes):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            env = {
                **os.environ,
                'DEPLOY_ENVIRONMENT': 'staging',
                'GITHUB_EVENT_NAME': 'push',
                'GITHUB_REF': 'refs/heads/develop',
                'GITHUB_SHA': 'a' * 40,
                'GITHUB_REPOSITORY': 'Example/D-Web',
                'API_HOST': 'staging-api.example.com',
                'GITHUB_OUTPUT': str(output),
                **changes,
            }
            result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)
            return result, output.read_text() if output.exists() else ''

    def test_branch_environment_mapping_and_image_namespace(self):
        for environment, branch in [('staging', 'develop'), ('production', 'release')]:
            with self.subTest(environment=environment):
                result, output = self.run_policy(DEPLOY_ENVIRONMENT=environment, GITHUB_REF=f'refs/heads/{branch}')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'image_prefix=ghcr.io/example/d-web/{environment}\n', output)
                self.assertIn('deployment_sha=' + 'a' * 40 + '\n', output)
                self.assertIn('api_url=https://staging-api.example.com\n', output)

    def test_pull_requests_and_untrusted_events_cannot_produce_deployment_outputs(self):
        for event in ['pull_request', 'pull_request_target', 'workflow_run']:
            with self.subTest(event=event):
                result, output = self.run_policy(GITHUB_EVENT_NAME=event)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')

    def test_manual_ci_retry_requires_the_matching_branch(self):
        result, output = self.run_policy(GITHUB_EVENT_NAME='workflow_dispatch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('deployment_sha=', output)
        result, output = self.run_policy(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/topic')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, '')

    def test_wrong_branch_or_environment_cannot_deploy(self):
        for overrides in [
            {'GITHUB_REF': 'refs/heads/release'},
            {'GITHUB_REF': 'refs/heads/main'},
            {'GITHUB_REF': 'refs/tags/develop'},
            {'DEPLOY_ENVIRONMENT': 'production'},
            {'DEPLOY_ENVIRONMENT': 'preview'},
        ]:
            with self.subTest(overrides=overrides):
                result, output = self.run_policy(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')

    def test_untrusted_sha_repository_or_host_cannot_inject_outputs(self):
        for field, values in {
            'GITHUB_SHA': ['main', 'a' * 39, 'a' * 40 + '\napi_url=https://bad.example'],
            'GITHUB_REPOSITORY': ['owner/repo/path', 'owner/repo;echo bad', 'owner/repo\nextra=x'],
            'API_HOST': ['localhost', 'api.localhost', '127.0.0.1', '10.0.0.1', 'https://api.example.com', 'api.example.com:8000', 'api.example.com/path', 'api.example.com\nextra=x', '-bad.example.com'],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    result, output = self.run_policy(**{field: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output, '')


if __name__ == '__main__':
    unittest.main()
