"""JSON that is safe to print inside a <script> block with |safe: a name like "</script><script>…"
can't close the tag, because <, > and & are written as unicode escapes (still valid JSON)."""
import json

_ESCAPES = {ord("<"): "\\u003c", ord(">"): "\\u003e", ord("&"): "\\u0026", 0x2028: "\\u2028", 0x2029: "\\u2029"}


def script_json(value, **kwargs):
    return json.dumps(value, **kwargs).translate(_ESCAPES)
