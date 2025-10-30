from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import time 
#handling cookie popups IF IT APPEARS
def accept_cookies(page): 
    try: 
        time.sleep(2)
        for button in page.query_selector_all("button"): 
            name = button.inner_text().strip().lower()
            if "accept" in name and "cookie" in name: 
                print(f"Clicking button: {name}")
                button.click()
                return True
    except Exception as e: 
        print(f"[warn] Could not click cookies banner {e}")
    return False

#searching for the highest stock that day 
#def search(page): 

#report price 
#def report(page): 


#opening our browser
def test_open_yahoo(): 
    with sync_playwright() as p: 
        browser = p.chromium.launch(headless=False)
        page = browser.new_page() 
        try: 
            #load and handle cookies
            page.set_default_timeout(60000)
            page.goto("https://finance.yahoo.com/markets/stocks/gainers/?fr=sycsrp_catchall", wait_until="domcontentloaded") 
            #  page.get_by_text("Search for news, tickers or companies").click()
            accept_cookies(page)
        
       # assert "" in page.title()
        #browser.close()
            try:
                page.wait_for_selector("table", timeout=4000) #40 sec timeout
                print("✅ Page loaded and table found.")
            except PWTimeout:
                print("Table not found, but page may still be usable.")
                print(f"Page title: {page.title()}")

        except PWTimeout:
            print(" Timeout while loading Yahoo Finance.")
        finally:
            browser.close()