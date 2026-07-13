"""Text-encoding repair for mislabeled pages."""

# Windows-1252 punctuation lives in 0x80–0x9F (curly quotes, en/em dashes, ellipsis).
# Pages served as text/html with no charset are decoded by `requests` as ISO-8859-1,
# which maps those same bytes to C1 control characters (e.g. a curly apostrophe 0x92
# becomes U+0092) — invisible mojibake that also makes YAML front matter unparseable.
# Latin-1 and cp1252 agree above 0x9F, so remapping just this range fully repairs the
# mislabel; on correctly-decoded UTF-8 there are no C1 chars, so it's a no-op.
_CP1252_C1_MAP: dict[int, str | None] = {
    code: bytes([code]).decode("cp1252", "ignore") or None for code in range(0x80, 0xA0)
}


def fix_cp1252_controls(text: str) -> str:
    """Repair Windows-1252 punctuation that arrived mis-decoded as C1 control chars."""
    return text.translate(_CP1252_C1_MAP)
