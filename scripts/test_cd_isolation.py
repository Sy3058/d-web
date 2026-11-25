import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "cd_isolation",
    Path(__file__).resolve().parents[1] / "deploy/scripts/check-isolation.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def config(name):
    env = {key: f"{name}-{key}" for key in module.AUTH_KEYS}
    env.update(
        DATABASE_URL=f"postgresql+asyncpg://dweb:{name}-password@postgres/dweb",
        R2_BUCKET=f"{name}-private",
        R2_PUBLIC_BUCKET=f"{name}-public",
        R2_ACCESS_KEY_ID=f"{name}-id",
        R2_SECRET_ACCESS_KEY=f"{name}-secret",
    )
    return {"services": {"api": {"environment": env}}}


class EnvironmentIsolationTests(unittest.TestCase):
    def test_separate_environments_are_accepted(self):
        module.check_isolation("production", config("production"), config("staging"))
        module.check_isolation("staging", config("staging"), config("production"))

    def test_first_staging_is_allowed_but_production_requires_staging(self):
        module.check_isolation("staging", config("staging"))
        with self.assertRaises(ValueError):
            module.check_isolation("production", config("production"))

    def test_shared_auth_secret_or_database_password_is_rejected(self):
        for key in (*module.AUTH_KEYS, "DATABASE_URL"):
            with self.subTest(key=key):
                first, other = config("production"), config("staging")
                first["services"]["api"]["environment"][key] = other["services"]["api"][
                    "environment"
                ][key]
                with self.assertRaises(ValueError):
                    module.check_isolation("production", first, other)

    def test_shared_or_crossed_r2_bucket_and_credentials_are_rejected(self):
        for key in (
            "R2_BUCKET",
            "R2_PUBLIC_BUCKET",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        ):
            with self.subTest(key=key):
                first, other = config("production"), config("staging")
                first["services"]["api"]["environment"][key] = other["services"]["api"][
                    "environment"
                ][key]
                with self.assertRaises(ValueError):
                    module.check_isolation("production", first, other)
        first, other = config("production"), config("staging")
        first["services"]["api"]["environment"]["R2_PUBLIC_BUCKET"] = other["services"][
            "api"
        ]["environment"]["R2_BUCKET"]
        with self.assertRaises(ValueError):
            module.check_isolation("production", first, other)

    def test_unused_storage_is_allowed(self):
        first, other = config("production"), config("staging")
        for env in (
            first["services"]["api"]["environment"],
            other["services"]["api"]["environment"],
        ):
            for key in tuple(env):
                if key.startswith("R2_"):
                    env[key] = ""
        module.check_isolation("production", first, other)

    def test_omitted_bucket_names_use_backend_defaults(self):
        first, other = config("production"), config("staging")
        for env in (
            first["services"]["api"]["environment"],
            other["services"]["api"]["environment"],
        ):
            del env["R2_BUCKET"]
            del env["R2_PUBLIC_BUCKET"]
        with self.assertRaises(ValueError):
            module.check_isolation("production", first, other)


if __name__ == "__main__":
    unittest.main()
