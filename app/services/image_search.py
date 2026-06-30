"""
app.services.image_search — Fetches open-source images based on query.
"""
from duckduckgo_search import DDGS

def get_open_source_image(query: str, max_results: int = 1) -> str:
    """
    Search DuckDuckGo for an image and return the first URL found.
    Returns empty string if none found or on error.
    """
    try:
        with DDGS() as ddgs:
            results = ddgs.images(
                keywords=query,
                max_results=max_results,
            )
            # DDGS().images returns a list of dicts
            for result in results:
                image_url = result.get("image")
                if image_url:
                    return image_url
    except Exception as e:
        print(f"Error fetching open-source image for '{query}': {e}")
    return ""
