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

Works on:
  - Windows: sends raw bytes through the existing Windows print
    driver via pywin32 (no libusb/Zadig needed)
  - macOS/Linux: talks directly to the USB device via pyusb
"""

import json
import sys
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
# ---------------------------------------------------------------------------

class WindowsPrinterOutput:
    """Wraps win32print raw-mode printing so it behaves like output_endpoint.write()."""

    def __init__(self, printer_name):
        self.printer_name = printer_name
        self.handle = win32print.OpenPrinter(printer_name)

    def write(self, data: bytes):
        win32print.StartDocPrinter(self.handle, 1, ("ESC/P Job", None, "RAW"))
        try:
            win32print.StartPagePrinter(self.handle)
            win32print.WritePrinter(self.handle, data)
            win32print.EndPagePrinter(self.handle)
        finally:
            win32print.EndDocPrinter(self.handle)

    def close(self):
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


def set_page_format(output, settings: dict) -> tuple[float, int]:
    """
    Configure margins, page length, and line spacing based on
    settings.json. Returns (line_height_inches, page_length_lines) so
    the caller can calculate top margin blank lines and how many
    lines of story content fit in the printable area.
    """
    cpi = settings["characters_per_inch"]

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

    page_length_inches = 11.0  # adjust here if your paper isn't 11" long
    printable_length_inches = (
        page_length_inches
        - settings["top_margin_inches"]
        - settings["bottom_margin_inches"]
    )
    page_length_lines = int(printable_length_inches / line_height_inches)

    # ESC C n still wants the *full* page length (top margin included),
    # since blank lines are used to simulate the top margin below.
    full_page_length_lines = round(
        (page_length_inches - settings["bottom_margin_inches"]) / line_height_inches
    )
    output.write(bytes([0x1B, 0x43, full_page_length_lines]))

    return line_height_inches, page_length_lines


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
) -> tuple[list[str], int]:
    """
    Starting at start_file_number, keep adding stories (in order) as
    long as they still exist and their combined line count fits
    within page_length_lines. A blank line is counted between stories
    as a separator.

    Returns (list_of_story_texts, next_file_number).
    """
    stories = []
    lines_used = 0
    file_number = start_file_number

    while True:
        file_path = news_file_path(settings, file_number)
        if not file_path.exists():
            break

        filename = file_path.name
        story_lines = line_counts.get(filename)
        if story_lines is None:
            # Fall back to counting directly if line_counts.json is
            # missing an entry for some reason.
            story_lines = len(file_path.read_text(encoding="utf-8").splitlines())

        separator_lines = 1 if stories else 0
        projected_lines = lines_used + separator_lines + story_lines

        if stories and projected_lines > page_length_lines:
            # Doesn't fit alongside what we've already queued for
            # this page; stop here and leave it for the next page.
            break

        story_text = file_path.read_text(encoding="utf-8").strip()
        stories.append(story_text)
        lines_used = projected_lines
        file_number += 1

    return stories, file_number


def print_page(output, settings: dict, stories: list[str]) -> None:
    line_height_inches, _ = set_page_format(output, settings)
    print_top_margin(output, settings, line_height_inches)

    page_text = "\r\n".join(stories)
    output.write(page_text.encode("ascii", errors="replace"))
    output.write(b"\r\n")

    output.write(b"\x0c")  # form feed to eject the page


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

            # page_length_lines depends on margins/line spacing, so
            # compute it the same way set_page_format does, without
            # actually sending bytes yet.
            cpi = settings["characters_per_inch"]
            default_line_units = 30
            line_units = round(default_line_units * settings["line_spacing"])
            line_height_inches = line_units / 180
            page_length_inches = 11.0
            printable_length_inches = (
                page_length_inches
                - settings["top_margin_inches"]
                - settings["bottom_margin_inches"]
            )
            page_length_lines = int(printable_length_inches / line_height_inches)

            stories, next_file_number = gather_stories_for_page(
                settings, line_counts, file_number, page_length_lines
            )

            if not stories:
                print(f"No more files found (looked for file number {file_number}).")
                print("Stopping.")
                break

            output.write(b"\x1b@")  # reset to defaults
            print_page(output, settings, stories)

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

# """
# Continuously print news stories, one page at a time, waiting between
# each print. All timing and page-layout settings are read from
# settings.json so they can be changed without editing this file.

# Files are read in order from a news_files/ folder: news_1.txt,
# news_2.txt, news_3.txt, and so on. The program stops automatically
# once it reaches a file number that doesn't exist.

# Works on:
#   - Windows: sends raw bytes through the existing Windows print
#     driver via pywin32 (no libusb/Zadig needed)
#   - macOS/Linux: talks directly to the USB device via pyusb
# """

# import json
# import sys
# import time
# from pathlib import Path

# SETTINGS_FILE = Path("settings.json")

# IS_WINDOWS = sys.platform.startswith("win")

# # ---- Windows-specific setup ----------------------------------------------
# if IS_WINDOWS:
#     import win32print

#     # Must match the exact name shown in Windows' Devices and Printers
#     PRINTER_NAME = "EPSON FX-2190II ESC/P"

# # ---- macOS/Linux-specific setup -------------------------------------------
# else:
#     import usb.core
#     import usb.util

#     EPSON_VENDOR_ID = 0x04B8


# # ---------------------------------------------------------------------------
# # Output abstraction: both platforms expose a simple `.write(bytes)` object
# # so all the printing logic below stays identical either way.
# # ---------------------------------------------------------------------------

# class WindowsPrinterOutput:
#     """Wraps win32print raw-mode printing so it behaves like output_endpoint.write()."""

#     def __init__(self, printer_name):
#         self.printer_name = printer_name
#         self.handle = win32print.OpenPrinter(printer_name)

#     def write(self, data: bytes):
#         win32print.StartDocPrinter(self.handle, 1, ("ESC/P Job", None, "RAW"))
#         try:
#             win32print.StartPagePrinter(self.handle)
#             win32print.WritePrinter(self.handle, data)
#             win32print.EndPagePrinter(self.handle)
#         finally:
#             win32print.EndDocPrinter(self.handle)

#     def close(self):
#         win32print.ClosePrinter(self.handle)


# def load_settings() -> dict:
#     with SETTINGS_FILE.open(encoding="utf-8") as file:
#         return json.load(file)


# def find_printer():
#     """macOS/Linux only: locate the USB device."""
#     printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
#     if printer is None:
#         raise RuntimeError("No Epson USB printer was found.")
#     return printer


# def find_output_endpoint(printer):
#     """macOS/Linux only: locate the USB OUT endpoint."""
#     printer.set_configuration()
#     configuration = printer.get_active_configuration()

#     for interface in configuration:
#         if interface.bInterfaceClass != 7:
#             continue
#         for endpoint in interface:
#             direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
#             if direction == usb.util.ENDPOINT_OUT:
#                 return interface, endpoint

#     raise RuntimeError("Could not find the printer output endpoint.")


# def set_page_format(output, settings: dict) -> float:
#     """
#     Configure margins, page length, and line spacing based on
#     settings.json. Returns the actual line height in inches, so the
#     caller can calculate how many blank lines make up the top margin.
#     """
#     cpi = settings["characters_per_inch"]

#     # Left/right margins: ESC/P wants these in characters, not inches.
#     left_margin_chars = round(settings["left_margin_inches"] * cpi)

#     # Right margin is measured from the left edge of the page, not
#     # from the right margin inward, so we need the printable width.
#     page_width_inches = 8.5  # adjust here if your paper isn't 8.5" wide
#     right_margin_position_inches = (
#         page_width_inches - settings["right_margin_inches"]
#     )
#     right_margin_chars = round(right_margin_position_inches * cpi)

#     output.write(bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
#     output.write(bytes([0x1B, 0x51, right_margin_chars]))  # ESC Q

#     # Line spacing: ESC 3 n sets spacing to n/180 inch per line.
#     # Default single spacing is 1/6 inch = 30/180.
#     # "line_spacing" is a multiplier on that default, matching how
#     # word processors describe 1.0x / 1.25x / 1.5x line spacing.
#     default_line_units = 30  # 1/6 inch, in 1/180ths
#     line_units = round(default_line_units * settings["line_spacing"])
#     output.write(bytes([0x1B, 0x33, line_units]))

#     line_height_inches = line_units / 180

#     # Page length: ESC C n sets the page length in lines, using the
#     # line spacing just configured. We want the *printable* area to
#     # stop short of the bottom margin, so we shrink the page length.
#     page_length_inches = 11.0  # adjust here if your paper isn't 11" long
#     printable_length_inches = (
#         page_length_inches - settings["bottom_margin_inches"]
#     )
#     page_length_lines = round(printable_length_inches / line_height_inches)
#     output.write(bytes([0x1B, 0x43, page_length_lines]))

#     return line_height_inches


# def print_top_margin(output, settings: dict, line_height_inches: float) -> None:
#     """
#     ESC/P has no direct "top margin" command, so we simulate it by
#     feeding blank lines before printing starts.
#     """
#     blank_lines = round(settings["top_margin_inches"] / line_height_inches)
#     output.write(b"\r\n" * blank_lines)


# def news_file_path(settings: dict, file_number: int) -> Path:
#     """
#     Build the path for a given file number, e.g. news_files/news_1.txt
#     """
#     folder = Path(settings["news_folder"])
#     filename = (
#         f"{settings['news_file_prefix']}{file_number}"
#         f"{settings['news_file_extension']}"
#     )
#     return folder / filename


# def print_story(output, settings: dict, story: str) -> None:
#     line_height_inches = set_page_format(output, settings)
#     print_top_margin(output, settings, line_height_inches)

#     output.write(story.encode("ascii", errors="replace"))
#     output.write(b"\r\n")

#     output.write(b"\x0c")  # form feed to eject the page


# def main() -> None:
#     settings = load_settings()

#     if IS_WINDOWS:
#         output = WindowsPrinterOutput(PRINTER_NAME)
#     else:
#         printer = find_printer()
#         interface, output = find_output_endpoint(printer)
#         usb.util.claim_interface(printer, interface.bInterfaceNumber)

#     file_number = 1

#     try:
#         while True:
#             # Re-read settings each loop, so the delay (or margins)
#             # can be changed without restarting the program.
#             settings = load_settings()

#             file_path = news_file_path(settings, file_number)

#             if not file_path.exists():
#                 print(f"No more files found (looked for: {file_path}).")
#                 print("Stopping.")
#                 break

#             story = file_path.read_text(encoding="utf-8").strip()

#             output.write(b"\x1b@")  # reset to defaults
#             print_story(output, settings, story)

#             print(f"Printed: {file_path}")
#             print(f"Waiting {settings['print_delay_seconds']} seconds...\n")

#             file_number += 1

#             time.sleep(settings["print_delay_seconds"])

#     except KeyboardInterrupt:
#         print("\nStopped.")

#     finally:
#         if IS_WINDOWS:
#             output.close()
#         else:
#             usb.util.release_interface(printer, interface.bInterfaceNumber)
#             usb.util.dispose_resources(printer)


# if __name__ == "__main__":
#     main()