#!/usr/bin/env python3
"""Etree metadata-only uploader — replicates competitor pattern (Strangefolk.po7e3x55-style).

Per item:
  - 1 tiny `notes.txt` (16 bytes) to materialize the bucket
  - mediatype=etree, collection=<low-volume band>, plus etree
  - Aggressive title:  emoji + brackets + MANDATORY adult KW + Arabic KW + zone tokens
  - Description PATCHed with the player-styled HTML blob (build_description from worker.py)
    → fake ▶ play button + 5 inline links to rotating panel target_url + body paragraphs

Burst: BURST_SIZE items per burst, BURST_PAUSE seconds pause between bursts.
Stops on 503/SlowDown (acct throttled/banned).

Env:
  IA_ACCESS, IA_SECRET     — fresh acct creds (REQUIRED)
  ACCOUNT_LABEL            — for logging
  BURST_SIZE               — items per burst (default 5)
  BURST_PAUSE              — pause secs between bursts (default 120)
  ITEM_GAP                 — secs between items inside a burst (default 4)
  MAX_ITEMS                — hard cap (default 9999)
  BAND_POOL                — etree bands JSON (default /tmp/ia-uploader/etree_band_pool.json)
  LOG_FILE                 — append log (default /tmp/ia-uploader/etree_meta.log)
"""
import os, sys, time, json, random, secrets, socket, itertools, threading
from datetime import datetime, timezone

# ----- IPv4 source rotation -------------------------------------------------
# Monkey-patch socket.create_connection so every outbound HTTPS connection
# binds to a rotating source IP from SOURCE_IPS. archive.org is v4-only, so
# we cycle our 5 OVH v4 addresses to dilute per-source rate limiting.
SOURCE_IPS = [s.strip() for s in os.environ.get('SOURCE_IPS', '').split(',') if s.strip()]
if SOURCE_IPS:
    _ip_cycle = itertools.cycle(SOURCE_IPS)
    _ip_lock  = threading.Lock()
    _orig_create_connection = socket.create_connection
    def _create_connection_bound(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                                  source_address=None, *args, **kwargs):
        if source_address is None:
            with _ip_lock:
                src = next(_ip_cycle)
            source_address = (src, 0)
        return _orig_create_connection(address, timeout, source_address, *args, **kwargs)
    socket.create_connection = _create_connection_bound

# Load worker.py module — provides ZONES, MASALA_CATS, REGIONS, SCENES, CATEGORIES,
# PRIMARY_ANCHORS, HOME_URL, gen_kw_line, build_description, s3_put_placeholder,
# patch_description, pick_ua, ascii_only.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import worker as W

ACCESS = os.environ['IA_ACCESS']
SECRET = os.environ['IA_SECRET']
LABEL  = os.environ.get('ACCOUNT_LABEL', 'unknown')
BURST_SIZE  = int(os.environ.get('BURST_SIZE',  '5'))
BURST_PAUSE = int(os.environ.get('BURST_PAUSE', '300'))
ITEM_GAP    = float(os.environ.get('ITEM_GAP',  '4'))
MAX_ITEMS   = int(os.environ.get('MAX_ITEMS',   '9999'))
BAND_POOL_F = os.environ.get('BAND_POOL', os.path.join(SCRIPT_DIR, 'etree_band_pool.json'))
PANEL_F     = os.environ.get('PANEL_LINKS', os.path.join(SCRIPT_DIR, 'panel_links.json'))
LOG_FILE    = os.environ.get('LOG_FILE',  os.path.join(SCRIPT_DIR, 'etree_meta.log'))

BANDS  = json.load(open(BAND_POOL_F))
PANELS = json.load(open(PANEL_F))['sites']

# Mandatory adult KW that MUST appear in every title (user explicit list).
MANDATORY_KW = [
    'xnxx', 'xnxx', 'xnxx',          # x3 to push xnxx density (user 2026-05-18)
    'xxx', 'porn', 'sex', 'video', 'videos', 'hot',
    'desi mms porn', 'auntymaza porn', 'desi mms sex',
    'xnxx hot', 'xnxx hd',           # extra anchored xnxx variants
]

# Arabic adult-relevant KW (user explicit request 2026-05-18).
ARABIC_KW = [
    'سكس', 'بورنو', 'افلام سكس', 'افلام', 'عربي', 'بنات', 'ساخن', 'فيديو',
    'مسرب', 'هندي', 'منزلي', 'محرم', 'مومس', 'سكسي', 'إغراء', 'عاهرات',
    'نيك', 'كس', 'مص', 'مكشوف', 'حلال', 'زوجة', 'خادمة', 'شرقي',
]

EMOJI_HOT = ['🔥', '🌶️', '🥵', '💋', '😘', '👅', '💦', '🍑', '🍆', '😍']
EMOJI_TAG = ['🔴LIVE', '🆕NEW', '🇮🇳', '💯', '⚡', '✨', '🎬', '📺']
BRACKET_PAIRS = [('(', ')'), ('[', ']'), ('{', '}')]

# Language codes rotated per item in IA metadata. Mix of Indo-Aryan + Dravidian +
# Arabic/Urdu — matches our content audience footprint.
LANGUAGES = [
    'eng', 'hin', 'ben', 'tam', 'tel', 'mar', 'guj', 'pan', 'urd', 'ara',
    'mal', 'kan', 'ori', 'asm', 'bho', 'nep', 'snd', 'fas',
]


SEPARATORS = ['~', '*', '!', '@', '#', '$', '^', '&', '+', '=', '`', '|', '/']
EMOJI_CHAOS = ['🌶️','🔥','🥵','👙','🍆','🍑','💋','😘','👅','💦','🍒','🌽','🥕','🧨','💯','⚡','✨']


def mix_case(rng: random.Random, s: str) -> str:
    """Random case treatment per token (lowercase / UPPERCASE / Title / AlT.)."""
    pick = rng.randint(0, 3)
    if   pick == 0: return s.lower()
    elif pick == 1: return s.upper()
    elif pick == 2: return s.title()
    else:
        return ''.join(c.upper() if i % 2 else c.lower() for i, c in enumerate(s))


def chaos_cluster(rng: random.Random, words: list, min_len: int = 3, max_len: int = 5,
                   use_all: bool = False) -> str:
    """Build a chaos-style KW cluster like:  seX~xNxN*xxx!@**  or  +SEX~VIDEOS~XNXX)
    by joining mix-cased words with random separator chars. May open/close brackets.
    If use_all=True, uses every word in `words`, ignoring min/max_len."""
    if use_all:
        picked = list(words); rng.shuffle(picked)
    else:
        n = rng.randint(min_len, max_len)
        picked = rng.sample(words, k=min(n, len(words)))
    cased  = [mix_case(rng, w) for w in picked]
    sep    = lambda: rng.choice(SEPARATORS)
    # Glue with single or doubled separators between tokens
    body = cased[0]
    for w in cased[1:]:
        sep_run = sep() * rng.randint(1, 2)
        body += sep_run + w
    # Optional bracket wrap
    if rng.random() < 0.55:
        bo, bc = rng.choice(BRACKET_PAIRS)
        body = f'{bo}{body}{bc}'
    # Optional leading +/!
    if rng.random() < 0.45: body = rng.choice(['+', '++', '!', '!!', '!+']) + body
    # Trailing punctuation noise (matches examples: "xxx!@**", "XNXX)", "xxx)@>")
    if rng.random() < 0.45:
        body += ''.join(rng.choice(SEPARATORS + [')','>','*']) for _ in range(rng.randint(1,3)))
    return body


def build_aggressive_title(rng: random.Random, zone_label: str) -> str:
    """Chaos-prefix + readable-suffix title pattern, mirrors user-specified examples:
       🌶️seX~xNxN*xxx!@** Sexy Aunty mallu bathing bf xnxx
       +👙🍆+SEX~XNXX) Xhamaster Xnxx Porn Video Hd +👙🍆 ...
       ++!🍆(XXX ok xxx)@> +SEX~VIDEOS~XNXX) Village Girl In ...
    Every title contains ALL mandatory KW (in mixed case) + 1-2 Arabic KW + emoji.
    ≤ 240 chars (IA truncates ~255)."""
    # ALL mandatory KW MUST appear. Split between two chaos clusters and force
    # use_all=True so chaos_cluster keeps every word (no random subset drop).
    kw = list(MANDATORY_KW); rng.shuffle(kw)
    arabic1, arabic2 = rng.sample(ARABIC_KW, 2)
    e_head = ''.join(rng.sample(EMOJI_CHAOS, k=rng.randint(1, 2)))
    e_mid  = rng.choice(EMOJI_CHAOS)
    e_tail = ''.join(rng.sample(EMOJI_CHAOS, k=rng.randint(1, 2)))

    half = len(kw) // 2
    c1_pool = kw[:half] + [arabic1]
    c2_pool = kw[half:] + [arabic2]
    cluster_head = chaos_cluster(rng, c1_pool, use_all=True)
    cluster_tail = chaos_cluster(rng, c2_pool, use_all=True)

    # Readable middle — zone + region + cat + scene words. Insert "xnxx" tokens
    # in a couple of slots so the title carries xnxx beyond the chaos clusters
    # (user pushed for more xnxx density 2026-05-18).
    region = rng.choice(W.REGIONS)
    cat    = rng.choice(W.CATEGORIES)
    scene  = rng.choice(W.SCENES)
    xn_variants = ['xnxx', 'Xnxx', 'XNXX', 'xNxx']
    x1, x2 = rng.choice(xn_variants), rng.choice(xn_variants)
    middle = f'{zone_label} {x1} {region} {cat} {x2} {scene}'

    title = f'{e_head}{cluster_head} {middle} {e_mid}{cluster_tail}{e_tail}'
    return title[:240]


def make_ident(rng: random.Random, band: str) -> str:
    """Identifier shape:  <BandName>.<8 lowercase alnum hash>
    Matches competitor pattern Strangefolk.po7e3x55 exactly."""
    suffix = ''.join(rng.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
    return f'{band}.{suffix}'


def log(msg: str) -> None:
    line = f'{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} [{LABEL}] {msg}\n'
    sys.stdout.write(line); sys.stdout.flush()
    with open(LOG_FILE, 'a') as f: f.write(line)


def build_player_description(rng: random.Random, zone_label: str, kw_line: str,
                              target_url: str, anchor: str) -> str:
    """Stripped player-only description. NO body paragraphs, NO chip strip.
    Visual layout (top to bottom): badge → ▶ play → chaos text → h2 → anchor → kw_line → subtitle.
    Every clickable link goes to target_url (the rotating panel root)."""
    theme = W.theme_for(zone_label) if zone_label else 'mainstream'
    pal = W._THEME_PALETTE.get(theme, W._THEME_PALETTE['mainstream'])
    headline = rng.choice(W._HEADLINE_POOL)
    h2       = rng.choice(W._H2_POOL)
    subtitle = rng.choice(W._SUBTITLE_POOL)
    chaos    = build_chaos_text(rng, zone_label)
    t = target_url
    # xnxx-heavy anchor line (user pushed for more xnxx 2026-05-18)
    xn_anchor_variants = [
        'xnxx hot indian video',
        'desi xnxx hd porn videos',
        'xnxx full hd sex video',
        'aunty xnxx mms leaked',
        'xnxx bhabhi sex video hd',
        'xnxx xxx desi mms full',
        'hindi xnxx hot porn aunty',
        'tamil xnxx mallu aunty sex',
        'xnxx bengali boudi sex video',
        'xnxx desi mms porn 2026',
    ]
    xn_line = rng.choice(xn_anchor_variants)
    return (
        f'<div style="background:{pal["bg"]};border:6px solid {pal["border"]};padding:60px 20px;text-align:center">'
        f'<p style="margin:0 auto 30px"><a href="{t}" style="color:{pal["cta"]};background:#000;font-weight:bold;padding:6px 14px;font-size:18px;border:2px solid {pal["cta"]};text-decoration:none" rel="ugc nofollow">{headline}</a></p>'
        f'<p style="margin:20px auto"><a href="{t}" style="background:{pal["cta"]};color:#fff;font-size:90px;padding:20px 50px;font-weight:bold;border:6px solid #fff;text-decoration:none" rel="ugc nofollow">▶</a></p>'
        f'<p style="margin:18px auto 28px;color:#fde68a;font-size:22px;font-weight:bold;line-height:1.4;max-width:760px">{chaos}</p>'
        f'<p style="margin:24px 0"><a href="{t}" style="color:{pal["head"]};font-size:44px;font-weight:bold;text-decoration:none" rel="ugc nofollow">{h2}</a></p>'
        f'<p style="margin:20px 0"><a href="{t}" style="color:{pal["accent"]};font-size:36px;font-weight:bold;text-decoration:underline" rel="ugc nofollow">{anchor}</a></p>'
        f'<p style="margin:14px 0"><a href="{t}" style="color:{pal["cta"]};font-size:30px;font-weight:bold;text-decoration:underline" rel="ugc nofollow">{xn_line}</a></p>'
        f'<p style="margin:24px 0 12px"><a href="{t}" style="color:{pal["mid"]};font-size:24px;font-weight:bold;text-decoration:none" rel="ugc nofollow">{kw_line}</a></p>'
        f'<p style="margin:8px 0 24px"><a href="{t}" style="color:#9ca3af;font-size:18px;text-decoration:none" rel="ugc nofollow">{subtitle}</a></p>'
        '</div>'
    )


def build_chaos_text(rng: random.Random, zone_label: str) -> str:
    """Short chaos-style descriptor placed UNDER the play button.
    Same chaos-character vocabulary as the title — 4-7 mandatory KW + Arabic + emoji.
    Visually mimics a hashtag soup tagline."""
    n = rng.randint(4, 7)
    kw_pool = [mix_case(rng, w) for w in MANDATORY_KW]
    rng.shuffle(kw_pool)
    arabic = rng.choice(ARABIC_KW)
    e1 = ''.join(rng.sample(EMOJI_CHAOS, 2))
    e2 = ''.join(rng.sample(EMOJI_CHAOS, 2))
    chaos = chaos_cluster(rng, kw_pool[:n] + [arabic], 4, 6)
    region = rng.choice(W.REGIONS)
    cat = rng.choice(W.CATEGORIES)
    return f'{e1} {chaos} :: {zone_label} {region} {cat} {e2}'


def put_placeholder_with_lang(ident: str, band: str, title: str, language: str):
    """Custom S3 PUT (mirrors worker.s3_put_placeholder) but with rotating language.
    worker.s3_put_placeholder hardcodes 'eng' — we need to vary it per item."""
    import urllib.request, urllib.error
    venue = rng_global.choice(W.VENUES)
    today = time.strftime('%Y-%m-%d')
    year = time.strftime('%Y')
    headers = {
        'Authorization':                f'LOW {ACCESS}:{SECRET}',
        'Content-Type':                 'text/plain',
        'x-archive-auto-make-bucket':   '1',
        'x-archive-keep-old-version':   '0',
        'x-archive-queue-derive':       '0',
        'x-archive-meta01-mediatype':   'etree',
        'x-archive-meta01-collection':  band,
        'x-archive-meta02-collection':  'etree',
        'x-archive-meta01-creator':     band,
        'x-archive-meta01-title':       W.ascii_only(title),
        'x-archive-meta01-date':        today,
        'x-archive-meta01-venue':       venue,
        'x-archive-meta01-year':        year,
        'x-archive-meta01-subject':     'Live concert',
        'x-archive-meta01-language':    language,                       # rotated
        'x-archive-meta01-scanner':     'Internet Archive HTML5 Uploader 1.7.0',
        'User-Agent':                   W.pick_ua(),
    }
    body = b'live show notes\n'
    url = f'https://s3.us.archive.org/{ident}/notes.txt'
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method='PUT')
        for k, v in headers.items(): req.add_header(k, v)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, ''
        except urllib.error.HTTPError as e:
            code = e.code
            err = e.read().decode('utf-8','ignore')[:200]
            if code in (401, 403): return code, err
            if code in (503, 429, 500, 502, 504):
                time.sleep(5 * (2 ** attempt)); continue
            return code, err
        except Exception as e:
            time.sleep(5)
    return -1, 'retry exhausted'


def do_one_item(rng: random.Random) -> dict:
    # 1. Pick a PANEL site (rotating across all 16 in xdaug panel) → target root URL.
    #    Each item points 13+ description links to ONE panel site root; across items
    #    the 16 sites all get backlinks evenly.
    panel = rng.choice(PANELS)
    target_url = panel['url']           # root, e.g. 'https://hindibfvideo.org/'
    anchor     = panel['anchor']        # brand anchor, e.g. 'hindibfvideo'

    # 2. Zone label only used for title chaos + kw_line theming (not target)
    zone_label, _ = rng.choice(W.ZONES)

    # 3. Band + identifier + language (all rotated)
    band = rng.choice(BANDS)
    ident = make_ident(rng, band)
    language = rng.choice(LANGUAGES)

    # 4. Title (chaos style)
    title = build_aggressive_title(rng, zone_label)

    # 5. kw_line for body paragraphs (uses zone vocabulary)
    kw_line = W.gen_kw_line(zone_label)

    # 5. Create item via custom S3 PUT (rotating language)
    started = time.time()
    code, err = put_placeholder_with_lang(ident, band, title, language)
    if code not in (200, 201):
        return {'ok': False, 'ident': ident, 'band': band, 'zone': zone_label, 'lang': language,
                'title': title[:80], 'phase': 'placeholder', 'code': code,
                'err': err[:200], 'elapsed': round(time.time()-started, 1)}

    # 6. Build description — STRIPPED VERSION (no body paragraphs, no chip strip).
    #    Keeps only: headline badge, big ▶ button, chaos paragraph, h2, anchor, kw_line, subtitle.
    desc = build_player_description(rng, zone_label, kw_line, target_url, anchor)

    # Brief settle pause so the freshly-PUT bucket has time for IA's metadata
    # API to recognize it. Without this, PATCH races and returns HTTP 400.
    time.sleep(rng.uniform(3.5, 5.5))

    ok, perr = W.patch_description_raw(ident, ACCESS, SECRET, desc)
    # If PATCH lost the race anyway, retro-retry once after a longer wait.
    if not ok and 'HTTP 400' in str(perr):
        time.sleep(8 + rng.uniform(0, 4))
        ok, perr = W.patch_description_raw(ident, ACCESS, SECRET, desc)
    elapsed = round(time.time() - started, 1)

    if ok:
        return {'ok': True, 'ident': ident, 'band': band, 'zone': zone_label, 'lang': language,
                'title': title[:80], 'target': target_url, 'elapsed': elapsed}
    return {'ok': False, 'ident': ident, 'band': band, 'zone': zone_label, 'lang': language,
            'title': title[:80], 'phase': 'patch', 'err': str(perr)[:200], 'elapsed': elapsed}


rng_global = random.Random()


def main():
    rng = random.Random()
    src_str = ','.join(SOURCE_IPS) if SOURCE_IPS else '(no rotation)'
    log(f'start  burst_size={BURST_SIZE}  burst_pause={BURST_PAUSE}s  max_items={MAX_ITEMS}  src={src_str}')

    # Warmup: send 1 benign notes file FIRST if acct hasn't been warmed yet.
    # Skips automatically if the warmup item already exists for this acct/date.
    screen = LABEL or 'user'
    try:
        w_ok, w_err = W.warmup_one_txt(ACCESS, SECRET, screen)
        log(f'warmup: {"ok" if w_ok else "skip/fail: " + str(w_err)[:120]}')
    except Exception as e:
        log(f'warmup exception (continuing): {e!r}')

    total = ok_n = fail_n = 0
    while total < MAX_ITEMS:
        burst_started = time.time()
        log(f'-- burst start  (total_so_far={total}  ok={ok_n}  fail={fail_n}) --')
        for i in range(BURST_SIZE):
            r = do_one_item(rng)
            total += 1
            if r['ok']:
                ok_n += 1
                log(f'  item {total:4d} OK   band={r["band"]:18}  zone="{r["zone"]:24}"  ident={r["ident"]}  ({r["elapsed"]}s)')
            else:
                fail_n += 1
                log(f'  item {total:4d} FAIL band={r["band"]:18}  zone="{r["zone"]:24}"  ident={r["ident"]}  phase={r.get("phase","?")}  code={r.get("code","?")}  err={r.get("err","")[:140]}')
                code = r.get('code', 0)
                if code in (503, 429) or 'SlowDown' in str(r.get('err','')):
                    log(f'STOPPING — IA returned {code}/SlowDown. Acct likely throttled or banned.')
                    return
                if code in (401, 403):
                    log(f'STOPPING — IA returned {code}. Acct banned. Pick next acct.')
                    return
            time.sleep(ITEM_GAP + rng.uniform(0, 1.5))
        burst_dur = time.time() - burst_started
        log(f'-- burst end    dur={burst_dur:.1f}s   pausing {BURST_PAUSE}s --')
        time.sleep(BURST_PAUSE)

    log(f'DONE  total={total}  ok={ok_n}  fail={fail_n}')


if __name__ == '__main__':
    main()
