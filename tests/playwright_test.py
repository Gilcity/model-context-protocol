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

#finding the highest ticker and its corresponding price
def search(page):
    # Wait for the first row to load
    page.wait_for_selector('table tbody tr', timeout=30000)
    first_row = page.locator('table tbody tr').first # selecting top gainer
    ticker = first_row.locator('a[href*="/quote/"]').first.inner_text().strip()
    price_cells = first_row.locator('td')
    price = None
    for i in range(price_cells.count()):
        text = price_cells.nth(i).inner_text().strip()
        if text.replace('.', '', 1).isdigit():  
            price = text
            break

    return ticker, price

#def report(page): 


#opening our browser 
def test_open_yahoo(): 
    with sync_playwright() as p: 
        browser = p.chromium.launch(headless=True)
        page = browser.new_page() 
        try: 
            #load and handle cookies
            page.set_default_timeout(60000)
            page.goto("https://finance.yahoo.com/markets/stocks/gainers/?fr=sycsrp_catchall", wait_until="domcontentloaded") 
            accept_cookies(page)

            #finding top gainer 
            ticker, price = search(page)
            print(f"Success!\n Highest gainer ticker: {ticker} \n Price: ${price}")
       # assert "" in page.title()
        #browser.close()
        except PWTimeout:
            print(" Timeout while loading Yahoo Finance.")
        finally:
            browser.close()