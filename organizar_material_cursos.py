#!/usr/bin/env python3
"""Create text-only, module-organized course compendiums from downloaded files.

Reads .srt, .txt, .pdf, .pptx, and .html files below descargas/ and writes
one text file per module plus one combined text file per course.

PDF extraction requires pypdf: python -m pip install pypdf
"""

from __future__ import annotations

import html
import re
import shutil
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "descargas"
OUTPUT_DIR = BASE_DIR / "resumenes_cursos_txt"
ORGANIZED_OUTPUT_DIR = BASE_DIR / "resumenes_cursos_por_curso"
SUPPORTED_EXTENSIONS = {".srt", ".txt", ".pdf", ".pptx", ".html", ".htm"}

COURSE_TITLES = {
    "claude-code": "Claude Code",
    "introduction-to-back-end-development": "Introduction to Back-End Development",
    "learning-how-to-learn": "Learning How to Learn",
}


class VisibleTextParser(HTMLParser):
    """Small standard-library HTML text extractor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        elif tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def srt_to_text(text: str) -> str:
    """Keep cue timestamps while removing SRT numbering and markup."""
    result: list[str] = []
    block: list[str] = []
    for line in text.replace("\r", "").split("\n") + [""]:
        if line.strip():
            block.append(line.strip())
            continue
        if block:
            timestamp = next((x for x in block if "-->" in x), None)
            words = [x for x in block if x != timestamp and not x.isdigit()]
            phrase = " ".join(words)
            phrase = re.sub(r"<[^>]*>", "", phrase)
            phrase = html.unescape(phrase)
            if phrase:
                result.append(f"[{timestamp}] {phrase}" if timestamp else phrase)
            block = []
    return clean_text("\n".join(result))


def pdf_to_text(path: Path) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Missing pypdf. Install it with: python -m pip install pypdf") from exc

    try:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            pages.append(f"[PDF page {page_number}]\n{text}" if text else f"[PDF page {page_number}] [No selectable text found]")
        extracted = "\n\n".join(pages).strip()
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            return extracted, "This PDF appears to be scanned or image-only; OCR is needed to read its pages."
        return extracted, None
    except Exception as exc:  # preserve the rest of the course if one source is damaged
        return "", f"Could not extract this PDF: {type(exc).__name__}: {exc}"


def pptx_to_text(path: Path) -> str:
    parts: list[tuple[int, str]] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        for name in sorted(slide_names, key=lambda n: int(re.search(r"slide(\d+)", n).group(1))):
            root = ElementTree.fromstring(archive.read(name))
            texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            slide_number = int(re.search(r"slide(\d+)", name).group(1))
            joined = clean_text(" ".join(texts))
            parts.append((slide_number, f"[Slide {slide_number}]\n{joined}" if joined else f"[Slide {slide_number}] [No text found]"))
    return "\n\n".join(value for _, value in parts)


def extract_source(path: Path) -> tuple[str, str | None]:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return srt_to_text(read_text(path)), None
    if suffix == ".txt":
        return clean_text(read_text(path)), None
    if suffix == ".pdf":
        return pdf_to_text(path)
    if suffix == ".pptx":
        try:
            return pptx_to_text(path), None
        except Exception as exc:
            return "", f"Could not extract this presentation: {type(exc).__name__}: {exc}"
    parser = VisibleTextParser()
    parser.feed(read_text(path))
    return clean_text("".join(parser.parts)), None


def pretty_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"\.en$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\d+[_ -]*", "", name)
    name = re.sub(r"[_-]+", " ", name)
    return name.strip().title() or path.name


def module_title(folder: Path) -> str:
    name = re.sub(r"^\d+[_ -]*", "", folder.name)
    return re.sub(r"[_-]+", " ", name).strip().title() or folder.name


def text_file_block(source: Path, module: Path) -> tuple[str, str | None]:
    relative = source.relative_to(module).as_posix()
    body, warning = extract_source(source)
    title = pretty_name(source)
    heading = f"SOURCE: {relative}\nTYPE: {source.suffix.upper().lstrip('.')}\nTITLE: {title}"
    if warning:
        body = (body + "\n\n" if body else "") + f"[NOTE: {warning}]"
    return f"{heading}\n\n{body or '[No text could be extracted from this file.]'}", warning


def main() -> int:
    if not SOURCE_DIR.exists():
        print(f"Source folder not found: {SOURCE_DIR}", file=sys.stderr)
        return 2
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove only previous .txt outputs from this dedicated output folder.
    # The downloaded source materials are never changed.
    for old_txt in OUTPUT_DIR.glob("*.txt"):
        old_txt.unlink()

    index: list[str] = ["COURSE MATERIALS — TEXT-ONLY COMPENDIUM", "=" * 44, ""]
    warnings: list[str] = []
    total_files = 0
    total_modules = 0

    for course_dir in sorted(p for p in SOURCE_DIR.iterdir() if p.is_dir()):
        course_name = COURSE_TITLES.get(course_dir.name, re.sub(r"[_-]+", " ", course_dir.name).title())
        module_dirs = sorted(p for p in course_dir.iterdir() if p.is_dir())
        course_blocks: list[str] = []
        module_files: list[tuple[str, str]] = []

        for module_number, module_dir in enumerate(module_dirs, start=1):
            sources = sorted(
                (p for p in module_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
                key=lambda p: str(p).casefold(),
            )
            # Prefer timestamped SRT captions over their duplicate plain .txt transcript.
            srt_stems = {p.with_suffix("").as_posix().casefold() for p in sources if p.suffix.lower() == ".srt"}
            sources = [p for p in sources if not (p.suffix.lower() == ".txt" and p.with_suffix("").as_posix().casefold() in srt_stems)]

            module_name = module_title(module_dir)
            module_heading = f"{course_name}\nMODULE {module_number:02d}: {module_name}\n" + "=" * (len(course_name) + len(module_name) + 15)
            blocks = [module_heading, "\nThis file collects the readable text from this module's subtitles and learning materials. Source paths are kept below each section.\n"]
            for source in sources:
                block, warning = text_file_block(source, module_dir)
                blocks.append("\n\n" + "-" * 78 + "\n\n" + block)
                total_files += 1
                if warning:
                    warnings.append(f"{course_name} / Module {module_number:02d} / {source.relative_to(course_dir)}: {warning}")
            content = "\n".join(blocks).strip() + "\n"
            filename = f"{course_dir.name}_Modulo_{module_number:02d}.txt"
            (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")
            module_files.append((filename, module_name))
            course_blocks.append(content)
            total_modules += 1

        combined_name = f"{course_dir.name}_Curso_Completo.txt"
        combined_heading = f"{course_name} — COMPLETE COURSE COMPENDIUM\n" + "=" * (len(course_name) + 32)
        combined = combined_heading + "\n\nThis is the full text compilation organized by module. It preserves source details; it is not an AI-written paraphrase.\n\n" + "\n\n".join(course_blocks)
        (OUTPUT_DIR / combined_name).write_text(combined, encoding="utf-8")

        index.append(f"COURSE: {course_name}")
        for filename, name in module_files:
            index.append(f"  {filename} — Module: {name}")
        index.append(f"  {combined_name} — all modules in one file")
        index.append("")

    index.extend([
        "HOW TO READ THESE FILES",
        "- Each module file brings together subtitles and readable text from PDFs, presentations, and HTML resources found in that module.",
        "- SRT captions keep their timestamps. PDF text keeps page numbers. Presentation text keeps slide numbers.",
        "- Duplicate plain-text transcripts are skipped when the same lesson has an SRT, to avoid repeating the same lecture twice.",
        "- This script extracts and organizes source content. It does not generate a human-like explanation or an AI summary.",
        "- For a detailed explained summary, open a course's Curso_Completo.txt in Claude Code and ask it to create a source-grounded study guide, preserving definitions, examples, steps, and references.",
        "",
        f"Modules created: {total_modules}",
        f"Source files included: {total_files}",
        f"Output folder: {OUTPUT_DIR}",
    ])
    if warnings:
        index.extend(["", "EXTRACTION WARNINGS"])
        index.extend(f"- {item}" for item in warnings)
    (OUTPUT_DIR / "00_INDICE.txt").write_text("\n".join(index) + "\n", encoding="utf-8")

    # Create a second view with one folder per course for easier browsing.
    ORGANIZED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    organized_index = ["COURSE MATERIALS — ORGANIZED BY COURSE", "=" * 42, ""]
    for course_dir in sorted(p for p in SOURCE_DIR.iterdir() if p.is_dir()):
        course_name = COURSE_TITLES.get(course_dir.name, re.sub(r"[_-]+", " ", course_dir.name).title())
        course_output = ORGANIZED_OUTPUT_DIR / re.sub(r"[^A-Za-z0-9_-]+", "_", course_name).strip("_")
        course_output.mkdir(parents=True, exist_ok=True)
        # Refresh only generated text files in this course's output directory.
        for old_txt in course_output.glob("*.txt"):
            old_txt.unlink()
        copied = sorted(OUTPUT_DIR.glob(f"{course_dir.name}_*.txt"))
        for source_txt in copied:
            if source_txt.name == "00_INDICE.txt":
                continue
            if "_Modulo_" in source_txt.name:
                new_name = source_txt.name.split("_Modulo_", 1)[1]
                new_name = f"Modulo_{new_name}"
            else:
                new_name = "Curso_Completo.txt"
            shutil.copyfile(source_txt, course_output / new_name)
        organized_index.append(f"{course_name}/")
        organized_index.extend(f"  {p.name}" for p in sorted(course_output.glob("*.txt")))
        organized_index.append("")
    (ORGANIZED_OUTPUT_DIR / "00_INDICE.txt").write_text("\n".join(organized_index) + "\n", encoding="utf-8")

    output_non_txt = [p.name for p in OUTPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() != ".txt"]
    print(f"Output folder: {OUTPUT_DIR}")
    print(f"Organized output folder: {ORGANIZED_OUTPUT_DIR}")
    print(f"Courses: {len([p for p in SOURCE_DIR.iterdir() if p.is_dir()])}")
    print(f"Modules: {total_modules}")
    print(f"Source files included: {total_files}")
    print(f"TXT files created: {len(list(OUTPUT_DIR.glob('*.txt')))}")
    print(f"Extraction warnings: {len(warnings)}")
    if output_non_txt:
        print("Unexpected non-TXT files found: " + ", ".join(output_non_txt))
        return 1
    if warnings:
        print("See 00_INDICE.txt for extraction warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
