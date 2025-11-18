# Overview 
This project is split into three parts. The first part uses Python's Playwright to automate web browsing. Playwright will open Yahoo Finance, navigate to Gainers, and return today's top gainer along with its Ticker and Price. 
The second part of this project integrates the intial program into a Playwright MCP Server that acts as a link to feed the LLM structured information about the webpage which allows the AI model to choose the next best action. 
Finally the third part is making turning the server into a small network-accessible service using FastMCP to create a web access point. 

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

# Output

Playwright_test.py opens Yahoo Finance, navigates to the highest gainers that day, and returns the Ticker and Price of the Highest Gainer. 

<img width="252" height="53" alt="image" src="https://github.com/user-attachments/assets/337bd778-277e-4cda-b435-d16e61609dde" />


Please feel free to change **headless=True** to **headless=False** if you'd like to watch the process of Playwright. 

# Using the MCP Server

# Part 1: Setting up the Server 

If you are already in a virtual environment type : 
```
source .\.venv\Scripts\Activate
```
in your powershell. Then run: 
```
pip install "mcp[cli]" playwright
playwright install
```
If you are not already in a virtual environment yo can initialize a uv- managed project with: 
```
uv init
uv add "mcp[cli]" playwright
uv run playwright install
```
# Part 2: Running the Server
You can run your server using 
```
uv run mcp dev server.py
```
You will know it is successful when you see 

<img width="199" height="38" alt="image" src="https://github.com/user-attachments/assets/20c149fd-127f-47f8-b6aa-e8678f935965" />  

The server should open up on your browser, where you can navigate to tools and utilize open_url, describe_page, and execute_plan. 

# Output 

Here is an example of running open_url: 

<img width="762" height="487" alt="image" src="https://github.com/user-attachments/assets/120d9bb3-46dc-41ad-b367-68d35b9cd4cc" />

describe_page: 


<img width="732" height="606" alt="image" src="https://github.com/user-attachments/assets/b595ec55-9d34-4b02-85e5-97223192beb6" />

Execute_plan: 

<img width="719" height="352" alt="image" src="https://github.com/user-attachments/assets/3fa91b6c-a489-4cf7-a4e5-c81a38f9afc5" />

<img width="738" height="432" alt="image" src="https://github.com/user-attachments/assets/8634d68f-3c5b-4f8a-803e-a16ec37e594d" />

**It is important to note that you must use this structure when using execute_plan**

