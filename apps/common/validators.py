"""
Shared validators for anything a tenant user can upload (expense receipts,
company logos, KYC/product images, ...). Phase 1 Section 27 calls out
"secure file uploads" as a platform-wide requirement — this is the one
place that logic lives, so every FileField/ImageField across the codebase
attaches the same validator instead of re-implementing it per app.
"""
from django.core.exceptions import ValidationError

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# A handful of well-known magic-byte signatures. This catches the common
# "rename a .php/.exe to .pdf" bypass that extension-checking alone misses
# — it does not attempt full content sniffing.
_SIGNATURES = {
    b"%PDF": ".pdf",
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # WEBP is RIFF container; good enough for this check
}


def validate_upload_file(uploaded_file):
    """
    Use as a model field validator: `validators=[validate_upload_file]` on
    a FileField/ImageField. Raises django.core.exceptions.ValidationError
    on anything that fails the extension, size, or magic-byte check.
    """
    import os

    name = uploaded_file.name or ""
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}."
        )

    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(f"File too large — max {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.")

    header = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not any(header.startswith(sig) for sig in _SIGNATURES):
        raise ValidationError("File content does not match its extension.")
