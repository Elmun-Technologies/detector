"""Dependency-free PDF export.

A minimal but standards-correct PDF writer (xref table, multiple pages,
Helvetica/Helvetica-Bold, WinAnsi text) so report export does not pull a native
rendering stack into the API image.
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from collections.abc import Iterable

PAGE_WIDTH = 595  # A4 at 72dpi
PAGE_HEIGHT = 842
MARGIN = 56
LINE_HEIGHT = 13
BODY_SIZE = 9.5
HEADING_SIZE = 12
TITLE_SIZE = 16
WRAP_COLUMNS = 96

# Characters outside cp1252 (Uzbek turned commas, dashes, quotes) get a safe twin.
TRANSLITERATION = {
    '\u2018': "'", '\u2019': "'", '\u02bb': "'", '\u02bc': "'", '\u02bd': "'",
    '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': '-', '\u2026': '...',
    '\u2022': '-', '\u00a0': ' ', '\u2192': '->', '\u201e': '"', '\u00ab': '"', '\u00bb': '"',
}


def _encode(text: str) -> bytes:
    for source, target in TRANSLITERATION.items():
        text = text.replace(source, target)
    return text.encode('cp1252', errors='replace')


def _escape(text: str) -> bytes:
    payload = _encode(text)
    return payload.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


class _Page:
    def __init__(self) -> None:
        self.commands: list[bytes] = []
        self.cursor = PAGE_HEIGHT - MARGIN

    def has_room(self, needed: int = LINE_HEIGHT) -> bool:
        return self.cursor - needed > MARGIN

    def write(self, text: str, size: float, bold: bool = False, indent: int = 0) -> None:
        font = b'/F2' if bold else b'/F1'
        self.commands.append(
            b'BT ' + font + b' ' + f'{size:.1f}'.encode() + b' Tf '
            + f'{MARGIN + indent} {self.cursor:.1f}'.encode() + b' Td ('
            + _escape(text) + b') Tj ET'
        )
        self.cursor -= LINE_HEIGHT

    def space(self, amount: int = 6) -> None:
        self.cursor -= amount

    def stream(self) -> bytes:
        return b'\n'.join(self.commands)


class PdfDocument:
    def __init__(self, title: str) -> None:
        self.title = title
        self.pages: list[_Page] = [_Page()]

    @property
    def page(self) -> _Page:
        return self.pages[-1]

    def _new_page(self) -> _Page:
        self.pages.append(_Page())
        return self.page

    def line(self, text: str, size: float = BODY_SIZE, bold: bool = False, indent: int = 0) -> None:
        page = self.page
        if not page.has_room():
            page = self._new_page()
        page.write(text, size, bold, indent)

    def paragraph(self, text: str, size: float = BODY_SIZE, bold: bool = False, indent: int = 0) -> None:
        for chunk in textwrap.wrap(text, WRAP_COLUMNS) or ['']:
            self.line(chunk, size, bold, indent)

    def heading(self, text: str) -> None:
        self.page.space(6)
        self.line(text, HEADING_SIZE, bold=True)

    def bullets(self, items: Iterable[str]) -> None:
        for item in items:
            wrapped = textwrap.wrap(str(item), WRAP_COLUMNS - 4) or ['']
            self.line(f'- {wrapped[0]}', indent=8)
            for extra in wrapped[1:]:
                self.line(f'  {extra}', indent=8)

    def build(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
        font_bold = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')

        pages_id = len(objects) + 1 + len(self.pages) * 2  # reserved below
        page_ids: list[int] = []
        for page in self.pages:
            stream = page.stream()
            content_id = add(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
            page_id = add(
                b'<< /Type /Page /Parent ' + str(pages_id).encode()
                + b' /MediaBox [0 0 ' + f'{PAGE_WIDTH} {PAGE_HEIGHT}'.encode() + b']'
                + b' /Resources << /Font << /F1 ' + str(font_regular).encode() + b' 0 R /F2 '
                + str(font_bold).encode() + b' 0 R >> >>'
                + b' /Contents ' + str(content_id).encode() + b' 0 R >>'
            )
            page_ids.append(page_id)

        kids = b' '.join(f'{pid} 0 R'.encode() for pid in page_ids)
        actual_pages_id = add(b'<< /Type /Pages /Count ' + str(len(page_ids)).encode() + b' /Kids [' + kids + b'] >>')
        # Fix up the parent reference if the reservation drifted.
        if actual_pages_id != pages_id:
            for page_id in page_ids:
                objects[page_id - 1] = objects[page_id - 1].replace(
                    b'/Parent ' + str(pages_id).encode(), b'/Parent ' + str(actual_pages_id).encode()
                )
        info_id = add(
            b'<< /Title (' + _escape(self.title) + b') /Producer (Viral Video AI) /CreationDate (D:'
            + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%SZ').encode() + b') >>'
        )
        catalog_id = add(b'<< /Type /Catalog /Pages ' + str(actual_pages_id).encode() + b' 0 R >>')

        out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets: list[int] = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += str(number).encode() + b' 0 obj\n' + body + b'\nendobj\n'
        xref_position = len(out)
        out += b'xref\n0 ' + str(len(objects) + 1).encode() + b'\n0000000000 65535 f \n'
        for offset in offsets:
            out += f'{offset:010d} 00000 n \n'.encode()
        out += (
            b'trailer\n<< /Size ' + str(len(objects) + 1).encode()
            + b' /Root ' + str(catalog_id).encode() + b' 0 R /Info ' + str(info_id).encode() + b' 0 R >>\n'
            b'startxref\n' + str(xref_position).encode() + b'\n%%EOF\n'
        )
        return bytes(out)


def render_report_pdf(video_name: str, status: str, report: dict | None, *, workspace: str | None = None) -> bytes:
    """Render the persisted report dictionary into a multi-section PDF."""
    document = PdfDocument(f'Viral Video AI report — {video_name}')
    document.line(f'Viral Video AI — {video_name}', TITLE_SIZE, bold=True)
    document.line(f'Status: {status} | Yaratildi: {datetime.now(timezone.utc).isoformat(timespec="seconds")}')
    if workspace:
        document.line(f'Workspace: {workspace}')

    if not report:
        document.heading('Hisobot mavjud emas')
        document.paragraph('Tahlil hali yakunlanmagan yoki hisobot saqlanmagan.')
        return document.build()

    scores = report.get('scores') or {}
    document.heading('Ballar')
    document.paragraph(
        'Viral score: {viral} | Hook: {hook} | Retention: {retention} | Visual: {visual} | Audio: {audio}'.format(
            viral=scores.get('viral_score'), hook=scores.get('hook_score'), retention=scores.get('retention_score'),
            visual=scores.get('visual_score'), audio=scores.get('audio_score'),
        )
    )
    document.paragraph(
        'Share: {share} | Save: {save} | Rewatch: {rewatch} | Clarity: {clarity} | CTA: {cta} | Ishonch: {confidence}'.format(
            share=scores.get('share_score'), save=scores.get('save_score'), rewatch=scores.get('rewatch_score'),
            clarity=scores.get('clarity_score'), cta=scores.get('cta_score'), confidence=scores.get('confidence'),
        )
    )

    document.heading('Xulosa')
    document.paragraph(str(report.get('short_summary', '')))

    media = report.get('media') or {}
    if media.get('analysed'):
        document.heading('Media o‘lchovlari')
        document.paragraph(
            'Davomiylik: {duration}s | O‘lcham: {width}x{height} ({ratio}) | Kodek: {codec} | '
            'Audio: {audio} | Sahna o‘zgarishi: {scenes} | Jimlik: {silence}s'.format(
                duration=media.get('duration_seconds'), width=media.get('width'), height=media.get('height'),
                ratio=media.get('aspect_ratio'), codec=media.get('video_codec'),
                audio=media.get('audio_codec') or 'yo‘q', scenes=media.get('scene_change_count'),
                silence=media.get('silence_seconds'),
            )
        )

    prediction = report.get('prediction') or {}
    if prediction:
        document.heading('Prognoz oralig‘i')
        if prediction.get('basis') == 'account_history':
            document.paragraph(
                f"Past: {prediction.get('low_views')} | Kutilayotgan: {prediction.get('expected_views')} | "
                f"Yuqori: {prediction.get('high_views')} (ishonch: {prediction.get('confidence')})"
            )
        document.paragraph(str(prediction.get('note', '')))

    for heading, key in (
        ('Majburiy o‘zgarishlar', 'required_changes'),
        ('Yaxshilangan hooklar', 'improved_hooks'),
        ('Ssenariy', 'improved_script'),
        ('Montajchi uchun brief', 'editor_brief'),
    ):
        items = report.get(key) or []
        if items:
            document.heading(heading)
            document.bullets(items)

    if report.get('improved_cta'):
        document.heading('CTA')
        document.paragraph(str(report['improved_cta']))

    segments = report.get('segments') or []
    if segments:
        document.heading('Segmentlar')
        for segment in segments:
            document.paragraph(
                f"{segment.get('start_time')}–{segment.get('end_time')}s {segment.get('title')} "
                f"[{segment.get('state')}] {segment.get('retention_probability')}%"
            )
            document.paragraph(f"  {segment.get('recommendation', '')}", indent=8)

    timeline = report.get('timeline') or []
    if timeline:
        document.heading('Soniya-soniya timeline')
        for entry in timeline[:120]:
            flags = []
            if entry.get('scene_change'):
                flags.append('sahna')
            if entry.get('silence'):
                flags.append('jimlik')
            if entry.get('speech'):
                flags.append('nutq')
            document.line(
                f"{entry.get('second'):>3}s  {entry.get('label'):<8} {entry.get('retention_probability'):>3}%  "
                f"{', '.join(flags)}",
                indent=8,
            )

    evidence = report.get('evidence') or []
    if evidence:
        document.heading('Dalil va manbalar')
        for item in evidence:
            document.paragraph(f"[{item.get('kind')}] {item.get('label')}: {item.get('detail')}")
            for source in item.get('citations') or []:
                document.paragraph(
                    f"    manba: {source.get('title')} — {source.get('url')} "
                    f"({source.get('published_on') or 'sana yo‘q'})",
                    indent=8,
                )

    usage = report.get('usage') or {}
    if usage.get('calls'):
        document.heading('Provayder sarfi')
        document.paragraph(
            f"Chaqiruvlar: {len(usage['calls'])} | Tokenlar: {usage.get('total_tokens')} | "
            f"Taxminiy narx: ${usage.get('total_cost_usd')}"
        )

    document.heading('Ogohlantirish')
    document.paragraph(str(report.get('disclaimer', '')))
    return document.build()
