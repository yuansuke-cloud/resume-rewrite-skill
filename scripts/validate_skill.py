#!/usr/bin/env python3
"""Validate the public package structure and local documentation links."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "leo-resume-rewrite"


def validate():
    errors = []
    source = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", source, re.S)
    if not match:
        return ["SKILL.md needs YAML frontmatter"]
    metadata = yaml.safe_load(match[1])
    if not isinstance(metadata, dict):
        return ["Skill metadata must be a mapping"]
    if metadata.get("name") != SKILL.name:
        errors.append("Skill name must match its folder")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", metadata.get("name", "")):
        errors.append("Invalid skill name")
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        errors.append("Skill description is required")
    ui = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    interface = ui.get("interface", {})
    if "$leo-resume-rewrite" not in interface.get("default_prompt", ""):
        errors.append("Default prompt must reference the skill")
    if not 25 <= len(interface.get("short_description", "")) <= 64:
        errors.append("UI short_description must be 25-64 characters")
    documents = [ROOT / "README.md", ROOT / "AGENTS.md", *SKILL.rglob("*.md"), * (ROOT / "docs").rglob("*.md")]
    for path in documents:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            target = target.strip("<>")
            parts = urlsplit(target)
            if parts.scheme or target.startswith("#"):
                continue
            resolved = (path.parent / unquote(parts.path)).resolve()
            if not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing target {target}")
            if path.is_relative_to(SKILL) and not resolved.is_relative_to(SKILL):
                errors.append(f"{path.relative_to(ROOT)}: skill link escapes installable folder")
    for path in (ROOT / "LICENSE", SKILL / "LICENSE", SKILL / "requirements.txt", ROOT / "examples" / "fictional-resume.md"):
        if not path.is_file():
            errors.append(f"Missing {path.relative_to(ROOT)}")
    return errors


if __name__ == "__main__":
    findings = validate()
    if findings:
        print("\n".join(findings), file=sys.stderr)
        raise SystemExit(1)
    print("PASS: Skill metadata, UI, self-contained references and documentation links")
