"""Places, as people say them. A country is a code; a place word is a SET of
codes: "scandinavian", "western", "spanish-speaking", "west african". The
table below is the only thing to edit. Every group word is derived from it,
so a country added here joins every group it belongs to.

Columns: code | name (and aliases) | demonyms | continent | sub-region | languages | extra groups
Sub-regions: EU-N nordic, EU-B baltic, EU-W western Europe, EU-C central Europe,
EU-S southern Europe, EU-E eastern Europe, EU-BK Balkans; AS-E east Asia,
AS-SE south-east Asia, AS-S south Asia, AS-C central Asia, AS-W middle east;
AF-N, AF-W, AF-E, AF-C, AF-S; NA northern America, CA central America,
CB Caribbean, SA south America; OC Oceania.
"""
_T = """
US|united states,usa,u.s.,u.s.a.,america,the states|american|AM|NA|en|western
CA|canada|canadian|AM|NA|en,fr|western
MX|mexico|mexican|AM|LA|es|
GT|guatemala|guatemalan|AM|CA|es|
BZ|belize|belizean|AM|CA|en|
HN|honduras|honduran|AM|CA|es|
SV|el salvador|salvadoran,salvadorian|AM|CA|es|
NI|nicaragua|nicaraguan|AM|CA|es|
CR|costa rica|costa rican|AM|CA|es|
PA|panama|panamanian|AM|CA|es|
CU|cuba|cuban|AM|CB|es|
JM|jamaica|jamaican|AM|CB|en|
HT|haiti|haitian|AM|CB|fr|
DO|dominican republic|dominican|AM|CB|es|
PR|puerto rico|puerto rican,boricua|AM|CB|es,en|
TT|trinidad and tobago,trinidad|trinidadian,trini|AM|CB|en|
BB|barbados|barbadian,bajan|AM|CB|en|
BS|bahamas,the bahamas|bahamian|AM|CB|en|
BR|brazil|brazilian|AM|SA|pt|
AR|argentina|argentinian,argentine|AM|SA|es|
CL|chile|chilean|AM|SA|es|
CO|colombia|colombian|AM|SA|es|
PE|peru|peruvian|AM|SA|es|
VE|venezuela|venezuelan|AM|SA|es|
UY|uruguay|uruguayan|AM|SA|es|
PY|paraguay|paraguayan|AM|SA|es|
BO|bolivia|bolivian|AM|SA|es|
EC|ecuador|ecuadorian|AM|SA|es|
GY|guyana|guyanese|AM|SA|en|
SR|suriname|surinamese|AM|SA|nl|
GB|united kingdom,uk,u.k.,britain,great britain,england,scotland,wales|british,english,scottish,welsh,brit|EU|EU-W|en|western,british-isles
IE|ireland|irish|EU|EU-W|en|western,british-isles
FR|france|french|EU|EU-W|fr|western,mediterranean
BE|belgium|belgian|EU|EU-W|nl,fr|western,benelux
NL|netherlands,the netherlands,holland|dutch|EU|EU-W|nl|western,benelux
LU|luxembourg|luxembourgish|EU|EU-W|fr,de|western,benelux
DE|germany|german|EU|EU-C|de|western
AT|austria|austrian|EU|EU-C|de|western
CH|switzerland|swiss|EU|EU-C|de,fr,it|western
LI|liechtenstein|liechtensteiner|EU|EU-C|de|western
PL|poland|polish|EU|EU-C|pl|
CZ|czechia,czech republic|czech|EU|EU-C|cs|
SK|slovakia|slovak,slovakian|EU|EU-C|sk|
HU|hungary|hungarian|EU|EU-C|hu|
SI|slovenia|slovenian,slovene|EU|EU-BK|sl|yugoslav
HR|croatia|croatian|EU|EU-BK|hr|yugoslav,mediterranean
BA|bosnia and herzegovina,bosnia|bosnian|EU|EU-BK|bs|yugoslav
RS|serbia|serbian|EU|EU-BK|sr|yugoslav
ME|montenegro|montenegrin|EU|EU-BK|sr|yugoslav,mediterranean
MK|north macedonia,macedonia|macedonian|EU|EU-BK|mk|yugoslav
XK|kosovo|kosovar|EU|EU-BK|sq|yugoslav
AL|albania|albanian|EU|EU-BK|sq|mediterranean
BG|bulgaria|bulgarian|EU|EU-BK|bg|
RO|romania|romanian|EU|EU-E|ro|
MD|moldova|moldovan|EU|EU-E|ro|soviet
UA|ukraine|ukrainian|EU|EU-E|uk|soviet
BY|belarus|belarusian|EU|EU-E|be,ru|soviet
RU|russia|russian|EU|EU-E|ru|soviet
GR|greece|greek|EU|EU-S|el|western,mediterranean
IT|italy|italian|EU|EU-S|it|western,mediterranean
SM|san marino|sammarinese|EU|EU-S|it|western
MT|malta|maltese|EU|EU-S|mt,en|western,mediterranean
ES|spain|spanish|EU|EU-S|es|western,iberian,mediterranean
PT|portugal|portuguese|EU|EU-S|pt|western,iberian
AD|andorra|andorran|EU|EU-S|ca|western,iberian
CY|cyprus|cypriot|EU|EU-S|el|mediterranean
NO|norway|norwegian|EU|EU-N|no|western,nordic,scandinavian
SE|sweden|swedish,swede|EU|EU-N|sv|western,nordic,scandinavian
DK|denmark|danish,dane|EU|EU-N|da|western,nordic,scandinavian
FI|finland|finnish,finn|EU|EU-N|fi,sv|western,nordic,scandinavian
IS|iceland|icelandic,icelander|EU|EU-N|is|western,nordic,scandinavian
FO|faroe islands,faroes|faroese|EU|EU-N|fo|nordic,scandinavian
GL|greenland|greenlandic|EU|EU-N|kl,da|nordic
EE|estonia|estonian|EU|EU-B|et|soviet
LV|latvia|latvian|EU|EU-B|lv|soviet
LT|lithuania|lithuanian|EU|EU-B|lt|soviet
JP|japan|japanese|AS|AS-E|ja|
KR|south korea,korea|korean,south korean|AS|AS-E|ko|
KP|north korea|north korean|AS|AS-E|ko|
CN|china|chinese|AS|AS-E|zh|
TW|taiwan|taiwanese|AS|AS-E|zh|
HK|hong kong|hongkonger,hong konger|AS|AS-E|zh,en|
MO|macau,macao|macanese|AS|AS-E|zh|
MN|mongolia|mongolian|AS|AS-E|mn|
TH|thailand|thai|AS|AS-SE|th|
VN|vietnam,viet nam|vietnamese|AS|AS-SE|vi|
ID|indonesia|indonesian|AS|AS-SE|id|
PH|philippines,the philippines|filipino,filipina,philippine|AS|AS-SE|tl,en|
MY|malaysia|malaysian|AS|AS-SE|ms|
SG|singapore|singaporean|AS|AS-SE|en,zh,ms|
MM|myanmar,burma|burmese|AS|AS-SE|my|
KH|cambodia|cambodian,khmer|AS|AS-SE|km|
LA|laos|laotian,lao|AS|AS-SE|lo|
BN|brunei|bruneian|AS|AS-SE|ms|
TL|timor-leste,east timor|timorese|AS|AS-SE|pt,tet|
IN|india|indian|AS|AS-S|hi,en|
PK|pakistan|pakistani|AS|AS-S|ur,en|
BD|bangladesh|bangladeshi|AS|AS-S|bn|
LK|sri lanka|sri lankan|AS|AS-S|si,ta|
NP|nepal|nepali,nepalese|AS|AS-S|ne|
BT|bhutan|bhutanese|AS|AS-S|dz|
MV|maldives|maldivian|AS|AS-S|dv|
AF|afghanistan|afghan|AS|AS-S|fa,ps|
KZ|kazakhstan|kazakh,kazakhstani|AS|AS-C|kk,ru|soviet
UZ|uzbekistan|uzbek|AS|AS-C|uz|soviet
KG|kyrgyzstan|kyrgyz|AS|AS-C|ky,ru|soviet
TJ|tajikistan|tajik|AS|AS-C|tg|soviet
TM|turkmenistan|turkmen|AS|AS-C|tk|soviet
TR|turkey,türkiye,turkiye|turkish,turk|AS|AS-W|tr|mediterranean
IR|iran|iranian,persian|AS|AS-W|fa|
IQ|iraq|iraqi|AS|AS-W|ar|arab
SA|saudi arabia|saudi,saudi arabian|AS|AS-W|ar|arab,gulf
AE|united arab emirates,uae,emirates|emirati|AS|AS-W|ar|arab,gulf
QA|qatar|qatari|AS|AS-W|ar|arab,gulf
KW|kuwait|kuwaiti|AS|AS-W|ar|arab,gulf
BH|bahrain|bahraini|AS|AS-W|ar|arab,gulf
OM|oman|omani|AS|AS-W|ar|arab,gulf
YE|yemen|yemeni|AS|AS-W|ar|arab
JO|jordan|jordanian|AS|AS-W|ar|arab,levant
LB|lebanon|lebanese|AS|AS-W|ar|arab,levant,mediterranean
SY|syria|syrian|AS|AS-W|ar|arab,levant,mediterranean
PS|palestine|palestinian|AS|AS-W|ar|arab,levant
IL|israel|israeli|AS|AS-W|he|mediterranean
AM|armenia|armenian|AS|AS-W|hy|soviet
AZ|azerbaijan|azerbaijani,azeri|AS|AS-W|az|soviet
GE|georgia|georgian|AS|AS-W|ka|soviet
EG|egypt|egyptian|AF|AF-N|ar|arab,mediterranean
LY|libya|libyan|AF|AF-N|ar|arab,maghreb,mediterranean
TN|tunisia|tunisian|AF|AF-N|ar|arab,maghreb,mediterranean
DZ|algeria|algerian|AF|AF-N|ar|arab,maghreb,mediterranean
MA|morocco|moroccan|AF|AF-N|ar|arab,maghreb,mediterranean
MR|mauritania|mauritanian|AF|AF-N|ar|arab,maghreb
SD|sudan|sudanese|AF|AF-N|ar|arab
NG|nigeria|nigerian|AF|AF-W|en|
GH|ghana|ghanaian|AF|AF-W|en|
SN|senegal|senegalese|AF|AF-W|fr|
ML|mali|malian|AF|AF-W|fr|
CI|ivory coast,côte d'ivoire,cote d'ivoire|ivorian|AF|AF-W|fr|
BF|burkina faso|burkinabe|AF|AF-W|fr|
NE|niger|nigerien|AF|AF-W|fr|
GN|guinea|guinean|AF|AF-W|fr|
SL|sierra leone|sierra leonean|AF|AF-W|en|
LR|liberia|liberian|AF|AF-W|en|
TG|togo|togolese|AF|AF-W|fr|
BJ|benin|beninese|AF|AF-W|fr|
GM|gambia,the gambia|gambian|AF|AF-W|en|
GW|guinea-bissau|bissau-guinean|AF|AF-W|pt|
CV|cape verde,cabo verde|cape verdean|AF|AF-W|pt|
KE|kenya|kenyan|AF|AF-E|sw,en|
TZ|tanzania|tanzanian|AF|AF-E|sw,en|
UG|uganda|ugandan|AF|AF-E|en,sw|
ET|ethiopia|ethiopian|AF|AF-E|am|
RW|rwanda|rwandan|AF|AF-E|rw,fr,en|
BI|burundi|burundian|AF|AF-E|fr|
SS|south sudan|south sudanese|AF|AF-E|en|
ER|eritrea|eritrean|AF|AF-E|ti,ar|
DJ|djibouti|djiboutian|AF|AF-E|fr,ar|arab
SO|somalia|somali|AF|AF-E|so,ar|arab
CD|democratic republic of the congo,dr congo,drc,congo-kinshasa|congolese|AF|AF-C|fr|
CG|republic of the congo,congo,congo-brazzaville|congolese|AF|AF-C|fr|
CM|cameroon|cameroonian|AF|AF-C|fr,en|
CF|central african republic|central african|AF|AF-C|fr|
GA|gabon|gabonese|AF|AF-C|fr|
GQ|equatorial guinea|equatoguinean|AF|AF-C|es|
TD|chad|chadian|AF|AF-C|fr,ar|
AO|angola|angolan|AF|AF-C|pt|
ST|são tomé and príncipe,sao tome and principe|são toméan|AF|AF-C|pt|
ZA|south africa|south african|AF|AF-S|en,af,zu|
ZW|zimbabwe|zimbabwean|AF|AF-S|en,sn|
ZM|zambia|zambian|AF|AF-S|en|
MZ|mozambique|mozambican|AF|AF-S|pt|
BW|botswana|botswanan,motswana|AF|AF-S|en,tn|
NA|namibia|namibian|AF|AF-S|en|
LS|lesotho|basotho|AF|AF-S|st,en|
SZ|eswatini,swaziland|swazi|AF|AF-S|ss,en|
MW|malawi|malawian|AF|AF-S|en|
MG|madagascar|malagasy,madagascan|AF|AF-S|mg,fr|
MU|mauritius|mauritian|AF|AF-S|en,fr|
AU|australia|australian,aussie|OC|OC|en|western
NZ|new zealand,aotearoa|new zealander,kiwi|OC|OC|en,mi|western
PG|papua new guinea|papua new guinean,papuan|OC|OC|en,tpi|
FJ|fiji|fijian|OC|OC|en,fj|
WS|samoa|samoan|OC|OC|sm,en|
TO|tonga|tongan|OC|OC|to,en|
VU|vanuatu|ni-vanuatu|OC|OC|bi,en,fr|
SB|solomon islands|solomon islander|OC|OC|en|
"""
COUNTRIES = {}   # code -> dict(name, aliases, demonyms, continent, sub, langs, groups)
for line in _T.strip().splitlines():
    code, names, dem, cont, sub, langs, groups = [x.strip() for x in line.split("|")]
    nm = [n.strip() for n in names.split(",") if n.strip()]
    COUNTRIES[code] = {"name": nm[0], "aliases": nm, "demonyms": [d.strip() for d in dem.split(",") if d.strip()], "continent": cont, "sub": sub,
                       "langs": [l.strip() for l in langs.split(",") if l.strip()], "groups": [g.strip() for g in groups.split(",") if g.strip()]}
def _where(pred): return frozenset(c for c, i in COUNTRIES.items() if pred(i))
def _sub(*subs): return _where(lambda i: i["sub"] in subs)
def _grp(g): return _where(lambda i: g in i["groups"])
def _lang(*ls): return _where(lambda i: any(l in i["langs"] for l in ls))
def _cont(c): return _where(lambda i: i["continent"] == c)
# Every way of saying a place that is bigger than one country. Words in
# free text; also the value of "from:", "country:" and "country is".
PLACES = {
  "european": _cont("EU"), "african": _cont("AF"), "asian": _cont("AS"), "oceanian": _cont("OC"), "australasian": frozenset({"AU", "NZ"}),
  "pacific islander": _cont("OC") - {"AU", "NZ"}, "polynesian": frozenset({"WS", "TO"}),
  "north american": frozenset({"US", "CA", "MX"}), "northern american": _sub("NA"), "central american": _sub("CA"), "caribbean": _sub("CB"), "west indian": _sub("CB"),
  "south american": _sub("SA"), "latin american": _sub("LA", "CA", "SA") | _lang("es", "pt", "fr") & _sub("CB"), "latino": _sub("LA", "CA", "SA") | _lang("es", "pt", "fr") & _sub("CB"),
  "nordic": _grp("nordic"), "scandinavian": _grp("scandinavian"), "scandi": _grp("scandinavian"), "baltic": _sub("EU-B"),
  "western european": _sub("EU-W"), "central european": _sub("EU-C"), "southern european": _sub("EU-S", "EU-BK"), "eastern european": _sub("EU-E", "EU-BK", "EU-B"), "northern european": _sub("EU-N", "EU-B"),
  "balkan": _sub("EU-BK"), "iberian": _grp("iberian"), "benelux": _grp("benelux"), "british isles": _grp("british-isles"), "mediterranean": _grp("mediterranean"),
  "east asian": _sub("AS-E"), "southeast asian": _sub("AS-SE"), "south east asian": _sub("AS-SE"), "south asian": _sub("AS-S"), "central asian": _sub("AS-C"),
  "middle eastern": (_sub("AS-W") - {"AM", "AZ", "GE"}) | {"EG"}, "west asian": _sub("AS-W"), "caucasian": frozenset({"AM", "AZ", "GE"}), "gulf": _grp("gulf"), "levantine": _grp("levant"), "arab": _grp("arab"), "arabic": _grp("arab"), "arabic-speaking": _grp("arab"),
  "north african": _sub("AF-N"), "maghreb": _grp("maghreb"), "maghrebi": _grp("maghreb"), "west african": _sub("AF-W"), "east african": _sub("AF-E"), "central african": _sub("AF-C"), "southern african": _sub("AF-S"),
  "sub-saharan": _cont("AF") - _sub("AF-N"), "sub saharan": _cont("AF") - _sub("AF-N"),
  "english-speaking": _lang("en"), "english speaking": _lang("en"), "anglophone": _lang("en"), "spanish-speaking": _lang("es"), "spanish speaking": _lang("es"), "hispanic": _lang("es"), "hispanophone": _lang("es"),
  "french-speaking": _lang("fr"), "french speaking": _lang("fr"), "francophone": _lang("fr"), "portuguese-speaking": _lang("pt"), "portuguese speaking": _lang("pt"), "lusophone": _lang("pt"),
  "german-speaking": _lang("de"), "german speaking": _lang("de"), "germanophone": _lang("de"), "dutch-speaking": _lang("nl"), "russian-speaking": _lang("ru"), "italian-speaking": _lang("it"),
  "western": _grp("western"), "post-soviet": _grp("soviet"), "ex-soviet": _grp("soviet"), "former soviet": _grp("soviet"), "soviet": _grp("soviet"),
  "ex-yugoslav": _grp("yugoslav"), "former yugoslav": _grp("yugoslav"), "yugoslav": _grp("yugoslav"), "yugoslavian": _grp("yugoslav"),
}
# Single countries: demonyms match in free text ("norwegian duo"); names only
# as the VALUE of a field ("from norway", "country is norway"), because names
# like Chad, Jordan, Georgia and Turkey are also words and artists.
DEMONYMS = {d: c for c, i in COUNTRIES.items() for d in i["demonyms"]}
NAMES = {n: c for c, i in COUNTRIES.items() for n in i["aliases"]}
# Noun forms, for "from X" and field values only ("from west africa", "country is scandinavia")
PLACE_NAMES = {
  "europe": PLACES["european"], "africa": PLACES["african"], "asia": PLACES["asian"], "oceania": PLACES["oceanian"], "australasia": PLACES["australasian"],
  "north america": PLACES["north american"], "central america": PLACES["central american"], "the caribbean": PLACES["caribbean"], "caribbean": PLACES["caribbean"], "the west indies": PLACES["caribbean"],
  "south america": PLACES["south american"], "latin america": PLACES["latin american"], "latam": PLACES["latin american"],
  "scandinavia": PLACES["scandinavian"], "the nordics": PLACES["nordic"], "the nordic countries": PLACES["nordic"], "the baltics": PLACES["baltic"], "the baltic states": PLACES["baltic"],
  "western europe": PLACES["western european"], "central europe": PLACES["central european"], "southern europe": PLACES["southern european"], "eastern europe": PLACES["eastern european"], "northern europe": PLACES["northern european"],
  "the balkans": PLACES["balkan"], "iberia": PLACES["iberian"], "the benelux": PLACES["benelux"], "benelux": PLACES["benelux"], "the british isles": PLACES["british isles"], "the mediterranean": PLACES["mediterranean"],
  "east asia": PLACES["east asian"], "southeast asia": PLACES["southeast asian"], "south east asia": PLACES["southeast asian"], "south asia": PLACES["south asian"], "central asia": PLACES["central asian"],
  "the middle east": PLACES["middle eastern"], "middle east": PLACES["middle eastern"], "west asia": PLACES["west asian"], "the gulf": PLACES["gulf"], "the levant": PLACES["levantine"], "the arab world": PLACES["arab"], "the caucasus": PLACES["caucasian"],
  "north africa": PLACES["north african"], "the maghreb": PLACES["maghreb"], "west africa": PLACES["west african"], "east africa": PLACES["east african"], "central africa": PLACES["central african"], "southern africa": PLACES["southern african"], "sub-saharan africa": PLACES["sub-saharan"],
  "the west": PLACES["western"], "the western world": PLACES["western"], "the former soviet union": PLACES["soviet"], "the soviet union": PLACES["soviet"], "the ussr": PLACES["soviet"], "yugoslavia": PLACES["yugoslav"], "the former yugoslavia": PLACES["yugoslav"],
}
def place(value):
    """the value of a place field -> frozenset of codes, or None"""
    v = (value or "").strip().lower().strip(".")
    if not v: return None
    if v.upper() in COUNTRIES and len(v) == 2: return frozenset([v.upper()])
    for table in (NAMES, DEMONYMS):
        if v in table: return frozenset([table[v]])
    if v in PLACES: return PLACES[v]
    if v in PLACE_NAMES: return PLACE_NAMES[v]
    v2 = v.replace("the ", "", 1)
    if v2 in NAMES: return frozenset([NAMES[v2]])
    if v2 in PLACE_NAMES: return PLACE_NAMES[v2]
    if "the " + v in PLACE_NAMES: return PLACE_NAMES["the " + v]
    return None

_SMALL = {"of", "the", "and"}
def display_name(code):
    """'NO' -> 'Norway', 'US' -> 'United States', 'CD' -> 'Democratic Republic of the Congo'"""
    i = COUNTRIES.get((code or "").upper())
    if not i: return code
    words = i["name"].split(" ")
    return " ".join(w if (w in _SMALL and n) else w[:1].upper() + w[1:] for n, w in enumerate(words))
