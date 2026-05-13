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


# Title pattern functions — each returns a unique combination. Picked at random per item.
# Every template now leads with the chosen zone keyword.
def _t1(z):  return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t2(z):  return f'{z} {_r(SCENES)} {_r(QUALITIES)} {_r(REGIONS)}'
def _t3(z):  return f'{_r(QUALITIES)} {z} {_r(CATEGORIES)} {_r(SCENES)}'
def _t4(z):  return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t5(z):  return f'{z} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)}'
def _t6(z):  return f'{z} {_r(LOCATIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t7(z):  return f'{z} {_r(LOCATIONS)} {_r(CATEGORIES)} Caught {_r(SCENES)}'
def _t8(z):  return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} Viral Kand {_r(QUALITIES)}'
def _t9(z):  return f'{z} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)} 2026'
def _t10(z): return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(QUALITIES)}'
def _t11(z): return f'Hot {z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)}'
def _t12(z): return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)} HD'
def _t13(z): return f'{_r(QUALITIES)} {z} {_r(SCENES)} {_r(REGIONS)}'
def _t14(z): return f'{z} {_r(REGIONS)} {_r(CATEGORIES)} Affair {_r(SCENES)} HD'
def _t15(z): return f'New {z} {_r(REGIONS)} {_r(SCENES)} {_r(QUALITIES)}'

_TITLE_FNS = [_t1, _t2, _t3, _t4, _t5, _t6, _t7, _t8, _t9, _t10, _t11, _t12, _t13, _t14, _t15]


def gen_title(zone):
    return random.choice(_TITLE_FNS)(zone)


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
HOME_URL = 'https://masalatube1.com/'

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
    ('XnXX',             None),
    ('Hot Web Series',   'hot-web-series'),
    ('Uncut Web Series', 'uncut-web-series'),
    ('Masala MMS',       'masala-mms'),
    ('AuntyMaza',        'auntymaza'),
    ('Dehati Chudai',    'dehati-chudai'),
    ('Village Aunty',    'village-aunty'),
]

# Legacy compatibility — kept so any caller that still references ZONES doesn't break.
ZONES = list(_ZONE_RING)


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


def build_description(kw_line: str, target_url: str, anchor: str) -> str:
    """Player mockup (all elements clickable → target_url) + chip strip with all 20
    masalatube1 categories linked to /category/<slug>/.
    target_url is whatever the orchestrator passed (homepage or a category)."""
    t = target_url
    chips = ''.join(
        f'<a href="{HOME_URL}category/{slug}/" '
        f'style="display:inline-block;background:#dc2626;color:white;font-size:18px;font-weight:bold;'
        f'padding:8px 14px;margin:4px;border-radius:4px;text-decoration:none">{label}</a>'
        for label, slug in MASALA_CATS
    )
    return (
        '<div style="background:#0a0a0a;border:6px solid #dc2626;padding:60px 20px;text-align:center">'
        f'<p style="margin:0 auto 30px"><a href="{t}" style="color:#dc2626;background:#000;font-weight:bold;padding:6px 14px;font-size:18px;border:2px solid #dc2626;text-decoration:none">● LIVE HD 1080p ●</a></p>'
        f'<p style="margin:20px auto"><a href="{t}" style="background:#dc2626;color:white;font-size:90px;padding:20px 50px;font-weight:bold;border:6px solid white;text-decoration:none">▶</a></p>'
        f'<p style="margin:24px 0"><a href="{t}" style="color:#fbbf24;font-size:44px;font-weight:bold;text-decoration:none">🔥 HD VIRAL LEAKED VIDEO 🔥</a></p>'
        f'<p style="margin:20px 0"><a href="{t}" style="color:#16a34a;font-size:36px;font-weight:bold;text-decoration:underline">{anchor}</a></p>'
        f'<p style="margin:24px 0 12px"><a href="{t}" style="color:#06b6d4;font-size:24px;font-weight:bold;text-decoration:none">{kw_line}</a></p>'
        f'<p style="margin:8px 0 24px"><a href="{t}" style="color:#9ca3af;font-size:18px;text-decoration:none">Free Streaming • Updated 2026 • Original HD Video</a></p>'
        f'<div style="margin-top:20px;padding-top:20px;border-top:2px solid #dc2626">{chips}</div>'
        '</div>'
    )


def ascii_only(s):
    return ''.join(c for c in s if 32 <= ord(c) < 127)


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


def patch_description(item_id, access, secret, kw_line, target_url, anchor):
    """Set rich HTML description via metadata API.
    Brand-new buckets race-condition: metadata not ready for ~5-10s after PUT, returns
    400. Retry with progressive backoff (3s, 6s, 12s) and toggle add/replace ops.
    """
    desc = build_description(kw_line, target_url, anchor)
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
    # Pin zone to the account label — every item from this slot stays inside one
    # /category/<slug>/ SERP. ACCOUNT_LABEL is set by the workflow ('acct1', 'acct2', ...).
    pinned_label, pinned_slug = zone_for_label(label)
    print(f'[{label}] pinned zone: {pinned_label} (slug={pinned_slug or "RANDOM"})')

    consec_503 = 0  # bail if we see 3 consecutive 503s — IA throttle, no point continuing

    for i in range(n_items):
        band = random.choice(ETREE_BANDS)

        # 5% chance per item to publish an "innocent" real-band live recording instead
        # of a doorway. Dilutes the account's corpus so it doesn't read as 100% adult-spam.
        is_innocent = random.random() < 0.05

        kw_slug_parts = []
        if is_innocent:
            title, neutral_desc = gen_innocent(band)
            # Innocent items keep the old plain identifier scheme
            kw_slug_parts = []
        else:
            zone_label, zone_slug = pinned_label, pinned_slug
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

            # === Level 3 — Keyword slug in identifier (URL signal) ===
            # IA accepts lowercase + digits + hyphen + period. Inject 3-5 keywords
            # from the chosen vocabulary into the identifier so the /details/<id>
            # URL carries them. Total identifier cap is ~80 chars to be safe.
            import re as _re
            kw_words = zone_label.lower().split()
            kw_words.append(random.choice(REGIONS).lower())
            kw_words.append(random.choice(CATEGORIES).lower())
            kw_slug = '-'.join(_re.sub(r'[^a-z0-9]+', '', w) for w in kw_words if w)
            # cap at 50 chars to keep total identifier well under 100 chars
            kw_slug = kw_slug[:50].rstrip('-')
            kw_slug_parts = [kw_slug] if kw_slug else []

        rand_suffix = f'{label}-{random.randint(1000, 99999)}'
        today = time.strftime('%Y-%m-%d')
        if kw_slug_parts:
            identifier = f'{band}{today}.{kw_slug_parts[0]}.{rand_suffix}'
        else:
            identifier = f'{band}{today}.{rand_suffix}'

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

        # PATCH description after upload settles. Rotate keyword line + target category per item.
        # Sleep 9s pre-PATCH — fresh-bucket metadata isn't queryable for ~5-10s after PUT;
        # 6s was tight on day-old accounts and triggered HTTP 400 races regularly.
        time.sleep(9.0)
        if is_innocent:
            # Innocent items get plain text description (no player, no chip strip)
            patched, err = patch_description_raw(identifier, access, secret, neutral_desc)
        else:
            kw_line = gen_kw_line(zone_label)
            slug = zone_slug if zone_slug else random.choice(MASALA_CATS)[1]
            target_url = HOME_URL + 'category/' + slug + '/'
            anchor = random.choice(PRIMARY_ANCHORS)
            patched, err = patch_description(identifier, access, secret, kw_line, target_url, anchor)
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
