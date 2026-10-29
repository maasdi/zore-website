import contextlib
import copy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_ci_run


REPOSITORY = "maasdi/zore-website"
COMMIT = "a" * 40
WORKFLOW = {"id": 12, "path": ".github/workflows/ci.yml"}
RUN = {
    "id": 34,
    "workflow_id": 12,
    "path": ".github/workflows/ci.yml",
    "repository": {"full_name": REPOSITORY},
    "head_repository": {"full_name": REPOSITORY},
    "event": "push",
    "head_branch": "main",
    "status": "completed",
    "conclusion": "success",
    "head_sha": COMMIT,
}


class VerifyCiRunTests(unittest.TestCase):
    def test_successful_main_push_is_verified(self):
        with patch.object(verify_ci_run, "github_json", side_effect=[WORKFLOW, RUN]):
            self.assertEqual(verify_ci_run.verified_commit("34", REPOSITORY), COMMIT)

    def test_untrusted_or_unsuccessful_runs_are_rejected(self):
        invalid_fields = {
            "id": 35,
            "workflow_id": 13,
            "path": ".github/workflows/other.yml",
            "repository": {"full_name": "other/repo"},
            "head_repository": {"full_name": "fork/zore-website"},
            "event": "pull_request",
            "head_branch": "feature",
            "status": "in_progress",
            "conclusion": "failure",
            "head_sha": "short-sha",
        }
        for field, value in invalid_fields.items():
            with self.subTest(field=field):
                invalid_run = copy.deepcopy(RUN)
                invalid_run[field] = value
                with patch.object(verify_ci_run, "github_json", side_effect=[WORKFLOW, invalid_run]):
                    with self.assertRaises(ValueError):
                        verify_ci_run.verified_commit("34", REPOSITORY)

    def promotion_output(self, automatic, current_head):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "output"
            environment = {
                "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_OUTPUT": str(destination),
                "AUTOMATIC_PROMOTION": str(automatic).lower(),
            }
            with patch.dict(os.environ, environment):
                with patch("sys.argv", ["verify_ci_run.py", "--run-id", "34"]):
                    with patch.object(verify_ci_run, "github_json", side_effect=[WORKFLOW, RUN, {"object": {"sha": current_head}}]) as api:
                        with contextlib.redirect_stdout(io.StringIO()):
                            verify_ci_run.main()
            return destination.read_text(encoding="utf-8"), api.call_count

    def test_automatic_promotion_accepts_current_main(self):
        output, calls = self.promotion_output(True, COMMIT)
        self.assertEqual(output, f"commit={COMMIT}\neligible=true\n")
        self.assertEqual(calls, 3)

    def test_automatic_promotion_skips_superseded_commit(self):
        output, calls = self.promotion_output(True, "b" * 40)
        self.assertEqual(output, f"commit={COMMIT}\neligible=false\n")
        self.assertEqual(calls, 3)

    def test_manual_rollback_accepts_older_successful_commit(self):
        output, calls = self.promotion_output(False, "b" * 40)
        self.assertEqual(output, f"commit={COMMIT}\neligible=true\n")
        self.assertEqual(calls, 2)

    def test_automatic_promotion_rejects_invalid_main_head(self):
        with self.assertRaises(ValueError):
            self.promotion_output(True, "invalid-sha")


if __name__ == "__main__":
    unittest.main()
