"""HTML parsing utilities for the scraper."""

import re
from html import unescape


def html_to_plain_text(html: str) -> str:
    """Convert HTML to plain text, stripping tags."""
    text = re.sub(r"<head.*?>.*?</head>", "", html, flags=re.M | re.S | re.I)
    text = re.sub(r"<a\s.*?>", "", text, flags=re.M | re.S | re.I)
    text = re.sub(r"<br.*?>", "\n", text, flags=re.M | re.S)
    text = re.sub(r"<.*?>", "", text, flags=re.M | re.S)
    text = re.sub(r"(\s*\n)+", "\n", text, flags=re.M | re.S)
    return unescape(text)
