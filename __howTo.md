## START HERE
1. enter the virtual environment: ```shell python3 -m venv venv```
2. activate it ```shell source venv/bin/activate```
3. (michael only) if first time running on machine, install libs ```shell pip install pdfplumber pyusb```

## Process the updated news file 
1. download the latest google doc as a pdf
2. rename it 'news.pdf'
3. remove the current news.pdf in the folder /news_files
4. move the new news.pdf file into /news_files
5. in the python venv (see above), run ```shell python3 doc2text.py```


## running the print app
1. (optional) check/update the settings in settings.json
2. in the python venv (see above), run ```shell python3 stories_loop.py```
3. to quit the app, use the hotkey ctrl-C (the current print job will continue printing until the page is completes)