"""
Continuously print .docx files, one per print delay interval, then
loop back to the first file once the last one has been printed.

Files are read in order from a docx_files/ folder: news1.docx,
news2.docx, news3.docx, and so on (no leading zeros, no page-length
or margin logic -- each .docx IS one page by convention, no packing
or wrapping needed). Text is sent to the printer as-is, using the
printer's own default formatting.

All timing is read from settings.json so it can be changed without
editing this file.

Keyboard commands (checked during the wait between prints):
  p = pause the countdown
  c = continue/resume the countdown
  r = restart from the first file once the current delay finishes
  q = quit (same as Ctrl+C)

Windows only.
"""

import json
import msvcrt
import sys
import textwrap
import time
from pathlib import Path

import win32print
from docx import Document

SETTINGS_FILE = Path("settings.json")
PRINTER_NAME = "EPSON FX-2190II ESC/P"

DOCX_FOLDER = Path("news_files")
DOCX_PREFIX = "news"
DOCX_EXTENSION = ".docx"

PHYSICAL_PAGE_WIDTH_INCHES = 8.5  # matches stories_loop.py's assumption

# Same typographic-character cleanup used elsewhere in this project,
# so curly quotes/dashes from Word don't turn into "?" at print time.
CHARACTER_REPLACEMENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
}


def get_key_nonblocking() -> str | None:
    """Return a single lowercase keypress if one is waiting, else None."""
    if msvcrt.kbhit():
        return msvcrt.getch().decode(errors="ignore").lower()
    return None


class WindowsPrinterOutput:
    """Wraps win32print raw-mode printing. One job spans all writes for a page."""

    def __init__(self, printer_name):
        self.handle = win32print.OpenPrinter(printer_name)
        self._job_open = False

    def start_job(self):
        win32print.StartDocPrinter(self.handle, 1, ("DOCX Print Job", None, "RAW"))
        win32print.StartPagePrinter(self.handle)
        self._job_open = True

    def write(self, data: bytes):
        if not self._job_open:
            raise RuntimeError("write() called outside of a job.")
        win32print.WritePrinter(self.handle, data)

    def end_job(self):
        if self._job_open:
            win32print.EndPagePrinter(self.handle)
            win32print.EndDocPrinter(self.handle)
            self._job_open = False

    def close(self):
        self.end_job()
        win32print.ClosePrinter(self.handle)


def load_settings() -> dict:
    with SETTINGS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def docx_file_path(file_number: int) -> Path:
    """Build the path for a given file number, e.g. docx_files/news1.docx"""
    return DOCX_FOLDER / f"{DOCX_PREFIX}{file_number}{DOCX_EXTENSION}"


def normalize_for_printer(text: str) -> str:
    for smart_char, plain_char in CHARACTER_REPLACEMENTS.items():
        text = text.replace(smart_char, plain_char)
    return text


def extract_docx_text(docx_path: Path) -> str:
    """
    Read every paragraph's text from the .docx, in order, joined with
    single spaces within a paragraph (so Word's own line breaks don't
    force premature wrapping) and blank-line separators between
    paragraphs -- same as print_docx.py.
    """
    document = Document(docx_path)

    paragraphs = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            paragraphs.append(text)

    full_text = "\n\n".join(paragraphs)
    return normalize_for_printer(full_text)


def get_printable_chars_per_line(settings: dict) -> int:
    """Same calculation used in stories_loop.py / print_docx.py."""
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
    """
    Word-wrap each paragraph separately (so blank lines between
    paragraphs are preserved as actual blank lines, not merged), then
    rejoin with CRLF -- same as print_docx.py.
    """
    paragraphs = text.split("\n\n")
    wrapped_paragraphs = []
    for paragraph in paragraphs:
        wrapped_lines = textwrap.wrap(
            paragraph,
            width=chars_per_line,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped_paragraphs.append("\r\n".join(wrapped_lines))
    return "\r\n\r\n".join(wrapped_paragraphs)


def set_page_format(output, settings: dict) -> float:
    """Same margin/line-spacing/font commands as stories_loop.py / print_docx.py."""
    cpi = settings["characters_per_inch"]
    left_margin_chars = round(settings["left_margin_inches"] * cpi)

    right_margin_position_inches = (
        PHYSICAL_PAGE_WIDTH_INCHES - settings["right_margin_inches"]
    )
    right_margin_chars = round(right_margin_position_inches * cpi)

    output.write(bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
    output.write(bytes([0x1B, 0x51, right_margin_chars]))  # ESC Q

    font_height = settings.get("font_height", 1)
    output.write(bytes([0x1B, 0x77, 1 if font_height == 2 else 0]))  # ESC w

    default_line_units = 30
    line_units = round(default_line_units * settings["line_spacing"])
    output.write(bytes([0x1B, 0x33, line_units]))  # ESC 3

    font_width = settings.get("font_width", 1)
    output.write(bytes([0x1B, 0x57, 1 if font_width == 2 else 0]))  # ESC W

    line_height_inches = line_units / 180
    return line_height_inches


def print_top_margin(output, settings: dict, line_height_inches: float) -> None:
    blank_lines = round(settings["top_margin_inches"] / line_height_inches)
    output.write(b"\r\n" * blank_lines)


def print_docx(output: WindowsPrinterOutput, settings: dict, docx_path: Path) -> None:
    text = extract_docx_text(docx_path)
    chars_per_line = get_printable_chars_per_line(settings)
    wrapped_text = wrap_text(text, chars_per_line)

    output.start_job()
    try:
        output.write(b"\x1b@")  # reset to defaults
        line_height_inches = set_page_format(output, settings)
        print_top_margin(output, settings, line_height_inches)

        output.write(wrapped_text.encode("ascii", errors="replace"))
        output.write(b"\r\n")
        output.write(b"\x0c")  # form feed to eject the page
    finally:
        output.end_job()


def wait_with_pause_support(total_seconds: float) -> bool:
    """
    Waits total_seconds, checking every 0.1s for a keypress:
      - 'p' pauses the countdown (remaining time is frozen, not lost)
      - 'c' continues/resumes counting down from wherever it was
      - 'r' flags a restart to the first file; does NOT change the
        countdown itself -- whatever time is left still elapses
        normally, and only once it reaches 0 does the caller act on
        the restart flag.
      - 'q' quits immediately, the same as Ctrl+C.
    Any other key is ignored.

    Returns True if 'r' was pressed at any point during this wait.
    """
    CHECK_INTERVAL = 0.1
    remaining = total_seconds
    paused = False
    restart_requested = False

    while remaining > 0:
        key = get_key_nonblocking()

        if key == "q":
            raise KeyboardInterrupt
        elif key == "p" and not paused:
            paused = True
            print(f"Paused. {remaining:.1f} seconds remaining.")
        elif key == "c" and paused:
            paused = False
            print(f"Resumed. {remaining:.1f} seconds remaining.")
        elif key == "r" and not restart_requested:
            restart_requested = True
            print(
                f"Restart requested. Will begin from file 1 once the "
                f"current {remaining:.1f} second delay finishes."
            )

        if not paused:
            remaining -= CHECK_INTERVAL

        time.sleep(CHECK_INTERVAL)

    return restart_requested


def main() -> None:
    settings = load_settings()
    output = WindowsPrinterOutput(PRINTER_NAME)

    file_number = 1

    try:
        while True:
            # Re-read settings each loop, so the delay can be
            # changed without restarting the program.
            settings = load_settings()

            file_path = docx_file_path(file_number)

            if not file_path.exists():
                print(
                    f"No more files found (looked for file number {file_number}). "
                    f"Looping back to the first file."
                )
                file_number = 1
                continue

            print_docx(output, settings, file_path)

            print(
                f"\n\n-----------"
                f"\n\nCommands:\n\np = pause\nc = continue\nr = restart from file 1\nq = quit\n"
                f"\n\nPrinted {file_path}"
                f"\n\nWaiting {settings['print_delay_seconds']} seconds until next print... "
            )

            file_number += 1

            restart_requested = wait_with_pause_support(settings["print_delay_seconds"])
            if restart_requested:
                file_number = 1

    except KeyboardInterrupt:
        print("\nStopped. Quitting...\nProgram Exited. \n\nTo run again, type:\npython3 print_docx_loop.py\n...and hit 'Enter'")

    finally:
        output.close()


if __name__ == "__main__":
    main()