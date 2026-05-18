#!/usr/bin/env python3
"""GH Actions worker — one account, ITEMS_PER_RUN /details/ items per run.

No PDFs. Each item = 1 tiny placeholder file (S3 needs ≥1 file to materialize the bucket).
Description is set via metadata PATCH AFTER initial upload (description in initial PUT
headers gets truncated when long; PATCH handles full HTML reliably).

Reads env:
  IA_ACCESS, IA_SECRET     — single account credentials
  ACCOUNT_LABEL            — for stats/logging
  ITEMS_PER_RUN            — items per worker invocation (default 50)
  GROUP                    — desi|auntymaza|xnxx|india|hindibf (rotated by orchestrator)

Outputs:
  /tmp/result.json  — { ok, items: [...], group, per_acct: {...}, error: str|null }
"""
import sys, os, random, time, json, urllib.parse, urllib.request
try:
    from doorway_pdf import build_doorway_pdf, slugify_title
except ImportError:
    build_doorway_pdf = None
    def slugify_title(t):
        import re
        return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')[:80]
try:
    from doorway_html import build_doorway_html
except ImportError:
    build_doorway_html = None

# SOURCE_IP binding — when set (e.g. via `SOURCE_IP=51.38.147.246 python3 worker.py`),
# all outbound HTTPS connections originate from that interface. Lets us run N workers
# in parallel from the same host but distributed across N source IPs so IA sees the
# uploads coming from different source addresses, not one server doing 47x the work.
# No-op when env var is empty (default urllib routing).
if os.environ.get('SOURCE_IP'):
    import http.client
    _sip = os.environ['SOURCE_IP']
    _orig_https_init = http.client.HTTPSConnection.__init__
    def _bound_https_init(self, *args, **kwargs):
        kwargs['source_address'] = (_sip, 0)
        _orig_https_init(self, *args, **kwargs)
    http.client.HTTPSConnection.__init__ = _bound_https_init

ETREE_BANDS = [
    # Originals (low-traffic etree sub-collections, validated as indexable)
    'Strangefolk', 'AcidMothersTemple', 'WidespreadPanic',
    'BirthMusic', 'BenTraverse', 'TheTravelinKine',
    # Diversifiers — real etree sub-collections sampled from
    # archive.org's 9200+ band catalog. Spreads our 100s-of-items-per-day
    # across 36 bands so no single collection becomes a spam-spike outlier
    # (each band averages low triple digits of items; ours add proportionally).
    'TheDBWalkerBand', 'UnseenStrangers', 'Clogs', 'Aristeia',
    'WoodenHorsemen', 'SteelGravy', 'Shorefire', 'MasonsChildren',
    'Harpoon', 'RogueWave', 'Innasci', 'KenoshaKid',
    'LoungeDrugs', 'GreenLight', 'FunkbudJohnny', 'TheHardestDaze',
    'DowdySmack', 'ElectricSoulParade', 'BigSwingTrio', 'Atoadaso',
    'PocketChange', 'SouthernFriedFunk', 'LeroyTownes', 'Spyscraper',
    'AnimalCollective', 'TheSilentTrees', 'ClaudiaJane', 'NagChampayons',
    'JonoManson', 'FreeGrassUnion',
]
VENUES = ['gthrny','live-show','outdoor-fest','soundcheck','rehearsal','jam-session']

# === Seed word pools — combinable into millions of unique titles/desc lines ===
REGIONS = [
    'Tamil', 'Telugu', 'Hindi', 'Bengali', 'Bhojpuri', 'Marathi', 'Marwadi',
    'Mallu', 'Punjabi', 'Gujarati', 'Odia', 'Bihari', 'Kannada', 'Malayalam',
    'Assamese', 'Dehati', 'Desi', 'Indian', 'South Indian', 'North Indian',
    'Pakistani', 'Bangladeshi', 'Bangla', 'Nepali', 'Sri Lankan', 'Punjabi Sikh',
]

CATEGORIES = [
    'Bhabhi', 'Aunty', 'Devar Bhabhi', 'Padosi Bhabhi', 'Mami', 'Mousi', 'Masi',
    'Boudi', 'Sasur Bahu', 'Jija Sali', 'Maid', 'Teacher', 'School Girl',
    'College Girl', 'Hostel Girl', 'Heroine', 'Actress', 'Married Aunty',
    'Housewife', 'Mami Bhanja', 'Cousin', 'Step Sister', 'Saali', 'Randi',
    'Office Aunty', 'Working Bhabhi', 'Saree Aunty', 'Big Boobs Aunty',
    'Hot Bhabhi', 'Married Bhabhi', 'Village Bhabhi', 'Tante', 'ABG',
]

SCENES = [
    'MMS', 'Sex Video', 'Chudai', 'Blue Film', 'BF', 'Caught', 'Leaked', 'Viral',
    'Real', 'Original', 'Hidden Cam', 'Live Cam', 'Webcam', 'Hotel Sex',
    'Bedroom Sex', 'Bathroom Sex', 'Outdoor Sex', 'Jungle Sex', 'Car Sex',
    'Office Sex', 'Hostel Sex', 'Reels', 'Viral Kand', 'Live Streaming',
    'Audio Sex', 'Hot Affair', 'Cheating', 'Romance', 'XXX', 'Sex Tape',
    'Strip', 'Suhaagrat', 'First Night', 'Honeymoon', 'Wedding Night',
    'Massage Parlor', 'Bus Groping', 'Train Sex', 'Telegram Leak',
    'WhatsApp Viral', 'Insta Reels', 'Live Show', 'Big Boobs Show',
]

QUALITIES = [
    'HD', '4K', '1080p', '720p', 'Uncut', 'Full HD', 'Full Length',
    'Latest', 'New', '2026', 'Premium', 'Mega Pack', 'Collection',
]

BRANDS = [
    'AuntyMaza', 'MmsMaza', 'FsiBlog', 'Masahub', 'Desihub', 'Webxmaza',
    'Aagmaal', 'Hindibfvideo', 'Mydesi', 'Desi49', 'Mmstown', 'Mmsdose',
    'UlluUncut', 'Webmaal', 'Uncutmaza', 'Uncutmasti', 'Antarvasna', 'Rajwap',
    'Mastibaba', 'Dropmms', 'Xmaza', 'Lol49', 'Xmasti', 'Desitales',
    'Xhamster', 'Xhamster19', 'XnXX', 'XnXX2', 'PornHub', 'Spankbang',
    'Faphouse', 'Redwap', 'Eporner', 'Xhopen', 'Theporndude', 'Masa49',
    'Masafun', 'Kamababa', 'Fry99', 'Desikahani', 'DesiPorn', 'Desileak',
    'Deephot', 'Desifile', 'XnXXVideos', 'VdsBlog', 'Tamilsexzone',
    'Thehappycenter', 'Masalaseen', 'Dinotube', 'Sexvid',
]

LOCATIONS = [
    'Delhi', 'Mumbai', 'Kolkata', 'Chennai', 'Bangalore', 'Hyderabad', 'Pune',
    'Ahmedabad', 'Lucknow', 'Patna', 'Jaipur', 'Surat', 'Kanpur',
    'GB Road', 'Sonagachi', 'MG Road', 'Red Light Area', 'Chandni Chowk',
    'Karol Bagh', 'Andheri', 'Bandra', 'Connaught Place',
]


def _r(pool):
    return random.choice(pool)


# Zones we're SEO-targeting: the 20 masalatube1 categories (so title + player target
# stay aligned with the category the user lands on) plus XnXX as an extra brand pin.
# Set after MASALA_CATS below.


# Title pattern functions. Reduced from 15 nearly-identical patterns (Google
# clustered them as duplicate-looking SERP titles) to 6 structurally distinct
# ones: 3 token-only + 2 with natural-language connectors + 1 serial-style.
# NL templates break the "Token Token Token Token" fingerprint that the
# spam-classifier flags.
def _t_tok_a(z):  return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t_tok_b(z):  return f'{z} {_r(LOCATIONS)} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)}'
def _t_tok_c(z):  return f'{z} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)} 2026'
def _t_nl_a(z):   return f'{z} leaked - {_r(REGIONS)} {_r(CATEGORIES)} caught on {_r(SCENES_NL)} - {_r(QUALITIES)}'
def _t_nl_b(z):   return f'{z} of {_r(LOCATIONS)} {_r(CATEGORIES)} during {_r(SCENES_NL)}, {_r(QUALITIES)}'
def _t_ser(z):    return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} (Vol {random.randint(7, 184)})'

_TITLE_FNS = [_t_tok_a, _t_tok_b, _t_tok_c, _t_nl_a, _t_nl_b, _t_ser]


def gen_title(zone):
    """Pick a structurally-distinct title template starting with the zone
    keywords (first-position SERP rank), then suffix from the theme-specific
    prefix pool with collision avoidance (suffix tokens must not overlap
    zone tokens — prevents 'desi mms <suffix> Desi MMS ...')."""
    base = random.choice(_TITLE_FNS)(zone)
    theme = theme_for(zone)
    pool = list(_THEME_PREFIX.get(theme, []))
    pool = [p for p in pool if not _prefix_collides(p, zone)]
    if pool:
        return f'{base} {random.choice(pool)}'
    return base


def gen_kw_line(zone):
    """5-7 tags pinned around the chosen zone, joined with ' • '."""
    pool = [zone]
    pool += random.sample(REGIONS, k=2)
    pool += random.sample(CATEGORIES, k=2)
    pool += [_r(SCENES)]
    if random.random() < 0.5:
        pool += [_r(LOCATIONS)]
    # zone always first; randomize the rest
    rest = pool[1:]
    random.shuffle(rest)
    return ' • '.join([pool[0]] + rest)

# Single money site — masalatube1.com. Player CTA → homepage; chip strip → /category/<slug>/.
HOME_URL = 'https://auntymazaporn1.com/'

# 20 live categories from category-sitemap.xml.php (2026-05-13).
MASALA_CATS = [
    ('Desi Porn',        'desi-porn'),
    ('Desi MMS',         'desi-mms'),
    ('Desi Bhabhi',      'desi-bhabhi'),
    ('Aunty Sex',        'aunty-sex'),
    ('Aunty XXX',        'aunty-xxx'),
    ('Hindi BF',         'hindi-bf'),
    ('Indian XXX',       'indian-xxx'),
    ('Indian Porn',      'indian-porn'),
    ('Bengali Sex',      'bengali-sex'),
    ('Tamil Aunty',      'tamil-aunty'),
    ('Telugu Sex',       'telugu-sex'),
    ('Mallu Aunty',      'mallu-aunty'),
    ('Punjabi Bhabhi',   'punjabi-bhabhi'),
    ('Bhojpuri Bhabhi',  'bhojpuri-bhabhi'),
    ('Hot Web Series',   'hot-web-series'),
    ('Uncut Web Series', 'uncut-web-series'),
    ('Masala MMS',       'masala-mms'),
    ('AuntyMaza',        'auntymaza'),
    ('Dehati Chudai',    'dehati-chudai'),
    ('Village Aunty',    'village-aunty'),
]

# Full pinned zone ring: 20 masalatube1 categories + XnXX. Each account is pinned to
# exactly one zone (deterministic by acctN index), so its entire footprint lives in
# one /category/<slug>/ SERP — no cross-pollination. Wraps around modulo len for
# account counts > len(_ZONE_RING).
_ZONE_RING = [
    ('Desi MMS Porn',              'desi-mms'),
    ('Hindi BF Porn',              'hindi-bf'),
    ('Aunty Sex Video',            'aunty-sex-video'),
    ('Auntymaza Porn',             'auntymaza'),
    ('Bengali Boudi Sex Videos',   'bengali-boudi'),
    ('Tamil Aunty Sex',            'tamil-aunty'),
    ('Mydesi Porn',                'mydesi'),
]

# Legacy compatibility — kept so any caller that still references ZONES doesn't break.
ZONES = list(_ZONE_RING)


# ===== Per-zone theming (2026-05-14 anti-duplicate-content rewrite) =====
# Google was de-indexing after the first wave because every /details/<id> had
# identical chip strip + identical player-mockup text + identical palette,
# differing only in 4 short strings. Per-zone themes vary:
#   - prefix_pool : title brand-prefixes that DON'T collide with the zone tokens
#   - chip_subset : 8 categories thematically relevant to this zone (not all 20)
#   - palette     : distinct CSS colors so inline-style hashes differ
# Copy pools (headlines/h2/subtitle) are shared but picked per item → enough
# combinatorial spread that two items rarely look identical at the shingle level.

_THEME_OF = {
    'desi porn':        'desi_mms',
    'desi mms':         'desi_mms',
    'masala mms':       'desi_mms',
    'desi bhabhi':      'bhabhi',
    'punjabi bhabhi':   'bhabhi',
    'bhojpuri bhabhi':  'bhabhi',
    'aunty sex':        'aunty',
    'aunty xxx':        'aunty',
    'mallu aunty':      'aunty',
    'tamil aunty':      'aunty',
    'village aunty':    'aunty',
    'auntymaza':        'aunty',
    'mydesi':           'desi_mms',
    'bengali boudi':    'regional',
    'bengali sex':      'regional',
    'telugu sex':       'regional',
    'dehati chudai':    'regional',
    'hindi bf':         'mainstream',
    'indian xxx':       'mainstream',
    'indian porn':      'mainstream',
    'xnxx':             'mainstream',
    'hot web series':   'webseries',
    'uncut web series': 'webseries',
}

# Brand-prefix pools per theme. Carefully chosen to NOT contain the theme's own
# zone-token vocabulary — prevents "desi mms <prefix> Desi MMS ..." stacking.
_THEME_PREFIX = {
    'desi_mms':   ['leaked tape', 'viral kand', 'hidden cam', 'telegram leak',
                   'whatsapp viral', 'exclusive clip', 'private recording',
                   'bedroom tape', 'reels leak', 'hot scandal'],
    'bhabhi':     ['married wife', 'hot housewife', 'newlywed couple',
                   'romantic affair', 'sasur bahu', 'jija sali', 'wedding night',
                   'first night', 'sexy wife', 'neighbor lady'],
    'aunty':      ['mature milf', 'big boobs lady', 'saree clad', 'office boss',
                   'married woman', 'landlady', 'teacher madam',
                   'working mom', 'housewife scene', 'older lady'],
    'regional':   ['kolkata leak', 'hyderabad cam', 'village affair',
                   'farmer wife', 'hostel girl', 'college clip',
                   'bus groping', 'train scene', 'massage parlor', 'rural kand'],
    'mainstream': ['hot leak', 'viral clip', 'sex tape', 'married couple',
                   'bedroom video', 'romance scene', 'college affair',
                   'hostel clip', 'webcam show', 'live cam'],
    'webseries':  ['ullu show', 'primeplay episode', 'kooku season', 'rabbit clip',
                   'nuefliks scene', 'hoichoi cut', 'full episode',
                   'premium clip', 'ott leak', 'season finale'],
}

# 8 chip categories per theme. Reduced from 20 → 8 so the chip block isn't
# identical across items; subset is also thematically tighter for relevance.
_THEME_CHIPS = {
    'desi_mms':   [('Desi MMS','desi-mms'), ('Masala MMS','masala-mms'),
                   ('Desi Porn','desi-porn'), ('Dehati Chudai','dehati-chudai'),
                   ('AuntyMaza','auntymaza'), ('Indian XXX','indian-xxx'),
                   ('Bhojpuri Bhabhi','bhojpuri-bhabhi'), ('Hot Web Series','hot-web-series')],
    'bhabhi':     [('Desi Bhabhi','desi-bhabhi'), ('Punjabi Bhabhi','punjabi-bhabhi'),
                   ('Bhojpuri Bhabhi','bhojpuri-bhabhi'), ('Aunty Sex','aunty-sex'),
                   ('Hindi BF','hindi-bf'), ('Indian Porn','indian-porn'),
                   ('Tamil Aunty','tamil-aunty'), ('AuntyMaza','auntymaza')],
    'aunty':      [('Aunty Sex','aunty-sex'), ('Aunty XXX','aunty-xxx'),
                   ('Mallu Aunty','mallu-aunty'), ('Tamil Aunty','tamil-aunty'),
                   ('Village Aunty','village-aunty'), ('AuntyMaza','auntymaza'),
                   ('Bhojpuri Bhabhi','bhojpuri-bhabhi'), ('Desi Bhabhi','desi-bhabhi')],
    'regional':   [('Bengali Sex','bengali-sex'), ('Telugu Sex','telugu-sex'),
                   ('Tamil Aunty','tamil-aunty'), ('Dehati Chudai','dehati-chudai'),
                   ('Mallu Aunty','mallu-aunty'), ('Punjabi Bhabhi','punjabi-bhabhi'),
                   ('Bhojpuri Bhabhi','bhojpuri-bhabhi'), ('Indian XXX','indian-xxx')],
    'mainstream': [('Hindi BF','hindi-bf'), ('Indian XXX','indian-xxx'),
                   ('Indian Porn','indian-porn'), ('Desi Porn','desi-porn'),
                   ('Desi MMS','desi-mms'), ('Aunty Sex','aunty-sex'),
                   ('Hot Web Series','hot-web-series'), ('Bengali Sex','bengali-sex')],
    'webseries':  [('Hot Web Series','hot-web-series'), ('Uncut Web Series','uncut-web-series'),
                   ('Masala MMS','masala-mms'), ('Desi Bhabhi','desi-bhabhi'),
                   ('Aunty Sex','aunty-sex'), ('Indian Porn','indian-porn'),
                   ('Hindi BF','hindi-bf'), ('Punjabi Bhabhi','punjabi-bhabhi')],
}

# Inline-style palettes per theme. Six knobs: page bg, border, CTA bg,
# big-headline color, mid-text color, accent color. Distinct enough that the
# overall HTML hash differs between themes.
_THEME_PALETTE = {
    'desi_mms':   {'bg':'#0a0a0a','border':'#dc2626','cta':'#dc2626',
                   'head':'#fbbf24','mid':'#06b6d4','accent':'#16a34a'},
    'bhabhi':     {'bg':'#1a0a0d','border':'#ec4899','cta':'#db2777',
                   'head':'#fde047','mid':'#f472b6','accent':'#a78bfa'},
    'aunty':      {'bg':'#1a0f0d','border':'#b91c1c','cta':'#dc2626',
                   'head':'#fde68a','mid':'#fb923c','accent':'#fbbf24'},
    'regional':   {'bg':'#0a141a','border':'#10b981','cta':'#059669',
                   'head':'#fbbf24','mid':'#22d3ee','accent':'#84cc16'},
    'mainstream': {'bg':'#0a0a14','border':'#3b82f6','cta':'#2563eb',
                   'head':'#fbbf24','mid':'#fb923c','accent':'#22d3ee'},
    'webseries':  {'bg':'#150a1f','border':'#a855f7','cta':'#9333ea',
                   'head':'#fbbf24','mid':'#ec4899','accent':'#22d3ee'},
}

# Headline / h2 / subtitle pools (shared but picked randomly per item).
_HEADLINE_POOL = [
    '● LIVE HD 1080p ●', '● STREAMING NOW ●',
    '● NEW UPLOAD ●', '● PREMIUM HD ●',
    '● VIRAL CLIP ●', '● EXCLUSIVE ●',
    '● TRENDING ●', '● 4K UNCUT ●',
    '● HOT LEAK ●', '● FRESH UPLOAD ●',
    '● WATCH NOW ●', '● LATEST 2026 ●',
]
_H2_POOL = [
    '\U0001f525 HD VIRAL LEAKED VIDEO \U0001f525',
    '\U0001f525 ORIGINAL UNCUT FOOTAGE \U0001f525',
    '\U0001f525 EXCLUSIVE FULL LENGTH \U0001f525',
    '\U0001f525 PREMIUM HOT CLIP \U0001f525',
    '\U0001f525 NEW VIRAL RECORDING \U0001f525',
    '\U0001f525 LATEST UPLOAD HD \U0001f525',
    '\U0001f525 FULL HOT SESSION \U0001f525',
    '\U0001f525 PRIVATE LEAKED TAPE \U0001f525',
    '\U0001f525 ORIGINAL HD VIDEO \U0001f525',
    '\U0001f525 HOT VIRAL STREAM \U0001f525',
    '\U0001f525 LATEST KAND CLIP \U0001f525',
    '\U0001f525 EXCLUSIVE HD VIDEO \U0001f525',
]
_SUBTITLE_POOL = [
    'Free Streaming • Updated 2026 • Original HD Video',
    'Watch Online • No Signup • Latest HD Upload',
    'Free Access • Fresh 2026 • Premium HD Quality',
    'Stream Now • Updated Daily • 4K Original',
    'Free HD • Direct Play • New Upload 2026',
    'Online Streaming • No Ads Page • Full HD',
    'Watch Free • Latest Clip • Original HD Source',
    'Mobile Friendly • HD Stream • Updated 2026',
]

# Natural-language scene phrases (read well with prepositions / connectors,
# unlike "Viral Kand" or "WhatsApp Viral"). Used by NL title templates.
SCENES_NL = [
    'hidden cam', 'leaked tape', 'sex tape', 'viral mms', 'live cam',
    'webcam', 'romance', 'affair', 'hot scene', 'private clip',
    'bedroom scene', 'cheating affair',
]

# Body paragraph pools per theme. Each item's /details/<id> page gets 3
# paragraphs picked randomly from its theme pool (~500 words of crawlable
# natural-language text between the player mockup and the chip strip). The
# 5-template-per-theme pool × C(5,3)=10 orderings × ~9 placeholder slots per
# paragraph produces effectively unique body text per item, giving Google
# real content to index instead of just inline-styled markup.
#
# Placeholders supported in templates:
#   {z}     — zone label (canonical pinned zone, not augmented form)
#   {region},{region2}     — random REGIONS picks (distinct)
#   {cat},{cat2}           — random CATEGORIES picks (distinct)
#   {loc},{loc2}           — random LOCATIONS picks (distinct)
#   {scene},{scene2}       — random SCENES_NL picks
#   {qual},{qual2}         — random QUALITIES picks (distinct)
#   {link1},{link2}        — pre-rendered inline <a> anchors to target_url
_THEME_BODY = {
    'desi_mms': [
        "Watch this {qual} {z} sex video featuring {region} {cat} fucking hard in {loc} during a leaked {scene}, full uncut runtime with original audio. The {z} porn archive collects thousands of real Indian xxx clips, viral sex tapes, hidden cam fuck videos, and hot leaked porn from real households. Browse the full {z} library at {link1} - free streaming, no signup, no popup ads. Watch {z} sex videos online with direct mobile playback on any device, in-browser, no app installs.",
        "Free {z} porn videos online - {region} {cat} caught fucking in {loc} on this {qual} viral leak. The {z} sex video archive runs daily uploads of hot Indian xxx clips: real fuck scenes, leaked sex tapes, hidden cam porn, hard fucking from regional households. The {link2} catalog handles full {z} browse with category and region filters. Watch online direct stream, no third-party rehosts, mobile-friendly across desktop and any modern device.",
        "Latest {z} sex video drop - {qual} {region} {cat} fucking real in {loc2} during {scene2}, uncut full length. {z} porn lovers come for the raw Indian xxx feel: no studio polish, no editorial cuts, no platform watermarks. The library covers thousands of {z} fuck clips plus matching {cat2} sex videos and {region2} porn variants. Free watch online, daily upload refresh, weekly batch drops every Friday with fresh hot content.",
        "This {qual} {z} sex video shows {region} {cat} fucking hard on a personal {scene} cam in {loc}, original audio kept intact. The {z} porn archive collects real Indian xxx from {region2} regions, with {cat2} fuck scenes filling out the catalog. {link1} indexes every active {z} sex video with category browse. Watch free, no signup, mobile-friendly playback for any device, direct stream, no popup interruptions during xxx playback.",
        "Hot {z} porn videos - {region} {cat} caught fucking in {loc2} on a viral {scene2} leak at {qual} resolution, full uncut runtime. The {z} sex video library hits thousands of real Indian xxx clips: leaked fuck tapes, hidden cam porn, hot regional sex videos. Free streaming, no signup wall, mobile playback works in-browser on any modern device. New {z} sex tape uploads drop daily with weekly batch refresh keeping the porn catalog fresh.",
    ],
    'bhabhi': [
        "Watch this {qual} {z} sex video - married {region} woman fucking hard in {loc} during a leaked {scene}, captured uncut on personal cam. The {z} porn archive shows real married woman xxx from {region2} households, with {cat} fuck videos plus {cat2} sex clips added daily. Hot Indian {z} sex tapes, leaked bedroom porn, viral married woman fucking - the full {z} library is at {link1}. Free streaming, no signup, watch {z} xxx online in HD with direct mobile playback.",
        "Free {z} porn videos featuring married {region} woman fucking in {loc} - this {qual} clip runs full uncut length with original audio. The {z} archive collects married Indian xxx from {region2} households, leaked bedroom sex tapes, viral {cat2} fuck videos from real couples. Watch the full {z} sex video catalog online, browse by region or by category, no signups in the playback chain. {link2} lists every active {z} porn clip with daily refresh.",
        "Latest {z} sex video drop - today's {qual} upload shows {region} {cat} fucking hard during {scene2} in {loc2}, full length and unedited. {z} fans come here for real married woman porn: raw leaked sex video, hidden cam fucking, no studio polish. The library covers {z} xxx from {region2} households, hot married woman {cat2} sex tapes, daily fresh fuck videos. Free online streaming, mobile playback works direct in-browser.",
        "This {qual} {z} sex video records married {region} {cat} fucking on a personal {scene} cam, filmed in {loc} with original audio intact. {z} porn lovers know the framing: real married woman xxx, no studio polish, full uncut length. The {z} fuck video archive covers {cat2} scenes across {region2} regional households. {link1} catalogs every active {z} sex video with category filter. Watch free, mobile-friendly, daily new porn drops.",
        "Hot {z} porn videos online - married {region} {cat} caught fucking in {loc2} on a viral {scene2} leak, {qual} resolution full uncut. The {z} sex video library hits thousands of married woman xxx clips: leaked bedroom porn, real Indian fuck tapes, hidden cam married woman {cat2} sex videos. Free streaming, no popup ads, mobile-friendly direct playback. New {z} sex tape uploads land daily with hot fresh fucking content.",
    ],
    'aunty': [
        "Watch this {qual} {z} sex video - mature {region} {cat} fucking hard in {loc} during a leaked {scene}, captured at source resolution with original audio. The {z} porn archive shows real aunty xxx from {region2} regions, with {cat2} fucking videos added daily. Hot Indian {z} fuck clips, viral aunty sex videos, leaked bedroom porn from mature women - the full {z} library is at {link1}. Free streaming, no signup wall, watch {z} xxx online in HD.",
        "Free {z} porn videos - mature {region} {cat} fucking real in {loc} on this {qual} uncut leak. The {z} sex video archive collects thousands of aunty xxx clips: hidden cam fuck scenes, hot Indian {region2} sex tapes, viral aunty porn from real {cat2} households. Watch {z} sex videos online with direct stream, no popup ads in the playback chain. {link2} handles the full {z} catalog browse with category and region filters.",
        "Latest {z} sex video archive drop - today's {qual} {region} aunty fuck clip captures {cat} in {loc2} during {scene2}, full uncut length preserved. {z} porn fans who follow mature aunty xxx come here for the raw real-recording library. The catalog covers {z} fucking from {region2} regions, leaked aunty sex tapes, hidden cam {cat2} fuck videos, full-length mature {region} xxx drops. Watch free, mobile direct playback, daily refresh.",
        "This {qual} {z} sex video shows {region} {cat} fucking hard on a personal {scene} cam, filmed in {loc} with original framing intact. {z} xxx fans recognize the raw look: real mature aunty porn, no studio production, full uncut length. The {z} archive spans {cat2} aunty fuck scenes across {region2} regional households at {qual2} encoding minimum. {link1} catalogs every active {z} aunty sex video. Watch free online direct stream.",
        "Hot {z} porn videos online - mature {region} {cat} caught fucking in {loc2} on a leaked {scene2} clip, {qual} resolution end-to-end. The {z} library hits thousands of aunty xxx videos: hidden cam aunty fuck, leaked aunty sex tapes, viral married woman {cat2} porn from real Indian households. Free streaming, no signup, mobile-friendly direct playback for any device. New {z} aunty sex video uploads land daily with hot fresh fucking content.",
    ],
    'regional': [
        "Watch this {qual} {z} sex video - {region} {cat} fucking hard in {loc} during a leaked {scene}, full uncut runtime with original {region} audio preserved. The {z} porn archive collects real regional Indian xxx from {region2} households, with {cat} fucking clips plus {cat2} sex tapes added daily. Hot {region} {z} fuck videos, leaked Indian sex tapes, viral regional porn - the full {z} library is at {link1}. Free streaming, watch online, mobile-friendly direct playback.",
        "Free {z} porn videos - {region} {cat} fucking real in {loc} on this {qual} uncut leak. The {z} sex video archive spans thousands of {region} xxx clips: hidden cam fuck scenes, hot regional {region2} sex tapes, viral Indian porn from real {cat2} households. Watch {z} sex videos online with direct stream, no popup ads, no signup wall. {link2} handles the full {z} catalog browse with regional and category filters.",
        "Latest {z} sex video archive - today's {qual} {region} {cat} fuck clip captures real Indian xxx during {scene2} in {loc2}, full uncut length. {z} porn fans who follow regional Indian content come here for the raw unedited sex video library. The catalog covers {z} fucking from {region2} households, leaked regional sex tapes, hidden cam {cat2} videos, full-length {region} xxx drops. Watch free, mobile direct playback, daily upload refresh.",
        "This {qual} {z} sex video records {region} {cat} fucking on a personal {scene} cam in {loc}, with original regional audio kept intact through to the natural end. {z} xxx fans recognize the framing: real regional Indian porn, full uncut length, no editorial trims. The {z} fuck video archive covers {cat2} scenes across {region2} regional households at {qual2} encoding. {link1} catalogs every active {z} sex clip. Watch free online direct.",
        "Hot {z} porn videos online - {region} {cat} caught fucking in {loc2} on a viral {scene2} leak, {qual} resolution full uncut. The {z} sex video library hits thousands of regional xxx clips: leaked Indian sex tapes, hidden cam {cat2} fuck videos, hot {region2} porn from real households. Free streaming, no popup ads, mobile-friendly playback. New {z} regional sex video uploads land daily with weekly batch refresh keeping the fuck catalog hot and fresh.",
    ],
    'mainstream': [
        "Watch this {qual} {z} sex video - {region} {cat} fucking hard in {loc} during a leaked {scene}, full uncut runtime with original audio. The {z} porn archive collects thousands of real Indian xxx clips from {region2} households, with {cat} fucking videos plus {cat2} sex tapes added daily. Hot {region} {z} fuck videos, viral leaked sex tapes, real Indian porn from across the country - the full {z} library is at {link1}. Free streaming, mobile-friendly.",
        "Free {z} porn videos online - {region} {cat} fucking in {loc} on this {qual} uncut leak. The {z} sex video archive spans thousands of Indian xxx clips: hidden cam {cat2} fuck scenes, hot {region2} sex tapes, viral regional porn from real households. Watch {z} sex videos online with direct stream, no popup ads, no signup. {link2} handles full {z} catalog browse with category and region filters covering every xxx variant.",
        "Latest {z} sex video archive drop - today's {qual} {region} {cat} fuck upload captures real Indian xxx during {scene2} in {loc2}, full uncut length. {z} porn fans come here for the raw unedited real-recording sex video library. The catalog covers {z} fucking from {region2} households, leaked Indian sex tapes, hidden cam {cat2} videos, full-length {region} xxx drops. Watch free online, mobile direct playback, daily refresh.",
        "This {qual} {z} sex video records {region} {cat} fucking on a personal {scene} cam in {loc}, original audio intact. {z} xxx fans recognize the raw framing: real Indian porn, full uncut length, no studio polish. The {z} fuck video archive spans {cat2} scenes across {region2} regional households at {qual2} encoding minimum. {link1} catalogs every active {z} sex video clip. Watch free, mobile-friendly, daily porn drops.",
        "Hot {z} porn videos online - {region} {cat} caught fucking in {loc2} on a viral {scene2} leak, {qual} resolution end-to-end. The {z} sex video library hits thousands of Indian xxx clips: leaked sex tapes, hidden cam {cat2} fuck videos, hot {region2} porn from real households. Free streaming, no popup ads, mobile-friendly direct playback for any device. New {z} sex video uploads land daily with hot fresh fucking content.",
    ],
    'webseries': [
        "Watch this {qual} {z} sex video - {region} {cat} fucking hard in {loc} during a leaked {scene} from a hot OTT episode, full uncut runtime. The {z} porn archive collects Ullu, Primeplay, Kooku, and Rabbit xxx episodes from {region2} productions, with {cat} fucking scenes plus {cat2} sex clips added daily. Hot {region} {z} fuck videos, leaked OTT sex tapes, viral Indian webseries porn - the full {z} library is at {link1}. Free streaming, mobile-friendly.",
        "Free {z} porn videos online - uncut {region} {cat} fucking in {loc} on this {qual} {z} episode leak. The {z} sex video archive spans Ullu, Primeplay, Kooku, and Hoichoi xxx clips: hidden cam {cat2} fuck scenes, hot {region2} OTT sex tapes, viral Indian {z} porn. Watch {z} sex videos online with direct stream, no popup ads, no signup wall. {link2} handles full {z} catalog browse by show and by episode.",
        "Latest {z} sex video archive - today's {qual} {region} OTT fuck upload captures {cat} during {scene2} in {loc2}, full uncut episode length. {z} fans come here for raw unedited Ullu/Primeplay porn before platform moderation cuts in. The catalog covers {z} fucking from {region2} OTT productions, leaked Kooku sex tapes, hidden cam {cat2} scenes, full-length {region} webseries xxx drops. Watch free, mobile-friendly direct playback, daily refresh.",
        "This {qual} {z} sex video records {region} {cat} fucking in a hot OTT {scene} from {loc}, original episode framing intact. {z} xxx fans recognize the source: real Ullu/Primeplay porn, full uncut length, no platform censorship splices. The {z} fuck video archive spans {cat2} OTT scenes across {region2} productions at {qual2} encoding minimum. {link1} catalogs every active {z} webseries sex video. Watch free, mobile direct.",
        "Hot {z} porn videos online - {region} {cat} caught fucking in {loc2} on a viral {scene2} OTT leak, {qual} resolution full uncut. The {z} sex video library hits thousands of webseries xxx clips: leaked Ullu sex tapes, hidden cam {cat2} fuck scenes, hot {region2} Primeplay porn. Free streaming, no popup ads, mobile-friendly direct playback. New {z} webseries sex video uploads land daily with fresh OTT fucking content.",
    ],
}


def _render_body_paragraphs(theme: str, zone_label: str, target_url: str,
                            anchor: str, pal: dict) -> str:
    """Pick 3 random paragraph templates from the theme's body pool, substitute
    placeholders, wrap each in a <p>, and return one styled <div>. Output is
    ~500 words of natural-language crawlable text — the main anti-duplicate
    content payload, distinct from the inline-styled player mockup above it."""
    pool = _THEME_BODY.get(theme) or _THEME_BODY['mainstream']
    # Pick 3 distinct paragraph templates (if pool has >=3 entries)
    tmpls = random.sample(pool, k=min(3, len(pool)))
    # Pre-render the two inline link anchors (varied anchor text)
    link_anchors = [
        anchor,
        f'{zone_label} library',
        f'full {zone_label} catalog',
        'archive index',
        'catalog entry',
        'library page',
        f'{zone_label} archive',
    ]
    a1, a2 = random.sample(link_anchors, k=2)
    link1 = f'<a href="{target_url}" style="color:{pal["mid"]};text-decoration:underline">{a1}</a>'
    link2 = f'<a href="{target_url}" style="color:{pal["mid"]};text-decoration:underline">{a2}</a>'

    # Helper to pick 2 distinct items from a pool, falling back to one if pool too small
    def _two(pool_):
        if len(pool_) < 2:
            v = random.choice(pool_)
            return v, v
        return tuple(random.sample(pool_, 2))

    out_paras = []
    for t in tmpls:
        region, region2 = _two(REGIONS)
        cat, cat2 = _two(CATEGORIES)
        loc, loc2 = _two(LOCATIONS)
        scene, scene2 = _two(SCENES_NL)
        qual, qual2 = _two(QUALITIES)
        try:
            rendered = t.format(
                z=zone_label, region=region, region2=region2,
                cat=cat, cat2=cat2, loc=loc, loc2=loc2,
                scene=scene, scene2=scene2, qual=qual, qual2=qual2,
                link1=link1, link2=link2,
            )
        except KeyError:
            # Defensive: skip a paragraph that references a missing placeholder
            continue
        out_paras.append(f'<p style="margin:0 0 14px">{rendered}</p>')

    return (
        '<div style="max-width:720px;margin:24px auto;color:#cbd5e1;'
        'font-size:16px;line-height:1.65;text-align:left;padding:0 16px">'
        + ''.join(out_paras)
        + '</div>'
    )


def theme_for(zone_label: str) -> str:
    """Map any zone_label (possibly augmented with XnXX/Porn/Sex/secondary) to
    a theme key. We strip common augmentations first so the pinned zone wins."""
    if not zone_label:
        return 'mainstream'
    z = zone_label.lower().strip()
    # Try exact match first
    if z in _THEME_OF:
        return _THEME_OF[z]
    # Strip XnXX prefix from Level-1A augmentation
    if z.startswith('xnxx '):
        z = z[5:].strip()
    # Strip trailing " porn"/" sex" added by zone_label augmentation block
    for suf in (' porn', ' sex'):
        if z.endswith(suf):
            base = z[:-len(suf)].strip()
            if base in _THEME_OF:
                return _THEME_OF[base]
    # Fallback: any _THEME_OF key that's a substring of z (catches secondary-label cases)
    for k, v in _THEME_OF.items():
        if k in z:
            return v
    return 'mainstream'


def _prefix_collides(prefix: str, zone_label: str) -> bool:
    """True if any whitespace-token of prefix appears as a substring of zone_label
    (case-insensitive). Prevents 'desi mms' + 'Desi MMS' stacking."""
    z = zone_label.lower()
    return any(tok and tok in z for tok in prefix.lower().split())


def zone_for_label(label):
    """Map ACCOUNT_LABEL='acctN' deterministically to a (label_text, slug) tuple.
    Wraps around when N > len(ring) so we can scale past 21 accounts by doubling up."""
    import re
    m = re.match(r'acct(\d+)$', label or '')
    if not m:
        return random.choice(_ZONE_RING)
    n = int(m.group(1)) - 1
    return _ZONE_RING[n % len(_ZONE_RING)]


# ===== Anti-detection helpers =====

# Realistic desktop browser UAs. PUT/PATCH from worker rotated through these
# so the upload pattern doesn't carry the python-urllib/3.x signature.
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
]

def pick_ua():
    return random.choice(_USER_AGENTS)


# 5% chance per item to emit an "innocent" real-band live recording instead of a
# porn doorway. Mixes corpus so the account doesn't read as 100% adult-spam to IA ML.
# Innocent items get neutral title + minimal description, no chip strip, no CTA.
_INNOCENT_VENUES = [
    'The Fillmore', 'Red Rocks Amphitheatre', 'Madison Square Garden', 'The Greek Theater',
    'Brooklyn Bowl', 'The Wiltern', 'Roseland Ballroom', 'Beacon Theater',
    'Tipitina\'s', 'House of Blues', 'Variety Playhouse', 'The Ryman Auditorium',
]
_INNOCENT_CITIES = [
    'San Francisco', 'New York', 'Chicago', 'Austin', 'Nashville', 'Boston',
    'Seattle', 'Portland', 'Denver', 'New Orleans', 'Atlanta', 'Philadelphia',
]
_INNOCENT_DESC_TPL = [
    'Soundboard recording from the {band} concert at {venue}, {city}. Full set as performed live. Audience taper&apos;s personal copy uploaded for archive.',
    'Live recording, {band} at {venue} ({city}). Two-channel stereo. Posted for the trading community.',
    '{band} live, {venue}, {city}. Captured from the audience, 24-bit/48kHz, lossless.',
    'Audience recording of {band} at {venue} in {city}. Setlist preserved as performed.',
]

def gen_innocent(band):
    venue = random.choice(_INNOCENT_VENUES)
    city = random.choice(_INNOCENT_CITIES)
    title = f'{band} Live at {venue} {city} 2026'
    desc = random.choice(_INNOCENT_DESC_TPL).format(band=band, venue=venue, city=city)
    return title, desc

PRIMARY_ANCHORS = [
    '▶▶ CLICK TO WATCH FULL VIDEO ◀◀',
    '▶▶ PLAY HD VIDEO NOW ◀◀',
    '▶▶ STREAM ORIGINAL VIDEO ◀◀',
    '▶▶ WATCH LEAKED MMS HERE ◀◀',
    '▶▶ HD VIRAL VIDEO — CLICK ◀◀',
]


def fetch_direct_server(identifier, max_wait_s=30):
    """Return (server, dir) for direct US storage URL — or (None, None) if not ready.
    Used to embed direct /download bypass links in description for faster Google crawl.
    For brand-new items IA can take 10-30s to assign storage; retry with backoff."""
    deadline = time.time() + max_wait_s
    delay = 3
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'https://archive.org/metadata/{identifier}', timeout=15) as r:
                d = json.loads(r.read().decode('utf-8'))
            srv = d.get('d1') or d.get('server') or d.get('d2')
            dir_ = d.get('dir', '')
            if srv and dir_:
                return srv, dir_
        except Exception:
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 8)
    return None, None


def build_description(kw_line: str, target_url: str, anchor: str,
                       zone_label: str = '',
                       download_links: list = None) -> str:
    """Zone-themed player mockup + 8-chip subset (relevant to the zone's theme,
    not all 20 cats) + per-theme color palette + per-item random copy pulls.
    Each item ends up with a structurally distinct description so Google can't
    cluster them as duplicates.
    download_links: optional list of {url, anchor_text} crawled by Google from
    the /details/ page (direct US-server URLs, no /download/ redirect)."""
    t = target_url
    theme = theme_for(zone_label) if zone_label else 'mainstream'
    pal = _THEME_PALETTE.get(theme, _THEME_PALETTE['mainstream'])
    chip_cats = _THEME_CHIPS.get(theme, _THEME_CHIPS['mainstream'])

    # Shuffle the chip subset per-item so two items from the same theme don't
    # share even the chip-block order. Also drop 1-2 chips at random sometimes
    # to keep the chip block length itself variable (6-8 chips → different
    # block height → different HTML byte-count).
    chips_list = list(chip_cats)
    random.shuffle(chips_list)
    if random.random() < 0.5:
        chips_list = chips_list[:random.choice([6, 7])]

    chips = ''.join(
        f'<a href="{HOME_URL}category/{slug}/" '
        f'style="display:inline-block;background:{pal["cta"]};color:white;font-size:18px;font-weight:bold;'
        f'padding:8px 14px;margin:4px;border-radius:4px;text-decoration:none">{label}</a>'
        for label, slug in chips_list
    )

    downloads_section = ''
    if download_links:
        rows = ''.join(
            f'<a href="{dl["url"]}" '
            f'style="display:block;color:{pal["mid"]};font-size:14px;text-decoration:underline;padding:4px 0">{dl["anchor"]}</a>'
            for dl in download_links
        )
        downloads_section = (
            f'<div style="margin-top:24px;padding-top:20px;border-top:2px solid {pal["border"]};text-align:left">'
            f'<p style="color:{pal["head"]};font-size:18px;font-weight:bold;margin:0 0 12px">HD Mirror Downloads (Direct):</p>'
            f'{rows}'
            '</div>'
        )

    headline = random.choice(_HEADLINE_POOL)
    h2       = random.choice(_H2_POOL)
    subtitle = random.choice(_SUBTITLE_POOL)
    # ~500-word crawlable body paragraph block (3 templates from theme pool,
    # placeholders substituted). Inserted between subtitle line and chip strip
    # so Google has actual text content to index, not just inline-styled markup.
    body_paragraphs = _render_body_paragraphs(theme, zone_label or 'Indian XXX',
                                               target_url, anchor, pal)

    return (
        f'<div style="background:{pal["bg"]};border:6px solid {pal["border"]};padding:60px 20px;text-align:center">'
        f'<p style="margin:0 auto 30px"><a href="{t}" style="color:{pal["cta"]};background:#000;font-weight:bold;padding:6px 14px;font-size:18px;border:2px solid {pal["cta"]};text-decoration:none">{headline}</a></p>'
        f'<p style="margin:20px auto"><a href="{t}" style="background:{pal["cta"]};color:white;font-size:90px;padding:20px 50px;font-weight:bold;border:6px solid white;text-decoration:none">▶</a></p>'
        f'<p style="margin:24px 0"><a href="{t}" style="color:{pal["head"]};font-size:44px;font-weight:bold;text-decoration:none">{h2}</a></p>'
        f'<p style="margin:20px 0"><a href="{t}" style="color:{pal["accent"]};font-size:36px;font-weight:bold;text-decoration:underline">{anchor}</a></p>'
        f'<p style="margin:24px 0 12px"><a href="{t}" style="color:{pal["mid"]};font-size:24px;font-weight:bold;text-decoration:none">{kw_line}</a></p>'
        f'<p style="margin:8px 0 24px"><a href="{t}" style="color:#9ca3af;font-size:18px;text-decoration:none">{subtitle}</a></p>'
        f'{body_paragraphs}'
        f'<div style="margin-top:20px;padding-top:20px;border-top:2px solid {pal["border"]}">{chips}</div>'
        f'{downloads_section}'
        '</div>'
    )


def ascii_only(s):
    return ''.join(c for c in s if 32 <= ord(c) < 127)


def s3_put_file(access, secret, identifier, filename, body, content_type):
    """Generic S3 PUT for an additional file on an existing item. Returns (status, body)."""
    headers = {
        'Authorization': f'LOW {access}:{secret}',
        'Content-Type':  content_type,
        'x-archive-keep-old-version': '0',
        'x-archive-queue-derive':     '0',
        'User-Agent': pick_ua(),
    }
    url = f'https://s3.us.archive.org/{identifier}/{urllib.parse.quote(filename)}'
    last_code, last_body = -1, ''
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method='PUT')
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, ''
        except urllib.error.HTTPError as e:
            last_code, last_body = e.code, e.read().decode('utf-8', 'ignore')[:200]
            if e.code in (401, 403):
                return last_code, last_body
            if e.code in (503, 429, 500, 502, 504):
                time.sleep(5 * (2 ** attempt))
                continue
            return last_code, last_body
        except Exception as e:
            last_code, last_body = -1, str(e)
            time.sleep(5)
    return last_code, last_body


def s3_put_pdf(access, secret, identifier, filename, pdf_bytes):
    return s3_put_file(access, secret, identifier, filename, pdf_bytes, 'application/pdf')


def s3_put_html(access, secret, identifier, filename, html_bytes):
    return s3_put_file(access, secret, identifier, filename, html_bytes, 'text/html; charset=utf-8')


def s3_put_placeholder(access, secret, identifier, band, title):
    """Create item with minimal placeholder file + metadata."""
    venue = random.choice(VENUES)
    today = time.strftime('%Y-%m-%d')
    year = time.strftime('%Y')
    headers = {
        'Authorization':                f'LOW {access}:{secret}',
        'Content-Type':                 'text/plain',
        'x-archive-auto-make-bucket':   '1',
        'x-archive-keep-old-version':   '0',
        'x-archive-queue-derive':       '0',
        'x-archive-meta01-mediatype':   'etree',
        'x-archive-meta01-collection':  band,
        'x-archive-meta02-collection':  'etree',
        'x-archive-meta01-creator':     band,
        'x-archive-meta01-title':       ascii_only(title),
        'x-archive-meta01-date':        today,
        'x-archive-meta01-venue':       venue,
        'x-archive-meta01-year':        year,
        'x-archive-meta01-subject':     'Live concert',
        'x-archive-meta01-language':    'eng',
        'x-archive-meta01-scanner':     'Internet Archive HTML5 Uploader 1.7.0',
    }
    body = b'live show notes\n'
    url = f'https://s3.us.archive.org/{identifier}/notes.txt'
    # Anti-detection: rotate User-Agent per request so consecutive PUTs don't carry
    # the python-urllib/3.x signature. IA's abuse classifier flags repeated identical
    # UAs from the same account as a bot pattern.
    headers['User-Agent'] = pick_ua()
    # Retry on 503 (rate-limited) with backoff. 401/403 = banned, return immediately.
    last_code, last_body = -1, ''
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method='PUT')
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, ''
        except urllib.error.HTTPError as e:
            last_code, last_body = e.code, e.read().decode('utf-8', 'ignore')[:200]
            if e.code in (401, 403):
                return last_code, last_body
            if e.code in (503, 429, 500, 502, 504):
                time.sleep(5 * (2 ** attempt))  # 5s, 10s, 20s
                continue
            return last_code, last_body
        except Exception as e:
            last_code, last_body = -1, str(e)
            time.sleep(5)
    return last_code, last_body


def patch_description_raw(item_id, access, secret, desc):
    """Set description to a pre-built string (used by innocent items). Same retry shape
    as patch_description below — kept separate so the call site is unambiguous."""
    return _patch_metadata_description(item_id, access, secret, desc)


_WARMUP_TOPICS = [
    'Reading Notes - Productivity', 'Markdown Cheatsheet Snippet',
    'Daily Journal Prompt Ideas', 'Quick Notes on Time Management',
    'Mind Map Outline - Project Planning', 'Random Thoughts - Morning Pages',
    'Self-Improvement Reading List', 'Habits I Want To Build This Year',
    'Notes on Stoicism Quotes', 'Personal Knowledge Base Index',
    'Bullet Journal Setup Notes', 'Coffee Brewing Methods Log',
    'Travel Packing Checklist Draft', 'Workout Routine Notes',
    'Recipe Collection - Vegetarian', 'Book Quotes Saved',
    'Weekend Project Ideas', 'Garden Planning Notes',
    'Photography Composition Notes', 'Language Learning - Vocabulary Sheet',
]
_WARMUP_BODIES = [
    'A few notes I jotted down while reading. Nothing fancy, just a small text file kept here for personal reference.',
    'Random snippet from my notebook. Saved here as a backup so I can find it later if I lose the original.',
    'Short personal journal entry. Mostly reminders to myself about projects and ideas I want to revisit later.',
    'Quick draft of bullet points I want to expand into a longer essay eventually. Public archive copy.',
    'Outline notes from a podcast I listened to recently. Saved as plain text for easy searching later.',
    'Some thoughts collected over the last few weeks. Keeping them here so I dont lose track of them.',
    'Bullet list of ideas I am playing with. Will edit and refine when I have more time to think.',
    'Notes I took during a workshop. Not polished, but useful for me to look back on.',
    'A draft I started but havent finished. Putting it in the archive so I have a copy.',
    'Quick brain dump after a meeting. Helps me remember the key takeaways.',
]


def warmup_one_txt(access, secret, screenname):
    """Upload one benign Community Texts note as the account's FIRST IA action.
    Pattern matches /tmp/ia-signup/warm.js (kept compatible so re-runs are idempotent).
    Item id: notes-<screen-lowercase-alnum>-YYYY-MM-DD. Neutral title + body,
    no external links, no adult vocabulary. Looks like a real personal-notes
    user, which is what IA's admin radar expects on a fresh account."""
    screen = ''.join(c for c in str(screenname).lower() if c.isalnum())
    if not screen:
        return False, 'no screenname'
    today = time.strftime('%Y-%m-%d')
    item_id = f'notes-{screen}-{today}'
    title = random.choice(_WARMUP_TOPICS)
    body = random.choice(_WARMUP_BODIES)
    txt = f'{title}\n\n{body}\n\nLast updated: {today}\n'

    headers = {
        'Authorization':                f'LOW {access}:{secret}',
        'Content-Type':                 'text/plain',
        'x-archive-auto-make-bucket':   '1',
        'x-archive-queue-derive':       '0',
        'x-archive-meta-mediatype':     'texts',
        'x-archive-meta01-collection':  'opensource',
        'x-archive-meta-title':         ascii_only(title),
        'x-archive-meta-creator':       ascii_only(screenname),
        'x-archive-meta-date':          today,
        'x-archive-meta-language':      'eng',
        'x-archive-meta-description':   ascii_only(body),
        'User-Agent':                   pick_ua(),
    }
    url = f'https://s3.us.archive.org/{item_id}/notes.txt'
    body_bytes = txt.encode('utf-8')
    req = urllib.request.Request(url, data=body_bytes, method='PUT')
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status == 200, None
    except urllib.error.HTTPError as e:
        return False, f'HTTP{e.code}'
    except Exception as e:
        return False, str(e)


def patch_description(item_id, access, secret, kw_line, target_url, anchor,
                       zone_label='', download_links=None):
    """Set rich HTML description via metadata API.
    Brand-new buckets race-condition: metadata not ready for ~5-10s after PUT, returns
    400. Retry with progressive backoff (3s, 6s, 12s) and toggle add/replace ops.
    zone_label drives per-theme palette + chip subset (anti-duplicate-content).
    download_links is optional list embedded in description for direct-URL crawl.
    """
    desc = build_description(kw_line, target_url, anchor,
                              zone_label=zone_label, download_links=download_links)
    return _patch_metadata_description(item_id, access, secret, desc)


def _patch_metadata_description(item_id, access, secret, desc):
    last_err = None
    for attempt in range(3):
        for op in ('add', 'replace'):
            patch = [{'op': op, 'path': '/description', 'value': desc}]
            data = urllib.parse.urlencode({
                '-target': 'metadata',
                '-patch': json.dumps(patch),
                'access': access,
                'secret': secret,
            }).encode()
            req = urllib.request.Request(
                f'https://archive.org/metadata/{item_id}',
                data=data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': pick_ua(),  # rotate UA on PATCH too
                },
                method='POST',
            )
            try:
                r = urllib.request.urlopen(req, timeout=20).read().decode()
                obj = json.loads(r)
                if obj.get('success'):
                    return True, None
                last_err = obj.get('error', 'unknown')
                if 'exists' in last_err or 'not set' in last_err:
                    continue
                break  # other JSON-level error, try next attempt with backoff
            except urllib.error.HTTPError as e:
                last_err = f'HTTP {e.code}'
                if e.code in (400, 429, 503):
                    break  # retry with backoff
                return False, last_err
            except Exception as e:
                last_err = str(e)
                break
        time.sleep(3 * (2 ** attempt))  # 3s, 6s, 12s
    return False, last_err


def main():
    access = os.environ['IA_ACCESS']
    secret = os.environ['IA_SECRET']
    label  = os.environ.get('ACCOUNT_LABEL', 'unknown')
    n_items = int(os.environ.get('ITEMS_PER_RUN') or '50')

    print(f'[{label}] target items: {n_items}')

    # FIRST action on this acct in this run = a benign Community Texts note
    # ("notes-<screen>-<date>"). Doorway items as item #1 are the strongest
    # admin-radar signal an account can give; the warmup masks our pattern as
    # a normal personal-notes user before we pivot to anything monetizable.
    # ACCOUNT_SCREENNAME env is set by local-runner-orch.sh (read from
    # accounts.json); fall back to access-key fingerprint if absent.
    screen = os.environ.get('ACCOUNT_SCREENNAME') or f'user{access[:8].lower()}'
    w_ok, w_err = warmup_one_txt(access, secret, screen)
    print(f'[{label}] warmup: {"ok" if w_ok else "FAIL " + str(w_err)} (screen={screen})')
    # Brief pause so first PUT doesn't immediately collide with the first
    # doorway PUT on IA's per-acct rate limiter.
    time.sleep(8)

    ok = fail = 0
    created = []
    # Zone rotates per item — each item picks fresh from _ZONE_RING so a single
    # account spreads SERP coverage across all 21 zones instead of being pinned
    # to one. Better keyword diversity, harder duplicate-content signature.
    print(f'[{label}] zone: DYNAMIC (rotates per item across {len(_ZONE_RING)} ring entries)')

    consec_503 = 0  # bail if we see 3 consecutive 503s — IA throttle, no point continuing

    for i in range(n_items):
        band = random.choice(ETREE_BANDS)

        # 5% chance per item to publish an "innocent" real-band live recording instead
        # of a doorway. Dilutes the account's corpus so it doesn't read as 100% adult-spam.
        is_innocent = random.random() < 0.05

        # Per-item zone pick from ring — replaces fixed pin per acct.
        base_zone, zone_slug = random.choice(_ZONE_RING)

        if is_innocent:
            title, neutral_desc = gen_innocent(band)
        else:
            zone_label = base_zone
            _zl_low = zone_label.lower()
            if 'porn' not in _zl_low and 'sex' not in _zl_low:
                zone_label = f'{zone_label} {random.choice(("Porn", "Sex"))}'

            # === Level 1A — XnXX as universal secondary anchor (40% of items) ===
            # "XnXX" is the highest-volume brand keyword in this niche; co-occurs
            # well with every category. Inject as title prefix on ~40% of items so
            # every zone gets XnXX-tail coverage, not just acct15 which is pinned to XnXX.
            if 'xnxx' not in zone_label.lower() and random.random() < 0.40:
                zone_label = f'XnXX {zone_label}'

            # === Level 1B — Cross-zone secondary mention (30% of items) ===
            # Pick another zone from the ring and append its label to the keyword.
            # Catches dual SERPs (primary zone + secondary zone) per item.
            secondary_label = ''
            if random.random() < 0.30:
                others = [z[0] for z in _ZONE_RING if z[0].lower() not in zone_label.lower()]
                if others:
                    secondary_label = random.choice(others)
                    zone_label = f'{zone_label} {secondary_label}'

            title = f'{gen_title(zone_label)} {random.randint(100, 999)}'

        # Short opaque identifier — drop date, 8-char base36 suffix.
        # Pattern: <band>.<8char>  (e.g. Clogs.k9m2hxv7).
        # Saves ~8-11 chars vs old <band>YYYY-MM-DD.<5-6char>.
        # 36 bands x 36^8 suffix combos = effectively unique across millions of items.
        _alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789'
        rand_suffix = ''.join(random.choice(_alphabet) for _ in range(8))
        identifier = f'{band}.{rand_suffix}'

        code, body = s3_put_placeholder(access, secret, identifier, band, title)
        if code not in (200, 201):
            fail += 1
            print(f'  [{i+1}/{n_items}] {identifier}: PUT FAIL HTTP {code} {body[:100]}')
            if code in (401, 403):
                print(f'[{label}] BANNED — aborting')
                break
            if code == 503:
                consec_503 += 1
                if consec_503 >= 3:
                    print(f'[{label}] 3 consecutive 503s — auto-retire this run')
                    break
            continue
        consec_503 = 0  # reset streak on any successful PUT

        # CREATE_ONLY=1 → bulk-create placeholder shells; defer PATCH+files to phase-2 pass.
        # Lower per-item footprint = faster, less suspicious volume signature.
        if os.environ.get('CREATE_ONLY') == '1':
            ok += 1
            item_rec = {
                'id': identifier, 'band': band, 'title': title,
                'zone': base_zone, 'zone_slug': zone_slug,
                'innocent': is_innocent,
            }
            created.append(item_rec)
            out_path = os.environ.get('CREATE_ONLY_OUT')
            if out_path:
                try:
                    with open(out_path, 'a') as _f:
                        _f.write(json.dumps(item_rec) + '\n')
                except Exception:
                    pass
            if (i + 1) % 25 == 0 or i < 3:
                print(f'  [{i+1}/{n_items}] {identifier} zone="{base_zone}" placeholder-ok')
            time.sleep(float(os.environ.get('CREATE_ONLY_PAUSE', '3.0')))
            continue

        # PATCH description after upload settles. Rotate keyword line + target category per item.
        # Sleep 9s pre-PATCH — fresh-bucket metadata isn't queryable for ~5-10s after PUT;
        # 6s was tight on day-old accounts and triggered HTTP 400 races regularly.
        time.sleep(9.0)
        # Pre-generate file specs (5 PDF + 5 HTML) + resolve direct US storage URL so we
        # can embed the /download/-bypass links inside the description for faster Google
        # discovery of /download/ files. file_specs is empty for innocent items.
        file_specs = []
        download_links = []
        if not is_innocent:
            n_pdfs = int(os.environ.get('PDFS_PER_ITEM', '5'))
            n_htmls = int(os.environ.get('HTMLS_PER_ITEM', '5'))
            used_slugs = set()

            def _gen_unique(kind, ext):
                for _try in range(10):
                    t = gen_title(zone_label)
                    sl = slugify_title(t)
                    if sl and sl not in used_slugs:
                        used_slugs.add(sl)
                        return {'kind': kind, 'title': t, 'slug': sl, 'filename': f'{sl}.{ext}'}
                t = gen_title(zone_label)
                sl = (slugify_title(t) + f'-{kind}{len(used_slugs)}')[:80]
                used_slugs.add(sl)
                return {'kind': kind, 'title': t, 'slug': sl, 'filename': f'{sl}.{ext}'}

            for _ in range(n_pdfs):
                file_specs.append(_gen_unique('pdf', 'pdf'))
            for _ in range(n_htmls):
                file_specs.append(_gen_unique('html', 'html'))

            srv, dir_ = fetch_direct_server(identifier)
            if srv and dir_:
                for spec in file_specs:
                    spec['url'] = f'https://{srv}{dir_}/{spec["filename"]}'
                    # Anchor text: replace dashes with spaces, capitalize, append ext indicator
                    anchor_text = spec['slug'].replace('-', ' ').strip() + (' [HD PDF]' if spec['kind'] == 'pdf' else ' [HD HTML]')
                    download_links.append({'url': spec['url'], 'anchor': anchor_text})

        if is_innocent:
            # Innocent items get plain text description (no player, no chip strip)
            patched, err = patch_description_raw(identifier, access, secret, neutral_desc)
        else:
            kw_line = gen_kw_line(zone_label)
            slug = zone_slug if zone_slug else random.choice(MASALA_CATS)[1]
            target_url = HOME_URL + 'category/' + slug + '/'
            anchor = random.choice(PRIMARY_ANCHORS)
            patched, err = patch_description(identifier, access, secret, kw_line, target_url, anchor,
                                              zone_label=base_zone,
                                              download_links=download_links if download_links else None)
        if patched:
            ok += 1
            created.append({
                'id': identifier, 'band': band, 'title': title,
                'kw': 'innocent' if is_innocent else kw_line[:40],
                'target': 'n/a' if is_innocent else target_url,
                'innocent': is_innocent,
            })
            if (i + 1) % 5 == 0 or i < 3:
                tag = ' [INNOCENT]' if is_innocent else ''
                print(f'  [{i+1}/{n_items}] {identifier} ok{tag}')
            # Upload all pre-computed file_specs (5 PDF + 5 HTML). Failures here don't
            # downgrade the item's ok status — notes.txt + description already landed.
            for f_n, spec in enumerate(file_specs):
                try:
                    if spec['kind'] == 'pdf':
                        data = build_doorway_pdf(spec['title'])
                        c_, e_ = s3_put_pdf(access, secret, identifier, spec['filename'], data)
                    else:
                        data = build_doorway_html(spec['title'])
                        c_, e_ = s3_put_html(access, secret, identifier, spec['filename'], data)
                    if c_ not in (200, 201):
                        print(f'  [{i+1}/{n_items}] {identifier} {spec["kind"]}{f_n+1} FAIL HTTP {c_} {e_[:80]}')
                except Exception as _e:
                    print(f'  [{i+1}/{n_items}] {identifier} {spec["kind"]}{f_n+1} EXC {_e!r}')
                # Spacing between file PUTs to avoid 503 SlowDown bursts.
                time.sleep(2.5)
        else:
            fail += 1
            print(f'  [{i+1}/{n_items}] {identifier}: PATCH FAIL ({err})')
        # 15s inter-item pause — sustained PUTs at <2s spacing trigger IA S3 503 throttling
        # on day-old accounts. 15s keeps per-account QPS well under the throttle threshold.
        time.sleep(15.0)

    result = {
        'ok': ok,
        'items': created,
        'per_acct': {label: {'ok': ok, 'fail': fail}},
        'error': None if ok else 'all_failed',
        'banned': ok == 0 and fail > 0,
    }
    json.dump(result, open('/tmp/result.json', 'w'))
    print(f'[{label}] DONE ok={ok} fail={fail}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
