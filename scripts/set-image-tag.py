#!/usr/bin/env python3
"""Change one known image tag without reformatting the manifests."""
import re
import sys
from pathlib import Path

PROJECTS = {"eudris-app": "eudris", "reporter-api": "reporter", "reporter-ui": "reporter"}

def set_tag(root, project, tag):
    if project not in PROJECTS:
        raise ValueError(f"Unknown project: {project}")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValueError("Invalid image tag")
    path = root / "onpremise/live" / PROJECTS[project] / "kustomization.yaml"
    image = "192.168.88.237:31081/ci-docker/" + project
    pattern = re.compile(r"(^[ \t]*- name: " + re.escape(image) + r"\n[ \t]+newTag: )[^\n]+", re.MULTILINE)
    original = path.read_text()
    if len(pattern.findall(original)) != 1:
        raise ValueError(f"Expected exactly one tag for {image} in {path}")
    updated = pattern.sub(lambda m: m[1] + tag, original)
    if updated != original:
        path.write_text(updated)
    return path.relative_to(root)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: set-image-tag.py PROJECT IMAGE_TAG")
    try:
        print(set_tag(Path(__file__).resolve().parents[1], *sys.argv[1:]))
    except ValueError as error:
        sys.exit(str(error))
