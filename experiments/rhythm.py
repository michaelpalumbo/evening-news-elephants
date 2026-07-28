"""
Send simple test commands to the FX-2190II that don't require paper
(or that are safe to try without paper loaded), using ESC/P.

Each function sends one command. Run this interactively or call
individual functions to test things one at a time.
"""

import usb.core
import usb.util

EPSON_VENDOR_ID = 0x04B8


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


def beep(output_endpoint) -> None:
    """
    ASCII BEL (0x07) triggers the printer's built-in beeper on most
    Epson impact printers, including the FX series. No paper needed.
    """
    output_endpoint.write(b"\x07")
    print("Sent beep command.")


def beep_pattern(output_endpoint, pattern: list[float]) -> None:
    """
    Beep in a rhythm by sending BEL repeatedly with delays in between.

    pattern is a list of pause durations (in seconds) between beeps.
    Example: [0.2, 0.2, 0.6] beeps, waits 0.2s, beeps, waits 0.2s,
    beeps, waits 0.6s. The printer's pitch and beep length are fixed
    by its hardware, so only the timing between beeps is adjustable.
    """
    import time

    for pause in pattern:
        output_endpoint.write(b"\x07")
        time.sleep(pause)

    print(f"Sent beep pattern with {len(pattern)} beeps.")


def initialize(output_endpoint) -> None:
    """
    ESC @ resets the printer to its power-on default settings.
    Safe with or without paper.
    """
    output_endpoint.write(b"\x1b@")
    print("Sent initialize (reset) command.")


def form_feed(output_endpoint) -> None:
    """
    Ejects/advances to the next page. Requires paper loaded to see
    an effect, but is safe to send without paper (it just won't
    move anything).
    """
    output_endpoint.write(b"\x0c")
    print("Sent form feed command.")


def set_condensed_mode(output_endpoint, enabled: bool) -> None:
    """
    ESC SI enables condensed print. ESC SO or 'DC2' cancels it (varies
    by mode). This changes the printer's internal state, no paper
    needed to set it.
    """
    if enabled:
        output_endpoint.write(b"\x0f")  # ESC SI equivalent: SI (0x0F)
        print("Condensed mode enabled.")
    else:
        output_endpoint.write(b"\x12")  # DC2 cancels condensed mode
        print("Condensed mode disabled.")


def set_emphasized_mode(output_endpoint, enabled: bool) -> None:
    """
    ESC E turns on bold/emphasized printing.
    ESC F turns it off.
    """
    if enabled:
        output_endpoint.write(b"\x1bE")
        print("Emphasized (bold) mode enabled.")
    else:
        output_endpoint.write(b"\x1bF")
        print("Emphasized (bold) mode disabled.")


def select_font(output_endpoint, font_number: int) -> None:
    """
    ESC k n selects a typeface. Font numbers on the FX-2190II
    typically range 0-4 (Draft, Roman, Sans Serif, Courier, Prestige,
    depending on firmware). Safe to send without paper.
    """
    output_endpoint.write(bytes([0x1B, 0x6B, font_number]))
    print(f"Font set to number {font_number}.")


def set_line_spacing_1_6_inch(output_endpoint) -> None:
    """
    ESC 2 sets line spacing to 1/6 inch (the default).
    """
    output_endpoint.write(b"\x1b2")
    print("Line spacing set to 1/6 inch.")


def main() -> None:
    printer = find_printer()
    interface, output_endpoint = find_output_endpoint(printer)

    usb.util.claim_interface(printer, interface.bInterfaceNumber)

    try:
        # Uncomment whichever you want to test:

        beep(output_endpoint)
        # beep_pattern(output_endpoint, [0.15, 0.15, 0.6])  # short-short-long
        # initialize(output_endpoint)
        # form_feed(output_endpoint)
        # set_condensed_mode(output_endpoint, enabled=True)
        # set_emphasized_mode(output_endpoint, enabled=True)
        # select_font(output_endpoint, font_number=1)
        # set_line_spacing_1_6_inch(output_endpoint)

    finally:
        usb.util.release_interface(printer, interface.bInterfaceNumber)
        usb.util.dispose_resources(printer)


if __name__ == "__main__":
    main()