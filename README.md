# evening-news-elephants

# installing

```shell
pip3 install pyusb

**IMPORTANT**: the 'speed' control is actually a delay time between characters being SENT to the printer. So a speeds of:

- 1.0 = 1 character / second
- .01 = 100 characters / second

The printer may still print in small bursts because of its internal buffer and mechanical limits.

## to run

```shell
python printer_controller.py
```

Then the terminal would show something like:

```shell
Controls:
  faster
  slower
  speed 0.25
  pause
  resume
  stop

Printing: 01-introduction.txt
>
```

At the > prompt, type:

```shell
slower
```

and press Enter.

Or:

```shell
speed 0.5
```

and press Enter.

The printer continues running because the script uses two threads:

1. the main thread sends text to the printer;
2. the control thread waits for your terminal input.
