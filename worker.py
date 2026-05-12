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
    """etree-mediatype metadata. /details/ is indexable when collection=[band, etree]."""
    venue = random.choice(VENUES)
    return {
        'x-archive-auto-make-bucket':   '1',
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
