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
import os
import sys
import pdfplumber

PDF_PATH = "./news_files/news.pdf"
OUTPUT_FOLDER = "./news_files"
BASE_NAME = "news"
DELIMITER = "#####"
LINE_COUNTS_FILENAME = "line_counts.json"


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


def main():
    if not os.path.isfile(PDF_PATH):
        print(f"Error: '{PDF_PATH}' is not a valid file.")
        sys.exit(1)

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    clear_old_txt_files()

    full_text = extract_full_text(PDF_PATH)
    stories = split_into_stories(full_text)

    line_counts = {}

    for i, story in enumerate(stories, start=1):
        filename = f"{BASE_NAME}_{i}.txt"
        out_path = os.path.join(OUTPUT_FOLDER, filename)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(story)

        line_count = len(story.splitlines())
        line_counts[filename] = line_count

        print(f"Wrote {out_path} ({line_count} lines)")

    line_counts_path = os.path.join(OUTPUT_FOLDER, LINE_COUNTS_FILENAME)
    with open(line_counts_path, "w", encoding="utf-8") as f:
        json.dump(line_counts, f, indent=2)

    print(f"Wrote {line_counts_path}")
    print(f"Done. {len(stories)} stories exported.")


if __name__ == "__main__":
    main()

# #!/usr/bin/env python3
# """
# Export each page of a PDF to its own .txt file (news_1.txt, news_2.txt, ...).

# Usage:
#     python pdf_to_txt_pages.py input.pdf [output_folder]

# If output_folder is omitted, files are written to the current directory.
# """

# import glob
# import os
# import sys
# import pdfplumber

# PDF_PATH = "./news_files/news.pdf"
# OUTPUT_FOLDER = "./news_files"
# BASE_NAME = "news"  # change this if you want a different filename prefix


# def clear_old_txt_files():
#     for txt_path in glob.glob(os.path.join(OUTPUT_FOLDER, "*.txt")):
#         os.remove(txt_path)
#         print(f"Removed {txt_path}")


# def main():
#     if not os.path.isfile(PDF_PATH):
#         print(f"Error: '{PDF_PATH}' is not a valid file.")
#         sys.exit(1)

#     os.makedirs(OUTPUT_FOLDER, exist_ok=True)

#     clear_old_txt_files()

#     with pdfplumber.open(PDF_PATH) as pdf:
#         for i, page in enumerate(pdf.pages, start=1):
#             text = page.extract_text() or ""
#             out_path = os.path.join(OUTPUT_FOLDER, f"{BASE_NAME}_{i}.txt")
#             with open(out_path, "w", encoding="utf-8") as f:
#                 f.write(text)
#             print(f"Wrote {out_path}")

#     print(f"Done. {len(pdf.pages)} pages exported.")


# if __name__ == "__main__":
#     main()