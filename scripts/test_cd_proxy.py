import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / 'ssh-cloudflare-proxy.sh'


class CloudflareProxyTests(unittest.TestCase):
    def test_binary_stream_and_token_environment_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'cloudflared'
            argv = root / 'arguments'
            binary.write_text("#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\nassert os.environ['TUNNEL_SERVICE_TOKEN_ID']=='test-id'\nassert os.environ['TUNNEL_SERVICE_TOKEN_SECRET']=='test-secret'\nPath(os.environ['ARGUMENTS_FILE']).write_text(' '.join(sys.argv[1:]))\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
            binary.chmod(0o700)
            payload = b'SSH-2.0-test\r\n\x00\xff'
            result = subprocess.run(['bash', str(SCRIPT), 'deploy.example.com'], input=payload, capture_output=True, env={**os.environ, 'RUNNER_TEMP': directory, 'TUNNEL_SERVICE_TOKEN_ID': 'test-id', 'TUNNEL_SERVICE_TOKEN_SECRET': 'test-secret', 'ARGUMENTS_FILE': str(argv)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, payload)
            self.assertEqual(argv.read_text(), 'access ssh --hostname deploy.example.com')
            self.assertNotIn(b'test-secret', result.stdout + result.stderr)

    def test_invalid_hostname_and_missing_token_fail_before_client_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'RUNNER_TEMP': directory, 'TUNNEL_SERVICE_TOKEN_ID': 'test-id', 'TUNNEL_SERVICE_TOKEN_SECRET': 'test-secret'}
            for host in ['bad;id', 'host.example.com\nother', '-oProxyCommand=bad']:
                with self.subTest(host=host):
                    result = subprocess.run(['bash', str(SCRIPT), host], capture_output=True, env=env)
                    self.assertNotEqual(result.returncode, 0)
            env['TUNNEL_SERVICE_TOKEN_SECRET'] = ''
            result = subprocess.run(['bash', str(SCRIPT), 'deploy.example.com'], capture_output=True, env=env)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
