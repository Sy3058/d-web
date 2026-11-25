"""Guard the CI/CD workflow trust boundaries without a YAML dependency."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
WORKFLOW_NAMES = ("ci.yml", "build-images.yml", "deploy.yml")

ALLOWED_ACTIONS = {
    "actions/checkout",
    "actions/setup-node",
    "astral-sh/setup-uv",
    "pnpm/action-setup",
}


def read_workflow(name):
    return (WORKFLOWS / name).read_text()


def job_block(document, job_id):
    match = re.search(
        rf"(?ms)^  {re.escape(job_id)}:\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*\n|\Z)",
        document,
    )
    if match is None:
        raise AssertionError(f"job not found: {job_id}")
    return match.group(0)


def top_level_block(document, key):
    match = re.search(
        rf"(?ms)^{re.escape(key)}:\s*\n(.*?)(?=^[A-Za-z0-9_-]+:\s*\n|\Z)",
        document,
    )
    if match is None:
        raise AssertionError(f"top-level block not found: {key}")
    return match.group(0)


def mapping_keys(block, indent):
    return set(re.findall(rf"(?m)^{' ' * indent}([A-Za-z0-9_-]+):", block))


def nested_block(document, key, indent):
    spaces = " " * indent
    match = re.search(
        rf"(?ms)^{spaces}{re.escape(key)}:\s*\n(.*?)"
        rf"(?=^{spaces}[A-Za-z0-9_-]+:\s*\n|\Z)",
        document,
    )
    if match is None:
        raise AssertionError(f"nested block not found: {key}")
    return match.group(0)


class WorkflowSupplyChainTests(unittest.TestCase):
    def test_external_actions_are_allowlisted_and_pinned_to_commits(self):
        for filename in WORKFLOW_NAMES:
            document = read_workflow(filename)
            for target in re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", document):
                with self.subTest(workflow=filename, action=target):
                    if target.startswith("./.github/workflows/"):
                        self.assertRegex(target, r"^\./\.github/workflows/[\w-]+\.yml$")
                        continue
                    action, separator, revision = target.partition("@")
                    self.assertEqual(separator, "@")
                    self.assertIn(action, ALLOWED_ACTIONS)
                    self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_every_checkout_disables_credential_persistence(self):
        for filename in WORKFLOW_NAMES:
            document = read_workflow(filename)
            checkout_steps = re.findall(
                r"(?ms)^\s{6}- (?:name:.*?\n\s{8})?uses:\s*actions/checkout@.*?"
                r"(?=^\s{6}- |^\s{2}[A-Za-z0-9_-]+:|\Z)",
                document,
            )
            self.assertTrue(checkout_steps, filename)
            for step in checkout_steps:
                with self.subTest(workflow=filename):
                    self.assertRegex(
                        step, r"(?m)^\s{10}persist-credentials:\s*false\s*$"
                    )

    def test_ci_publishes_only_after_all_gates_and_explicit_opt_in(self):
        document = read_workflow("ci.yml")
        publish = job_block(document, "publish")
        self.assertEqual(
            set(re.findall(r"\b(branch-policy|backend|frontend|admin)\b", publish)),
            {"branch-policy", "backend", "frontend", "admin"},
        )
        for required in (
            "github.event_name == 'push'",
            "refs/heads/develop",
            "refs/heads/release",
            "vars.STAGING_DEPLOY_ENABLED == 'true'",
            "vars.PRODUCTION_DEPLOY_ENABLED == 'true'",
            "uses: ./.github/workflows/build-images.yml",
            "deployment_environment:",
            "api_host:",
            "vars[github.ref == 'refs/heads/develop' && 'STAGING_API_HOST' || "
            "'PRODUCTION_API_HOST']",
        ):
            self.assertIn(required, publish)
        self.assertNotIn("vars.STAGING_API_HOST || vars.PRODUCTION_API_HOST", publish)
        self.assertNotRegex(publish, r"(?m)^\s{4}environment:")
        self.assertNotRegex(publish, r"(?m)^\s*secrets:")
        self.assertNotIn("${{ secrets.", publish)

        deploy = job_block(document, "deploy")
        self.assertRegex(deploy, r"(?m)^\s{4}needs:\s*publish\s*$")
        self.assertIn("uses: ./.github/workflows/deploy.yml", deploy)

    def test_image_build_has_only_public_inputs_and_registry_write_access(self):
        document = read_workflow("build-images.yml")
        workflow_call = re.search(
            r"(?ms)^  workflow_call:\s*\n(.*?)(?=^[A-Za-z0-9_-]+:|\Z)", document
        )
        self.assertIsNotNone(workflow_call)
        call = workflow_call.group(0)
        self.assertEqual(mapping_keys(call, 6), {"deployment_environment", "api_host"})
        self.assertNotRegex(call, r"(?m)^\s{4}secrets:")

        permissions = top_level_block(document, "permissions")
        self.assertEqual(mapping_keys(permissions, 2), {"contents"})
        self.assertRegex(permissions, r"(?m)^  contents:\s*read\s*$")
        build = job_block(document, "build")
        self.assertRegex(build, r"(?m)^\s{6}contents:\s*read\s*$")
        self.assertRegex(build, r"(?m)^\s{6}packages:\s*write\s*$")
        self.assertNotRegex(document, r"(?m)^\s+environment:")
        secret_references = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", document))
        self.assertLessEqual(secret_references, {"GITHUB_TOKEN"})
        for forbidden in (
            "SSH_PRIVATE_KEY",
            "SSH_KNOWN_HOSTS",
            "CF_ACCESS_CLIENT_ID",
            "CF_ACCESS_CLIENT_SECRET",
            "ssh ",
            "cloudflared",
        ):
            self.assertNotIn(forbidden, document)

    def test_deploy_is_a_fresh_runner_with_only_deployment_credentials(self):
        document = read_workflow("deploy.yml")
        call = re.search(
            r"(?ms)^  workflow_call:\s*\n(.*?)(?=^[A-Za-z0-9_-]+:|\Z)", document
        )
        self.assertIsNotNone(call)
        secrets = nested_block(call.group(0), "secrets", 4)
        self.assertEqual(
            mapping_keys(secrets, 6),
            {
                "SSH_PRIVATE_KEY",
                "SSH_KNOWN_HOSTS",
                "CF_ACCESS_CLIENT_ID",
                "CF_ACCESS_CLIENT_SECRET",
            },
        )

        permissions = top_level_block(document, "permissions")
        self.assertEqual(mapping_keys(permissions, 2), {"contents"})
        self.assertRegex(permissions, r"(?m)^  contents:\s*read\s*$")
        self.assertNotIn("packages: write", document)

        deploy = job_block(document, "deploy")
        self.assertRegex(deploy, r"(?m)^\s{4}runs-on:\s*ubuntu-latest\s*$")
        self.assertRegex(deploy, r"(?m)^\s{4}environment:")
        ordered_markers = (
            "actions/checkout@",
            "prepare-deployment.sh",
            "cloudflared",
            "sha256sum --check",
            "SSH_KNOWN_HOSTS",
            "Deploy the verified commit over SSH",
        )
        positions = [deploy.find(marker) for marker in ordered_markers]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

        lowered = deploy.lower()
        for forbidden in (
            "docker build",
            "docker push",
            "docker login",
            "pnpm install",
            "npm install",
            "uv sync",
            "apt-get",
            "actions/cache",
            "upload-artifact",
            "download-artifact",
        ):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
