import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY = REPO_ROOT / "deploy/scripts/deploy.sh"
DISPATCH = REPO_ROOT / "deploy/scripts/dispatch.sh"
RUN_JOB = REPO_ROOT / "deploy/scripts/run-job.sh"
SHA = "a" * 40
REPOSITORY = "https://github.com/Example/D-Web.git"


class DeploymentScriptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "root"
        self.bin = self.root / "bin"
        self.fake_bin = Path(self.temp.name) / "fake-bin"
        self.fixture = Path(self.temp.name) / "fixture"
        self.bin.mkdir(parents=True)
        self.fake_bin.mkdir()
        (self.fixture / "deploy/scripts").mkdir(parents=True)
        (self.fixture / "deploy/runtime.yml").write_text("services: {}\n")
        shutil.copy2(
            REPO_ROOT / "deploy/scripts/check-isolation.py",
            self.fixture / "deploy/scripts/check-isolation.py",
        )
        shutil.copy2(DEPLOY, self.bin / "deploy.sh")
        shutil.copy2(DISPATCH, self.bin / "dispatch.sh")
        shutil.copy2(RUN_JOB, self.bin / "run-job.sh")
        for script in self.bin.iterdir():
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        (self.root / "repository.url").write_text(REPOSITORY + "\n")
        (self.root / "source.git").mkdir()
        env_dir = self.root / "staging"
        env_dir.mkdir()
        (env_dir / "deploy.env").write_text("OPERATOR_SETTING=present\n")
        self.log = Path(self.temp.name) / "commands.log"
        self._write_fake(
            "git",
            r"""#!/usr/bin/env bash
set -eu
printf 'git %s\n' "$*" >> "$FAKE_LOG"
case " $* " in
  *" config --get remote.origin.url "*) printf '%s\n' "$FAKE_REPOSITORY" ;;
  *" rev-parse FETCH_HEAD "*)
    if [[ ${FAKE_MODE-} == wrong_branch ]]; then printf '%040d\n' 0; else printf '%s\n' "$FAKE_SHA"; fi ;;
  *" archive "*) tar -C "$FAKE_FIXTURE" -cf - . ;;
esac
""",
        )
        self._write_fake(
            "docker",
            r"""#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f: f.write("docker " + " ".join(args) + "\n")
mode=os.environ.get("FAKE_MODE", "ok")
if args[:2] == ["network", "inspect"]:
    if "--format" in args: print(args[-1])
    sys.exit(0)
if "config" in args and "--format" in args:
    sha=os.environ["FAKE_SHA"]
    prefix="ghcr.io/foreign/d-web/staging" if mode == "wrong_prefix" else "ghcr.io/example/d-web/staging"
    payment="live" if mode == "crossenv" else "test"
    services={"postgres":{"networks":{"default":{}},"volumes":[{"source":"postgres_data","target":"/var/lib/postgresql/data"}]}}
    for name in ("api", "frontend", "admin"):
        services[name]={"image":f"{prefix}/{name}:{sha}", "networks":{"edge":{"aliases":[f"staging-{name}"]}}}
    services["api"]["environment"]={
      "PAYMENT_ENVIRONMENT":payment,"API_BASE_URL":"https://api.staging.example.com",
      "JWT_SECRET":"jwt-stage","PASSWORD_PEPPER":"password-stage","TOKEN_PEPPER":"token-stage",
      "TOTP_ENCRYPTION_KEY":"totp-stage","DATABASE_URL":"postgresql://dweb:db-stage@postgres/dweb",
      "R2_BUCKET":"stage-private","R2_PUBLIC_BUCKET":"stage-public",
      "R2_ACCESS_KEY_ID":"r2-stage","R2_SECRET_ACCESS_KEY":"r2-secret-stage"
    }
    services["migrate"]={"image":services["api"]["image"]}
    print(json.dumps({"name":"dweb-staging","services":services,"networks":{"default":{"name":"dweb-staging_default"},"edge":{"name":"dweb-staging-edge","external":True}},"volumes":{"postgres_data":{"name":"dweb-staging_postgres_data"}}}))
    sys.exit(0)
if args[:2] == ["image", "inspect"]:
    joined=" ".join(args)
    image=args[-1]
    if "RepoDigests" in joined:
        repo=image.rsplit(":",1)[0]
        digest="bad" if mode == "invalid_digest" else "sha256:" + "1"*64
        print(json.dumps([repo+"@"+digest]))
    elif "io.dweb.api-url" in joined:
        print("https://wrong.example.com" if mode == "api_label_mismatch" else "https://api.staging.example.com")
    else: print(os.environ["FAKE_SHA"])
    sys.exit(0)
if "exec" in args and "pg_dump" in args:
    if mode == "backup_fail": sys.exit(7)
    sys.stdout.buffer.write(b"dump-data"); sys.exit(0)
if "run" in args and "migrate" in args:
    if mode == "migration_fail": sys.exit(8)
    if mode == "worker_block":
        import time
        while not os.path.exists(os.environ["FAKE_RELEASE_WORKER"]): time.sleep(0.05)
if mode == "health_fail" and "up" in args and "api" in args:
    sys.exit(9)
sys.exit(0)
""",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _write_fake(self, name, text):
        path = self.fake_bin / name
        path.write_text(text)
        path.chmod(0o700)

    def env(self, mode="ok"):
        env = os.environ.copy()
        env.update(
            PATH=f"{self.fake_bin}:{env['PATH']}",
            DWEB_DEPLOY_ROOT=str(self.root),
            FAKE_LOG=str(self.log),
            FAKE_REPOSITORY=REPOSITORY,
            FAKE_SHA=SHA,
            FAKE_FIXTURE=str(self.fixture),
            FAKE_MODE=mode,
            FAKE_RELEASE_WORKER=str(Path(self.temp.name) / "release-worker"),
        )
        return env

    def run_deploy(self, *args, mode="ok"):
        return subprocess.run(
            [str(self.bin / "deploy.sh"), *args],
            env=self.env(mode),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def run_dispatch(self, mode="ok", timeout=10):
        return subprocess.run(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env(mode), "SSH_ORIGINAL_COMMAND": f"deploy {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )

    def write_completed_job(self):
        job_dir = self.root / f"staging/jobs/{SHA}"
        job_dir.mkdir(parents=True)
        (job_dir / "state").write_text("success\n")
        (job_dir / "job.log").write_text("previous success\n")
        (self.root / "staging/current.sha").write_text("b" * 40 + "\n")
        return job_dir

    def test_invalid_arguments_are_rejected_before_git_or_docker(self):
        for args in (
            ("preview", SHA),
            ("staging", "a;touch-pwned"),
            ("staging", SHA, "extra"),
        ):
            with self.subTest(args=args):
                result = self.run_deploy(*args)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_dispatch_accepts_only_exact_two_token_command(self):
        for command in (
            f"deploy {SHA} extra",
            f"deploy {SHA};id",
            f"deploy  {SHA}",
            f"deploy {SHA}\nid",
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    [str(self.bin / "dispatch.sh"), "staging"],
                    env={**self.env(), "SSH_ORIGINAL_COMMAND": command},
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_cross_environment_payment_config_stops_before_operational_docker(self):
        result = self.run_deploy("staging", SHA, mode="crossenv")
        self.assertNotEqual(result.returncode, 0)
        log = self.log.read_text()
        self.assertIn("config --format json", log)
        self.assertNotIn(" pull ", log)
        self.assertNotIn(" up ", log)
        self.assertFalse((self.root / "staging/current.sha").exists())

    def test_failed_backup_never_runs_migration_or_updates_health_state(self):
        current = self.root / "staging/current.sha"
        current.write_text("b" * 40 + "\n")
        result = self.run_deploy("staging", SHA, mode="backup_fail")
        self.assertNotEqual(result.returncode, 0)
        log = self.log.read_text()
        self.assertIn("pg_dump", log)
        self.assertNotIn(" run --rm --no-deps", log)
        self.assertEqual(current.read_text().strip(), "b" * 40)

    def test_failed_migration_preserves_current_sha(self):
        current = self.root / "staging/current.sha"
        current.write_text("b" * 40 + "\n")
        result = self.run_deploy("staging", SHA, mode="migration_fail")
        self.assertNotEqual(result.returncode, 0)
        log = self.log.read_text()
        self.assertIn("run --rm --no-deps --pull never migrate", log)
        self.assertNotIn(
            "up -d --no-deps --pull never --wait --wait-timeout 180 api", log
        )
        self.assertEqual(current.read_text().strip(), "b" * 40)

    def test_untrusted_branch_or_image_prefix_stops_before_service_changes(self):
        for mode in ("wrong_branch", "wrong_prefix"):
            with self.subTest(mode=mode):
                result = self.run_deploy("staging", SHA, mode=mode)
                self.assertNotEqual(result.returncode, 0)
                log = self.log.read_text()
                self.assertNotIn(" stop ", log)
                self.assertNotIn(" pull ", log)
                self.log.unlink()

    def test_invalid_digest_or_api_label_stops_before_service_changes(self):
        for mode in ("invalid_digest", "api_label_mismatch"):
            with self.subTest(mode=mode):
                result = self.run_deploy("staging", SHA, mode=mode)
                self.assertNotEqual(result.returncode, 0)
                log = self.log.read_text()
                self.assertIn(" pull postgres api frontend admin", log)
                self.assertNotIn(" stop ", log)
                self.assertFalse((self.root / "staging/current.sha").exists())
                self.log.unlink()

    def test_success_uses_digest_override_and_only_then_updates_state(self):
        old_sha = "b" * 40
        current = self.root / "staging/current.sha"
        current.write_text(old_sha + "\n")
        result = self.run_deploy("staging", SHA)
        self.assertEqual(result.returncode, 0, result.stderr)
        lock_file = self.root / f"staging/releases/{SHA}/images.lock.json"
        lock = lock_file.read_text()
        self.assertIn("@sha256:" + "1" * 64, lock)
        self.assertNotIn(":" + SHA, lock)
        operational = [
            line
            for line in self.log.read_text().splitlines()
            if " run " in line or " up -d " in line
        ]
        self.assertIn(" pull postgres api frontend admin", self.log.read_text())
        self.assertTrue(
            any(
                f"-f {lock_file}" in line and "--pull never migrate" in line
                for line in operational
            )
        )
        self.assertTrue(
            any(
                f"-f {lock_file}" in line and "--pull never --wait" in line
                for line in operational
            )
        )
        self.assertEqual(current.read_text().strip(), SHA)
        self.assertEqual(
            (self.root / "staging/previous.sha").read_text().strip(), old_sha
        )

    def test_worker_survives_dispatch_monitor_disconnect(self):
        worker_release = Path(self.env()["FAKE_RELEASE_WORKER"])
        process = subprocess.Popen(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env("worker_block"), "SSH_ORIGINAL_COMMAND": f"deploy {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        state_file = self.root / f"staging/jobs/{SHA}/state"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if state_file.exists() and state_file.read_text().strip() == "running":
                if self.log.exists() and " run " in self.log.read_text():
                    break
            time.sleep(0.05)
        else:
            process.terminate()
            self.fail("detached worker did not reach migration")
        retry = subprocess.Popen(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env("worker_block"), "SSH_ORIGINAL_COMMAND": f"deploy {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.2)
        self.assertFalse(list(state_file.parent.glob("job.previous.*.log")))
        retry.terminate()
        retry.wait(timeout=5)
        retry.communicate()
        process.terminate()
        process.wait(timeout=5)
        process.communicate()
        worker_release.touch()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if state_file.read_text().strip() == "success":
                break
            time.sleep(0.05)
        else:
            self.fail("worker stopped when the dispatcher monitor disconnected")
        self.assertEqual((self.root / "staging/current.sha").read_text().strip(), SHA)
        status = subprocess.run(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env(), "SSH_ORIGINAL_COMMAND": f"status {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(status.returncode, 0)
        self.assertEqual(status.stdout.strip(), "deployment job: success")

    def test_stale_running_state_without_lock_restarts_same_sha(self):
        job_dir = self.root / f"staging/jobs/{SHA}"
        job_dir.mkdir(parents=True)
        (job_dir / "state").write_text("running\n")
        (job_dir / "job.log").write_text("interrupted previous worker\n")
        process = subprocess.Popen(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env(), "SSH_ORIGINAL_COMMAND": f"deploy {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if (job_dir / "state").read_text().strip() == "success":
                break
            time.sleep(0.05)
        else:
            process.terminate()
            self.fail("stale running state was not restarted")
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        process.communicate()
        previous_logs = list(job_dir.glob("job.previous.*.log"))
        self.assertEqual(len(previous_logs), 1)
        self.assertEqual(previous_logs[0].read_text(), "interrupted previous worker\n")
        self.assertEqual((self.root / "staging/current.sha").read_text().strip(), SHA)

    def test_failed_job_retry_monitor_waits_for_new_worker_success(self):
        job_dir = self.root / f"staging/jobs/{SHA}"
        job_dir.mkdir(parents=True)
        (job_dir / "state").write_text("failed\n")
        (job_dir / "job.log").write_text("previous failure\n")
        result = subprocess.run(
            [str(self.bin / "dispatch.sh"), "staging"],
            env={**self.env(), "SSH_ORIGINAL_COMMAND": f"deploy {SHA}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "deployment job: success")
        self.assertEqual((job_dir / "state").read_text().strip(), "success")
        previous_logs = list(job_dir.glob("job.previous.*.log"))
        self.assertEqual(len(previous_logs), 1)
        self.assertEqual(previous_logs[0].read_text(), "previous failure\n")

    def test_successful_job_retry_revalidates_branch_before_docker_changes(self):
        job_dir = self.write_completed_job()

        result = self.run_dispatch(mode="wrong_branch")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((job_dir / "state").read_text().strip(), "failed")
        log = self.log.read_text()
        self.assertIn("rev-parse FETCH_HEAD", log)
        self.assertNotIn("docker ", log)
        self.assertEqual(
            (self.root / "staging/current.sha").read_text().strip(), "b" * 40
        )

    def test_successful_job_retry_runs_git_docker_and_health_checks(self):
        job_dir = self.write_completed_job()

        result = self.run_dispatch()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "deployment job: success")
        self.assertEqual((job_dir / "state").read_text().strip(), "success")
        log = self.log.read_text()
        self.assertIn("rev-parse FETCH_HEAD", log)
        self.assertIn(" pull postgres api frontend admin", log)
        self.assertIn(
            "up -d --no-deps --pull never --wait --wait-timeout 180 api frontend admin",
            log,
        )
        self.assertEqual((self.root / "staging/current.sha").read_text().strip(), SHA)

    def test_successful_job_retry_returns_failure_when_health_check_fails(self):
        job_dir = self.write_completed_job()

        result = self.run_dispatch(mode="health_fail")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((job_dir / "state").read_text().strip(), "failed")
        self.assertIn(
            "up -d --no-deps --pull never --wait --wait-timeout 180 api frontend admin",
            self.log.read_text(),
        )
        self.assertEqual(
            (self.root / "staging/current.sha").read_text().strip(), "b" * 40
        )


if __name__ == "__main__":
    unittest.main()
