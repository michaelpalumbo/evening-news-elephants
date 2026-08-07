## ONLY IF THE LEFT TERMINAL DOESNT HAVE "(VENV)" in green text
1. enter the virtual environment: ```venv\Scripts\activate.ps1``` and press enter
3. (michael only) if first time running on machine, install libs ```shell pip install pdfplumber pyusb pywin32``` and press enter
4. to exit the venv, type ```shell exit``` and press enter


## running the print app
1. (optional) check/update the settings in settings.json
2. in the python venv (see above), run ```shell python3 stories_loop.py``` and press enter
3. to quit the app, use the hotkey ctrl-C (the current print job will continue printing until the page is completes)