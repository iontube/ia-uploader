#!/usr/bin/env python3
"""GH Actions worker — one account, ITEMS_PER_RUN /details/ items per run.

No PDFs. Each item = 1 tiny placeholder file (S3 needs ≥1 file to materialize the bucket).
Description is set via metadata PATCH AFTER initial upload (description in initial PUT
headers gets truncated when long; PATCH handles full HTML reliably).

Reads env:
  IA_ACCESS, IA_SECRET     — single account credentials
  ACCOUNT_LABEL            — for stats/logging
  ITEMS_PER_RUN            — items per worker invocation (default 30)
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


# Title pattern functions — each returns a unique combination. Picked at random per item.
def _t1(): return f'{_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t2(): return f'{_r(REGIONS)} {_r(SCENES)} {_r(QUALITIES)}'
def _t3(): return f'{_r(QUALITIES)} {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t4(): return f'{_r(BRANDS)} {_r(REGIONS)} {_r(SCENES)}'
def _t5(): return f'{_r(BRANDS)} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)}'
def _t6(): return f'{_r(LOCATIONS)} {_r(CATEGORIES)} {_r(SCENES)}'
def _t7(): return f'{_r(LOCATIONS)} {_r(CATEGORIES)} Caught {_r(SCENES)}'
def _t8(): return f'{_r(REGIONS)} {_r(CATEGORIES)} Viral Kand {_r(QUALITIES)}'
def _t9(): return f'{_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)} 2026'
def _t10(): return f'{_r(BRANDS)} {_r(REGIONS)} {_r(CATEGORIES)} {_r(QUALITIES)}'
def _t11(): return f'Hot {_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)} {_r(QUALITIES)}'
def _t12(): return f'{_r(REGIONS)} {_r(CATEGORIES)} {_r(SCENES)} - {_r(BRANDS)}'
def _t13(): return f'{_r(QUALITIES)} {_r(BRANDS)} {_r(SCENES)} {_r(REGIONS)}'
def _t14(): return f'{_r(REGIONS)} {_r(CATEGORIES)} Affair {_r(SCENES)} HD'
def _t15(): return f'New {_r(REGIONS)} {_r(SCENES)} {_r(QUALITIES)} {_r(BRANDS)}'

_TITLE_FNS = [_t1, _t2, _t3, _t4, _t5, _t6, _t7, _t8, _t9, _t10, _t11, _t12, _t13, _t14, _t15]


def gen_title():
    return random.choice(_TITLE_FNS)()


def gen_kw_line():
    """5-7 tags mixing all seed pools, joined with ' • '."""
    pool = []
    pool += random.sample(REGIONS, k=2)
    pool += random.sample(CATEGORIES, k=2)
    pool += [_r(SCENES)]
    pool += [_r(BRANDS)]
    if random.random() < 0.5:
        pool += [_r(LOCATIONS)]
    random.shuffle(pool)
    return ' • '.join(pool)

# 3 money sites — rotated per item; each /details/ has ONE link in the player (no secondary).
TARGET_URLS = [
    'https://masalatube1.com/',
    'https://auntymazaporn1.com/',
    'https://auntymazaporn.com/',
]

PRIMARY_ANCHORS = [
    '▶▶ CLICK TO WATCH FULL VIDEO ◀◀',
    '▶▶ PLAY HD VIDEO NOW ◀◀',
    '▶▶ STREAM ORIGINAL VIDEO ◀◀',
    '▶▶ WATCH LEAKED MMS HERE ◀◀',
    '▶▶ HD VIRAL VIDEO — CLICK ◀◀',
]


def build_description(kw_line: str, target_url: str, anchor: str) -> str:
    """Player-mockup CTA. Every text element wrapped in <a> so entire player is clickable
    (sanitizer-friendly — flat anchors, no nested-wrap rewriting)."""
    t = target_url  # short alias
    return (
        '<div style="background:#0a0a0a;border:6px solid #dc2626;padding:60px 20px;text-align:center">'
        f'<p style="margin:0 auto 30px"><a href="{t}" style="color:#dc2626;background:#000;font-weight:bold;padding:6px 14px;font-size:18px;border:2px solid #dc2626;text-decoration:none">● LIVE HD 1080p ●</a></p>'
        f'<p style="margin:20px auto"><a href="{t}" style="background:#dc2626;color:white;font-size:90px;padding:20px 50px;font-weight:bold;border:6px solid white;text-decoration:none">▶</a></p>'
        f'<p style="margin:24px 0"><a href="{t}" style="color:#fbbf24;font-size:44px;font-weight:bold;text-decoration:none">🔥 HD VIRAL LEAKED VIDEO 🔥</a></p>'
        f'<p style="margin:20px 0"><a href="{t}" style="color:#16a34a;font-size:36px;font-weight:bold;text-decoration:underline">{anchor}</a></p>'
        f'<p style="margin:24px 0 12px"><a href="{t}" style="color:#06b6d4;font-size:24px;font-weight:bold;text-decoration:none">{kw_line}</a></p>'
        f'<p style="margin:8px 0"><a href="{t}" style="color:#9ca3af;font-size:18px;text-decoration:none">Free Streaming • Updated 2026 • Original HD Video</a></p>'
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
    req = urllib.request.Request(url, data=body, method='PUT')
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, ''
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'ignore')[:200]
    except Exception as e:
        return -1, str(e)


def patch_description(item_id, access, secret, kw_line, target_url, anchor):
    """Set rich HTML description via metadata API. Try add first, fall back to replace."""
    desc = build_description(kw_line, target_url, anchor)
    last_err = None
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
            return False, last_err
        except urllib.error.HTTPError as e:
            last_err = f'HTTP {e.code}'
            if e.code in (400, 429):
                time.sleep(2)
                continue
            return False, last_err
        except Exception as e:
            return False, str(e)
    return False, last_err


def main():
    access = os.environ['IA_ACCESS']
    secret = os.environ['IA_SECRET']
    label  = os.environ.get('ACCOUNT_LABEL', 'unknown')
    n_items = int(os.environ.get('ITEMS_PER_RUN') or '30')

    print(f'[{label}] target items: {n_items}')

    ok = fail = 0
    created = []
    for i in range(n_items):
        band = random.choice(ETREE_BANDS)
        title = f'{gen_title()} {random.randint(100, 999)}'
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

        # PATCH description after upload settles. Rotate keyword line + target per item.
        kw_line = gen_kw_line()
        target_url = random.choice(TARGET_URLS)
        anchor = random.choice(PRIMARY_ANCHORS)
        time.sleep(2.0)
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
        time.sleep(0.5)

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
