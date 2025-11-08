# server.py
import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, Optional, List, Dict, Any

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ValidationError

# IMPORTANT: MCP over stdio must not write normal output to stdout.
# Log to stderr instead:
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("mcp-playwright")

# We’ll reuse your *sync* Playwright helpers via asyncio.to_thread
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


# -----------------------
# Your existing helpers
# -----------------------
def accept_cookies_sync(page) -> bool:
    try:
        time.sleep(2)
        for button in page.query_selector_all("button"):
            name = (button.inner_text() or "").strip().lower()
            if "accept" in name and "cookie" in name:
                log.info(f"Clicking button: {name}")
                button.click()
                return True
    except Exception as e:
        log.warning(f"[warn] Could not click cookies banner {e}")
    return False


def search_top_gainer_sync(page):
    # Wait for the first row to load
    page.wait_for_selector("table tbody tr", timeout=30000)
    first_row = page.locator("table tbody tr").first  # selecting top gainer
    ticker = first_row.locator('a[href*="/quote/"]').first.inner_text().strip()
    price_cells = first_row.locator("td")
    price = None
    # find the first numeric-looking td (basic heuristic)
    count = price_cells.count()
    for i in range(count):
        text = (price_cells.nth(i).inner_text() or "").strip()
        # allow one dot in number
        if text.replace(".", "", 1).isdigit():
            price = text
            break
    return ticker, price


# -----------------------
# Lifespan-managed state
# -----------------------
@dataclass
class AppState:
    p: any
    browser: any
    context: any
    page: any


@asynccontextmanager
async def lifespan(server: FastMCP):
    def _start():
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        return AppState(p=p, browser=browser, context=context, page=page)

    state = await asyncio.to_thread(_start)
    log.info("Playwright started")
    try:
        yield state
    finally:
        def _stop(s: AppState):
            try:
                s.context.close()
                s.browser.close()
                s.p.stop()
            except Exception as e:
                log.warning(f"Error shutting down Playwright: {e}")

        await asyncio.to_thread(_stop, state)
        log.info("Playwright stopped")


# -----------------------
# Planning: action schema
# -----------------------
# A small, explicit command language the LLM will emit and we’ll execute.

Op = Literal[
    "goto",            # {op, url}
    "click",           # {op, selector}
    "type",            # {op, selector, text, pressEnter?}
    "wait_for",        # {op, selector, state?}
    "accept_cookies",  # {op}
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
    steps: List[Step] = Field(..., min_items=1)


# -----------------------
# MCP server + tools
# -----------------------
mcp = FastMCP("Playwright MCP (Yahoo Finance)", lifespan=lifespan)


@mcp.tool()
async def open_url(ctx: Context, url: str) -> str:
    """Navigate to a URL."""
    await asyncio.to_thread(ctx.state.page.goto, url, {"wait_until": "domcontentloaded"})
    return f"navigated:{ctx.state.page.url}"


@mcp.tool()
async def describe_page(ctx: Context) -> Dict[str, Any]:
    """
    Return a structured snapshot of the current page to help an LLM plan.
    Includes common controls and a hint for the Yahoo 'gainers' table.
    """
    page = ctx.state.page

    def _collect():
        # Buttons and links with text for planner
        buttons = []
        for b in page.query_selector_all("button"):
            try:
                txt = (b.inner_text() or "").strip()
                if txt:
                    # build a stable-ish selector for the planner (heuristic)
                    role_sel = "button"
                    buttons.append({"text": txt, "selector": role_sel})
            except Exception:
                pass

        links = []
        for a in page.query_selector_all("a"):
            try:
                txt = (a.inner_text() or "").strip()
                href = a.get_attribute("href")
                if txt or href:
                    links.append({"text": txt, "href": href})
            except Exception:
                pass

        # Inputs
        inputs = []
        for inp in page.query_selector_all("input, textarea, [contenteditable='true']"):
            try:
                placeholder = inp.get_attribute("placeholder")
                itype = inp.get_attribute("type")
                inputs.append({"type": itype, "placeholder": placeholder})
            except Exception:
                pass

        # Yahoo gainers table hint
        table_hint = None
        try:
            if page.query_selector("table tbody tr"):
                # simple schema: the planner now knows where rows live
                table_hint = {
                    "rows_selector": "table tbody tr",
                    "top_row_selector": "table tbody tr:first-of-type",
                    "ticker_link_selector": 'a[href*=\"/quote/\"]'
                }
        except Exception:
            pass

        return {
            "url": page.url,
            "title": page.title(),
            "buttons": buttons[:50],
            "links": links[:50],
            "inputs": inputs[:50],
            "yahoo_gainers_table": table_hint
        }

    return await asyncio.to_thread(_collect)


@mcp.tool()
async def execute_plan(ctx: Context, plan_json: str) -> Dict[str, Any]:
    """
    Execute a structured plan produced by an LLM.
    plan_json must conform to the Plan schema:
    {
      "steps": [
        {"op":"goto","url":"..."},
        {"op":"accept_cookies"},
        {"op":"wait_for","selector":"table tbody tr"},
        {"op":"extract_top_gainer"}
      ]
    }
    Returns a list of per-step results and, if extraction was requested, the final payload.
    """
    page = ctx.state.page

    # Validate plan
    try:
        plan = Plan.model_validate_json(plan_json)
    except ValidationError as e:
        return {"ok": False, "error": f"Invalid plan: {e}"}

    results: List[Dict[str, Any]] = []
    final_payload: Dict[str, Any] | None = None

    for idx, step in enumerate(plan.steps, start=1):
        try:
            if step.op == "goto":
                if not step.url:
                    raise ValueError("goto requires url")
                await asyncio.to_thread(page.goto, step.url, {"wait_until": "domcontentloaded"})
                results.append({"step": idx, "op": step.op, "ok": True, "url": page.url})

            elif step.op == "click":
                if not step.selector:
                    raise ValueError("click requires selector")
                await asyncio.to_thread(page.click, step.selector, {"timeout": step.timeout_ms})
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "type":
                if not step.selector:
                    raise ValueError("type requires selector")
                await asyncio.to_thread(page.fill, step.selector, step.text or "")
                if step.pressEnter:
                    await asyncio.to_thread(page.keyboard.press, "Enter")
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "wait_for":
                if not step.selector:
                    raise ValueError("wait_for requires selector")
                await asyncio.to_thread(page.wait_for_selector, step.selector, {"state": step.state, "timeout": step.timeout_ms})
                results.append({"step": idx, "op": step.op, "ok": True})

            elif step.op == "accept_cookies":
                accepted = await asyncio.to_thread(accept_cookies_sync, page)
                results.append({"step": idx, "op": step.op, "ok": True, "accepted": accepted})

            elif step.op == "extract_top_gainer":
                ticker, price = await asyncio.to_thread(search_top_gainer_sync, page)
                payload = {"ticker": ticker, "price": price}
                results.append({"step": idx, "op": step.op, "ok": True, "data": payload})
                final_payload = payload

            else:
                raise ValueError(f"Unknown op: {step.op}")

        except PWTimeout:
            results.append({"step": idx, "op": step.op, "ok": False, "error": "timeout"})
            break
        except Exception as e:
            results.append({"step": idx, "op": step.op, "ok": False, "error": str(e)})
            break

    return {"ok": True, "results": results, "final": final_payload}
