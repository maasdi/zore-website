import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def require(condition, message):
    if not condition:
        raise ValueError(message)


def github_json(endpoint):
    result = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)


def verified_commit(run_id, repository):
    require(re.fullmatch(r"[1-9][0-9]*", run_id), "run ID must be a positive integer")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "invalid repository")
    workflow = github_json(f"repos/{repository}/actions/workflows/ci.yml")
    run = github_json(f"repos/{repository}/actions/runs/{run_id}")
    require(workflow.get("path") == ".github/workflows/ci.yml", "CI workflow path differs")
    require(type(workflow.get("id")) is int, "CI workflow ID is missing")
    require(run.get("id") == int(run_id), "returned run ID differs")
    require(run.get("workflow_id") == workflow["id"], "run is not from the CI workflow")
    require(run.get("path") == ".github/workflows/ci.yml", "run workflow path differs")
    require(run.get("repository", {}).get("full_name") == repository, "run repository differs")
    require(run.get("head_repository", {}).get("full_name") == repository, "run head repository differs")
    require(run.get("event") == "push", "only push runs may be promoted")
    require(run.get("head_branch") == "main", "only main runs may be promoted")
    require(run.get("status") == "completed", "CI run is incomplete")
    require(run.get("conclusion") == "success", "CI run did not succeed")
    commit = run.get("head_sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "CI commit is not a full SHA")
    return commit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    options = parser.parse_args()
    commit = verified_commit(options.run_id, os.environ["GITHUB_REPOSITORY"])
    eligible = True
    if os.environ.get("AUTOMATIC_PROMOTION") == "true":
        branch = github_json(f"repos/{os.environ['GITHUB_REPOSITORY']}/git/ref/heads/main")
        head = branch.get("object", {}).get("sha", "")
        require(re.fullmatch(r"[0-9a-f]{40}", head), "main head is not a full SHA")
        eligible = commit == head
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as destination:
        destination.write(f"commit={commit}\n")
        destination.write(f"eligible={str(eligible).lower()}\n")
    print(f"Verified successful main CI run {options.run_id} for {commit}")
    if not eligible:
        print("Skipping automatic promotion because main has a newer commit")


if __name__ == "__main__":
    main()
