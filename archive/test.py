import json
settings = json.load(open("settings.json"))
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
print("line_height_inches:", line_height_inches)
print("printable_length_inches:", printable_length_inches)
print("page_length_lines:", page_length_lines)