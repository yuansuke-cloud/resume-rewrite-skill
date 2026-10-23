#!/usr/bin/env python3
"""Build a deterministic installable ZIP from an explicit public-file allowlist."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "resume-rewrite"
PUBLIC_FILES = (
    "SKILL.md", "LICENSE", "requirements.txt", "agents/openai.yaml",
    "references/facts-and-writing.md", "references/role-research.md",
    "references/layout.md", "references/renderer-contract.md",
    "scripts/render_resume_pdf.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "resume-rewrite.zip")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    payload = []
    for name in PUBLIC_FILES:
        path = SKILL / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Missing or symlinked public file: {name}")
        if output == path.resolve():
            raise SystemExit("Output must not overwrite a source file")
        payload.append((name, path.read_bytes()))
    if output.suffix.lower() != ".zip":
        raise SystemExit("Output must use .zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload):
            info = zipfile.ZipInfo("resume-rewrite/" + name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"archive": str(output), "files": len(payload), "sha256": digest}))


if __name__ == "__main__":
    main()
