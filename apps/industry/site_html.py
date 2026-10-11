"""
Cleans what a business owner writes for their website: page text (simple HTML) and their own CSS.
Scripts, event handlers, forms and javascript: links are removed, so a page can never run code on a
visitor's browser or on BookPilot's own domain. Plain text (no tags) is turned into paragraphs.
"""
import re
from html import escape
from html.parser import HTMLParser

ALLOWED = {"p", "br", "hr", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s", "small", "mark", "blockquote",
           "ul", "ol", "li", "a", "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
           "div", "span", "section", "iframe", "code", "pre"}
VOID = {"br", "hr", "img"}
DROP_WITH_CONTENT = {"script", "style", "noscript", "template", "object", "embed", "form", "textarea", "select",
                     "svg", "math", "head", "title"}
ATTRS = {"*": {"class", "style", "title", "id", "dir", "lang"}, "a": {"href", "target", "rel"},
         "img": {"src", "alt", "width", "height", "loading"}, "iframe": {"src", "width", "height", "allowfullscreen", "title"},
         "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}
SAFE_URL = re.compile(r"^(https?://|mailto:|tel:|/|#|\?|[\w.-]+(/|$))", re.I)
EMBEDS = ("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/", "https://player.vimeo.com/video/",
          "https://www.google.com/maps/embed")
BAD_STYLE = re.compile(r"expression|javascript:|behavior|url\s*\(|@import|</", re.I)


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        kept = []
        for name, value in attrs:
            name = name.lower()
            if name not in ATTRS["*"] and name not in ATTRS.get(tag, set()):
                continue
            value = (value or "").strip()
            if name in ("href", "src"):
                compact = re.sub(r"[\s\x00-\x1f]", "", value)
                if not SAFE_URL.match(compact) or compact.lower().startswith(("javascript:", "data:", "vbscript:")):
                    continue
                if tag == "iframe" and not compact.startswith(EMBEDS):
                    return  # only video / map embeds
            if name == "style" and BAD_STYLE.search(value):
                continue
            kept.append(f' {name}="{escape(value, quote=True)}"' if value or name != "allowfullscreen" else f" {name}")
        if tag == "a" and any(a.startswith(' target="_blank"') for a in kept):
            kept.append(' rel="noopener"')
        if tag == "iframe" and not any(a.startswith(" src=") for a in kept):
            return
        self.out.append(f"<{tag}{''.join(kept)}>")
        if tag not in VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.open and self.open[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.open:
            return
        while self.open:  # close anything left open inside it
            last = self.open.pop()
            self.out.append(f"</{last}>")
            if last == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def close(self):
        super().close()
        while self.open:
            self.out.append(f"</{self.open.pop()}>")
        return "".join(self.out)


def clean_html(text):
    text = (text or "").strip()
    if not text:
        return ""
    if "<" not in text:  # plain text: blank lines make paragraphs
        return "".join(f"<p>{escape(p).replace(chr(10), '<br>')}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())
    parser = _Cleaner()
    parser.feed(text)
    return parser.close()


def clean_css(text):
    """The owner's own CSS: nothing that can close the <style> tag, load scripts or pull in other files."""
    text = (text or "").replace("<", "").replace("\\3c", "").replace("\\3C", "")
    text = re.sub(r"@import[^;]*;?", "", text, flags=re.I)
    text = re.sub(r"expression\s*\(|javascript:|behavior\s*:|-moz-binding", "", text, flags=re.I)
    return text[:20000]
