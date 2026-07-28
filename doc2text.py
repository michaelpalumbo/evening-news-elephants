#!/usr/bin/env python3
"""
Export each page of a PDF to its own .txt file (news_1.txt, news_2.txt, ...).

Usage:
    python pdf_to_txt_pages.py input.pdf [output_folder]

If output_folder is omitted, files are written to the current directory.
"""

import os
import sys
import pdfplumber

PDF_PATH = "./news_files/news.pdf"
OUTPUT_FOLDER = "./news_files"
BASE_NAME = "news"  # change this if you want a different filename prefix


def main():
    if not os.path.isfile(PDF_PATH):
        print(f"Error: '{PDF_PATH}' is not a valid file.")
        sys.exit(1)

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    with pdfplumber.open(PDF_PATH) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            out_path = os.path.join(OUTPUT_FOLDER, f"{BASE_NAME}_{i}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Wrote {out_path}")

    print(f"Done. {len(pdf.pages)} pages exported.")


if __name__ == "__main__":
    main()