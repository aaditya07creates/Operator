from typing import Tuple, List, Dict, Optional
from urllib.parse import urlparse, parse_qs, unquote
from logger_config import op_logger


class WebOps:
    """Web operations using DuckDuckGo search"""

    @staticmethod
    def _clean_url(url: str) -> str:
        """
        Clean redirect URLs and extract actual destination.

        DuckDuckGo sometimes returns Bing redirect URLs like:
        https://www.bing.com/ck/a?!&&p=abc123...&u=https://actual-url.com

        This extracts the actual URL from the 'u' parameter.
        """
        try:
            # Check if it's a redirect URL
            if 'bing.com/ck/' in url or 'duckduckgo.com/l/' in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)

                # Extract the 'u' parameter which contains the actual URL
                if 'u' in params:
                    actual_url = params['u'][0]
                    # URL decode it
                    actual_url = unquote(actual_url)
                    return actual_url

            # If not a redirect, return as-is
            return url

        except Exception as e:
            op_logger.logger.warning(f"URL cleaning failed: {e}, returning original URL")
            return url

    @classmethod
    def search(cls, query: str, max_results: int = 5) -> Tuple[bool, str, str]:
        """
        Search the web using DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum number of results (default 5, max 10)

        Returns:
            (success, formatted_results, details)
        """
        try:
            # Import here to avoid dependency issues if not installed
            from ddgs import DDGS

            # Limit max_results to reasonable range
            max_results = min(max(1, max_results), 10)

            op_logger.logger.info(f"🌐 Searching web: '{query}' (max {max_results} results)")

            # Perform search
            results = DDGS().text(query, max_results=max_results)

            if not results:
                return False, f"No results found for: {query}", ""

            # Format results
            formatted_lines = [f"🔍 Search results for: {query}\n"]

            for i, result in enumerate(results, 1):
                title = result.get('title', 'No title')
                link = result.get('link', result.get('href', 'No link'))
                snippet = result.get('body', result.get('description', 'No description'))

                # Clean redirect URLs to get actual destination
                clean_link = cls._clean_url(link)

                # Truncate snippet if too long
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."

                formatted_lines.append(f"{i}. **{title}**")
                formatted_lines.append(f"   🔗 {clean_link}")
                formatted_lines.append(f"   {snippet}")
                formatted_lines.append("")

            formatted_output = "\n".join(formatted_lines)
            details = f"Query: {query} | Results: {len(results)}"

            op_logger.logger.info(f"✓ Found {len(results)} results")
            return True, formatted_output, details

        except ImportError:
            error_msg = """❌ DuckDuckGo search not available.

To enable web search, install the required package:
    pip install ddgs

Then restart OPERATOR."""
            op_logger.logger.error("ddgs package not installed")
            return False, error_msg, "Missing dependency: ddgs"

        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            op_logger.logger.error(f"Web search error: {e}")
            return False, error_msg, f"Error: {type(e).__name__}"

    @classmethod
    def search_news(cls, query: str, max_results: int = 5) -> Tuple[bool, str, str]:
        """
        Search for recent news articles.

        Args:
            query: Search query
            max_results: Maximum number of results (default 5)

        Returns:
            (success, formatted_results, details)
        """
        try:
            from ddgs import DDGS

            max_results = min(max(1, max_results), 10)

            op_logger.logger.info(f"📰 Searching news: '{query}'")

            # Use news search
            results = DDGS().news(query, max_results=max_results)

            if not results:
                return False, f"No news found for: {query}", ""

            # Format results
            formatted_lines = [f"📰 News results for: {query}\n"]

            for i, result in enumerate(results, 1):
                title = result.get('title', 'No title')
                link = result.get('link', result.get('url', 'No link'))
                snippet = result.get('body', result.get('description', ''))
                date = result.get('date', 'Unknown date')
                source = result.get('source', 'Unknown source')

                # Clean redirect URLs to get actual destination
                clean_link = cls._clean_url(link)

                formatted_lines.append(f"{i}. **{title}**")
                formatted_lines.append(f"   📅 {date} | 📰 {source}")
                formatted_lines.append(f"   🔗 {clean_link}")
                if snippet:
                    if len(snippet) > 200:
                        snippet = snippet[:197] + "..."
                    formatted_lines.append(f"   {snippet}")
                formatted_lines.append("")

            formatted_output = "\n".join(formatted_lines)
            details = f"Query: {query} | News results: {len(results)}"

            op_logger.logger.info(f"✓ Found {len(results)} news articles")
            return True, formatted_output, details

        except ImportError:
            error_msg = """❌ DuckDuckGo search not available.

To enable web search, install:
    pip install ddgs"""
            return False, error_msg, "Missing dependency"

        except Exception as e:
            error_msg = f"News search failed: {str(e)}"
            op_logger.logger.error(f"News search error: {e}")
            return False, error_msg, f"Error: {type(e).__name__}"
