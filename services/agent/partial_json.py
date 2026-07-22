"""
Pull a string field out of JSON that is still arriving.

Why this exists: the per-turn call returns structured output, but waiting for
the closing brace before speaking costs ~1.2s of dead air on a live call.
`reply` is the first field in the schema, so it completes long before the rest
of the object. Extracting it incrementally lets TTS start on sentence one while
the model is still emitting `sentiment` and `next_action`.

Deliberately not a JSON parser. It finds one known key and decodes its string
value, which is all the hot path needs.
"""
from __future__ import annotations

# Order matters for the two-character escapes; \\ must resolve before \".
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b",
            "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def extract_string_prefix(buf: str, key: str) -> str:
    """
    Return as much of `buf`'s `key` string value as has arrived.

    Returns "" if the key or its opening quote has not appeared yet. Handles
    backslash escapes, and never returns a partial escape sequence — a trailing
    lone backslash or a truncated \\uXXXX is withheld until it completes, so the
    caller never sees a broken character.
    """
    marker = f'"{key}"'
    i = buf.find(marker)
    if i == -1:
        return ""

    # Skip past the key, its colon and any whitespace, to the opening quote.
    j = i + len(marker)
    while j < len(buf) and buf[j] in " \t\r\n":
        j += 1
    if j >= len(buf) or buf[j] != ":":
        return ""
    j += 1
    while j < len(buf) and buf[j] in " \t\r\n":
        j += 1
    if j >= len(buf) or buf[j] != '"':
        return ""
    j += 1

    out: list[str] = []
    while j < len(buf):
        ch = buf[j]
        if ch == '"':
            break                      # value complete
        if ch != "\\":
            out.append(ch)
            j += 1
            continue

        # Escape sequence — withhold it entirely if it hasn't fully arrived.
        if j + 1 >= len(buf):
            break
        esc = buf[j + 1]
        if esc == "u":
            if j + 6 > len(buf):
                break                  # \uXXXX still in flight
            try:
                out.append(chr(int(buf[j + 2:j + 6], 16)))
            except ValueError:
                break
            j += 6
        elif esc in _ESCAPES:
            out.append(_ESCAPES[esc])
            j += 2
        else:
            break                      # unknown escape: stop rather than guess
    return "".join(out)


def extract_complete_string(buf: str, key: str) -> str | None:
    """
    Return `key`'s value only once its closing quote has arrived, else None.

    `extract_string_prefix` is right for `reply`, where speaking a prefix early
    is the whole point. It is wrong for the delivery fields: acting on a partial
    "empathetic" the moment it reads "emp" would set a bogus emotion. These are
    short enums, so waiting for the terminator costs nothing.
    """
    marker = f'"{key}"'
    i = buf.find(marker)
    if i == -1:
        return None

    j = i + len(marker)
    while j < len(buf) and buf[j] in " \t\r\n":
        j += 1
    if j >= len(buf) or buf[j] != ":":
        return None
    j += 1
    while j < len(buf) and buf[j] in " \t\r\n":
        j += 1
    if j >= len(buf) or buf[j] != '"':
        return None

    end = buf.find('"', j + 1)
    if end == -1:
        return None                     # value still arriving
    return buf[j + 1:end]


# Sentence enders. A phone reply is short, so a simple rule beats a tokenizer.
_ENDERS = ".?!"

# Abbreviations whose trailing period is not a sentence end. Only the ones that
# realistically show up in a sales script — this is not meant to be exhaustive,
# and a miss costs a slightly early TTS chunk, not a wrong word.
_ABBREV = frozenset({
    "e.g.", "i.e.", "etc.", "vs.", "approx.", "no.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.",
    "inc.", "ltd.", "co.", "corp.", "dept.", "est.",
    "a.m.", "p.m.", "u.s.", "u.k.",
})
_MAX_ABBREV_LEN = max(len(a) for a in _ABBREV)


def _ends_with_abbreviation(text: str, dot_index: int) -> bool:
    """True if the period at `dot_index` closes a known abbreviation."""
    start = max(0, dot_index - _MAX_ABBREV_LEN + 1)
    tail = text[start:dot_index + 1].lower()
    # Compare against the last whitespace-delimited token, so "(e.g." matches too.
    token = tail.rsplit(" ", 1)[-1].lstrip("([\"'")
    return any(token.endswith(a) for a in _ABBREV)


def complete_sentences(text: str, already_emitted: int) -> tuple[list[str], int]:
    """
    Split off whole sentences past `already_emitted`.

    Returns the new sentences and the updated offset. A trailing fragment is
    withheld until its terminator arrives, so TTS never speaks half a clause.
    """
    out: list[str] = []
    cursor = already_emitted
    i = already_emitted

    while i < len(text):
        if text[i] in _ENDERS:
            if text[i] == ".":
                # "$4.99" — a digit straight after the dot means it's a decimal.
                nxt = text[i + 1] if i + 1 < len(text) else " "
                if nxt.isdigit() or nxt.isalpha():
                    i += 1
                    continue
                # "e.g. HubSpot" — space after the dot, but still mid-abbreviation.
                if _ends_with_abbreviation(text, i):
                    i += 1
                    continue
            sentence = text[cursor:i + 1].strip()
            if sentence:
                out.append(sentence)
            cursor = i + 1
        i += 1

    return out, cursor


def flush_remainder(text: str, already_emitted: int) -> str:
    """Whatever is left once the stream ends without a final terminator."""
    return text[already_emitted:].strip()
