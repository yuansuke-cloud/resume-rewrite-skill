"""Behavioral tests using synthetic text and a dependency's bundled test font."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import reportlab
from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "resume-rewrite" / "scripts" / "render_resume_pdf.py"
SPEC = importlib.util.spec_from_file_location("resume_renderer", SCRIPT)
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)
TEST_FONT = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"

MINIMAL = "# Sample Candidate\n\n## Summary\n\nSupplied text only.\n"
RICH = """# Sample Candidate

Target: Account Manager | City: Example City
Email: example@example.com

## Summary

Research **customer needs** & write proposals; preserve <tags>, 12.5%, and café.

- Read source documents.
  Continue the same item without changing facts.
- Check repeated text.
- Check repeated text.

## Work Experience

**Example Organization | Account Specialist | 2021.01 - Present**

Drafted documents for internal review.

## A Custom Section

1. Confirm the source.
2. Keep punctuation!
"""


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source = self.directory / "source.md"
        self.output = self.directory / "resume.pdf"
        self.qa = self.output.with_suffix(".layout.json")

    def tearDown(self):
        self.temp.cleanup()

    def run_render(self, source=MINIMAL, extra=(), output=None):
        self.source.write_text(source, encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = renderer.main(["--markdown", str(self.source), "--output", str(output or self.output),
                                    "--font", str(TEST_FONT), *extra])
        return result, stdout.getvalue(), stderr.getvalue()

    def read_text(self):
        return "".join(page.extract_text() for page in PdfReader(self.output).pages)

    def test_missing_fields_are_not_invented(self):
        result, _, error = self.run_render()
        self.assertEqual(result, 0, error)
        text = self.read_text()
        self.assertEqual(renderer.canonical_text(text), "SampleCandidateSummarySuppliedtextonly.")
        self.assertNotIn("Education", text)
        self.assertNotIn("Email", text)
        qa = json.loads(self.qa.read_text())
        self.assertEqual(qa["program_checks"]["page_count"], 1)
        self.assertGreaterEqual(qa["program_checks"]["body_font_size_pt"], 10)
        self.assertIsNone(qa["portrait"])
        self.assertEqual(qa["visual_review"]["status"], "pending")

    def test_special_characters_lists_unknown_section_and_duplicates_survive(self):
        result, _, error = self.run_render(RICH)
        self.assertEqual(result, 0, error)
        extracted = self.read_text()
        renderer.verify_text(renderer.parse_markdown(RICH), extracted)
        self.assertEqual(extracted.count("Check repeated text."), 2)
        self.assertIn("A Custom Section", extracted)
        self.assertIn("<tags>", extracted)
        self.assertIn("café", extracted)
        self.assertIn("12.5%", extracted)
        self.assertIn("2.", extracted)

    def test_source_and_photo_bytes_are_unchanged(self):
        photo = self.directory / "portrait.png"
        Image.new("RGB", (200, 300), "#8aa0b4").save(photo)
        before = hashlib.sha256(photo.read_bytes()).hexdigest()
        result, _, error = self.run_render(RICH, ("--style", "classic", "--photo", str(photo)))
        self.assertEqual(result, 0, error)
        self.assertEqual(self.source.read_text(), RICH)
        self.assertEqual(before, hashlib.sha256(photo.read_bytes()).hexdigest())
        self.assertIsNotNone(json.loads(self.qa.read_text())["portrait"])

    def test_classic_without_photo_contains_no_placeholder(self):
        result, _, error = self.run_render(MINIMAL, ("--style", "classic"))
        self.assertEqual(result, 0, error)
        renderer.verify_text(renderer.parse_markdown(MINIMAL), self.read_text())

    def test_plain_photo_request_fails_explicitly(self):
        photo = self.directory / "portrait.png"
        Image.new("RGB", (20, 20), "gray").save(photo)
        result, _, error = self.run_render(extra=("--photo", str(photo)))
        self.assertEqual(result, 2)
        self.assertIn("plain has no portrait", error)
        self.assertFalse(self.output.exists())

    def test_overflow_never_replaces_existing_output(self):
        self.output.write_bytes(b"previous approved output")
        self.qa.write_text('{"previous": true}')
        long_source = "# Sample Candidate\n\n## Summary\n\n" + "\n\n".join(["A long supplied paragraph with several words." * 5] * 100)
        result, _, error = self.run_render(long_source)
        self.assertEqual(result, 2)
        self.assertIn("10 pt minimum", error)
        self.assertEqual(self.output.read_bytes(), b"previous approved output")
        self.assertEqual(self.qa.read_text(), '{"previous": true}')
        self.assertFalse(list(self.directory.glob(".resume-*")))

    def test_missing_glyph_fails_before_replacement(self):
        self.output.write_bytes(b"previous output")
        result, _, error = self.run_render("# Sample Candidate\n\n## Summary\n\n中文内容\n")
        self.assertEqual(result, 2)
        self.assertIn("missing glyphs", error)
        self.assertEqual(self.output.read_bytes(), b"previous output")

    def test_rejected_text_checks_do_not_replace_existing_pdf(self):
        self.output.write_bytes(b"previous output")
        with patch.object(renderer, "verify_text", side_effect=renderer.ResumeError("Rejected PDF text")):
            result, _, error = self.run_render()
        self.assertEqual(result, 2)
        self.assertIn("Rejected PDF text", error)
        self.assertEqual(self.output.read_bytes(), b"previous output")
        self.assertFalse(list(self.directory.glob(".resume-*")))

    def test_full_text_validation_rejects_missing_duplicate_and_added_claim(self):
        resume = renderer.parse_markdown(RICH)
        expected = renderer.expected_text(resume)
        renderer.verify_text(resume, expected.replace(" ", "\n"))
        for invalid in (expected.replace("Check repeated text.", "", 1), expected + " Extra claim.",
                        expected.replace("12.5%", "15.2%")):
            with self.assertRaises(renderer.ResumeError):
                renderer.verify_text(resume, invalid)

    def test_invalid_input_does_not_silently_discard_text(self):
        bad_sources = ("## No Name\ntext", "# Sample Candidate\nUnknown: value\n## Summary\ntext",
                       "# Sample Candidate\n## Summary\n> hidden claim",
                       "# Sample Candidate\n## Summary\n**unfinished",
                       "# Sample Candidate\n## Work Experience\nA paragraph without company",
                       "# Sample Candidate\n## Summary\n<!-- unfinished")
        for source in bad_sources:
            with self.subTest(source=source):
                result, _, _ = self.run_render(source)
                self.assertEqual(result, 2)
                self.assertFalse(self.output.exists())

    def test_source_cannot_be_overwritten_via_qa_or_output(self):
        result, _, error = self.run_render(extra=("--qa", str(self.source)))
        self.assertEqual(result, 2)
        self.assertIn("cannot overwrite", error)
        result, _, error = self.run_render(output=self.source)
        self.assertEqual(result, 2)
        self.assertEqual(self.source.read_text(), MINIMAL)

    def test_no_qa_and_unicode_output_path(self):
        output = self.directory / "结果.pdf"
        result, _, error = self.run_render(extra=("--no-qa",), output=output)
        self.assertEqual(result, 0, error)
        self.assertTrue(output.is_file())
        self.assertFalse(output.with_suffix(".layout.json").exists())

    def test_help_does_not_create_files_or_load_dependencies(self):
        result = subprocess.run([sys.executable, "-S", str(SCRIPT), "--help"], cwd=self.directory,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--style", result.stdout)
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
