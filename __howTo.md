## ELEPHANTS INSTRUCTIONS
# running the print app
1. (optional) update the settings in settings.json
2. in the python venv (see above), run ```python3 print_docx_loop.py``` and press enter
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

# processing the updated news file
<< first stop the print loop app>>
1. download the lastest news file from google docs as a .docx file
2. rename it "source_doc.docx"
3. move it into the evening-news-elephants folder (can drag and drop it from /Downloads into the panel on the left-side of Visual Studio Code where all the files are listed)
4. open a new terminal window (click the little window icon to the left of the trashcan icon in the upper-right corner of terminal)
5. run this: oooenv env -t
6. run this: python split_docx.py source_doc.docx
7. will probably take up to 10 minutes. watch terminal for updates on which page it is processing. 
8. once completed, run this: oooenv env -t
9. start the print loop program again




## MICHAEL-ONLY STUFF, thanks!
1. enter the virtual environment: ```venv\Scripts\activate.ps1``` and press enter
3. (michael only) if first time running on machine, install libs ```shell pip install pdfplumber pyusb pywin32``` and press enter
4. to exit the venv, type ```shell exit``` and press enter

## Process the updated news file 
1. download the latest google doc as a pdf
2. rename it 'news.pdf'
3. remove the current news.pdf in the folder /news_files
4. move the new news.pdf file into /news_files
5. in the python venv (see above), run ```shell python3 doc2text.py``` and press enter




# running the splitter 
oooenv env -t (toggle the env into libre's uno env)
python doc_split source_Doc.docx
oooenv env -t (toggle back to python default so you can run the print loop)
move the output docs from news_docs over to news_files