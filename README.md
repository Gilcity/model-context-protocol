# Part 1: Setting up a Virtual Environment

First make sure you can create a virtual environment by running: 

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

From there navigate to the directory you'd like to run your project in and create your virtual environment and run these commands: 
```
python -m venv .venv //creating a virtual environment
```

```
.\.venv\Scripts\Activate //initializing virtual environment
```

You will know when you are successful if you see **(.venv)** before your directory 

# Part 2: Installing Dependencies
From there you can Install Playwright with Pytest support within your virtual environment : 

```
pip install pytest-playwright
```

Then install the Playwright browsers using : 

```
playwright install 
```

# Part 3: Running Playwright

You can run the program using 
```
pytest -s
```
Pytests will run all tests under the folder named "tests." 

# Part 4: Clean Up

To deactivate your virtual environment simply type 

```
deactivate
```



