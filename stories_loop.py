"""
Continuously print news stories, one page at a time, waiting between
each print. All timing and page-layout settings are read from
settings.json so they can be changed without editing this file.

Files are read in order from a news_files/ folder: news_1.txt,
news_2.txt, news_3.txt, and so on. The program stops automatically
once it reaches a file number that doesn't exist.
"""

import json
import time
from pathlib import Path

import usb.core
import usb.util

EPSON_VENDOR_ID = 0x04B8
SETTINGS_FILE = Path("settings.json")


def load_settings() -> dict:
    with SETTINGS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def find_printer():
    printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
    if printer is None:
        raise RuntimeError("No Epson USB printer was found.")
    return printer


def find_output_endpoint(printer):
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


def set_page_format(output_endpoint, settings: dict) -> float:
    """
    Configure margins, page length, and line spacing based on
    settings.json. Returns the actual line height in inches, so the
    caller can calculate how many blank lines make up the top margin.
    """
    cpi = settings["characters_per_inch"]

    # Left/right margins: ESC/P wants these in characters, not inches.
    left_margin_chars = round(settings["left_margin_inches"] * cpi)

    # Right margin is measured from the left edge of the page, not
    # from the right margin inward, so we need the printable width.
    page_width_inches = 8.5  # adjust here if your paper isn't 8.5" wide
    right_margin_position_inches = (
        page_width_inches - settings["right_margin_inches"]
    )
    right_margin_chars = round(right_margin_position_inches * cpi)

    output_endpoint.write(bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
    output_endpoint.write(bytes([0x1B, 0x51, right_margin_chars]))  # ESC Q

    # Line spacing: ESC 3 n sets spacing to n/180 inch per line.
    # Default single spacing is 1/6 inch = 30/180.
    # "line_spacing" is a multiplier on that default, matching how
    # word processors describe 1.0x / 1.25x / 1.5x line spacing.
    default_line_units = 30  # 1/6 inch, in 1/180ths
    line_units = round(default_line_units * settings["line_spacing"])
    output_endpoint.write(bytes([0x1B, 0x33, line_units]))

    line_height_inches = line_units / 180

    # Page length: ESC C n sets the page length in lines, using the
    # line spacing just configured. We want the *printable* area to
    # stop short of the bottom margin, so we shrink the page length.
    page_length_inches = 11.0  # adjust here if your paper isn't 11" long
    printable_length_inches = (
        page_length_inches - settings["bottom_margin_inches"]
    )
    page_length_lines = round(printable_length_inches / line_height_inches)
    output_endpoint.write(bytes([0x1B, 0x43, page_length_lines]))

    return line_height_inches


def print_top_margin(output_endpoint, settings: dict, line_height_inches: float) -> None:
    """
    ESC/P has no direct "top margin" command, so we simulate it by
    feeding blank lines before printing starts.
    """
    blank_lines = round(settings["top_margin_inches"] / line_height_inches)
    output_endpoint.write(b"\r\n" * blank_lines)


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


def print_story(output_endpoint, settings: dict, story: str) -> None:
    line_height_inches = set_page_format(output_endpoint, settings)
    print_top_margin(output_endpoint, settings, line_height_inches)

    output_endpoint.write(story.encode("ascii", errors="replace"))
    output_endpoint.write(b"\r\n")

    output_endpoint.write(b"\x0c")  # form feed to eject the page


def main() -> None:
    settings = load_settings()

    printer = find_printer()
    interface, output_endpoint = find_output_endpoint(printer)
    usb.util.claim_interface(printer, interface.bInterfaceNumber)

    file_number = 1

    try:
        while True:
            # Re-read settings each loop, so the delay (or margins)
            # can be changed without restarting the program.
            settings = load_settings()

            file_path = news_file_path(settings, file_number)

            if not file_path.exists():
                print(f"No more files found (looked for: {file_path}).")
                print("Stopping.")
                break

            story = file_path.read_text(encoding="utf-8").strip()

            output_endpoint.write(b"\x1b@")  # reset to defaults
            print_story(output_endpoint, settings, story)

            print(f"Printed: {file_path}")
            print(f"Waiting {settings['print_delay_seconds']} seconds...\n")

            file_number += 1

            time.sleep(settings["print_delay_seconds"])

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        usb.util.release_interface(printer, interface.bInterfaceNumber)
        usb.util.dispose_resources(printer)


if __name__ == "__main__":
    main()