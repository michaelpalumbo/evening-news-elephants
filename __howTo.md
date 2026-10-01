## ELEPHANTS INSTRUCTIONS
# running the print app
1. (optional) update the settings in settings.json
2. in the python venv (see above), run ```python print_docx_loop.py``` and press enter
3. to quit the app, use the hotkey ctrl-C (the current print job will continue printing until the page is completes)
4. to run again, just click the 'up arrow' key to recall the last command, and hit enter

** if you get this error after step 2: 
Traceback (most recent call last):
  File "C:\Users\eleph\evening-news-elephants\print_docx_loop.py", line 30, in <module>
    import win32print
ModuleNotFoundError: No module named 'win32print'

THEN run this first: 
```venv\Scripts\activate.ps1``` (then press Enter)

THEN try steps 1-3 again

## MICHAEL-ONLY STUFF, thanks!
1. enter the virtual environment: ```venv\Scripts\activate.ps1``` and press enter
3. (michael only) if first time running on machine, install libs ```shell pip install pdfplumber pyusb pywin32``` and press enter
4. to exit the venv, type ```shell exit``` and press enter


# running the splitter 
1. download the latest news document from google docs as a .docx file
2. rename it 'latest_news.docx'
3. copy it into evening-news-elephants\news_docs (replace the current file if prompted)
4. in terminal, run this: oooenv env -t 
(this will toggle the env into libre's uno env)
* if step 4 errors out, run this first then try again: venv\Scripts\activate.ps1 (then press Enter)
5. run this: python3 split_docx.py news_docs\latest_news.docx
* it will take about 10-15 minutes to run
6. once it says it is completed in the terminal, toggle the env back to python:
oooenv env -t
7. 
move the output docs from news_docs over to news_files