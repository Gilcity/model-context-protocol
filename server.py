import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PWTimeout,
    Error as PWError,
)
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ValidationError

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


#logging

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("mcp-playwright")

def accept_cookies_sync(page) -> bool:
    """Try to click an 'Accept cookies' button if it appears."""
    try:
        time.sleep(2)
        for button in page.query_selector_all("button"):
            name = (button.inner_text() or "").strip().lower()
            if "accept" in name and "cookie" in name:
                log.info(f"Clicking cookie button: {name!r}")
                button.click()
                return True
    except Exception as e:
        log.warning(f"[warn] Could not click cookies banner: {e}")
    return False


def search_top_gainer_sync(page) -> Dict[str, Optional[str]]:
    """
    Extract the top gainer (ticker + price) from Yahoo's Gainers table.

    This function assumes we are already on the Gainers page.
    """
    # Wait for the first row to load
    page.wait_for_selector("table tbody tr", timeout=30000)

    first_row = page.locator("table tbody tr").first
    if not first_row:
        raise RuntimeError("No rows found in gainers table")

    # Ticker is the first /quote/ link in the row
    ticker = (
        first_row.locator('a[href*="/quote/"]').first.inner_text().strip()
    )

    # Find the first numeric-looking <td> to use as the price
    price_cells = first_row.locator("td")
    price: Optional[str] = None
    count = price_cells.count()
    for i in range(count):
        text = (price_cells.nth(i).inner_text() or "").strip()
        # allow one dot in number
        if text.replace(".", "", 1).isdigit():
            price = text
            break

    if not price:
        raise RuntimeError("Could not locate a numeric price cell")

    return {"ticker": ticker, "price": price}


class YahooGainersClient:
    """
    Thin wrapper around a Playwright page that knows how to:
    - Open Yahoo Finance gainers page
    - Accept cookies
    - Extract top gainer
    """

    GAINERS_URL = (
        "https://finance.yahoo.com/markets/stocks/gainers/?fr=sycsrp_catchall"
    )

    def __init__(self, page):
        self.page = page

    def open_gainers_page(self) -> None:
        self.page.goto(self.GAINERS_URL, wait_until="domcontentloaded")

    def accept_cookies_if_needed(self) -> bool:
        return accept_cookies_sync(self.page)

    def get_top_gainer(self) -> Dict[str, str]:
        return search_top_gainer_sync(self.page)


#part1

def run_fixed_task() -> Dict[str, Any]:
    """
    Core browser robot:

    1. Starts Playwright
    2. Opens Yahoo Finance Gainers page
    3. Accepts cookies if needed
    4. Extracts top gainer ticker + price

    Returns a dict describing success/failure and the result.
    """
    log.info("Starting core Playwright robot to fetch top gainer...")
    result: Dict[str, Any] = {
        "success": False,
        "ticker": None,
        "price": None,
        "error": None,
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(60000)

            client = YahooGainersClient(page)

            try:
                client.open_gainers_page()
                client.accept_cookies_if_needed()
                data = client.get_top_gainer()

                result["success"] = True
                result["ticker"] = data["ticker"]
                result["price"] = data["price"]

                log.info(
                    "Success! Top gainer found: %s at %s",
                    data["ticker"],
                    data["price"],
                )
            finally:
                context.close()
                browser.close()

    except (PWTimeout, PWError) as e:
        log.error(f"Playwright error while fetching top gainer: {e}")
        result["error"] = f"Playwright error: {e}"
    except Exception as e:
        log.error(f"Unexpected error while fetching top gainer: {e}")
        result["error"] = str(e)

    # Clear final console output for the assignment requirement
    if result["success"]:
        print(
            f"Success! Top gainer found: {result['ticker']} at {result['price']}"
        )
    else:
        print(f"Failed to fetch top gainer. Error: {result['error']!r}")

    return result


#part 2

@dataclass
class AppState:
    p: Any
    browser: Any
    context: Any
    page: Any


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    MCP lifespan hook.

    Starts a Playwright browser when the MCP server starts, and
    shuts it down when the server stops.
    """

    def _start() -> AppState:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        return AppState(p=p, browser=browser, context=context, page=page)

    state = await asyncio.to_thread(_start)
    log.info("Playwright started for MCP server")

    try:
        yield state
    finally:
        def _stop(s: AppState) -> None:
            try:
                s.context.close()
                s.browser.close()
                s.p.stop()
            except Exception as e:
                log.warning(f"Error shutting down Playwright: {e}")

        await asyncio.to_thread(_stop, state)
        log.info("Playwright stopped for MCP server")


# Commands the LLM can choose when constructing a plan
Op = Literal[
    "goto",             # {op, url}
    "click",            # {op, selector}
    "type",             # {op, selector, text, pressEnter?}
    "wait_for",         # {op, selector, state?}
    "accept_cookies",   # {op}
    "extract_top_gainer"  # {op} -> returns {ticker, price}
]


class Step(BaseModel):
    op: Op = Field(..., description="Operation to perform")
    url: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    pressEnter: Optional[bool] = False
    state: Optional[Literal["attached", "visible", "hidden", "detached"]] = "visible"
    timeout_ms: Optional[int] = 30000


class Plan(BaseModel):
    """
    A structured plan produced by an LLM, e.g.:

    {
      "steps": [
        {"op":"goto","url":"https://finance.yahoo.com/markets/stocks/gainers"},
        {"op":"accept_cookies"},
        {"op":"wait_for","selector":"table tbody tr"},
        {"op":"extract_top_gainer"}
      ]
    }
    """

    steps: List[Step] = Field(..., min_items=1)


def run_plan_on_page(page, plan: Plan) -> Dict[str, Any]:
    """
    Execute a Plan against a Playwright page.

    This is used both by the MCP tool and by the HTTP API.
    """
    results: List[Dict[str, Any]] = []
    final_payload: Optional[Dict[str, Any]] = None

    for idx, step in enumerate(plan.steps, start=1):
        try:
            if step.op == "goto":
                if not step.url:
                    raise ValueError("goto requires 'url'")
                page.goto(step.url, wait_until="domcontentloaded")
                results.append(
                    {"step": idx, "op": step.op, "ok": True, "url": page.url}
                )

            elif step.op == "click":
                if not step.selector:
                    raise ValueError("click requires 'selector'")
                page.click(step.selector, timeout=step.timeout_ms)
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "type":
                if not step.selector:
                    raise ValueError("type requires 'selector'")
                page.fill(step.selector, step.text or "", timeout=step.timeout_ms)
                if step.pressEnter:
                    page.keyboard.press("Enter")
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "wait_for":
                if not step.selector:
                    raise ValueError("wait_for requires 'selector'")
                page.wait_for_selector(
                    step.selector,
                    state=step.state or "visible",
                    timeout=step.timeout_ms,
                )
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "accept_cookies":
                accepted = accept_cookies_sync(page)
                results.append(
                    {
                        "step": idx,
                        "op": step.op,
                        "ok": True,
                        "accepted": accepted,
                    }
                )

            elif step.op == "extract_top_gainer":
                payload = search_top_gainer_sync(page)
                results.append(
                    {
                        "step": idx,
                        "op": step.op,
                        "ok": True,
                        "data": payload,
                    }
                )
                final_payload = payload

            else:
                raise ValueError(f"Unknown op: {step.op}")

        except PWTimeout:
            results.append(
                {
                    "step": idx,
                    "op": step.op,
                    "ok": False,
                    "error": "timeout",
                }
            )
            break
        except Exception as e:
            results.append(
                {
                    "step": idx,
                    "op": step.op,
                    "ok": False,
                    "error": str(e),
                }
            )
            break

    return {"ok": True, "results": results, "final": final_payload}


#server and tools

mcp = FastMCP("Playwright MCP (Yahoo Finance)", lifespan=lifespan)


@mcp.tool()
async def open_url(ctx: Context, url: str) -> str:
    """Navigate to a URL."""
    page = ctx.request_context.lifespan_context.page
    await asyncio.to_thread(page.goto, url, wait_until="domcontentloaded")
    return f"navigated:{page.url}"


@mcp.tool()
async def describe_page(ctx: Context) -> Dict[str, Any]:
    """
    Return a structured snapshot of the current page to help an LLM plan.

    Includes:
      * Buttons
      * Links
      * Inputs
      * A hint about the Yahoo gainers table (if present)
    """
    page = ctx.request_context.lifespan_context.page

    def _collect() -> Dict[str, Any]:
        # Buttons and links with text for planner
        buttons: List[Dict[str, Any]] = []
        for b in page.query_selector_all("button"):
            try:
                txt = (b.inner_text() or "").strip()
                if txt:
                    buttons.append({"text": txt, "selector": "button"})
            except Exception:
                pass

        links: List[Dict[str, Any]] = []
        for a in page.query_selector_all("a"):
            try:
                txt = (a.inner_text() or "").strip()
                href = a.get_attribute("href")
                if txt or href:
                    links.append({"text": txt, "href": href})
            except Exception:
                pass

        # Inputs
        inputs: List[Dict[str, Any]] = []
        for inp in page.query_selector_all(
            "input, textarea, [contenteditable='true']"
        ):
            try:
                placeholder = inp.get_attribute("placeholder")
                itype = inp.get_attribute("type")
                inputs.append(
                    {
                        "type": itype,
                        "placeholder": placeholder,
                    }
                )
            except Exception:
                pass

        # Yahoo gainers table hint
        table_hint = None
        try:
            if page.query_selector("table tbody tr"):
                table_hint = {
                    "rows_selector": "table tbody tr",
                    "top_row_selector": "table tbody tr:first-of-type",
                    "ticker_link_selector": 'a[href*="/quote/"]',
                }
        except Exception:
            pass

        return {
            "url": page.url,
            "title": page.title(),
            "buttons": buttons[:50],
            "links": links[:50],
            "inputs": inputs[:50],
            "yahoo_gainers_table": table_hint,
        }

    return await asyncio.to_thread(_collect)


@mcp.tool()
async def execute_plan(ctx: Context, plan_json: str) -> Dict[str, Any]:
    """
    Execute a structured plan produced by an LLM.

    plan_json must conform to the Plan schema, e.g.:

    {
      "steps": [
        {"op":"goto","url":"https://finance.yahoo.com/markets/stocks/gainers"},
        {"op":"accept_cookies"},
        {"op":"wait_for","selector":"table tbody tr"},
        {"op":"extract_top_gainer"}
      ]
    }
    """
    page = ctx.request_context.lifespan_context.page

    # Validate plan
    try:
        plan = Plan.model_validate_json(plan_json)
    except ValidationError as e:
        return {"ok": False, "error": f"Invalid plan: {e}"}

    # Run it using the shared executor
    return await asyncio.to_thread(run_plan_on_page, page, plan)


#making it shareable

api = FastAPI(
    title="Playwright Yahoo Gainers API",
    description=(
        "Small HTTP wrapper around the Playwright robot.\n\n"
        "Endpoints:\n"
        "- POST /run-fixed-task  : core deterministic robot task\n"
        "- POST /run-plan        : execute a structured Plan\n"
        "(In a real system, an LLM would generate the Plan from a plain-English goal.)"
    ),
    version="1.0.0",
)


class GoalRequest(BaseModel):
    goal: str = Field(
        ...,
        description=(
            "Plain-English goal. For now, this is logged only; "
            "the server still runs the fixed 'top gainer' task."
        ),
    )


class PlanRequest(BaseModel):
    plan: Plan


@api.post("/run-fixed-task")
def api_run_fixed_task(body: GoalRequest) -> JSONResponse:
    """
    Start the core fixed robot remotely.

    In a fuller implementation, 'goal' could be used to choose different flows,
    but here we always run the 'top gainer' task and log the goal.
    """
    log.info("Received API goal: %s", body.goal)

    result = run_fixed_task()
    if not result["success"]:
        raise HTTPException(
            status_code=500, detail=result.get("error") or "Unknown error"
        )

    return JSONResponse(
        {
            "status": "ok",
            "goal": body.goal,
            "ticker": result["ticker"],
            "price": result["price"],
        }
    )


@api.post("/run-plan")
def api_run_plan(body: PlanRequest) -> JSONResponse:
    """
    Execute a structured Plan using a fresh browser session.

    This mirrors what the MCP `execute_plan` tool does, but over HTTP.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(60000)

            execution_result = run_plan_on_page(page, body.plan)

            context.close()
            browser.close()

        return JSONResponse(execution_result)

    except Exception as e:
        log.error(f"Error running plan via API: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CLI entrypoint for the core robot (so you can run: python server.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Run the fixed Playwright robot and print a clear final result
    run_fixed_task()
