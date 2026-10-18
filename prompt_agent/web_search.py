"""Optional Tavily search; credentials stay outside model-visible arguments."""

import json

import httpx


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web with Tavily for character, work, costume or other factual visual references. Returns source titles, URLs and excerpts; use search_tags to verify Danbooru tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A focused web search query."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def execute_web_search(api_key, query, max_results=5):
    """Return bounded source excerpts or a sanitized error, without automatic retries."""
    def error(message):
        return json.dumps({"error": message}, ensure_ascii=False)

    if not isinstance(api_key, str) or not api_key.strip():
        return error("Tavily API key is not configured.")
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        return error("query must be a non-empty string of at most 2000 characters.")
    if type(max_results) is not int or not 1 <= max_results <= 5:
        return error("max_results must be an integer between 1 and 5.")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {api_key.strip()}"},
                json={
                    "query": query.strip(), "max_results": max_results,
                    "topic": "general", "search_depth": "basic",
                    "include_answer": False, "include_raw_content": False,
                    "include_images": False, "auto_parameters": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        results = data.get("results")
        if not isinstance(results, list):
            return error("Tavily returned an invalid response.")
        sources = [
            {"title": str(item.get("title") or "")[:300],
             "url": str(item.get("url") or "")[:2000],
             "content": str(item.get("content") or "")[:4000]}
            for item in results[:max_results] if isinstance(item, dict)
        ]
        return json.dumps({"query": query.strip(), "results": sources}, ensure_ascii=False)
    except httpx.HTTPStatusError as exc:
        return error(f"Tavily request failed (HTTP {exc.response.status_code}).")
    except httpx.TimeoutException:
        return error("Tavily search timed out.")
    except Exception:
        # Do not expose response bodies, request headers or exception text containing keys.
        return error("Tavily search failed; check the connection and API configuration.")
