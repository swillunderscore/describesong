"""Facts stated in a search, pulled out without a model: years and decades,
instrumental / vocals, and nationality words. Microseconds, no guessing —
it only ever copies what the text says. (The Pi's 1.5B Qwen did this
correctly but took ~90 s per query on this CPU; a search cannot wait.)"""
import re
DECADES = {"fifties": 1950, "sixties": 1960, "seventies": 1970, "eighties": 1980, "nineties": 1990, "noughties": 2000, "two thousands": 2000}
import places as _places
# Demonyms ("norwegian") match in free text; place words ("scandinavian",
# "western", "spanish-speaking") too; country NAMES only as a field value
# ("from norway", "country is norway") — see places.py for why.
COUNTRIES = {k: v for k, v in _places.DEMONYMS.items()}
PLACES = _places.PLACES
REGIONS = PLACES
_LONGEST = lambda d: sorted(d, key=len, reverse=True)
_FROM_RE = re.compile(r"(?<![\w])from ((?:the )?(?:" + "|".join(re.escape(n) for n in _LONGEST([x for x in list(_places.NAMES) + list(_places.PLACE_NAMES) if not x.startswith("the ")])) + r"))(?![\w])")
def place(value):
    """the value of a place field -> set of country codes, or None: a name, a demonym or a place word"""
    p = parse(value)["country"]
    return p or _places.place(value)


def parse(q):
    """-> dict(year_from, year_to, instrumental, vocals, country) with None where the text says nothing. Also `stripped`: the query without those words."""
    ql = " " + q.lower() + " "; out = {"year_from": None, "year_to": None, "instrumental": None, "vocals": None, "country": None}; strip = []
    m = re.search(r"\b(early|mid|late)?\s*-?\s*(19[5-9]0|20[0-2]0)s\b", ql)                       # 1990s / early 2000s / mid-80s handled below
    if m:
        d = int(m.group(2)); a, b = d, d + 9
        if m.group(1) == "early": b = d + 4
        elif m.group(1) == "late": a = d + 5
        elif m.group(1) == "mid": a, b = d + 3, d + 6
        out["year_from"], out["year_to"] = a, b; strip.append(m.group(0))
    m = re.search(r"\b(early|mid|late)?\s*-?\s*'?([5-9]0|00|10|20)s\b", ql) if not m else None                # 80s / '90s / mid 90s
    if m:
        two = int(m.group(2)); d = (1900 if two >= 50 else 2000) + two; a, b = d, d + 9
        if m.group(1) == "early": b = d + 4
        elif m.group(1) == "late": a = d + 5
        elif m.group(1) == "mid": a, b = d + 3, d + 6
        out["year_from"], out["year_to"] = a, b; strip.append(m.group(0))
    for word, d in DECADES.items():
        m = re.search(r"\b(early|mid|late)?\s*" + word + r"\b", ql)
        if m and out["year_from"] is None:
            a, b = d, d + 9
            if m.group(1) == "early": b = d + 4
            elif m.group(1) == "late": a = d + 5
            elif m.group(1) == "mid": a, b = d + 3, d + 6
            out["year_from"], out["year_to"] = a, b; strip.append(m.group(0))
    m = re.search(r"\b(around|about|circa|from|in)?\s*(19[5-9]\d|20[0-2]\d)\b", ql)                        # a year: ±2 (people misremember)
    if m and out["year_from"] is None:
        y = int(m.group(2)); out["year_from"], out["year_to"] = y - 2, y + 2; strip.append(m.group(0))
    if re.search(r"\binstrumental\b|\bno vocals?\b|\bwithout vocals?\b|\bno singing\b|\bno lyrics\b", ql): out["instrumental"] = True; strip += re.findall(r"\binstrumental\b|\bno vocals?\b|\bwithout vocals?\b|\bno singing\b|\bno lyrics\b", ql)
    if re.search(r"\b(female|woman|girl|women)\b.{0,12}\b(vocal|vocals|singer|singing|voice|rapper)\b|\b(she|her) (sings|raps)\b", ql): out["vocals"] = "female"
    elif re.search(r"\b(male|man|guy|men|dude)\b.{0,12}\b(vocal|vocals|singer|singing|voice|rapper)\b|\b(he|his) (sings|raps)\b", ql): out["vocals"] = "male"
    for word in _LONGEST(COUNTRIES):                      # longest first: "south african" before "african"
        if re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", ql): out["country"] = frozenset([COUNTRIES[word]]); strip.append(word); break
    if not out["country"]:
        m = _FROM_RE.search(ql)
        if m: out["country"] = _places.place(m.group(1)); strip.append(m.group(0).strip())
    if not out["country"]:
        for word in _LONGEST(PLACES):
            if re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", ql): out["country"] = PLACES[word]; strip.append(word); break
    s = ql
    for w in strip: s = s.replace(w, " ")
    out["stripped"] = re.sub(r"\s+", " ", re.sub(r"\b(from|around|about|circa|by a|by an|in the)\s*$", "", s)).strip(" ,")
    return out

import unicodedata as _ud
def script_of(text):
    """Dominant writing system of a name: latin, cyrillic, greek, cjk, kana, hangul, arabic, hebrew, thai, devanagari — or None."""
    counts = {}
    for ch in text or "":
        if not ch.isalpha(): continue
        try: name = _ud.name(ch)
        except ValueError: continue
        for key, tag in (("CJK", "cjk"), ("HIRAGANA", "kana"), ("KATAKANA", "kana"), ("HANGUL", "hangul"), ("CYRILLIC", "cyrillic"), ("GREEK", "greek"), ("ARABIC", "arabic"), ("HEBREW", "hebrew"), ("THAI", "thai"), ("DEVANAGARI", "devanagari"), ("LATIN", "latin")):
            if name.startswith(key): counts[tag] = counts.get(tag, 0) + 1; break
    return max(counts, key=counts.get) if counts else None
# letters that only some languages use: a weak hint, used only when the artist's country is unknown
_LETTER_HINTS = {"ø": ["NO", "DK"], "å": ["NO", "DK", "SE"], "æ": ["NO", "DK", "IS"], "ö": ["SE", "FI", "DE", "TR", "IS"], "ä": ["SE", "FI", "DE"], "ü": ["DE", "TR"], "ß": ["DE"], "ð": ["IS"], "þ": ["IS"],
  "ñ": ["ES", "MX", "AR", "CO"], "ã": ["PT", "BR"], "ç": ["PT", "BR", "FR", "TR"], "õ": ["PT", "BR", "EE"], "ł": ["PL"], "ż": ["PL"], "ś": ["PL"], "ę": ["PL"], "ą": ["PL"], "ř": ["CZ"], "ě": ["CZ"], "ů": ["CZ"], "ő": ["HU"], "ű": ["HU"], "ı": ["TR"], "ş": ["TR", "RO"], "ğ": ["TR"], "ț": ["RO"], "ș": ["RO"], "ħ": ["MT"], "ĳ": ["NL"]}
SCRIPT_COUNTRIES = {"JP": "kana", "KR": "hangul", "CN": "cjk", "TW": "cjk", "RU": "cyrillic", "UA": "cyrillic", "BG": "cyrillic", "RS": "cyrillic", "GR": "greek", "IL": "hebrew", "TH": "thai", "IN": "devanagari", "EG": "arabic", "SA": "arabic", "MA": "arabic", "IR": "arabic"}
def lang_hints(text):
    out = []
    for ch in (text or "").lower():
        for c in _LETTER_HINTS.get(ch, []):
            if c not in out: out.append(c)
    return out
FIELDS = ("artist", "band", "singer", "by", "title", "song", "album", "year", "country", "from", "lyrics", "lyric", "words", "sound", "sounds")
_FIELD_RE = re.compile(r"(?<![\w])(" + "|".join(FIELDS) + r")\s*:\s*", re.I)
_IS_RE = re.compile(r"(?<![\w])(?:the\s+)?(artist|band|singer|title|song|album|year|country|lyrics|lyric|words)\s+is\s+", re.I)
def parse_fields(q):
    """'beepy synth artist: röyksopp year: 2001 lyrics: "up all night"' ->
    {'artist': 'röyksopp', 'year': '2001', 'lyrics': 'up all night', 'free': 'beepy synth'}.
    Precision on demand: anything labelled is matched as that thing, the rest is the sound."""
    q = _IS_RE.sub(lambda m: m.group(1) + ": ", q)          # "artist is kendrick" is "artist: kendrick"
    parts = _FIELD_RE.split(q); out = {"free": parts[0].strip(" ,;")}
    for i in range(1, len(parts) - 1, 2):
        k = parts[i].lower(); raw = parts[i + 1]
        # a value is the quoted phrase if it starts with a quote, else up to the first comma; the rest is free text
        m = re.match(r'\s*["“]([^"”]+)["”]\s*(.*)$', raw, re.S) or re.match(r"\s*([^,;]+)[,;]?\s*(.*)$", raw, re.S)
        v, rest = (m.group(1).strip(), m.group(2).strip(" ,;")) if m else (raw.strip(), "")
        k = {"by": "artist", "band": "artist", "singer": "artist", "song": "title", "lyric": "lyrics", "words": "lyrics", "sounds": "sound"}.get(k, k)
        if k == "from": k = "year" if re.search(r"\d{2}", v) or any(w in v.lower() for w in DECADES) else "country"
        if k == "sound": out["free"] = (out["free"] + " " + v).strip()
        elif v: out[k] = v
        if rest: out["free"] = (out["free"] + " " + rest).strip()
    return out

_NEG_RE = re.compile(r"\b(?:but\s+)?(?:not|no|without|minus|except|nothing like|unlike)\s+(?:a |an |the |any )?([\w'-]+(?:\s+[\w'-]+){0,3}?)(?=\s*(?:,|;|\.|$|\s+(?:and|but|with|just|more)\b))", re.I)
def strip_negations(text):
    """The sound model has no idea what 'not' means: 'not microwave beepy' pulls in
    microwaves. Negated phrases are dropped from the sound query (kept nowhere)."""
    return re.sub(r"\s{2,}", " ", _NEG_RE.sub("", text)).strip(" ,;")

if __name__ == "__main__":
    for q in ["plucky staccato beepy hip hop ish beat with synths, early 2000s, norwegian duo, no vocals", "laid back nineties rap with a jazzy sample and a relaxed male rapper", "female singer, acoustic guitar, whistling in the intro, around 2010",
              "hard electro house with a massive bass drop from around 2012", "something sad on piano", "mid 80s synth pop, she sings the chorus", "instrumental trip hop from 2001 with a bouncy synth riff", "late '70s disco with strings"]:
        print(q, "\n   ->", parse(q))
    for q in ['beepy synth artist: röyksopp year: 2001', 'title: chicago', 'lyrics: "up all night" female vocals from: norway', 'by: daft punk album: discovery, funky', 'beepy but not microwave beepy, retro sci-fi bleeps', 'no vocals, just piano, without drums']:
        f = parse_fields(q); print(q, "\n   fields ->", f, "| free after negations:", repr(strip_negations(f["free"])))
