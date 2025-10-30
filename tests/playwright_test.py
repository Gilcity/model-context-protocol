from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

#handling cookie popups 
def accept_cookies(page): 
    for button in page.query_selector_all("button"): 
        name = button.inner_text().strip().lower()
        if "accept" in name and "cookie" in name: 
            button.click()
            break

#searching for the highest stock that day 
#def search(page): 

#report price 
#def report(page): 
#opening our browser
def test_open_yahoo(): 
    with sync_playwright() as p: 
        browser = p.chromium.launch(headless=False)
        page = browser.new_page() 
        page.goto("https://finance.yahoo.com/markets/stocks/gainers/?fr=sycsrp_catchall") 
        accept_cookies(page)  
      #  page.get_by_text("Search for news, tickers or companies").click()
       # assert "" in page.title()
        #browser.close()