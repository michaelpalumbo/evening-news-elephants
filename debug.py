"""
Diagnostic: shows the exact raw bytes print_docx_loop.py's
print_docx() function would send to the printer for a given .docx
file, WITHOUT sending them -- so we can inspect them directly instead
of guessing.

Usage:
    python debug_docx_bytes.py <path_to_docx>
"""

import json
import sys
import textwrap
from pathlib import Path

from docx import Document

SETTINGS_FILE = Path("settings.json")
PHYSICAL_PAGE_WIDTH_INCHES = 8.5

CHARACTER_REPLACEMENTS = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...",
}


def load_settings() -> dict:
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_for_printer(text: str) -> str:
    for smart_char, plain_char in CHARACTER_REPLACEMENTS.items():
        text = text.replace(smart_char, plain_char)
    return text


def extract_docx_text(docx_path: Path) -> str:
    document = Document(docx_path)
    paragraphs = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            paragraphs.append(text)
    return normalize_for_printer("\n\n".join(paragraphs))


def get_printable_chars_per_line(settings: dict) -> int:
    printable_width_inches = (
        PHYSICAL_PAGE_WIDTH_INCHES
        - settings["left_margin_inches"]
        - settings["right_margin_inches"]
    )
    chars_per_line = int(printable_width_inches * settings["characters_per_inch"])
    if settings.get("font_width", 1) == 2:
        chars_per_line = chars_per_line // 2
    return max(1, chars_per_line)


def wrap_text(text: str, chars_per_line: int) -> str:
    paragraphs = text.split("\n\n")
    wrapped_paragraphs = []
    for paragraph in paragraphs:
        wrapped_lines = textwrap.wrap(
            paragraph, width=chars_per_line,
            break_long_words=False, break_on_hyphens=False,
        )
        wrapped_paragraphs.append("\r\n".join(wrapped_lines))
    return "\r\n\r\n".join(wrapped_paragraphs)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python debug_docx_bytes.py <path_to_docx>")
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    settings = load_settings()

    cpi = settings["characters_per_inch"]
    left_margin_chars = round(settings["left_margin_inches"] * cpi)
    right_margin_position_inches = PHYSICAL_PAGE_WIDTH_INCHES - settings["right_margin_inches"]
    right_margin_chars = round(right_margin_position_inches * cpi)
    font_height = settings.get("font_height", 1)
    font_width = settings.get("font_width", 1)
    line_units = round(30 * settings["line_spacing"])
    line_height_inches = line_units / 180
    top_margin_blank_lines = round(settings["top_margin_inches"] / line_height_inches)

    print("=== settings.json values in use ===")
    print(f"left_margin_inches: {settings['left_margin_inches']} -> left_margin_chars: {left_margin_chars}")
    print(f"right_margin_inches: {settings['right_margin_inches']} -> right_margin_chars: {right_margin_chars}")
    print(f"characters_per_inch: {cpi}")
    print(f"font_height: {font_height}, font_width: {font_width}")
    print(f"line_spacing: {settings['line_spacing']} -> line_units: {line_units}")
    print(f"top_margin_inches: {settings['top_margin_inches']} -> blank_lines: {top_margin_blank_lines}")

    print("\n=== Exact byte sequence that would be sent ===")
    sequence = []
    sequence.append(("ESC @ (reset)", bytes([0x1B, 0x40])))
    sequence.append(("ESC l (left margin)", bytes([0x1B, 0x6C, left_margin_chars])))
    sequence.append(("ESC Q (right margin)", bytes([0x1B, 0x51, right_margin_chars])))
    sequence.append(("ESC w (double-height)", bytes([0x1B, 0x77, 1 if font_height == 2 else 0])))
    sequence.append(("ESC 3 (line spacing)", bytes([0x1B, 0x33, line_units])))
    sequence.append(("ESC W (double-width)", bytes([0x1B, 0x57, 1 if font_width == 2 else 0])))
    sequence.append(("Top margin blank lines", b"\r\n" * top_margin_blank_lines))

    for label, data in sequence:
        print(f"{label}: {data!r}")

    text = extract_docx_text(docx_path)
    chars_per_line = get_printable_chars_per_line(settings)
    wrapped_text = wrap_text(text, chars_per_line)

    print(f"\nchars_per_line calculated: {chars_per_line}")
    print("\n=== First 200 chars of wrapped text that would be sent ===")
    print(repr(wrapped_text[:200]))


if __name__ == "__main__":
    main()