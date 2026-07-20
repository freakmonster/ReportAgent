"""Unit tests for url_loader — fetch, extract, noise removal."""

import httpx
import pytest

from retrieval.loaders.url_loader import WebPage, fetch_multiple, fetch_url


@pytest.fixture
def html_page():
    return """<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
    <nav>Navigation menu</nav>
    <script>console.log('js');</script>
    <style>.ad { display: none; }</style>
    <article>
        <h1>Main Content</h1>
        <p>This is the main article body.</p>
        <p>Second paragraph with important data.</p>
    </article>
    <footer>Copyright 2025</footer>
    <div class="sidebar">Related links</div>
</body>
</html>"""


class TestFetchURL:
    async def test_extracts_main_content(self, mocker, html_page):
        mock_response = mocker.MagicMock()
        mock_response.text = html_page
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client = mocker.AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        mocker.patch("httpx.AsyncClient", return_value=mock_client)

        page = await fetch_url("https://example.com/article")
        assert isinstance(page, WebPage)
        assert "Main Content" in page.text
        assert "This is the main article body" in page.text
        assert "Navigation" not in page.text
        assert "Copyright" not in page.text

    async def test_extracts_title(self, mocker, html_page):
        mock_response = mocker.MagicMock()
        mock_response.text = html_page
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client = mocker.AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        mocker.patch("httpx.AsyncClient", return_value=mock_client)

        page = await fetch_url("https://example.com/article")
        assert page.title == "Test Article"

    async def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            await fetch_url("not-a-url")

    async def test_http_error_continues_in_batch(self, mocker):
        """fetch_multiple skips failed URLs but returns successful ones."""

        async def mock_fetch(url, **kwargs):
            if "fail" in url:
                raise httpx.HTTPError("Connection failed")
            return WebPage(url=url, text="content", title="OK")

        mocker.patch(
            "retrieval.loaders.url_loader.fetch_url",
            side_effect=mock_fetch,
        )

        pages = await fetch_multiple(
            [
                "https://example.com/ok1",
                "https://fail.com/bad",
                "https://example.com/ok2",
            ]
        )
        assert len(pages) == 2
        assert pages[0].url == "https://example.com/ok1"
        assert pages[1].url == "https://example.com/ok2"
