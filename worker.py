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

ETREE_BANDS = [
    'Strangefolk', 'AcidMothersTemple', 'WidespreadPanic',
    'BirthMusic', 'BenTraverse', 'TheTravelinKine',
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

# Zones for title/keyword bias. Restricted to user-requested SEO focus:
# Desi MMS (with /category/desi-mms/ alignment) + XnXX (fallback random category).
# Porn/Sex anchor word is appended automatically downstream in main loop.
ZONES = [
    ('Desi MMS', 'desi-mms'),
    ('XnXX',     None),
]

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


def patch_description(item_id, access, secret, kw_line, target_url, anchor):
    """Set rich HTML description via metadata API.
    Brand-new buckets race-condition: metadata not ready for ~5-10s after PUT, returns
    400. Retry with progressive backoff (3s, 6s, 12s) and toggle add/replace ops.
    """
    desc = build_description(kw_line, target_url, anchor)
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
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
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

    ok = fail = 0
    created = []
    for i in range(n_items):
        band = random.choice(ETREE_BANDS)
        zone_label, zone_slug = random.choice(ZONES)
        # Always carry "Porn" or "Sex" in the zone keyword (porn-vocab anchor for SERP).
        # Skip if the zone already contains either word to avoid "Desi Porn Porn".
        _zl_low = zone_label.lower()
        if 'porn' not in _zl_low and 'sex' not in _zl_low:
            zone_label = f'{zone_label} {random.choice(("Porn", "Sex"))}'
        title = f'{gen_title(zone_label)} {random.randint(100, 999)}'
        suffix = f'{label}-{int(time.time())%100000}-{random.randint(100, 9999)}'
        today = time.strftime('%Y-%m-%d')
        identifier = f'{band}{today}.{suffix}'

        code, body = s3_put_placeholder(access, secret, identifier, band, title)
        if code not in (200, 201):
            fail += 1
            print(f'  [{i+1}/{n_items}] {identifier}: PUT FAIL HTTP {code} {body[:100]}')
            if code in (401, 403):
                print(f'[{label}] BANNED — aborting')
                break
            continue

        # PATCH description after upload settles. Rotate keyword line + target category per item.
        # Sleep 9s pre-PATCH — fresh-bucket metadata isn't queryable for ~5-10s after PUT;
        # 6s was tight on day-old accounts and triggered HTTP 400 races regularly.
        kw_line = gen_kw_line(zone_label)
        # Align player CTA with the chosen zone where possible; fallback random for XnXX.
        slug = zone_slug if zone_slug else random.choice(MASALA_CATS)[1]
        target_url = HOME_URL + 'category/' + slug + '/'
        anchor = random.choice(PRIMARY_ANCHORS)
        time.sleep(9.0)
        patched, err = patch_description(identifier, access, secret, kw_line, target_url, anchor)
        if patched:
            ok += 1
            created.append({
                'id': identifier, 'band': band, 'title': title,
                'kw': kw_line[:40], 'target': target_url,
            })
            if (i + 1) % 5 == 0 or i < 3:
                print(f'  [{i+1}/{n_items}] {identifier} ok')
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
