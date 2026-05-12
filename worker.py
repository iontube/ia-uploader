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

TITLES = [
    # auntymaza niche
    'AuntyMaza Hot Porn Viral Sex Video HD',
    'AuntyMaza Indian Bhabhi Aunty XXX Collection',
    'AuntyMaza Married Aunty MMS Leaked',
    'AuntyMaza Padosi Bhabhi Chudai Video',
    'AuntyMaza Pakistani Aunty Sex HD',
    # desimms niche
    'Desi MMS Viral Leak HD Sex Videos',
    'Desi MMS Hidden Cam Aunty Real',
    'Desi MMS Village Bhabhi Original Video',
    'Desi MMS Whatsapp Viral 2026',
    'Desi MMS Bhabhi Devar Real Affair',
    # hindi bf
    'Hindi BF Porn Viral Collection 2026',
    'Hindi BF Full HD Movie Sex',
    'Hindi BF Audio Bhabhi Chudai',
    'Hindi BF Dehati Randi Sex Video',
    'Hindi BF Bollywood Style XXX',
    # xnxx-india
    'XnXX India Viral MMS Hot Sex Videos',
    'XnXX Desi Aunty Bhabhi Original',
    'XnXX Tamil Telugu Hot Sex Tape',
    'XnXX Pakistani Indian Sex Compilation',
    'XnXX Bollywood Actress Leaked',
    # tamil
    'Tamil Aunty Sex Video HD Viral',
    'Tamil Mami Chudai Hidden Cam',
    'Tamil Chennai Aunty Hot MMS',
    'Tamil Nadu Married Aunty Affair',
    # telugu
    'Telugu Aunty Saree Sex Video',
    'Telugu Mom Audio Hot Chudai',
    'Telugu Hyderabad Bhabhi MMS',
    'Telugu Andhra Aunty Original',
    # mallu/malayalam
    'Mallu Aunty Big Boobs Sex HD',
    'Mallu Kerala Housewife Affair',
    'Malayalam Hot Sex Video Viral',
    'Mallu Married Aunty MMS Leak',
    # bengali / odia / assamese
    'Bengali Boudi Saree MMS Viral',
    'Bengali Kolkata Bhabhi Hot Sex',
    'Boudi Bengali Hidden Cam Chudai',
    'Odia Bhabhi Viral Sex Video',
    'Assamese Aunty Hot Chudai HD',
    # bhojpuri / bihari / dehati
    'Bhojpuri Aunty Devar Chudai Video',
    'Bhojpuri Hot Bhabhi Sex MMS',
    'Bihari Dehati Village Sex Tape',
    'Bhojpuri Audio Hot Chudai Original',
    # marathi
    'Marathi Bhabhi Hot Sex Video',
    'Marathi Aunty Pune Affair MMS',
    'Marathi Mumbai Housewife Sex',
    # punjabi / haryana
    'Punjabi Bhabhi Sex Video Viral',
    'Punjabi Amritsar Aunty Hot',
    'Haryana Randi Sex Tape 2026',
    'Sikh Aunty XXX Viral MMS',
    # gujarati / rajasthani
    'Gujarati Aunty Hot Porn Video',
    'Rajasthani Bhabhi Devar Sex',
    'Gujju Married Aunty MMS Leak',
    # kannada
    'Kannada Aunty Bangalore Sex MMS',
    'Kannada Bhabhi Chudai HD Video',
    # bokep / indonesia
    'Bokep Indo Viral Hot Sex 2026',
    'Bokep ABG Indo Smp Original',
    'Bokep Indonesia Tante Hot Video',
    'Bokep Viral Live Streaming',
    # mixed / generic
    'Indian Village Saree Aunty Sex',
    'Indian Devar Bhabhi Real Chudai',
    'Married Couple First Night MMS',
    'Indian Webseries Hot Scene 2026',
    'Office Aunty Affair Sex Video',
    'Massage Parlor Hidden Cam India',
    'Indian Bus Train Groping MMS',
    'Indian School Girl Real... NO STOP',  # safety: this marker triggers skip below
    'Honeymoon Couple Suhaagrat MMS',
    'Wedding Night Real Sex Tape',
    'Indian Hostel Lesbian Video',
    'Telegram Channel Indian Leaks',
    'WhatsApp Viral Desi MMS 2026',
    'Hidden Cam Hotel Aunty Sex',
    'Real Indian Maid Sex Master',
    'Indian Webcam Live Show MMS',
    'Bhabhi Saree Strip Live HD',
    'Sasur Bahu Audio Chudai Video',
    'Jija Sali Hot Romance MMS',
    'Mami Bhanja Real Affair Video',
    'Devar Bhabhi Raat Ki Chudai',
    'Indian Pron Star Original Video',
    'Hot Desi Cousin Sex Tape',
    'Indian Webcam Girl Live Strip',
]
# Filter out the safety marker (defensive — the "NO STOP" label means do not use)
TITLES = [t for t in TITLES if 'NO STOP' not in t]

# Description keyword lines — rotated per item for diversification.
DESC_KEYWORD_LINES = [
    'Desi MMS • Indian Bhabhi • Tamil Telugu Mallu • Hindi BF Aunty XXX',
    'AuntyMaza • Married Bhabhi • Village Chudai • Hidden Cam Indian',
    'Tamil • Telugu • Mallu • Kannada • South Indian Aunty Sex',
    'Bengali Boudi • Bhojpuri • Marathi • Punjabi • Gujarati Sex',
    'XnXX • XHamster • PornHub • Original Indian Viral MMS',
    'Hindi BF • Blue Film • Dehati • Randi • Indian Original',
    'Bokep Indo • Tante • ABG • Indonesia Viral Hot 2026',
    'Pakistan Aunty • Bangla Boudi • Sri Lanka • Nepal Desi',
    'Devar Bhabhi • Sasur Bahu • Jija Sali • Mami Bhanja Affair',
    'Office Aunty • Maid Sex • Teacher Bhabhi • Hostel Lesbian',
    'Live Webcam • Hidden Cam • Real Hotel Sex • Telegram Leak',
    'First Night • Honeymoon • Suhaagrat • Wedding Night MMS',
]

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
    """Player-mockup CTA. Single link in description, rotating per item across 3 money sites."""
    return (
        '<div style="background:#0a0a0a;border:6px solid #dc2626;padding:60px 20px;text-align:center">'
        '<p style="color:#dc2626;background:#000;font-weight:bold;padding:6px 14px;font-size:18px;margin:0 auto 30px;border:2px solid #dc2626;display:inline-block">● LIVE HD 1080p ●</p>'
        '<p style="background:#dc2626;color:white;font-size:90px;padding:20px 50px;margin:20px auto;font-weight:bold;border:6px solid white;width:120px;line-height:1">▶</p>'
        '<p style="color:#fbbf24;font-size:44px;font-weight:bold;margin:24px 0;line-height:1.2">🔥 HD VIRAL LEAKED VIDEO 🔥</p>'
        f'<p style="font-size:36px;font-weight:bold;margin:20px 0"><a href="{target_url}" style="color:#16a34a;font-weight:bold;text-decoration:underline">{anchor}</a></p>'
        f'<p style="color:#06b6d4;font-size:24px;margin:24px 0 12px;font-weight:bold">{kw_line}</p>'
        '<p style="color:#9ca3af;font-size:18px;margin:8px 0">Free Streaming • Updated 2026 • Original HD Video</p>'
        '</div>'
    )


def ascii_only(s):
    return ''.join(c for c in s if 32 <= ord(c) < 127)


def s3_put_placeholder(access, secret, identifier, band, title):
    """Create item with minimal placeholder file + metadata."""
    venue = random.choice(VENUES)
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
        'x-archive-meta01-date':        '2026-05-12',
        'x-archive-meta01-venue':       venue,
        'x-archive-meta01-year':        '2026',
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
    for op in ('add', 'replace'):
        patch = [{'op': op, 'path': '/description', 'value': desc}]
        data = urllib.parse.urlencode({
            '-target': 'metadata',
            '-patch': json.dumps(patch),
            'access': access,
            'secret': secret,
        }).encode()
        req = urllib.request.Request(f'https://archive.org/metadata/{item_id}', data=data)
        try:
            r = urllib.request.urlopen(req, timeout=20).read().decode()
            obj = json.loads(r)
            if obj.get('success'):
                return True
            err = obj.get('error', '')
            if 'exists' in err or 'not set' in err:
                continue
            return False
        except urllib.error.HTTPError as e:
            if e.code in (400, 429):
                time.sleep(2)
                continue
            return False
        except Exception:
            return False
    return False


def main():
    access = os.environ['IA_ACCESS']
    secret = os.environ['IA_SECRET']
    label  = os.environ.get('ACCOUNT_LABEL', 'unknown')
    n_items = int(os.environ.get('ITEMS_PER_RUN', '30'))

    print(f'[{label}] target items: {n_items}')

    ok = fail = 0
    created = []
    for i in range(n_items):
        band = random.choice(ETREE_BANDS)
        title = f'{random.choice(TITLES)} {random.randint(100, 999)}'
        suffix = f'{label}-{int(time.time())%100000}-{random.randint(100, 9999)}'
        identifier = f'{band}2026-05-12.{suffix}'

        code, body = s3_put_placeholder(access, secret, identifier, band, title)
        if code not in (200, 201):
            fail += 1
            print(f'  [{i+1}/{n_items}] {identifier}: PUT FAIL HTTP {code} {body[:100]}')
            if code in (401, 403):
                print(f'[{label}] BANNED — aborting')
                break
            continue

        # PATCH description after upload settles. Rotate keyword line + target per item.
        kw_line = random.choice(DESC_KEYWORD_LINES)
        target_url = random.choice(TARGET_URLS)
        anchor = random.choice(PRIMARY_ANCHORS)
        time.sleep(1.0)
        patched = patch_description(identifier, access, secret, kw_line, target_url, anchor)
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
            print(f'  [{i+1}/{n_items}] {identifier}: PATCH FAIL')
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
