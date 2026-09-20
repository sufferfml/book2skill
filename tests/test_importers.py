"""Import correctness, source locations, failures, and compatibility boundaries."""
import copy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'examples')]
from book2skill import __version__, workflow
from book2skill.source import ingest, inspect, passages, verify_sources
from book2skill.storage import load
from run_demo import config
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def epub_bytes(spine=('second', 'first'), missing=False, encrypted=False, only_images=False, href='text/a%20b.xhtml'):
    first = '<html><head><title>First</title></head><body><h1>第一章</h1><p>甲🙂</p><table><tr><td>A</td><td>B</td></tr></table><p>表后</p><img src="picture.png" alt="画布"/></body></html>'
    second = '<html><head><title>Second</title><style>SECRET STYLE</style></head><body><h1>第二章</h1><p>乙</p><script>SECRET SCRIPT</script></body></html>'
    if only_images:
        first = second = '<html><head><title>Title is not body text</title></head><body><img src="picture.png"/></body></html>'
    package = '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
    package += f'<item id="first" href="{href}" media-type="application/xhtml+xml"/>'
    package += '<item id="second" href="text/z.xhtml" media-type="application/xhtml+xml"/>'
    package += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    package += '</manifest><spine>' + ''.join(f'<itemref idref="{i}"/>' for i in spine) + '</spine></package>'
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OPS/content.opf"/></rootfiles></container>')
        z.writestr('OPS/content.opf', package)
        if not missing:
            z.writestr('OPS/text/a b.xhtml', first)
        z.writestr('OPS/text/z.xhtml', second)
        z.writestr('OPS/nav.xhtml', '<html><body><p>目录</p></body></html>' if not only_images else '<html><body></body></html>')
        z.writestr('OPS/text/picture.png', b'not a real picture; not decoded by this importer')
        if encrypted:
            z.writestr('META-INF/encryption.xml', '<encryption><CipherReference URI="OPS/text/z.xhtml"/></encryption>')
    return stream.getvalue()


def pdf_bytes(pages=('First page', '', 'Third page'), encrypted=False):
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('test-password')
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def write(self, name, data):
        p = self.base / name
        p.write_bytes(data)
        return p

    def test_epub_spine_overrides_manifest_order_and_supplements_are_labelled(self):
        sources, segments, warnings = ingest([self.write('book.epub', epub_bytes())], max_chars=25)
        source = sources[0]
        self.assertLess(source['text'].index('第二章'), source['text'].index('第一章'))
        self.assertLess(source['text'].index('A'), source['text'].index('表后'))
        self.assertNotIn('SECRET', source['text'])
        self.assertIn('[图像未解析：picture.png；替代文字：画布]', source['text'])
        self.assertEqual(source['extraction']['image_assets'], 1)
        self.assertEqual([u['original_location']['role'] for u in source['units']], ['spine', 'spine', 'supplemental'])
        self.assertEqual(source['units'][1]['original_location']['href'], 'OPS/text/a b.xhtml')
        self.assertEqual(segments[0]['original_location']['spine_index'], 1)
        state = {'sources': sources, 'segments': segments}
        verify_sources(state)
        self.assertEqual(''.join(p['text'] for p in passages(state, [s['id'] for s in segments])), source['text'])
        self.assertTrue(any('not OCRed' in w for w in warnings))

    def test_epub_broken_member_does_not_commit_partial_run(self):
        p = self.write('missing.epub', epub_bytes(missing=True))
        with self.assertRaisesRegex(ValueError, 'missing'):
            workflow.initialize(self.base / 'run', [p], config())
        self.assertFalse((self.base / 'run/HEAD.json').exists())

    def test_epub_rejects_bad_spine_encryption_and_root_escape(self):
        for kwargs, message in [({'spine': ('unknown',)}, 'missing manifest'), ({'spine': ()}, 'no reading-order'), ({'encrypted': True}, 'encrypted'), ({'href': '../../escape.xhtml'}, 'escapes'), ({'href': 'https://example.org/book'}, 'local archive')]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                ingest([self.write('broken.epub', epub_bytes(**kwargs))])

    def test_epub_image_only_requires_visual_transcription(self):
        with self.assertRaisesRegex(ValueError, 'no readable body text'):
            ingest([self.write('scan.epub', epub_bytes(only_images=True))])

    def test_pdf_order_page_locators_and_textless_page_survive(self):
        sources, segments, warnings = ingest([self.write('book.pdf', pdf_bytes())], max_chars=20)
        source = sources[0]
        self.assertEqual(source['extraction']['textless_pages'], [2])
        self.assertEqual(source['extraction']['pages'], 3)
        self.assertFalse(source['extraction']['ocr_performed'])
        self.assertLess(source['text'].index('First page'), source['text'].index('Third page'))
        self.assertEqual([u['original_location']['page'] for u in source['units']], [1, 2, 3])
        self.assertIn(2, {s['original_location']['page'] for s in segments})
        verify_sources({'sources': sources, 'segments': segments})
        self.assertTrue(any('blank or scanned' in w for w in warnings))

    def test_pdf_all_textless_and_encrypted_rejected_without_commit(self):
        for kwargs, message in [({'pages': ('', '')}, 'no readable text layer'), ({'encrypted': True}, 'encrypted PDF'), ({'pages': ()}, 'no pages')]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                workflow.initialize(self.base / 'run', [self.write('unreadable.pdf', pdf_bytes(**kwargs))], config())
            self.assertFalse((self.base / 'run/HEAD.json').exists())

    def test_malformed_documents_fail_with_useful_error(self):
        for ext in ('epub', 'pdf'):
            with self.subTest(ext=ext), self.assertRaises(ValueError):
                ingest([self.write('broken.' + ext, b'not a document')])

    def test_mixed_sources_keep_file_order_offsets_and_raw_identity(self):
        paths = [self.write('first.txt', '甲🙂\r\n乙'.encode()), self.write('second.pdf', pdf_bytes()), self.write('third.epub', epub_bytes())]
        workflow.initialize(self.base / 'run', paths, config())
        state = load(self.base / 'run')
        self.assertEqual(state['tool_version'], __version__)
        self.assertEqual([s['extraction']['format'] for s in state['sources']], ['text', 'pdf', 'epub'])
        self.assertEqual(state['sources'][0]['text'], '甲🙂\n乙')
        self.assertTrue(all(c['status'] == 'unread' for c in state['coverage'].values()))
        verify_sources(state)
        # Existing 0.0.1 snapshots have no new metadata and remain valid.
        legacy = copy.deepcopy(state)
        for s in legacy['sources']:
            del s['units']
            del s['extraction']
        verify_sources(legacy)

    def test_location_mismatch_and_cross_unit_segments_detected(self):
        sources, segments, _ = ingest([self.write('book.pdf', pdf_bytes())])
        segments[0]['original_location'] = {'format': 'pdf', 'page': 2}
        with self.assertRaisesRegex(ValueError, 'locator'):
            verify_sources({'sources': sources, 'segments': segments})

    def test_preview_is_read_only_and_excludes_full_text(self):
        path = self.write('book.epub', epub_bytes())
        before = sorted(self.base.iterdir())
        result = inspect([path])
        self.assertEqual(sorted(self.base.iterdir()), before)
        self.assertNotIn('text', result['sources'][0])
        self.assertEqual(result['sources'][0]['extraction']['spine_items'], 2)
        with self.assertRaisesRegex(ValueError, 'positive'):
            ingest([path], max_chars=0)

    def test_cli_exposes_preview_and_file_location(self):
        import os
        result = subprocess.run([sys.executable, '-m', 'book2skill', 'inspect', str(self.write('book.pdf', pdf_bytes()))],
                                capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['sources'][0]['units'][2]['original_location']['page'], 3)


if __name__ == '__main__':
    unittest.main()
