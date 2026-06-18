from __future__ import annotations

from backend.core.model_router import ask_model
from backend.tools.browser_tools import search_web_basic


def search_google_with_links(query: str) -> list[dict[str, str]]:
    from urllib.parse import quote_plus
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
        
    try:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            links = page.locator("a").element_handles()
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()
                    if href and href.startswith("https://") and not any(domain in href for domain in ("google.com", "youtube.com", "wikipedia.org/wiki/Special", "w3.org")):
                        if not any(r["url"] == href for r in results):
                            results.append({"url": href, "title": text})
                except Exception:
                    continue
            browser.close()
        return results[:5]
    except Exception:
        return []


def researcher_node(state):
    state["logs"].append("researcher: starting deep search grounding...")
    query = state["user_input"]
    
    state["logs"].append(f"researcher: searching Google for: '{query}'")
    links = search_google_with_links(query)
    
    scraped_contents = []
    if links:
        state["logs"].append(f"researcher: found {len(links)} search results. Selecting top links for deep scraping.")
        for index, link in enumerate(links[:2]):
            url = link["url"]
            title = link["title"] or f"Result {index+1}"
            state["logs"].append(f"researcher: scraping target page: {url}")
            try:
                from backend.tools.browser_tools import read_url
                web = read_url(url)
                if web and web.get("text"):
                    scraped_contents.append({
                        "url": url,
                        "title": title,
                        "text": web["text"][:5000]
                    })
                    state["logs"].append(f"researcher: successfully scraped {len(web['text'])} chars from {url}")
                else:
                    state["logs"].append(f"researcher: target page {url} returned no text")
            except Exception as exc:
                state["logs"].append(f"researcher: failed to scrape {url}: {exc}")
    else:
        state["logs"].append("researcher: no external links found. Falling back to basic web search.")
        from backend.tools.browser_tools import search_web_basic
        web = search_web_basic(query)
        scraped_contents.append({
            "url": "https://google.com",
            "title": "Google Search Snippet Summary",
            "text": web.get("text", "")[:8000]
        })

    state["logs"].append("researcher: synthesizing research dossier...")
    dossier_context = ""
    for c in scraped_contents:
        dossier_context += f"--- Source: {c['title']} ({c['url']}) ---\n{c['text']}\n\n"
        
    prompt = (
        "You are the Kattappa AI OS Researcher. Analyze the user request and synthesize "
        "a comprehensive research dossier based on the scraped web page contents. Cite sources using [Source Name](URL).\n"
        f"Request: {query}\n\n"
        f"Scraped Web Contents:\n{dossier_context}\n\n"
        "Unified Research Dossier:"
    )
    
    summary = ask_model(prompt, role="general")
    state["result"] = summary
    state["logs"].append("researcher: finalized dossier synthesis")
    return state
