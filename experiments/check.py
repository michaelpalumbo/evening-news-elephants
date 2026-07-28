"""
Check the connection status of an Epson USB printer.

This performs two levels of checking:

1. USB-level: confirms the device is plugged in, readable, and its
   endpoints can be found. This works for basically any USB printer.

2. ESC/P-level (optional): asks the printer for its actual status
   byte (paper out, offline, error, etc.) using the DLE EOT real-time
   status command. Not all Epson printers support this over USB in
   the same way — some only support it over serial/parallel or a
   specific "ESC/P2" or "D4" status mode. If it doesn't respond, the
   script will tell you and fall back to USB-level info only.
"""

import sys

import usb.core
import usb.util

EPSON_VENDOR_ID = 0x04B8


def find_printer():
    printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
    if printer is None:
        raise RuntimeError("No Epson USB printer was found.")
    return printer


def find_endpoints(printer):
    """
    Return (interface, out_endpoint, in_endpoint).
    in_endpoint may be None if the printer has no readable IN endpoint.
    """
    printer.set_configuration()
    configuration = printer.get_active_configuration()

    for interface in configuration:
        if interface.bInterfaceClass != 7:
            continue

        out_endpoint = None
        in_endpoint = None

        for endpoint in interface:
            direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
            if direction == usb.util.ENDPOINT_OUT:
                out_endpoint = endpoint
            elif direction == usb.util.ENDPOINT_IN:
                in_endpoint = endpoint

        if out_endpoint is not None:
            return interface, out_endpoint, in_endpoint

    raise RuntimeError("Could not find the printer output endpoint.")


def describe_usb_status(printer) -> None:
    """
    Print basic USB-level info: manufacturer, product name, and
    whether the device responds at all (i.e. is powered on and
    plugged in, as opposed to being unplugged or asleep).
    """
    try:
        manufacturer = usb.util.get_string(printer, printer.iManufacturer)
    except Exception:
        manufacturer = "(unavailable)"

    try:
        product = usb.util.get_string(printer, printer.iProduct)
    except Exception:
        product = "(unavailable)"

    print("USB device found:")
    print(f"  Vendor ID:  {hex(printer.idVendor)}")
    print(f"  Product ID: {hex(printer.idProduct)}")
    print(f"  Manufacturer: {manufacturer}")
    print(f"  Product: {product}")


def query_escp_status(printer, interface, out_endpoint, in_endpoint) -> None:
    """
    Send the ESC/P real-time status request (DLE EOT n) and try to
    read back a status byte. This is best-effort: many printers
    ignore this over USB, in which case we just report that.
    """
    if in_endpoint is None:
        print("\nNo IN endpoint available; cannot request detailed status.")
        return

    # DLE EOT n commands, per Epson's real-time command set:
    #   n=1: printer status
    #   n=2: ink/ribbon status (not applicable to impact printers)
    #   n=3: paper sensor status
    requests = {
        "Printer status (n=1)": b"\x10\x04\x01",
        "Paper sensor status (n=3)": b"\x10\x04\x03",
    }

    try:
        usb.util.claim_interface(printer, interface.bInterfaceNumber)

        for label, command in requests.items():
            out_endpoint.write(command)

            try:
                data = in_endpoint.read(
                    in_endpoint.wMaxPacketSize, timeout=1000
                )

                if len(data) == 0:
                    print(f"\n{label}: printer responded with no data.")
                    continue

                raw_bytes = list(data)
                print(f"\n{label}: raw bytes = {raw_bytes}")
                print(
                    f"  binary = "
                    f"{[bin(b) for b in raw_bytes]}"
                )

                if label.startswith("Printer status"):
                    decode_status_byte(raw_bytes[0])

            except usb.core.USBTimeoutError:
                print(f"\n{label}: no response (timed out).")

    finally:
        usb.util.release_interface(printer, interface.bInterfaceNumber)
        usb.util.dispose_resources(printer)


def decode_status_byte(status_byte: int) -> None:
    """
    Rough decode of the standard Epson status byte bits.
    Bit meanings vary slightly by model/generation, so treat this
    as a best guess rather than a guarantee.
    """
    print("  Paper out:  ", bool(status_byte & 0b00100000))
    print("  Offline:    ", bool(status_byte & 0b00001000))
    print("  Error:      ", bool(status_byte & 0b00000010))


def main() -> None:
    try:
        printer = find_printer()
    except RuntimeError as error:
        print(f"NOT CONNECTED: {error}")
        sys.exit(1)

    describe_usb_status(printer)

    try:
        interface, out_endpoint, in_endpoint = find_endpoints(printer)
    except RuntimeError as error:
        print(f"\nDevice found, but endpoints could not be read: {error}")
        sys.exit(1)

    query_escp_status(printer, interface, out_endpoint, in_endpoint)


if __name__ == "__main__":
    main()