"""
Pick a random news story from a text file (stories separated by
lines of "#####") and print it on the FX-2190II.
"""

import random
from pathlib import Path

import usb.core
import usb.util

EPSON_VENDOR_ID = 0x04B8

# Path to the text file containing all the stories.
STORIES_FILE = Path("news_files/news.txt")

# The delimiter line used to separate stories.
DELIMITER = "#####"


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


def set_page_format(output_endpoint) -> None:
    """
    Configure margins and page length for standard-ish letter-style
    output on continuous tractor paper.
    """
    # ESC l n: set left margin, n = characters from left edge (at 10 cpi)
    output_endpoint.write(bytes([0x1B, 0x6C, 0]))  # left margin = 0

    # ESC Q n: set right margin, n = characters from left edge (at 10 cpi)
    # At 10 characters-per-inch, 80 columns = 8 inches of print width.
    output_endpoint.write(bytes([0x1B, 0x51, 80]))

    # ESC C n: set page length in lines (uses current line spacing)
    # At 6 lines/inch (default), 66 lines = 11 inches.
    output_endpoint.write(bytes([0x1B, 0x43, 66]))


def load_stories() -> list[str]:
    """
    Read the stories file and split it into a list of individual
    stories, using the ##### delimiter. Empty/whitespace-only
    entries are dropped, and each story is stripped of leading and
    trailing whitespace.
    """
    text = STORIES_FILE.read_text(encoding="utf-8")
    raw_stories = text.split(DELIMITER)
    stories = [story.strip() for story in raw_stories if story.strip()]
    return stories


def choose_random_story(stories: list[str]) -> str:
    return random.choice(stories)


def print_text(output_endpoint, text: str) -> None:
    output_endpoint.write(text.encode("ascii", errors="replace"))
    output_endpoint.write(b"\r\n")


def main() -> None:
    stories = load_stories()

    if not stories:
        print(f"No stories found in: {STORIES_FILE.resolve()}")
        return

    story = choose_random_story(stories)

    printer = find_printer()
    interface, output_endpoint = find_output_endpoint(printer)

    usb.util.claim_interface(printer, interface.bInterfaceNumber)

    try:
        output_endpoint.write(b"\x1b@")  # reset
        set_page_format(output_endpoint)  # set margins/page length
        print_text(output_endpoint, story)
        output_endpoint.write(b"\x0c")  # form feed

    finally:
        usb.util.release_interface(printer, interface.bInterfaceNumber)
        usb.util.dispose_resources(printer)

    print("Printed story:")
    print(story)


if __name__ == "__main__":
    main()

# """
# Pick a random news story from a text file (stories separated by
# lines of "#####") and print it on the FX-2190II.
# """

# import random
# from pathlib import Path

# import usb.core
# import usb.util

# EPSON_VENDOR_ID = 0x04B8

# # Path to the text file containing all the stories.
# STORIES_FILE = Path("news.txt")

# # The delimiter line used to separate stories.
# DELIMITER = "#####"


# def find_printer():
#     printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
#     if printer is None:
#         raise RuntimeError("No Epson USB printer was found.")
#     return printer


# def find_output_endpoint(printer):
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


# def load_stories() -> list[str]:
#     """
#     Read the stories file and split it into a list of individual
#     stories, using the ##### delimiter. Empty/whitespace-only
#     entries are dropped, and each story is stripped of leading and
#     trailing whitespace.
#     """
#     text = STORIES_FILE.read_text(encoding="utf-8")
#     raw_stories = text.split(DELIMITER)
#     stories = [story.strip() for story in raw_stories if story.strip()]
#     return stories


# def choose_random_story(stories: list[str]) -> str:
#     return random.choice(stories)


# def print_text(output_endpoint, text: str) -> None:
#     output_endpoint.write(text.encode("ascii", errors="replace"))
#     output_endpoint.write(b"\r\n")


# def main() -> None:
#     stories = load_stories()

#     if not stories:
#         print(f"No stories found in: {STORIES_FILE.resolve()}")
#         return

#     story = choose_random_story(stories)

#     printer = find_printer()
#     interface, output_endpoint = find_output_endpoint(printer)

#     usb.util.claim_interface(printer, interface.bInterfaceNumber)

#     try:
#         output_endpoint.write(b"\x1b@")  # reset
#         print_text(output_endpoint, story)
#         output_endpoint.write(b"\x0c")  # form feed

#     finally:
#         usb.util.release_interface(printer, interface.bInterfaceNumber)
#         usb.util.dispose_resources(printer)

#     print("Printed story:")
#     print(story)


# if __name__ == "__main__":
#     main()