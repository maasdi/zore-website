import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


COMPILER_VERSION = "0.1.0-alpha.1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_metadata(metadata, expected_commit):
    require(re.fullmatch(r"[0-9a-f]{40}", expected_commit), "expected commit is not a full SHA")
    require(metadata.get("source_commit") == expected_commit, "artifact source commit differs")
    require(metadata.get("compiler_version") == COMPILER_VERSION, "artifact compiler differs")
    image_id = metadata.get("image_id", "")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id), "artifact image ID is invalid")
    return image_id


def verify_image(image, metadata, expected_commit):
    image_id = verify_metadata(metadata, expected_commit)
    require(image.get("Id") == image_id, "loaded image ID differs from artifact metadata")
    require(image.get("Architecture") == "amd64" and image.get("Os") == "linux", "loaded image platform differs")
    labels = image.get("Config", {}).get("Labels") or {}
    require(labels.get("org.opencontainers.image.revision") == expected_commit, "loaded image revision differs")
    require(labels.get("dev.zore.compiler.version") == COMPILER_VERSION, "loaded image compiler differs")
    return image_id


def load_verified_image(archive, checksum, metadata_path, expected_commit):
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_id = verify_metadata(metadata, expected_commit)
    checksum_text = checksum.read_text(encoding="utf-8")
    checksum_match = re.fullmatch(r"([0-9a-f]{64})  image\.tar\.gz\n?", checksum_text)
    require(checksum_match is not None, "invalid archive checksum file")
    with archive.open("rb") as source:
        actual_checksum = hashlib.file_digest(source, "sha256").hexdigest()
    require(actual_checksum == checksum_match[1], "runtime archive checksum differs")
    subprocess.run(["docker", "load", "--input", str(archive)], check=True, timeout=300)
    result = subprocess.run(
        ["docker", "image", "inspect", image_id],
        capture_output=True, text=True, check=True, timeout=30,
    )
    images = json.loads(result.stdout)
    require(isinstance(images, list) and len(images) == 1, "loaded image inspection differs")
    return verify_image(images[0], metadata, expected_commit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    options = parser.parse_args()
    image_id = load_verified_image(options.archive, options.checksum, options.metadata, options.expected_commit)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as destination:
            destination.write(f"image_id={image_id}\n")
    print(f"Verified runtime image {image_id} for {options.expected_commit}")


if __name__ == "__main__":
    main()
