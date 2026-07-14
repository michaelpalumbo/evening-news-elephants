from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


# The IP address on which this program listens.
#
# "0.0.0.0" means:
# accept OSC messages from this computer and other devices
# on the same network.
LISTEN_IP = "0.0.0.0"

# The UDP port on which the program listens.
#
# Your OSC sender must use this same destination port.
LISTEN_PORT = 9000


def receive_message(address: str, *arguments: object) -> None:
    """
    This function runs whenever an OSC message arrives.

    address contains the OSC address, such as:
        /printer/speed

    arguments contains any values sent with the message, such as:
        0.25
    """
    print(f"Address: {address}")
    print(f"Arguments: {arguments}")
    print()


def main() -> None:
    # The dispatcher decides which function handles each OSC address.
    dispatcher = Dispatcher()

    # Use receive_message() for every incoming OSC address.
    dispatcher.set_default_handler(receive_message)

    # Create the OSC server.
    server = BlockingOSCUDPServer(
        (LISTEN_IP, LISTEN_PORT),
        dispatcher,
    )

    print(f"Listening for OSC on port {LISTEN_PORT}")
    print("Press Ctrl+C to stop.")

    try:
        # Keep listening until the program is stopped.
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nOSC receiver stopped.")


if __name__ == "__main__":
    main()
