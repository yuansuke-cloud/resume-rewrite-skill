#!/usr/bin/env python3
"""Render supplied Markdown as one A4 page without inventing resume content.

No files or fonts are loaded on import. Dependencies: reportlab, Pillow, pypdf.
Use --help for options; see references/renderer-contract.md for the input grammar.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
from itertools import groupby
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
DATE_PATTERN = re.compile(
    r"^\d{4}(?:[./-]\d{1,2}|年\d{1,2}月?)?\s*(?:—|–|－|-|至|到)\s*"
    r"(?:\d{4}(?:[./-]\d{1,2}|年\d{1,2}月?)?|至今|现在|Present|Current)$",
    re.IGNORECASE,
)
WORK_TITLES = {"工作经历", "实习经历", "work experience", "experience", "employment"}
HEADER_KEYS = {
    "求职意向", "目标岗位", "电话", "手机", "联系方式", "微信", "邮箱", "电子邮箱",
    "毕业院校", "学校", "院校", "城市", "所在地", "求职城市", "网站", "作品集", "领英",
    "target", "role", "phone", "contact", "email", "city", "location", "school",
    "website", "portfolio", "linkedin",
}
LIST_PATTERN = re.compile(r"^([-*+]|\d+[.)])\s+(.+)$")
CLOSING = set("，。、；：？！）》】％%,.;:!?)]}")
OPENING = set("（《【([{")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[./@_+\-][A-Za-z0-9]+)*|.", re.DOTALL)


class ResumeError(ValueError):
    """Invalid input or unsafe output; existing output must not be replaced."""


@dataclass
class Paragraph:
    text: str
    marker: str = ""


@dataclass
class Entry:
    company: str
    role: str = ""
    dates: str = ""
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class Section:
    title: str
    is_work: bool = False
    paragraphs: list[Paragraph] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)


@dataclass
class Resume:
    name: str
    metadata: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)


def text_cells(value: str) -> list[tuple[str, bool]]:
    """Only paired **bold** is formatting; other characters remain literal."""
    if value.count("**") % 2:
        raise ResumeError("Unpaired ** emphasis; close the marker or remove it.")
    result = []
    for index, part in enumerate(value.split("**")):
        result.extend((character, bool(index % 2)) for character in part)
    return result


def plain_text(value: str) -> str:
    return "".join(character for character, _ in text_cells(value))


def split_fields(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[｜|]", value)]


def parse_markdown(source: str) -> Resume:
    """Parse the documented subset, rejecting unsupported markup rather than losing it."""
    source = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
    if "<!--" in source or "-->" in source:
        raise ResumeError("Unclosed HTML comment.")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None or not re.match(r"^#\s+\S", lines[first].strip()):
        raise ResumeError("First non-empty line must be '# Name'; no name will be invented.")
    resume = Resume(name=plain_text(lines[first].strip()[2:].strip()))
    if not resume.name:
        raise ResumeError("Name cannot be empty.")
    current = None
    entry = None
    pending = None
    for number, raw in enumerate(lines[first + 1:], first + 2):
        line = raw.strip()
        if not line:
            pending = None
            continue
        if line.startswith("## "):
            title = plain_text(line[3:].strip())
            if not title:
                raise ResumeError(f"Line {number}: empty section title.")
            current = Section(title, title.lower() in WORK_TITLES)
            resume.sections.append(current)
            entry, pending = None, None
            continue
        if line.startswith(("#", ">", "```", "~~~")):
            raise ResumeError(f"Line {number}: use ## sections and paragraphs; nested headings, quotes and code blocks are unsupported.")
        if current is None:
            for part in split_fields(line):
                pair = re.split(r"[：:]", part, maxsplit=1)
                if len(pair) != 2 or pair[0].strip().lower() not in HEADER_KEYS:
                    raise ResumeError(f"Line {number}: unknown header field; use an explicit supported label or move this text to a section.")
                if not pair[1].strip():
                    raise ResumeError(f"Line {number}: empty header field; omit it instead of adding a placeholder.")
                resume.metadata.append(plain_text(part))
            continue
        listed = LIST_PATTERN.fullmatch(line)
        if current.is_work and not listed and not raw.startswith(("  ", "\t")):
            parts = split_fields(plain_text(line))
            if len(parts) >= 2:
                if len(parts) > 3 or not parts[0]:
                    raise ResumeError(f"Line {number}: expected Company | Role | optional dates.")
                if len(parts) == 3 and not DATE_PATTERN.fullmatch(parts[2]):
                    raise ResumeError(f"Line {number}: dates must be a year/month range or end in Present/至今.")
                entry = Entry(parts[0], parts[1], parts[2] if len(parts) == 3 else "")
                current.entries.append(entry)
                pending = None
                continue
            if DATE_PATTERN.fullmatch(plain_text(line)):
                if entry is None or entry.dates:
                    raise ResumeError(f"Line {number}: date has no entry or duplicates an existing date.")
                entry.dates = plain_text(line)
                pending = None
                continue
        if current.is_work:
            if entry is None:
                raise ResumeError(f"Line {number}: work paragraphs need a preceding Company | Role entry.")
            target = entry.paragraphs
        else:
            target = current.paragraphs
        marker, value = (listed[1], listed[2]) if listed else ("", line)
        plain_text(value)  # Validate the formatting before any output is created.
        if raw.startswith(("  ", "\t")) and pending is not None and not marker:
            pending.text += " " + value
        else:
            pending = Paragraph(value, marker)
            target.append(pending)
    if not resume.sections:
        raise ResumeError("At least one ## section is required; missing education or experience will not be added.")
    return resume


def supplied_text(resume: Resume) -> str:
    parts = [resume.name, *resume.metadata]
    for section in resume.sections:
        parts.append(section.title)
        for paragraph in section.paragraphs:
            parts.extend([paragraph.marker if paragraph.marker[:1].isdigit() else "", plain_text(paragraph.text)])
        for entry in section.entries:
            parts.extend([entry.company, entry.role, entry.dates])
            for paragraph in entry.paragraphs:
                parts.extend([paragraph.marker if paragraph.marker[:1].isdigit() else "", plain_text(paragraph.text)])
    return "\n".join(parts)


def font_candidates(explicit: Path | None, index: int | None):
    """Deterministic, bounded discovery; never scan arbitrary personal directories."""
    if explicit:
        yield explicit, index or 0
        return
    if os.environ.get("RESUME_FONT"):
        yield Path(os.environ["RESUME_FONT"]).expanduser(), 0
        return
    roots = [SKILL_ROOT / "assets" / "fonts"]
    if sys.platform == "darwin":
        roots += [Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
    elif os.name == "nt":
        roots += [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    else:
        roots += [Path("/usr/share/fonts/truetype/noto"), Path("/usr/share/fonts/truetype/dejavu"),
                  Path("/usr/local/share/fonts"), Path.home() / ".local" / "share" / "fonts"]
    names = ("NotoSansSC-Regular.ttf", "NotoSansCJKsc-Regular.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf")
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                yield candidate, 0


def register_font(resume: Resume, explicit: Path | None, index: int | None,
                  metrics: Any, ttfont: Any) -> dict:
    required = {ord(ch) for ch in supplied_text(resume) + " | " if not ch.isspace()}
    attempts = []
    for path, face_index in font_candidates(explicit, index):
        try:
            font = ttfont("ResumeBody", str(path), subfontIndex=face_index)
            missing = sorted(code for code in required if not font.face.charToGlyph.get(code, 0))
            if missing:
                sample = " ".join(f"{chr(code)} (U+{code:04X})" for code in missing[:12])
                attempts.append(f"{path.name}[{face_index}]: missing glyphs {sample}")
                continue
            metrics.registerFont(font)
            face_name = font.face.name
            return {"file": path.name, "index": face_index,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "face_name": face_name.decode("utf-8", errors="replace") if isinstance(face_name, bytes) else str(face_name),
                    "validated_character_count": len(required), "missing_glyphs": []}
        except Exception as exc:
            attempts.append(f"{path.name}[{face_index}]: {exc}")
    detail = "; ".join(attempts) or "No compatible font found in the documented search locations."
    raise ResumeError("No font covers every required character. Use --font PATH to a licensed static TrueType TTF/TTC (and --font-index for TTC). " + detail)


@dataclass(frozen=True)
class Profile:
    size: float
    leading_ratio: float
    paragraph_gap: float
    section_gap: float
    section_after: float
    entry_gap: float


# Space is reduced before size; body and dates never fall below 10 pt.
PROFILES = (Profile(11.2, 1.43, 5, 8, 23, 8), Profile(11.2, 1.43, 3, 5, 20, 5),
            Profile(11.2, 1.32, 3, 4, 19, 4), Profile(10.7, 1.32, 3, 4, 19, 4),
            Profile(10.3, 1.32, 3, 4, 19, 4), Profile(10.0, 1.30, 2.5, 4, 18, 4))


class Renderer:
    def __init__(self, resume, metrics, page_size, colors, image_reader, style="plain", photo=False):
        self.resume, self.metrics = resume, metrics
        self.width, self.height = page_size
        self.left = self.right = 38
        self.body_width = self.width - self.left - self.right
        self.ink = colors.HexColor("#171717")
        self.gray = colors.HexColor("#404040")
        self.rule = colors.HexColor("#CDCDCD")
        self.image_reader, self.style, self.has_photo = image_reader, style, photo
        self.drawn_text: list[str] = []

    def measure(self, text, size):
        return self.metrics.stringWidth(text, "ResumeBody", size)

    def wrap(self, value, size, available):
        if available <= size:
            raise ResumeError("Not enough width for this text field.")
        cells = text_cells(value)
        text = "".join(ch for ch, _ in cells)
        tokens = [cells[m.start():m.end()] for m in TOKEN_PATTERN.finditer(text)]
        tokens = [piece for token in tokens for piece in
                  ([token] if self.measure("".join(ch for ch, _ in token), size) <= available else [[cell] for cell in token])]
        result, current = [], []

        def flatten(items):
            return [cell for item in items for cell in item]

        def used(items):
            return self.measure("".join(ch for ch, _ in flatten(items)), size)

        for token in tokens:
            if current and used(current + [token]) > available:
                carry = []
                if token[0][0] in CLOSING:
                    carry.insert(0, current.pop())
                while current and current[-1][-1][0] in OPENING:
                    carry.insert(0, current.pop())
                if current:
                    result.append(flatten(current))
                current = carry
            current.append(token)
            if used(current) > available + 0.1:
                raise ResumeError("Text or punctuation cannot wrap safely; shorten the relevant field.")
        if current:
            result.append(flatten(current))
        return result

    def draw_line(self, c, cells, x, top, size):
        self.drawn_text.append("".join(ch for ch, _ in cells))
        baseline = self.height - top - size * 0.88
        c.setFillColor(self.ink)
        c.setStrokeColor(self.ink)
        c.setLineWidth(0.17)
        for bold, group in groupby(cells, key=lambda item: item[1]):
            text = "".join(ch for ch, _ in group)
            c.saveState()
            obj = c.beginText(x, baseline)
            obj.setFont("ResumeBody", size)
            obj.setTextRenderMode(2 if bold else 0)
            obj.textOut(text)
            c.drawText(obj)
            c.restoreState()
            x += self.measure(text, size)

    def draw_plain(self, c, text, x, top, size, bold=False):
        self.draw_line(c, [(ch, bold) for ch in text], x, top, size)

    def header_plan(self):
        name_top = (122 if self.has_photo else 71) if self.style == "classic" else 37
        if self.measure(self.resume.name, 19) > self.body_width:
            raise ResumeError("Name is too long for the header.")
        y = name_top + 28
        rows = []
        for value in self.resume.metadata:
            lines = self.wrap(value, 10, self.body_width)
            rows.append((y, lines))
            y += len(lines) * 13.5 + 1.5
        return {"name_top": name_top, "rows": rows, "body_top": y + 15}

    def draw_header(self, c, plan, photo, photo_shift_up, image_module):
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        if self.style == "classic":
            # Original vector geometry; no reference artwork or icon font.
            depth = 74 if photo else 42
            path = c.beginPath()
            path.moveTo(0, self.height)
            path.lineTo(self.width, self.height)
            path.lineTo(self.width, self.height - depth + 18)
            path.curveTo(self.width * .72, self.height - depth - 12,
                         self.width * .28, self.height - depth - 12, 0, self.height - depth + 18)
            path.close()
            c.setFillColor(self.gray)
            c.drawPath(path, stroke=0, fill=1)
        portrait = None
        if photo:
            from PIL import ImageOps
            with image_module.open(photo) as original:
                im = ImageOps.exif_transpose(original).convert("RGB")
                pw, ph = im.size
                diameter, top, cx = 74, 32, self.width / 2
                scale = max(diameter / pw, diameter / ph)
                scaled_w, scaled_h = pw * scale, ph * scale
                limit = max(0.0, scaled_h - diameter)
                if photo_shift_up > limit + .01:
                    raise ResumeError(f"--photo-shift-up-pt must be between 0 and {limit:.2f} for this image.")
                cy = self.height - top - diameter / 2
                c.saveState()
                clip = c.beginPath()
                clip.circle(cx, cy, diameter / 2)
                c.clipPath(clip, stroke=0, fill=0)
                c.drawImage(self.image_reader(im), cx - scaled_w / 2,
                            self.height - top - scaled_h + photo_shift_up,
                            width=scaled_w, height=scaled_h)
                c.restoreState()
                portrait = {"diameter_pt": diameter, "frame_top_pt": top,
                            "image_shift_up_inside_frame_pt": photo_shift_up,
                            "sha256": hashlib.sha256(photo.read_bytes()).hexdigest()}
        x = (self.width - self.measure(self.resume.name, 19)) / 2 if self.style == "classic" else self.left
        self.draw_plain(c, self.resume.name, x, plan["name_top"], 19, True)
        for top, rows in plan["rows"]:
            for index, row in enumerate(rows):
                value = "".join(ch for ch, _ in row)
                x = (self.width - self.measure(value, 10)) / 2 if self.style == "classic" else self.left
                self.draw_line(c, row, x, top + index * 13.5, 10)
        return portrait

    def body(self, c, profile, body_top):
        size, leading = profile.size, profile.size * profile.leading_ratio
        y, positions = body_top, []

        def paragraph(value, kind, marker=""):
            nonlocal y
            ordered = marker[:1].isdigit()
            inset = max(14, self.measure(marker, size) + 7) if marker else 0
            rows = self.wrap(value, size, self.body_width - inset)
            before = y
            if c:
                if ordered:
                    self.draw_plain(c, marker, self.left, y, size)
                elif marker:
                    c.setFillColor(self.ink)
                    c.circle(self.left + 4, self.height - y - size * .46, 1.3, stroke=0, fill=1)
                for i, row in enumerate(rows):
                    self.draw_line(c, row, self.left + inset, y + i * leading, size)
            y += len(rows) * leading + profile.paragraph_gap
            positions.append({"kind": kind, "top_pt": before, "bottom_pt": y, "line_count": len(rows)})

        for section_index, section in enumerate(self.resume.sections):
            if section_index:
                y += profile.section_gap
            title_size, inset = 12.7, (13 if self.style == "classic" else 0)
            title_x = self.left + inset
            title_width = self.measure(section.title, title_size)
            if title_width > self.body_width - inset:
                raise ResumeError("Section title is too long.")
            if c:
                if self.style == "classic":
                    c.setFillColor(self.gray)
                    c.rect(self.left + 1, self.height - y - 10, 5, 7, stroke=0, fill=1)
                self.draw_plain(c, section.title, title_x, y, title_size, True)
                start = title_x + title_width + 9
                if start < self.width - self.right:
                    c.setStrokeColor(self.rule)
                    c.setLineWidth(.5)
                    c.line(start, self.height - y - 7.2, self.width - self.right, self.height - y - 7.2)
            positions.append({"kind": "section", "top_pt": y, "bottom_pt": y + title_size, "line_count": 1})
            y += profile.section_after
            for item in section.paragraphs:
                paragraph(item.text, "paragraph", item.marker)
            for index, entry in enumerate(section.entries):
                if index:
                    y += profile.entry_gap
                date_size = max(10, size - .5)
                date_width = self.measure(entry.dates, date_size)
                available = self.body_width - (date_width + 18 if entry.dates else 0)
                if available < size * 6:
                    raise ResumeError("Date field leaves too little room for the company and role.")
                title = "**" + entry.company + "**" + (" | " + entry.role if entry.role else "")
                rows = self.wrap(title, size, available)
                before = y
                if c:
                    for i, row in enumerate(rows):
                        self.draw_line(c, row, self.left, y + i * leading, size)
                    if entry.dates:
                        self.draw_plain(c, entry.dates, self.width - self.right - date_width, y, date_size)
                y += len(rows) * leading + profile.paragraph_gap
                positions.append({"kind": "entry", "top_pt": before, "bottom_pt": y, "line_count": len(rows)})
                for item in entry.paragraphs:
                    paragraph(item.text, "work", item.marker)
        return y, positions


def expected_text(resume: Resume) -> str:
    """Expected reading order, independent of the drawing functions."""
    parts = [resume.name, *resume.metadata]
    for section in resume.sections:
        parts.append(section.title)
        for paragraph in section.paragraphs:
            if paragraph.marker[:1].isdigit():
                parts.append(paragraph.marker)
            parts.append(plain_text(paragraph.text))
        for entry in section.entries:
            parts.append(entry.company + (" | " + entry.role if entry.role else ""))
            parts.append(entry.dates)
            for paragraph in entry.paragraphs:
                if paragraph.marker[:1].isdigit():
                    parts.append(paragraph.marker)
                parts.append(plain_text(paragraph.text))
    return "\n".join(parts)


def canonical_text(value: str) -> str:
    # Wrapping changes whitespace only. Punctuation, case, digits, and duplicates matter.
    return re.sub(r"\s+", "", value)


def verify_text(resume: Resume, extracted: str):
    if canonical_text(expected_text(resume)) != canonical_text(extracted):
        raise ResumeError("PDF text differs from the complete input text (ignoring layout whitespace); output was not replaced.")


def stage_json(path: Path, data: dict) -> Path:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".resume-qa-", suffix=".json", delete=False) as handle:
        target = Path(handle.name)
        try:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render supplied Markdown as one A4 page; never invent missing resume facts.")
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--style", choices=("plain", "classic"), default="plain")
    parser.add_argument("--font", type=Path, help="Licensed static TrueType TTF/TTC covering every input character")
    parser.add_argument("--font-index", type=int, help="TTC face index; requires --font, default 0")
    parser.add_argument("--photo", type=Path, help="Original candidate photo; classic style only")
    parser.add_argument("--photo-shift-up-pt", type=float, default=0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--qa", type=Path, help="Checks JSON; default: output basename.layout.json")
    group.add_argument("--no-qa", action="store_true")
    args = parser.parse_args(argv)
    temporary_pdf = temporary_qa = None
    try:
        if not math.isfinite(args.photo_shift_up_pt) or args.photo_shift_up_pt < 0:
            raise ResumeError("--photo-shift-up-pt must be finite and non-negative.")
        if args.font_index is not None and (not args.font or args.font_index < 0):
            raise ResumeError("A non-negative --font-index requires --font.")
        if args.style == "plain" and args.photo:
            raise ResumeError("plain has no portrait. Use --style classic with --photo.")
        if args.photo_shift_up_pt and not args.photo:
            raise ResumeError("--photo-shift-up-pt requires --photo.")
        source, output = args.markdown.expanduser().resolve(), args.output.expanduser().resolve()
        photo = args.photo.expanduser().resolve() if args.photo else None
        explicit_font = args.font.expanduser().resolve() if args.font else None
        protected = {source, photo, explicit_font} - {None}
        if not source.is_file():
            raise ResumeError("Markdown file does not exist.")
        if output.suffix.lower() != ".pdf" or output in protected:
            raise ResumeError("Output must be a separate .pdf and cannot overwrite an input.")
        if output.exists() and not output.is_file():
            raise ResumeError("PDF output path is not a regular file.")
        if photo and not photo.is_file():
            raise ResumeError("Photo does not exist.")
        if explicit_font and not explicit_font.is_file():
            raise ResumeError("Font does not exist.")
        qa = None if args.no_qa else (args.qa.expanduser().resolve() if args.qa else output.with_suffix(".layout.json"))
        if qa and (qa in protected or qa == output or qa.suffix.lower() != ".json"):
            raise ResumeError("QA must be a separate .json and cannot overwrite an input or the PDF.")
        if qa and qa.exists() and not qa.is_file():
            raise ResumeError("QA output path is not a regular file.")
        source_bytes = source.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        photo_hash = hashlib.sha256(photo.read_bytes()).hexdigest() if photo else None
        resume = parse_markdown(source_bytes.decode("utf-8-sig"))
        try:
            from PIL import Image
            from pypdf import PdfReader
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
        except ImportError as exc:
            raise ResumeError("Install dependencies: python -m pip install reportlab Pillow pypdf") from exc
        font_info = register_font(resume, explicit_font, args.font_index, pdfmetrics, TTFont)
        renderer = Renderer(resume, pdfmetrics, A4, colors, ImageReader, args.style, bool(photo))
        header = renderer.header_plan()
        profile = None
        for candidate in PROFILES:
            bottom, positions = renderer.body(None, candidate, header["body_top"])
            if bottom <= renderer.height - 38:
                profile = candidate
                break
        if profile is None:
            raise ResumeError("Content exceeds one A4 page at the 10 pt minimum. Shorten the source; existing output was not replaced.")
        output.parent.mkdir(parents=True, exist_ok=True)
        if qa:
            qa.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".resume-", suffix=".pdf", delete=False) as handle:
            temporary_pdf = Path(handle.name)
        c = canvas.Canvas(str(temporary_pdf), pagesize=A4)
        c.setTitle(resume.name)
        c.setAuthor("")
        portrait = renderer.draw_header(c, header, photo, args.photo_shift_up_pt, Image)
        renderer.body(c, profile, header["body_top"])
        c.showPage()
        c.save()
        reader = PdfReader(str(temporary_pdf))
        if len(reader.pages) != 1:
            raise ResumeError("PDF failed the one-page check.")
        page = reader.pages[0]
        if abs(float(page.mediabox.width) - A4[0]) > .1 or abs(float(page.mediabox.height) - A4[1]) > .1:
            raise ResumeError("PDF failed the A4 page-size check.")
        verify_text(resume, page.extract_text() or "")
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
            raise ResumeError("Source changed during rendering; retry with the current source.")
        if photo and hashlib.sha256(photo.read_bytes()).hexdigest() != photo_hash:
            raise ResumeError("Photo changed during rendering; retry with the current photo.")
        pdf_hash = hashlib.sha256(temporary_pdf.read_bytes()).hexdigest()
        checks = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "source_file": source.name, "source_sha256": source_hash, "source_unchanged": True,
                  "pdf_file": output.name, "pdf_sha256": pdf_hash, "style": args.style,
                  "program_checks": {"page_count": 1, "page_size": "A4", "text_matches_input": True,
                      "text_comparison": "complete reading-order sequence, excluding layout whitespace and Markdown markers",
                      "all_body_glyphs_available": True, "body_font_size_pt": profile.size,
                      "minimum_body_font_size_pt": 10, "body_bottom_top_coordinate_pt": bottom,
                      "source_punctuation_preserved": True},
                  "font": font_info, "layout_profile": asdict(profile), "portrait": portrait, "layout": positions,
                  "visual_review": {"status": "pending", "instructions": "Render and inspect the entire final page, including glyphs, wrapping, margins and any portrait."},
                  "content_verification": {"status": "not_performed", "instructions": "The renderer does not verify claims, credentials or outcomes."}}
        # Stage both before replacement, so a JSON serialization/write error keeps the PDF.
        if qa:
            temporary_qa = stage_json(qa, checks)
        os.replace(temporary_pdf, output)
        temporary_pdf = None
        if qa:
            os.replace(temporary_qa, qa)
            temporary_qa = None
        print(json.dumps({"pdf": str(output), "qa": str(qa) if qa else None, "page_count": 1,
                          "body_font_size_pt": profile.size, "visual_review": "pending"}, ensure_ascii=False))
        return 0
    except (ResumeError, OSError, UnicodeError) as exc:
        print("Render failed: " + str(exc), file=sys.stderr)
        return 2
    finally:
        for temporary in (temporary_pdf, temporary_qa):
            if temporary and temporary.exists():
                temporary.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
