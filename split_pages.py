#!/usr/bin/env python3
"""
split_pdf_by_page.py

Splits a .pdf file into one .txt file per page, named like:
    news_1.txt, news_2.txt, news_3.txt, ...

Requirements:
    pip install pypdf

Usage:
    python split_pdf_by_page.py input.pdf --outdir pages --prefix news
"""

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader


def split_pdf_to_txt(pdf_path: Path, outdir: Path, prefix: str) -> int:
    reader = PdfReader(str(pdf_path))
    outdir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        out_file = outdir / f"{prefix}_{i}.txt"
        out_file.write_text(text, encoding="utf-8")
        print(f"Wrote {out_file}  ({len(text)} chars)")

    return len(reader.pages)


def main():
    parser = argparse.ArgumentParser(description="Split a .pdf into per-page .txt files.")
    parser.add_argument("pdf", type=Path, help="Path to the input .pdf file")
    parser.add_argument("--outdir", type=Path, default=Path("pages"), help="Output directory (default: ./pages)")
    parser.add_argument("--prefix", type=str, default="news", help="Filename prefix (default: news)")
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    n_pages = split_pdf_to_txt(args.pdf, args.outdir, args.prefix)
    print(f"\nDone. {n_pages} pages written to {args.outdir}/")


if __name__ == "__main__":
    main()