# check_site.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import re

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'dev'


class DocumentLinks(HTMLParser):
    """Collect internal links and image references from an HTML document."""
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            if values['id'] in self.ids:
                raise ValueError(f'Duplicate element ID: {values["id"]}')
            self.ids.add(values['id'])
        if tag == 'a' and 'href' in values:
            self.links.append(values['href'])
        if tag == 'img':
            self.images.append((values.get('src', ''), values.get('alt', '')))


def verify_page(path):
    text = path.read_text(encoding='utf-8')
    parser = DocumentLinks()
    parser.feed(text)
    if not re.search(r'<title>\s*\S', text, re.I):
        raise ValueError(f'Missing title: {path}')
    if 'noindex, nofollow' not in text:
        raise ValueError(f'Review page must remain unindexed: {path}')
    for src, alt in parser.images:
        if not alt:
            raise ValueError(f'Image missing alternative text: {path}, {src}')
        if urlparse(src).scheme:
            continue
        target = (path.parent / src.split('?', 1)[0]).resolve()
        if not target.is_file():
            raise ValueError(f'Missing image: {target}')
    for href in parser.links:
        if href.startswith('#'):
            if href[1:] and href[1:] not in parser.ids:
                raise ValueError(f'Broken in-page anchor: {path}, {href}')
            continue
        if urlparse(href).scheme or href.startswith(('mailto:', 'tel:')):
            continue
        local = href.split('#', 1)[0].split('?', 1)[0]
        if not local:
            continue
        target = (path.parent / local).resolve()
        if target.is_dir():
            target /= 'index.html'
        if not target.is_file():
            raise ValueError(f'Broken local link: {path}, {href}')
    return len(parser.images)


def main():
    """Validate the links and local assets in the static website."""
    pages = sorted(SITE.rglob('*.html'))
    assert pages, 'No HTML pages found'
    images = sum(verify_page(page) for page in pages)
    assert (SITE / 'consultants' / 'index.html').is_file()
    assert (SITE / 'assets' / 'jee-logo.png').is_file()
    assert (SITE / 'assets' / 'kjc-logo.png').is_file()
    # Deployment must contain only the re-encoded, opaque consultant portraits.
    photo_dir = SITE / 'assets' / 'consultants'
    for photo in photo_dir.iterdir():
        if not photo.is_file() or photo.name == '.gitkeep':
            continue
        if not re.fullmatch(r'p-[0-9a-f]{32}\.webp', photo.name):
            raise ValueError(f'Non-opaque consultant image filename in public site: {photo.name}')
    print(f'Validated {len(pages)} pages and {images} image references')


if __name__ == '__main__':
    main()
