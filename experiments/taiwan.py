"""
Print a single line of text on the FX-2190II.
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


def main() -> None:
    text = "Hello from Python!"

    printer = find_printer()
    interface, output_endpoint = find_output_endpoint(printer)

    usb.util.claim_interface(printer, interface.bInterfaceNumber)

    try:
        # Reset to defaults.
        output_endpoint.write(b"\x1b@")

        # Send the text as ASCII.
        output_endpoint.write(text.encode("ascii", errors="replace"))

        # Move to a new line and feed the page out so you can see it.
        output_endpoint.write(b"\r\n")
        output_endpoint.write(b"\x0c")  # form feed

    finally:
        usb.util.release_interface(printer, interface.bInterfaceNumber)
        usb.util.dispose_resources(printer)

    print("Done. Sent one line to the printer.")


if __name__ == "__main__":
    main()