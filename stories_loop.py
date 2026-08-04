"""
Continuously print news stories, packing as many as will fit on a
single printed page before ejecting, and waiting between each page.
All timing and page-layout settings are read from settings.json so
they can be changed without editing this file.

Stories are read in order from a news_files/ folder: news_1.txt,
news_2.txt, news_3.txt, and so on, using news_files/line_counts.json
(produced by pdf_to_stories.py) to know how many lines each story
takes up. The program stops automatically once it reaches a file
number that doesn't exist.

Since ESC/P printers wrap purely on character count (no concept of
word boundaries), stories are word-wrapped in Python before being
sent, rather than relying on the printer's own line wrapping.

Works on:
  - Windows: sends raw bytes through the existing Windows print
    driver via pywin32 (no libusb/Zadig needed)
  - macOS/Linux: talks directly to the USB device via pyusb
"""

import json
import sys
import textwrap
import time
from pathlib import Path

SETTINGS_FILE = Path("settings.json")

IS_WINDOWS = sys.platform.startswith("win")

# ---- Windows-specific setup ----------------------------------------------
if IS_WINDOWS:
    import win32print

    # Must match the exact name shown in Windows' Devices and Printers
    PRINTER_NAME = "EPSON FX-2190II ESC/P"

# ---- macOS/Linux-specific setup -------------------------------------------
else:
    import usb.core
    import usb.util

    EPSON_VENDOR_ID = 0x04B8


# ---------------------------------------------------------------------------
# Output abstraction: both platforms expose a simple `.write(bytes)` object
# so all the printing logic below stays identical either way.
#
# IMPORTANT: on Windows, one whole print job (StartDocPrinter ...
# EndDocPrinter) must span an entire page's worth of ESC/P commands
# and data, not one job per write() call. Fragmenting a single page
# across multiple jobs can let the spooler/driver disturb the
# printer's internal page-position tracking between writes, causing
# the printed content to land at the wrong vertical position on the
# page. Use start_job()/end_job() (or the job() context manager)
# around every write() that belongs to the same physical page.
# ---------------------------------------------------------------------------

class WindowsPrinterOutput:
    """Wraps win32print raw-mode printing so it behaves like output_endpoint.write()."""

    def __init__(self, printer_name):
        self.printer_name = printer_name
        self.handle = win32print.OpenPrinter(printer_name)
        self._job_open = False

    def start_job(self):
        win32print.StartDocPrinter(self.handle, 1, ("ESC/P Job", None, "RAW"))
        win32print.StartPagePrinter(self.handle)
        self._job_open = True

    def write(self, data: bytes):
        if not self._job_open:
            raise RuntimeError(
                "write() called outside of a job. Call start_job() before "
                "writing, and end_job() once all of a page's writes are done."
            )
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


def find_printer():
    """macOS/Linux only: locate the USB device."""
    printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
    if printer is None:
        raise RuntimeError("No Epson USB printer was found.")
    return printer


def find_output_endpoint(printer):
    """macOS/Linux only: locate the USB OUT endpoint."""
    printer.set_configuration()
    configuration = printer.get_active_configuration()

    for interface in configuration:
        if interface.bInterfaceClass != 7:
            continue
        for endpoint in interface:
            direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
            if direction == usb.util.ENDPOINT_OUT:
                return interface, endpoint

    raise RuntimeError("Could not find the printer output endpoint.")


def get_printable_chars_per_line(settings: dict) -> int:
    """
    Same calculation used in pdf_to_stories.py's line-count
    estimate, kept here so actual print-time wrapping matches it.

    When large_print is enabled, double-width mode halves how many
    characters physically fit per line, since each character takes
    up twice the horizontal space.
    """
    page_width_inches = 8.5  # matches set_page_format's assumption
    printable_width_inches = (
        page_width_inches
        - settings["left_margin_inches"]
        - settings["right_margin_inches"]
    )
    chars_per_line = int(printable_width_inches * settings["characters_per_inch"])

    if settings.get("large_print"):
        chars_per_line = chars_per_line // 2

    return max(1, chars_per_line)


def set_page_format(output, settings: dict) -> float:
    """
    Configure margins and line spacing based on settings.json.
    Returns line_height_inches so the caller can calculate how many
    blank lines make up the top margin, and how many line feeds are
    needed to advance to the next physical page.

    Deliberately does NOT set a page length (ESC C) or use form feed
    (0x0C) -- those rely on the printer's own page-length tracking,
    which is exactly what caused the paper to advance an unreliable
    amount. Instead, the caller advances the paper by sending a
    calculated number of plain line feeds: enough to cover whatever
    wasn't already used by this page's content.
    """
    cpi = settings["characters_per_inch"]
    if settings.get("large_print"):
        cpi = cpi / 2  # double-width characters are twice as wide, so
                        # margin character-positions must be halved to
                        # land at the same physical inch position

    left_margin_chars = round(settings["left_margin_inches"] * cpi)

    page_width_inches = 8.5  # adjust here if your paper isn't 8.5" wide
    right_margin_position_inches = (
        page_width_inches - settings["right_margin_inches"]
    )
    right_margin_chars = round(right_margin_position_inches * cpi)

    output.write(bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
    output.write(bytes([0x1B, 0x51, right_margin_chars]))  # ESC Q

    default_line_units = 30  # 1/6 inch, in 1/180ths
    line_units = round(default_line_units * settings["line_spacing"])
    output.write(bytes([0x1B, 0x33, line_units]))

    line_height_inches = line_units / 180

    # ESC W 1 / ESC W 0: double-width printing on/off. This is a
    # standing mode (stays on until turned off), unlike SO which is
    # a one-line-only version of the same effect. Used as the "make
    # text bigger" control, since the FX-2190II doesn't offer a
    # clean way to select non-standard pitches below 10 CPI directly.
    if settings.get("large_print"):
        output.write(bytes([0x1B, 0x57, 1]))  # ESC W 1 -> double-width on
    else:
        output.write(bytes([0x1B, 0x57, 0]))  # ESC W 0 -> double-width off

    return line_height_inches


def print_top_margin(output, settings: dict, line_height_inches: float) -> None:
    """
    ESC/P has no direct "top margin" command, so we simulate it by
    feeding blank lines before printing starts.
    """
    blank_lines = round(settings["top_margin_inches"] / line_height_inches)
    output.write(b"\r\n" * blank_lines)


def news_file_path(settings: dict, file_number: int) -> Path:
    """
    Build the path for a given file number, e.g. news_files/news_1.txt
    """
    folder = Path(settings["news_folder"])
    filename = (
        f"{settings['news_file_prefix']}{file_number}"
        f"{settings['news_file_extension']}"
    )
    return folder / filename


def load_line_counts(settings: dict) -> dict:
    folder = Path(settings["news_folder"])
    line_counts_path = folder / "line_counts.json"
    with line_counts_path.open(encoding="utf-8") as f:
        return json.load(f)


def gather_stories_for_page(
    settings: dict, line_counts: dict, start_file_number: int, page_length_lines: int
) -> tuple[list[str], int, int]:
    """
    Starting at start_file_number, keep adding stories (in order) as
    long as they still exist, their combined line count fits within
    page_length_lines, and the max_stories_per_page cap (if set)
    hasn't been reached. Two blank lines are counted between stories
    as a separator.

    Returns (list_of_story_texts, next_file_number, story_lines_used).
    story_lines_used is just the story+separator line total -- it
    does NOT include the top margin, since that's added separately
    by the caller (top margin is constant regardless of story
    content, so it doesn't belong in the packing decision itself).
    """
    SEPARATOR_LINES = 2
    max_stories_per_page = settings.get("max_stories_per_page")

    stories = []
    lines_used = 0
    file_number = start_file_number

    while True:
        if max_stories_per_page is not None and len(stories) >= max_stories_per_page:
            break

        file_path = news_file_path(settings, file_number)
        if not file_path.exists():
            break

        filename = file_path.name
        story_lines = line_counts.get(filename)
        if story_lines is None:
            # Fall back to counting directly if line_counts.json is
            # missing an entry for some reason.
            story_lines = len(file_path.read_text(encoding="utf-8").splitlines())

        separator_lines = SEPARATOR_LINES if stories else 0
        projected_lines = lines_used + separator_lines + story_lines

        if stories and projected_lines > page_length_lines:
            # Doesn't fit alongside what we've already queued for
            # this page; stop here and leave it for the next page.
            break

        story_text = file_path.read_text(encoding="utf-8").strip()
        stories.append(story_text)
        lines_used = projected_lines
        file_number += 1

    return stories, file_number, lines_used


def wrap_story(story: str, chars_per_line: int) -> str:
    """
    Word-wrap a single-line story to chars_per_line, breaking only at
    spaces (never mid-word), then rejoin with CRLF so the printer
    treats each wrapped line as its own printed line.
    """
    wrapped_lines = textwrap.wrap(
        story,
        width=chars_per_line,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\r\n".join(wrapped_lines)


def print_page(
    output, settings: dict, stories: list[str], story_lines_used: int
) -> None:
    """
    Sends every command and every byte of text for one physical page
    as a single Windows print job, so the driver/spooler can't
    disturb the printer's page-position tracking partway through.

    Instead of a form feed (which jumps to a fixed, printer-tracked
    page length), the paper is advanced by a calculated number of
    plain line feeds: exactly enough to cover whatever vertical
    space this page's top margin + content didn't already use.
    """
    if IS_WINDOWS:
        output.start_job()

    try:
        output.write(b"\x1b@")  # reset to defaults

        line_height_inches = set_page_format(output, settings)

        top_margin_lines = round(settings["top_margin_inches"] / line_height_inches)
        print_top_margin(output, settings, line_height_inches)

        chars_per_line = get_printable_chars_per_line(settings)
        wrapped_stories = [wrap_story(story, chars_per_line) for story in stories]

        page_text = "\r\n\r\n".join(wrapped_stories)
        output.write(page_text.encode("ascii", errors="replace"))
        output.write(b"\r\n")

        # Total lines actually used on this physical page so far:
        # top margin blanks + story/separator content.
        total_lines_used = top_margin_lines + story_lines_used

        physical_lines_per_page = settings["page_length_lines"]
        advance_amount = max(0, physical_lines_per_page - total_lines_used)

        output.write(b"\r\n" * advance_amount)
    finally:
        if IS_WINDOWS:
            output.end_job()


def main() -> None:
    settings = load_settings()

    if IS_WINDOWS:
        output = WindowsPrinterOutput(PRINTER_NAME)
    else:
        printer = find_printer()
        interface, output = find_output_endpoint(printer)
        usb.util.claim_interface(printer, interface.bInterfaceNumber)

    file_number = 1

    try:
        while True:
            # Re-read settings each loop, so the delay (or margins)
            # can be changed without restarting the program.
            settings = load_settings()
            line_counts = load_line_counts(settings)

            # page_length_lines is read directly from settings, rather
            # than derived from line_spacing math -- the line-spacing
            # ESC/P command's real effect on the printer isn't
            # confirmed, so deriving a line budget from it can be
            # wrong. Set this directly based on what you observe
            # fitting on an actual printed page.
            page_length_lines = settings["page_length_lines"]

            stories, next_file_number, story_lines_used = gather_stories_for_page(
                settings, line_counts, file_number, page_length_lines
            )

            if not stories:
                print(f"No more files found (looked for file number {file_number}).")
                print("Stopping.")
                break

            print_page(output, settings, stories, story_lines_used)

            printed_range = (
                f"{file_number}-{next_file_number - 1}"
                if next_file_number - 1 > file_number
                else str(file_number)
            )
            print(f"Printed stories {printed_range}")
            print(f"Waiting {settings['print_delay_seconds']} seconds...\n")

            file_number = next_file_number

            time.sleep(settings["print_delay_seconds"])

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        if IS_WINDOWS:
            output.close()
        else:
            usb.util.release_interface(printer, interface.bInterfaceNumber)
            usb.util.dispose_resources(printer)


if __name__ == "__main__":
    main()