# Scottish House Value Checker
 This project allows a user to input a Rightmove URL, it will extract the details, and provide value comparators using a variety of websites.
 
 # Build Instructions
 - Clone the repository.
 - Open the folder within an IDE, or go to the location via Terminal. 
 - Run pip install -r requirements.txt
 - Run uvicorn main:app and then go to http://127.0.0.1:8000/docs within the browser.
 - Enter the Rightmove URL into the "Try it out" segment.
 
 # Mandatory dependencies
 - The build is based on Webdriver stable 111.0.5563.65, if your version differs, replace the Webdriver binary in the folder.
 - Windows, no MAC support (yet).
 - Python already being installed on the machine (V3.12 was used for this build).
