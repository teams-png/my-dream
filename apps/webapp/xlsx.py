"""A tiny Excel (.xlsx) writer with no extra dependencies, for report downloads.

Text is written as inline strings, so a cell that starts with "=" is shown as text
and never runs as a formula (no spreadsheet-formula injection from customer names).
"""
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils.text import slugify

BOLD, MONEY, DATE, TITLE = 1, 2, 3, 4
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


class Bold(str):
    """Wrap a header/total label to show it in bold."""


def _col(n):
    name = ""
    while n:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell(ref, value, bold=False):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = "Yes" if value else "No"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{BOLD if bold else MONEY if isinstance(value, (Decimal, float)) else 0}"><v>{value}</v></c>'
    if isinstance(value, (date, datetime)):
        day = value.date() if isinstance(value, datetime) else value
        serial = (day - date(1899, 12, 30)).days
        return f'<c r="{ref}" s="{DATE}"><v>{serial}</v></c>'
    text = escape(_BAD_XML.sub("", str(value)))[:32000]
    style = BOLD if (bold or isinstance(value, Bold)) else 0
    return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet(rows, header_rows):
    widths = {}
    out = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row, start=1):
            cells.append(_cell(f"{_col(c)}{r}", value, bold=r <= header_rows))
            size = len(str(value)) if value is not None else 0
            widths[c] = min(max(widths.get(c, 8), size + 2), 60)
        out.append(f'<row r="{r}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>' for c, w in sorted(widths.items()))
    pane = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="{0}" topLeftCell="A{1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'.format(
        header_rows, header_rows + 1) if header_rows else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{pane}{"<cols>" + cols + "</cols>" if cols else ""}<sheetData>{"".join(out)}</sheetData></worksheet>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
          '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
          '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
          '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
          '<cellXfs count="5"><xf/><xf fontId="1" applyFont="1"/><xf numFmtId="164" applyNumberFormat="1"/>'
          '<xf numFmtId="14" applyNumberFormat="1"/><xf fontId="1" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def build(sheets):
    """sheets: [(name, rows, header_rows)] -> xlsx bytes."""
    names, used = [], set()
    for name, _rows, _h in sheets:
        clean = re.sub(r"[\[\]:*?/\\]", " ", str(name))[:31].strip() or "Sheet"
        base, i = clean, 2
        while clean.lower() in used:
            clean = f"{base[:28]} {i}"
            i += 1
        used.add(clean.lower())
        names.append(clean)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(sheets) + 1)) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml", STYLES)
        for i, (_name, rows, header_rows) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet(rows, header_rows))
    return buf.getvalue()


def response(filename, sheets):
    """Download response. sheets: [(name, rows)] or [(name, rows, header_rows)]; header_rows defaults to 1."""
    sheets = [s if len(s) == 3 else (s[0], s[1], 1) for s in sheets]
    resp = HttpResponse(build(sheets), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{slugify(filename) or "export"}.xlsx"'
    return resp


def wants(request):
    return request.GET.get("format") == "xlsx"
