#!/usr/bin/env python3
"""GH Actions worker — one account, one item, N PDFs.

Reads env:
  IA_ACCESS, IA_SECRET     — single account credentials
  ACCOUNT_LABEL            — for stats/logging
  PDFS_PER_ITEM            — default 100
  TAGS_FILE                — default all_tags.txt
  STATE_USED_TAGS_JSON     — JSON array of already-used tags (input from current state)
  GROUP                    — desi|auntymaza|xnxx|india|hindibf (rotated by orchestrator)

Outputs:
  /tmp/result.json  — { ok, item_id, group, tags_used: [...], per_acct: {...}, error: str|null }
"""
import sys, os, re, random, time, json, requests
from urllib.parse import quote
from build_pdf import build_pdf

SEEDS = {
    'desi':      ['desi','mms','bhabhi','chudai','hindi','indian'],
    'auntymaza': ['auntymaza','aunty','bhabhi'],
    'xnxx':      ['xnxx','xvideos','xhamster','pornhub'],
    'india':     ['tamil','telugu','mallu','bengali','marathi','punjabi','bhojpuri','bihari','dehati','village','kannada','malayalam','aunty'],
    'hindibf':   ['bf','hindi','blue','film','chudai'],
}

BAD = ['child','children','kid','baby','infant','minor','underage','pedo','preteen','tween','lolita','rape','rapist','forced','molest','incest','school-girl','young-girl','young-boy','young-teen','ladki','larki','baccha','bachi','bachii','bachia','bachcha','balika','kachi','choti','nabalig','kumari','sister-and-brother','brother-and-sister','sister-brother','brother-sister','real-sister','real-brother','family-incest','real-incest','real-mom-son','real-dad-daughter','high-school','kindergarten','pre-school','preschool','mom-son','son-mom','dad-daughter','daughter-dad','der-mom']

ID_BASES = ['viral-hot-sex-videos','desi-mms-viral-2026','indian-bhabhi-aunty-sex','hindi-bf-porn-collection','xnxx-india-viral-mms','auntymaza-hot-porn','bokep-indo-viral','tamil-telugu-mallu-sex','desi-village-aunty-mms','viral-leaked-sex-videos','desi-hindi-bf-collection','indian-aunty-bhabhi-mms']
TITLES   = ['Viral Hot Sex Videos 2026 Collection','Desi MMS Viral Leak HD Sex Videos','Indian Bhabhi Aunty Hot Sex Video XXX HD','Hindi BF Porn Viral Collection 2026','XnXX India Viral MMS Hot Sex Videos','AuntyMaza Hot Porn Viral Sex Video HD','Tamil Telugu Mallu Sex Viral Video HD','Desi Village Aunty MMS Viral Sex HD','Viral Leaked Sex Videos Indian Hot 2026']

# etree real-band pool. Confirmed accepted via S3 PUT 2026-05-12. Add more from
# archive.org/details/etree if rotation needs growing.
ETREE_BANDS = [
    'Strangefolk',
    'AcidMothersTemple',
    'WidespreadPanic',
    'BirthMusic',
    'BenTraverse',
    'TheTravelinKine',
]
# Plausible venue names (gibberish enough to not collide with real shows).
VENUES = ['gthrny','live-show','outdoor-fest','soundcheck','rehearsal','jam-session']


def is_safe(t):
    if re.search(r'[0-9]', t): return False
    if not re.match(r'^[a-z\-]+$', t): return False
    for b in BAD:
        if b in t: return False
    return True


def pick_tags(group, n, used_set, tags_file):
    seed_words = set(SEEDS[group])
    out = []
    with open(tags_file) as f:
        for line in f:
            t = line.strip()
            if not t or len(t) < 14 or len(t) > 70: continue
            if t in used_set: continue
            parts = t.split('-')
            if len(parts) < 3 or len(parts) > 12: continue
            if not is_safe(t): continue
            if not any(p in seed_words for p in parts): continue
            out.append(t)
    random.shuffle(out)
    return out[:n]


def ascii_only(s):
    return ''.join(c for c in s if 32 <= ord(c) < 127)


def s3_put(access, secret, identifier, pdf_path, name, meta_headers=None):
    url = f'https://s3.us.archive.org/{identifier}/{quote(name)}'
    h = {'Authorization': f'LOW {access}:{secret}',
         'x-archive-keep-old-version': '0',
         'x-archive-queue-derive': '0'}
    if meta_headers: h.update(meta_headers)
    data = open(pdf_path, 'rb').read()
    r = requests.put(url, headers=h, data=data, timeout=120)
    return r.status_code, len(data), r.text[:200]


def build_meta(title, band):
    """etree-mediatype metadata. /details/ is indexable when collection=[band, etree].
    Description = player-mockup CTA pointing at masalatube1.com + secondary link to auntymazaporn1.com.
    Archive runs a delayed HTML sanitizer that strips linear-gradient/box-shadow/<style> tags and
    adds rel="ugc nofollow" to links — visual CTA still survives (border + colored text + clickable)."""
    venue = random.choice(VENUES)
    description = (
        '<style>'
        'ia-book-theater,.theatre-wrap,.no-preview,#theatre-ia-wrap,#theatre-ia,#theatre-controls{display:none !important}'
        '.thats-left.item-details-metadata > h1,.thats-left.item-details-metadata > .key-val-big,.thats-left.item-details-metadata > .row.metadata-list,.thats-left.item-details-metadata > .key-val-big-row,.thats-left .titlecredit{display:none !important}'
        '.col-sm-4.thats-right.item-details-archive-info{display:none !important}'
        '.thats-left.item-details-metadata,.col-sm-8.col-sm-pull-4,.col-sm-8{width:100% !important;max-width:100% !important;float:none !important;left:0 !important;right:auto !important;flex:0 0 100% !important;padding:0 15px !important}'
        '#descript{margin:0 !important;width:100% !important;padding:0 !important}'
        '</style>'
        '<a href="https://masalatube1.com/" style="display:block;text-decoration:none;color:inherit;width:100%">'
        '<div style="background:linear-gradient(135deg,#0a0a0a 0%,#1a1f2e 50%,#0a0a0a 100%);padding:60px 20px 40px;text-align:center;border-radius:16px;border:3px solid #dc2626;box-shadow:0 0 40px rgba(220,38,38,0.4);width:100%;box-sizing:border-box">'
        '<div style="font-size:14px;color:#dc2626;background:#000;display:inline-block;padding:4px 12px;border-radius:4px;font-weight:bold;letter-spacing:2px;margin-bottom:24px">● LIVE HD 1080p</div>'
        '<div style="width:140px;height:140px;background:radial-gradient(circle,#ef4444 0%,#dc2626 70%,#991b1b 100%);border-radius:50%;margin:0 auto 24px;display:block;line-height:140px;font-size:60px;color:white;box-shadow:0 8px 24px rgba(220,38,38,0.6);border:5px solid white">▶</div>'
        '<p style="color:#fbbf24;font-size:38px;font-weight:bold;margin:16px 0;line-height:1.2;text-shadow:0 2px 8px rgba(0,0,0,0.8)">🔥 HD VIRAL LEAKED VIDEO 🔥</p>'
        '<p style="color:white;font-size:28px;font-weight:bold;margin:12px 0">▶▶ CLICK TO WATCH FULL VIDEO ◀◀</p>'
        '<p style="color:#06b6d4;font-size:22px;margin:18px 0 10px">Desi MMS • Indian Bhabhi • Tamil Telugu Mallu • Hindi BF Aunty XXX</p>'
        '<p style="color:#9ca3af;font-size:16px">Free Streaming • Updated 2026 • Original HD Video</p>'
        '</div></a>'
        '<p style="margin-top:16px;text-align:center"><a href="https://auntymazaporn1.com/" style="color:#ea580c;font-size:26px;font-weight:bold;text-decoration:underline">🔴 More Aunty XXX Clips Here 🔴</a></p>'
    )
    return {
        'x-archive-auto-make-bucket':   '1',
        'x-archive-meta01-mediatype':   'etree',
        'x-archive-meta01-collection':  band,
        'x-archive-meta02-collection':  'etree',
        'x-archive-meta01-creator':     band,
        'x-archive-meta01-title':       ascii_only(title),
        'x-archive-meta01-description': description,
        'x-archive-meta01-date':        '2026-05-12',
        'x-archive-meta01-venue':       venue,
        'x-archive-meta01-year':        '2026',
        'x-archive-meta01-subject':     'Live concert',
        'x-archive-meta01-language':    'eng',
        'x-archive-meta01-scanner':     'Internet Archive HTML5 Uploader 1.7.0',
    }


def main():
    access  = os.environ['IA_ACCESS']
    secret  = os.environ['IA_SECRET']
    label   = os.environ.get('ACCOUNT_LABEL', 'unknown')
    n_pdfs  = int(os.environ.get('PDFS_PER_ITEM', '100'))
    tagsf   = os.environ.get('TAGS_FILE', 'all_tags.txt')
    used_file = os.environ.get('STATE_USED_TAGS_FILE', '')
    if used_file and os.path.exists(used_file):
        used = json.load(open(used_file))
    else:
        used = json.loads(os.environ.get('STATE_USED_TAGS_JSON', '[]'))
    group   = os.environ.get('GROUP', 'desi')

    used_set = set(used)
    print(f"[{label}] group={group} n_pdfs={n_pdfs} used_count={len(used_set)}")

    tags = pick_tags(group, n_pdfs, used_set, tagsf)
    if not tags:
        print(f"[{label}] NO TAGS for group={group}")
        json.dump({'ok': 0, 'item_id': None, 'group': group, 'tags_used': [], 'per_acct': {label: {'ok': 0, 'fail': 0}}, 'error': 'no_tags'}, open('/tmp/result.json', 'w'))
        return 1

    # etree-style identifier: <Band><Date>.<RandomSuffix>
    band = random.choice(ETREE_BANDS)
    suffix = f"{label}-{random.randint(1000,9999)}"
    identifier = f"{band}2026-05-12.{suffix}"
    title      = f"{random.choice(TITLES)} {random.randint(100,999)}"
    print(f"[{label}] item={identifier} band={band} title={title!r} tags={len(tags)}")

    pdf_dir = '/tmp/pdfs'
    os.makedirs(pdf_dir, exist_ok=True)
    files = []
    for j, tag in enumerate(tags, 1):
        p = f"{pdf_dir}/{j:03d}__{tag[:60]}.pdf"
        try:
            build_pdf(tag, p, pages=random.randint(3, 5))
        except Exception as e:
            print(f"[{label}] build_pdf({tag}) failed: {e}")
            continue
        files.append((p, f"{tag}-viral-hd-2026-{j:03d}.pdf"))

    if not files:
        json.dump({'ok': 0, 'item_id': identifier, 'group': group, 'tags_used': [], 'per_acct': {label: {'ok': 0, 'fail': 0}}, 'error': 'no_pdfs_built'}, open('/tmp/result.json', 'w'))
        return 1

    meta = build_meta(title, band)
    sent_meta = False
    ok = fail = 0
    for i, (pf, nm) in enumerate(files):
        headers = meta if not sent_meta else None
        code, _sz, body = s3_put(access, secret, identifier, pf, nm, headers)
        if code in (200, 201):
            ok += 1
            sent_meta = True
        else:
            fail += 1
            print(f"  [{i+1}/{len(files)}] {nm} HTTP {code} {body[:120]}")
            if code in (401, 403):
                print(f"[{label}] BANNED — aborting run")
                break
        time.sleep(0.8)
        # clean local PDF (keep first 5 as sample)
        if i >= 5:
            try: os.unlink(pf)
            except: pass

    result = {
        'ok': ok,
        'item_id': identifier,
        'group': group,
        'tags_used': tags[:ok],   # only tags we actually uploaded
        'per_acct': {label: {'ok': ok, 'fail': fail}},
        'error': None if ok else 'all_failed',
        'banned': ok == 0 and fail > 0,
        'details_url': f'https://archive.org/details/{identifier}',
    }
    json.dump(result, open('/tmp/result.json', 'w'))
    print(f"[{label}] DONE ok={ok}/{len(files)} → {result['details_url']}")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
