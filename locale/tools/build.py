"""
Builds locale/<lang>/LC_MESSAGES/django.po and .mo from the translation
dictionaries in this folder, using the {% translate %} strings found in the
templates. Run after changing template text:  python locale/tools/build.py
(needs `pip install polib`; the compiled .mo files are committed).
"""
import pathlib
import re
import sys

import polib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ar import AR  # noqa: E402
from ml import ML  # noqa: E402

PATTERN = re.compile(r"{%\s*translate\s+([\"'])(.*?)\1\s*%}")
PY_PATTERN = re.compile(r"""\b_\(\s*(["'])(.+?)\1\s*\)""")


def msgids():
    found = {}
    for path in sorted((ROOT / "templates").rglob("*.html")):
        for match in PATTERN.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(match.group(2), str(path.relative_to(ROOT)))
    for path in sorted((ROOT / "apps").rglob("*.py")):
        if "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "gettext" not in text:
            continue
        for match in PY_PATTERN.finditer(text):
            found.setdefault(match.group(2), str(path.relative_to(ROOT)))
    # per-business-type words shown through {% translate variable %}
    catalog = (ROOT / "apps" / "modules" / "catalog.py").read_text(encoding="utf-8")
    for block in re.findall(r"(?:BOOKING|EDUCATION)_TERMS = \{(.*?)\n\}", catalog, re.S):
        for words in re.findall(r"\((\".*?)\)", block):
            for word in re.findall(r"\"([^\"]+)\"", words):
                found.setdefault(word, "apps/modules/catalog.py")
    return found


def build(lang, table, plural):
    ids = msgids()
    po = polib.POFile()
    po.metadata = {"Content-Type": "text/plain; charset=UTF-8", "Language": lang, "Plural-Forms": plural}
    missing = []
    for msgid, source in ids.items():
        msgstr = table.get(msgid, "")
        if not msgstr:
            missing.append(msgid)
        po.append(polib.POEntry(msgid=msgid, msgstr=msgstr, occurrences=[(source, "")]))
    out = ROOT / "locale" / lang / "LC_MESSAGES"
    out.mkdir(parents=True, exist_ok=True)
    po.save(str(out / "django.po"))
    po.save_as_mofile(str(out / "django.mo"))
    print(f"{lang}: {len(ids) - len(missing)}/{len(ids)} translated")
    return missing


if __name__ == "__main__":
    build("ar", AR, "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;")
    build("ml", ML, "nplurals=2; plural=(n != 1);")
