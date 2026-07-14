import time
import threading
from pathlib import Path

import usb.core
import usb.util


# Epson's USB vendor ID.
EPSON_VENDOR_ID = 0x04B8

# Folder containing the text files to print.
TEXT_FOLDER = Path("texts")

# Delay between characters, measured in seconds.
#
# This value can be changed while the printer is running.
print_delay = 0.15

# Controls whether printing is paused.
is_paused = False

# Controls whether the program should stop.
should_stop = False


def find_printer():
    """
    Find the first connected Epson USB device.
    """
    printer = usb.core.find(idVendor=EPSON_VENDOR_ID)

    if printer is None:
        raise RuntimeError("No Epson USB printer was found.")

    return printer


def find_output_endpoint(printer):
    """
    Find the USB endpoint used to send data from the computer
    to the printer.
    """
    printer.set_configuration()
    configuration = printer.get_active_configuration()

    for interface in configuration:
        # USB printer interfaces normally use class number 7.
        if interface.bInterfaceClass != 7:
            continue

        for endpoint in interface:
            direction = usb.util.endpoint_direction(
                endpoint.bEndpointAddress
            )

            if direction == usb.util.ENDPOINT_OUT:
                return interface, endpoint

    raise RuntimeError("Could not find the printer output endpoint.")


def read_text_files() -> list[Path]:
    """
    Return all .txt files in the text folder.

    sorted() means files will be printed alphabetically,
    which is why numbered names such as 01, 02 and 03 are useful.
    """
    return sorted(TEXT_FOLDER.glob("*.txt"))


def control_speed() -> None:
    """
    Listen for commands typed into the terminal.

    This function runs in a separate thread, allowing it to accept
    commands while the main thread continues printing.
    """
    global print_delay
    global is_paused
    global should_stop

    print("Controls:")
    print("  faster      decrease the delay")
    print("  slower      increase the delay")
    print("  speed 0.25  set the delay to 0.25 seconds")
    print("  pause       pause printing")
    print("  resume      resume printing")
    print("  stop        stop the program")

    while not should_stop:
        command = input("> ").strip().lower()

        if command == "faster":
            # Reduce the delay by 20%.
            print_delay = max(0.0, print_delay * 0.8)
            print(f"Delay: {print_delay:.3f} seconds")

        elif command == "slower":
            # Increase the delay by 25%.
            print_delay = print_delay * 1.25
            print(f"Delay: {print_delay:.3f} seconds")

        elif command.startswith("speed "):
            # Example:
            #   speed 0.5
            #
            # This sets the delay to half a second per character.
            try:
                new_delay = float(command.split()[1])
                print_delay = max(0.0, new_delay)
                print(f"Delay: {print_delay:.3f} seconds")
            except (ValueError, IndexError):
                print("Enter a number, for example: speed 0.25")

        elif command == "pause":
            is_paused = True
            print("Printing paused.")

        elif command == "resume":
            is_paused = False
            print("Printing resumed.")

        elif command == "stop":
            should_stop = True
            print("Stopping.")

        else:
            print("Unknown command.")


def print_text(output_endpoint, text: str) -> None:
    """
    Print a string one character at a time.

    Because print_delay is checked during every loop, another thread
    can change the speed while this function is printing.
    """
    global should_stop

    for character in text:
        if should_stop:
            return

        # Stay inside this loop while printing is paused.
        while is_paused and not should_stop:
            time.sleep(0.05)

        if should_stop:
            return

        # Convert the character to ASCII bytes.
        #
        # errors="replace" substitutes unsupported characters rather
        # than crashing the program.
        encoded_character = character.encode(
            "ascii",
            errors="replace",
        )

        output_endpoint.write(encoded_character)

        # Read the current delay value.
        #
        # Because the value may change during printing, each character
        # can use a different delay.
        time.sleep(print_delay)


def main() -> None:
    global should_stop

    printer = find_printer()
    interface, output_endpoint = find_output_endpoint(printer)

    usb.util.claim_interface(
        printer,
        interface.bInterfaceNumber,
    )

    # Run the terminal-control function alongside the printer function.
    #
    # daemon=True means this thread closes automatically when the main
    # program exits.
    control_thread = threading.Thread(
        target=control_speed,
        daemon=True,
    )
    control_thread.start()

    try:
        # Initialize the printer using the ESC/P "ESC @" command.
        output_endpoint.write(b"\x1b@")

        text_files = read_text_files()

        if not text_files:
            print(f"No text files found in: {TEXT_FOLDER.resolve()}")
            return

        for file_path in text_files:
            if should_stop:
                break

            print(f"Printing: {file_path.name}")

            # Read the entire text file.
            text = file_path.read_text(
                encoding="utf-8",
            )

            print_text(output_endpoint, text)

            # Add two line breaks between files.
            output_endpoint.write(b"\r\n\r\n")

    finally:
        should_stop = True

        usb.util.release_interface(
            printer,
            interface.bInterfaceNumber,
        )

        usb.util.dispose_resources(printer)


if __name__ == "__main__":
    main()
