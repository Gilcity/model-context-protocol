Part 1: 
Writing a Python program that opens Yahoo Fiance automatically, searches for the highest grossing stock for today, and returns the ticker and price for the stock. The program will print a clear, final result with the stock, price, and sucess message. 
Includes proper error handlings in order to make sure Playwright will not timeout. 

Part 2:
Integrates solution with the Playwright MCP Server and feeds the LLM detailed, structured information about the current state of the webpage--such as accessiblity data and element roles--allowing the AI to choose the next best action. 
Example: the User provides a goal, "Find me the highest grossing stock of all time"
Model Context Protocol will then give the LLMk the necessary tools and page context where it will then generate a step-by-step plan using structured commands based on the current page's elements provdied by the MCP. 
Execution: The program reads the AI's plan and executes the steps using Playwright. 

Please make sure before running you have all the dependecies ready: 
pip install pytest-playwright
playwright install
