#!/usr/bin/env python3
"""
Export each story in a PDF to its own .txt file (news_1.txt, news_2.txt,
...), splitting on a "#####" delimiter line rather than on PDF page
boundaries (stories don't align to pages).

Also writes news_files/line_counts.json, mapping each output filename
to how many lines of text it contains, so the print script can pack
multiple stories onto a single printed page.

Usage:
    python pdf_to_stories.py
"""

import glob
import json
import math
import os
import sys
import pdfplumber

PDF_PATH = "./news_files/news.pdf"
OUTPUT_FOLDER = "./news_files"
SETTINGS_PATH = "./settings.json"
BASE_NAME = "news"
DELIMITER = "#####"
LINE_COUNTS_FILENAME = "line_counts.json"


def load_printable_chars_per_line() -> int:
    """
    Read characters_per_inch and left/right margins from settings.json
    to figure out how many characters fit on one printed line. Used to
    estimate wrapped line count for stories that are now written as a
    single unbroken line (letting the printer wrap them itself).
    """
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)

    page_width_inches = 8.5  # matches stories_loop.py's assumption
    printable_width_inches = (
        page_width_inches
        - settings["left_margin_inches"]
        - settings["right_margin_inches"]
    )
    return max(1, int(printable_width_inches * settings["characters_per_inch"]))


def clear_old_txt_files():
    for txt_path in glob.glob(os.path.join(OUTPUT_FOLDER, "*.txt")):
        os.remove(txt_path)
        print(f"Removed {txt_path}")


def extract_full_text(pdf_path: str) -> str:
    """Concatenate text from every page, so stories spanning a PDF
    page boundary are joined back together before splitting on the
    delimiter."""
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages_text)


def split_into_stories(full_text: str) -> list[str]:
    raw_chunks = full_text.split(DELIMITER)
    stories = [chunk.strip() for chunk in raw_chunks]
    # Drop empty chunks (e.g. delimiter at very start/end of doc)
    return [story for story in stories if story]


def collapse_to_single_line(story: str) -> str:
    """
    Join all whitespace (including the newlines pdfplumber inserted
    per line of the original layout) into single spaces, so the
    printer does its own word-wrapping instead of us forcing breaks
    at the PDF's original line boundaries.
    """
    return " ".join(story.split())


def main():
    if not os.path.isfile(PDF_PATH):
        print(f"Error: '{PDF_PATH}' is not a valid file.")
        sys.exit(1)

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    clear_old_txt_files()

    full_text = extract_full_text(PDF_PATH)
    stories = split_into_stories(full_text)
    chars_per_line = load_printable_chars_per_line()

    line_counts = {}

    for i, story in enumerate(stories, start=1):
        single_line_story = collapse_to_single_line(story)

        filename = f"{BASE_NAME}_{i}.txt"
        out_path = os.path.join(OUTPUT_FOLDER, filename)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(single_line_story)

        # Estimate wrapped line count now that we're not forcing our
        # own line breaks — the printer will wrap at chars_per_line.
        line_count = max(1, math.ceil(len(single_line_story) / chars_per_line))
        line_counts[filename] = line_count

        print(f"Wrote {out_path} (~{line_count} printed lines)")

    line_counts_path = os.path.join(OUTPUT_FOLDER, LINE_COUNTS_FILENAME)
    with open(line_counts_path, "w", encoding="utf-8") as f:
        json.dump(line_counts, f, indent=2)

    print(f"Wrote {line_counts_path}")
    print(f"Done. {len(stories)} stories exported.")


if __name__ == "__main__":
    main()