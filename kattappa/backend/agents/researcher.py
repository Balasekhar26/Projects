from __future__ import annotations

import json
from backend.core.model_router import ask_model
from backend.core.action_broker import ActionBroker


def search_google_with_links(query: str) -> list[dict[str, str]]:
    from urllib.parse import quote_plus
    try:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        broker_res = ActionBroker.intake_request("researcher", "BROWSER_MAP_LINKS", {"url": url}, {})
        if not broker_res.get("success"):
            return []
        
        result_str = broker_res.get("result", "")
        links = []
        for line in result_str.splitlines():
            line_clean = line.strip()
            if line_clean.startswith("https://") and not any(domain in line_clean for domain in ("google.com", "youtube.com", "wikipedia.org/wiki/Special", "w3.org")):
                if not any(r["url"] == line_clean for r in links):
                    links.append({"url": line_clean, "title": "Mapped link"})
        return links[:5]
    except Exception:
        return []


def researcher_node(state):
    state["logs"].append("researcher: starting deep search grounding...")
    query = state["user_input"]
    
    state["logs"].append(f"researcher: searching Google for: '{query}'")
    links = search_google_with_links(query)
    
    scraped_contents = []
    sources = []
    if links:
        state["logs"].append(f"researcher: found {len(links)} search results. Selecting top links for deep scraping.")
        for index, link in enumerate(links[:2]):
            url = link["url"]
            title = link["title"] or f"Result {index+1}"
            sources.append(title)
            state["logs"].append(f"researcher: scraping target page: {url}")
            try:
                broker_res = ActionBroker.intake_request("researcher", "BROWSER_READ", {"url": url}, {})
                if broker_res.get("success"):
                    web = broker_res.get("result", {})
                    text = web.get("content") or web.get("text", "") if isinstance(web, dict) else str(web)
                    if text:
                        scraped_contents.append({
                            "url": url,
                            "title": title,
                            "text": text[:5000]
                        })
                        state["logs"].append(f"researcher: successfully scraped {len(text)} chars from {url}")
                    else:
                        state["logs"].append(f"researcher: target page {url} returned no text")
                else:
                    state["logs"].append(f"researcher: Action Broker failed to read page {url}")
            except Exception as exc:
                state["logs"].append(f"researcher: failed to scrape {url}: {exc}")
    else:
        state["logs"].append("researcher: no external links found. Falling back to basic web search.")
        broker_res = ActionBroker.intake_request("researcher", "BROWSER_SEARCH", {"query": query}, {})
        if broker_res.get("success"):
            web = broker_res.get("result", {})
            text = web.get("content") or web.get("text", "") if isinstance(web, dict) else str(web)
            sources.append("Google Search Snippet Summary")
            scraped_contents.append({
                "url": "https://google.com",
                "title": "Google Search Snippet Summary",
                "text": text[:8000]
            })
        else:
            state["logs"].append("researcher: Action Broker failed basic web search fallback")

    # Vetting Sources & Consensus Calculation via SourceTrustEngine
    from backend.core.source_trust_engine import SourceTrustEngine, TrustLevel
    
    valid_sources = []
    for src in sources:
        rep = SourceTrustEngine.get_source_reputation(src)
        if rep.get("trust_level") == TrustLevel.REJECTED.value:
            state["logs"].append(f"researcher: source '{src}' is REJECTED. Skipping.")
        else:
            valid_sources.append(src)
            
    if not valid_sources:
        state["result"] = "Error: All research sources are low-reputation or rejected. Skipping proposal generation."
        state["logs"].append("researcher: blocked due to rejected/low-reputation sources")
        return state

    consensus_score = SourceTrustEngine.calculate_consensus(valid_sources)
    state["logs"].append(f"researcher: calculated consensus score: {consensus_score}")
    
    if consensus_score < 0.50:
        state["result"] = f"Error: Consensus score ({consensus_score}) is below the required threshold of 0.50. Skipping proposal generation."
        state["logs"].append("researcher: blocked due to low source consensus")
        return state

    state["logs"].append("researcher: unifying research dossier...")
    dossier_context = ""
    for c in scraped_contents:
        if c['title'] in valid_sources:
            dossier_context += f"--- Source: {c['title']} ({c['url']}) ---\n{c['text']}\n\n"
        
    prompt = (
        "You are the Kattappa AI OS Researcher. Analyze the user request and synthesize "
        "a comprehensive research dossier based on the scraped web page contents. Cite sources using [Source Name](URL).\n"
        f"Request: {query}\n\n"
        f"Scraped Web Contents:\n{dossier_context}\n\n"
        "Unified Research Dossier:"
    )
    
    summary = ask_model(prompt, role="general")
    
    # Idea Extraction and Proposal Generation
    if any(word in query.lower() for word in ("propose", "proposal", "improve", "idea", "upgrade")):
        state["logs"].append("researcher: proposal keyword detected, generating proposal")
        try:
            from backend.core.proposal_engine import ProposalEngine
            prop_prompt = (
                f"Based on the dossier: {summary}\n"
                "Extract an improvement proposal for Kattappa.\n"
                "Respond with a JSON object matching this schema:\n"
                "{\n"
                "  \"title\": \"Proposal Title\",\n"
                "  \"problem\": \"Problem statement\",\n"
                "  \"evidence\": \"Supporting evidence\",\n"
                "  \"proposal\": \"Proposed change details\",\n"
                "  \"expected_gain\": 1.2,\n"
                "  \"complexity\": 3,\n"
                "  \"confidence\": 7,\n"
                "  \"affected_modules\": []\n"
                "}\n"
                "Do not include any other text."
            )
            prop_res = ask_model(prop_prompt, role="coder")
            import re
            json_match = re.search(r"\{.*\}", prop_res, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                proposal = ProposalEngine.create_proposal(
                    title=data.get("title", f"Improvement from {valid_sources[0]}"),
                    problem=data.get("problem", "Identified performance potential"),
                    evidence=data.get("evidence", summary[:500]),
                    proposal=data.get("proposal", "Refactor system nodes"),
                    expected_gain=float(data.get("expected_gain", 1.0)),
                    complexity=int(data.get("complexity", 3)),
                    confidence=int(data.get("confidence", 7)),
                    affected_modules=data.get("affected_modules", []),
                    source_name=valid_sources[0]
                )
                state["result"] = f"Research Dossier:\n{summary}\n\nGenerated Proposal:\n{json.dumps(proposal, indent=2)}"
                state["logs"].append(f"researcher: registered proposal successfully (ID: {proposal.get('id')})")
                return state
        except Exception as e:
            state["logs"].append(f"researcher failed to generate proposal: {e}")
            
    state["result"] = summary
    state["logs"].append("researcher: finalized dossier synthesis")
    return state
