"""Local document import with explicit reading order and source locations.

Text extraction is not OCR or a proof that figures, tables and equations were read.
No network access or dependency installation is performed by these adapters.
"""

from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from .storage import require

MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_EPUB_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif', '.bmp', '.tif', '.tiff'}


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def xml(data, label):
    require(len(data) <= MAX_XML_BYTES, f'{label}: XML exceeds import limit')
    require(not re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', data, re.I), f'{label}: DTD/entities are unsupported')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f'{label}: malformed XML: {exc}') from exc


def member_path(base, href):
    url = urlsplit(href)
    require(not url.scheme and not url.netloc, 'EPUB content must refer to a local archive member')
    decoded = unquote(url.path)
    require(decoded and '\\' not in decoded and not decoded.startswith('/'), 'invalid EPUB member path')
    path = posixpath.normpath(posixpath.join(base, decoded))
    require(path != '..' and not path.startswith('../'), 'EPUB reference escapes archive root')
    return path


class BookHTML(HTMLParser):
    """Preserve heading/block/table order; mark images instead of inventing text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.images = []
        self.title_parts = []
        self.in_title = False
        self.readable = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'title':
            self.in_title = True
            return
        if tag in ('img', 'image'):
            src = attrs.get('src') or attrs.get('href') or attrs.get('xlink:href') or '(unknown)'
            self.images.append(src)
            alt = re.sub(r'\s+', ' ', attrs.get('alt', '')).strip()
            self.parts.append(f'\n[图像未解析：{src}' + (f'；替代文字：{alt}' if alt else '') + ']\n')
        elif re.fullmatch(r'h[1-6]', tag):
            self.parts.append('\n' + '#' * int(tag[1]) + ' ')
        elif tag in ('p', 'div', 'section', 'article', 'blockquote', 'pre', 'table', 'tr'):
            self.parts.append('\n')
        elif tag == 'br':
            self.parts.append('\n')
        elif tag == 'li':
            self.parts.append('\n- ')
        elif tag in ('td', 'th'):
            self.parts.append(' | ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.hidden:
            self.hidden -= 1
            return
        if self.hidden:
            return
        if tag == 'title':
            self.in_title = False
        elif tag in ('p', 'div', 'section', 'article', 'blockquote', 'pre', 'table', 'tr', 'li') or re.fullmatch(r'h[1-6]', tag):
            self.parts.append('\n')

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)
            self.readable.append(data)

    def text(self):
        text = normalize(''.join(self.parts))
        return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', text).strip()


def epub(raw):
    warnings, units = [], []
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(len({x.filename for x in infos}) == len(infos), 'EPUB has duplicate archive member names')
            require(sum(x.file_size for x in infos) <= MAX_EPUB_EXPANDED_BYTES, 'EPUB expanded size exceeds import limit')
            names = {x.filename for x in infos}

            def read(name):
                require(name in names, f'EPUB referenced member is missing: {name}')
                require(archive.getinfo(name).file_size <= MAX_XML_BYTES, f'EPUB text member too large: {name}')
                return archive.read(name)

            container = xml(read('META-INF/container.xml'), 'container.xml')
            roots = [e for e in container.iter() if local_name(e.tag) == 'rootfile']
            require(roots, 'EPUB container has no package document')
            opf_path = member_path('', roots[0].get('full-path', ''))
            opf = xml(read(opf_path), opf_path)
            manifest_nodes = [e for e in opf if local_name(e.tag) == 'manifest']
            spine_nodes = [e for e in opf if local_name(e.tag) == 'spine']
            require(len(manifest_nodes) == len(spine_nodes) == 1, 'EPUB needs one manifest and one spine')
            items = {}
            for e in manifest_nodes[0]:
                if local_name(e.tag) != 'item':
                    continue
                ident = e.get('id')
                require(ident and ident not in items, 'EPUB manifest has missing or duplicate IDs')
                items[ident] = dict(path=member_path(posixpath.dirname(opf_path), e.get('href', '')),
                                    media=e.get('media-type', ''), properties=e.get('properties', ''))
            order = []
            for e in spine_nodes[0]:
                if local_name(e.tag) != 'itemref':
                    continue
                require(e.get('idref') in items, 'EPUB spine refers to a missing manifest ID')
                order.append((e.get('idref'), e.get('linear', 'yes'), 'spine'))
            require(order, 'EPUB has no reading-order spine; refusing to guess chapter order')
            spine_count = len(order)
            selected = {x[0] for x in order}
            supplemental = [ident for ident, item in items.items() if ident not in selected and item['media'] in ('application/xhtml+xml', 'text/html')]
            order.extend((ident, 'no', 'supplemental') for ident in supplemental)
            if supplemental:
                warnings.append(f'{len(supplemental)} non-spine HTML documents appended as explicitly marked supplements')
            encrypted = set()
            if 'META-INF/encryption.xml' in names:
                enc = xml(read('META-INF/encryption.xml'), 'encryption.xml')
                encrypted = {member_path('', e.get('URI', '')) for e in enc.iter() if local_name(e.tag) == 'CipherReference'}
            readable = 0
            for index, (ident, linear, role) in enumerate(order, 1):
                item = items[ident]
                path = item['path']
                require(path not in encrypted, f'EPUB content is encrypted: {path}; provide a readable export')
                require(item['media'] in ('application/xhtml+xml', 'text/html'), f'unsupported EPUB spine media: {item["media"]} ({path})')
                html = BookHTML()
                try:
                    html.feed(read(path).decode('utf-8-sig'))
                    html.close()
                except UnicodeDecodeError as exc:
                    raise ValueError(f'EPUB {path}: expected UTF-8 HTML') from exc
                body = html.text()
                has_text = bool(''.join(html.readable).strip())
                readable += int(has_text)
                if not has_text:
                    warnings.append(f'{path}: no readable body text; inspect cover/figure/scan before excluding')
                title = ''.join(html.title_parts).strip() or path
                units.append(dict(text=(body or '[本单元未提取到可读文字，需要视觉核查。]') + '\n\n',
                                  title=title, location=dict(format='epub', href=path,
                                      spine_index=index if role == 'spine' else None, role=role, linear=linear),
                                  images=html.images, has_readable_text=has_text))
            require(readable, 'EPUB contains no readable body text; OCR or visual transcription is required')
            images = sum(PurePosixPath(n).suffix.lower() in IMAGE_SUFFIXES for n in names)
            if images:
                warnings.append(f'{images} EPUB image assets are not OCRed or visually read; inline images are marked in text')
            warnings.append('EPUB tables preserve cell order, not merged-cell/visual semantics; inspect diagrams and formulas')
            return units, dict(format='epub', parser='stdlib-spine-v1', spine_items=spine_count,
                               supplemental_items=len(supplemental), image_assets=images,
                               needs_visual_review=bool(images) or any(not u['has_readable_text'] for u in units)), warnings
    except (zipfile.BadZipFile, RuntimeError, ET.ParseError) as exc:
        raise ValueError(f'invalid or unreadable EPUB: {exc}') from exc


def pdf(raw):
    try:
        import pypdf
    except ImportError as exc:
        raise ValueError('PDF import requires pypdf==6.10.0; use the complete book2skill skill zipapp or install the project dependencies') from exc
    try:
        reader = pypdf.PdfReader(BytesIO(raw), strict=False)
        require(not reader.is_encrypted, 'encrypted PDF is unsupported; provide an unlocked readable copy')
        require(len(reader.pages) > 0, 'PDF has no pages')
        units, warnings, empty_pages = [], [], []
        for number, page in enumerate(reader.pages, 1):
            # Layout extraction preserves columns/spacing where possible; geometry still needs inspection.
            body = '' if page.get_contents() is None else normalize(
                page.extract_text(extraction_mode='layout', layout_mode_strip_rotated=False) or '').strip()
            has_text = bool(body)
            if not has_text:
                empty_pages.append(number)
            units.append(dict(text=(body or '[本页未提取到可读文字；可能是空白页或扫描页，需要视觉核查/OCR。]') + '\n\n',
                              title=f'PDF文件页 {number}', location=dict(format='pdf', page=number),
                              has_readable_text=has_text))
        require(len(empty_pages) < len(units), 'PDF has no readable text layer; run OCR or supply a text export before import')
        if empty_pages:
            warnings.append(f'PDF pages without readable text: {empty_pages}; may be blank or scanned, inspect/OCR before claiming full coverage')
        warnings.append('PDF page numbers are 1-based file pages, not printed book labels; images are not read and layout/tables/formulas may be incomplete')
        return units, dict(format='pdf', parser=f'pypdf-{pypdf.__version__}-layout', pages=len(units),
                           textless_pages=empty_pages, needs_visual_review=True, ocr_performed=False), warnings
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'PDF extraction failed; no partial import was committed: {type(exc).__name__}: {exc}') from exc


def extract(path, raw):
    require(len(raw) <= MAX_INPUT_BYTES, 'source exceeds 256 MiB import limit; split the source explicitly')
    suffix = path.suffix.lower()
    if suffix == '.epub':
        return epub(raw)
    if suffix == '.pdf':
        return pdf(raw)
    require(suffix in ('.md', '.txt', '.markdown'), 'supported inputs: UTF-8 Markdown/TXT, EPUB and text-layer PDF')
    try:
        text = normalize(raw.decode('utf-8-sig'))
    except UnicodeDecodeError as exc:
        raise ValueError(f'{path.name}: not UTF-8') from exc
    require(text.strip(), f'empty source: {path}')
    return [dict(text=text, title=None, location=None)], dict(format='text', parser='utf8-bom-lf-v1'), []
