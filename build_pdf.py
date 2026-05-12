#!/usr/bin/env python3
"""Emoji-heavy keyword-spam PDF doorway. Real emoji via Symbola TTF, PDF /Title set."""
import sys, os, re, random
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

REDIR_BASE = 'https://masalatube1.com/'

# Register Symbola for real emoji rendering (monochrome but real codepoints).
SYMBOLA = '/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf'
pdfmetrics.registerFont(TTFont('Symbola', SYMBOLA))

# Real Unicode emojis covering hot/heart/fire/explicit + sparkle
EMOJI_SETS = {
    'hot':    ['🔥','💋','💦','🍑','🍆','😈','💯','🥵','🤤','😍','😘','💕','💖','💘','😜','🤩'],
    'sparkle':['✨','⭐','🌟','💫','🌠','💥','🎯','💎','👀','🌹','🎬','📹','💻','📱','🎥','🎞️'],
    'arrow':  ['👉','👆','👇','🔻','⬇️','▶️','⏩','⏯️','▶','🔴','🟢','🔵','🟡','✅','🆕','🆓'],
}
ALL_EMOJI = EMOJI_SETS['hot'] + EMOJI_SETS['sparkle'] + EMOJI_SETS['arrow']

def emoji_run(n=3, kind=None):
    """Return ParaXML with emoji wrapped in <font name=Symbola>...</font>."""
    pool = EMOJI_SETS.get(kind, ALL_EMOJI)
    chars = ' '.join(random.choice(pool) for _ in range(n))
    return f'<font name="Symbola">{chars}</font>'


LINES = [
    "{e3} Latest Update : {date} {e3}",
    "{hot} {title} Original Viral HD Video {hot}",
    "{spk} Sex Videos Hot Sex Video Hot Porn Viral Video new link link original Video link {spk}",
    "{hot} Viral hot video, {title} viral sex video, Viral Porn 2026 {hot}",
    "{spk} Last Updates: May 2026 {spk}",
    "{e3} Sex Videos Hot Sex Video Hot Porn viral video new link link viral on social media x trending now {e3}",
    "{hot} leaked Video {title} new link link original Video Viral Video leaked on x twitter {hot}",
    "{spk} Watch {title} full HD video on social media trending now {spk}",
    "{e5} CLICK HERE CLICK HERE CLICK HERE {e5}",
    "{hot} {title} XXX Video porn Original Video Video took the internet by storm {hot}",
    "{spk} Free {title} HD streaming porn sex XXX MMS fuck video {spk}",
    "{hot} Indian desi MMS, Hindi BF, Bhabhi Aunty XXX viral video link {hot}",
    "{e3} {title} desi mms porn xxx hindi bf aunty bhabhi chudai {e3}",
    "{hot} Auntymaza porn, tamil aunty, bengali boudi, mallu, telugu, marathi, punjabi, bhojpuri viral mms {hot}",
    "{spk} {title} full HD 1080p 720p free download streaming online {spk}",
    "{hot} XnXX, xhamster, pornhub viral indian desi sex video leaked {hot}",
]

def fmt(line, title, date):
    return (line
            .replace('{date}', date)
            .replace('{title}', title)
            .replace('{e3}', emoji_run(3))
            .replace('{e5}', emoji_run(5))
            .replace('{hot}', emoji_run(2, 'hot'))
            .replace('{spk}', emoji_run(2, 'sparkle')))


class PlayerMockup(Flowable):
    def __init__(self, width, height, title, redir):
        super().__init__()
        self.w, self.h, self.title, self.redir = width, height, title, redir
    def wrap(self, *_): return self.w, self.h
    def draw(self):
        c = self.canv
        c.setFillColor(HexColor('#0a0a0a'))
        c.rect(0, 0, self.w, self.h, fill=1, stroke=0)
        c.setFillColor(HexColor('#1a1f2e'))
        for y in range(0, int(self.h), 24):
            c.rect(0, y, self.w, 12, fill=1, stroke=0)
        cx, cy, r = self.w / 2, self.h / 2 + 10, 38
        c.setFillColor(HexColor('#dc2626'))
        c.circle(cx, cy, r, fill=1, stroke=0)
        c.setStrokeColor(white); c.setLineWidth(3)
        c.circle(cx, cy, r, fill=0, stroke=1)
        c.setFillColor(white)
        p = c.beginPath()
        p.moveTo(cx - 12, cy - 18); p.lineTo(cx - 12, cy + 18); p.lineTo(cx + 22, cy); p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 18)
        c.drawCentredString(self.w / 2, 30, self.title[:60])
        c.setFillColor(HexColor('#06b6d4')); c.setFont('Helvetica-Bold', 11)
        c.drawCentredString(self.w / 2, 12, '>> CLICK TO PLAY FULL HD VIDEO <<')
        c.setFillColor(HexColor('#dc2626'))
        c.rect(self.w - 60, self.h - 28, 50, 20, fill=1, stroke=0)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(self.w - 35, self.h - 22, 'HD')
        c.setFillColor(HexColor('#000000'))
        c.rect(10, self.h - 28, 50, 20, fill=1, stroke=0)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 11)
        c.drawCentredString(35, self.h - 22, '24:18')
        x0,y0 = c.absolutePosition(0,0); x1,y1 = c.absolutePosition(self.w,self.h); c.linkURL(self.redir, (x0,y0,x1,y1), relative=0, thickness=0)


class BigButton(Flowable):
    def __init__(self, width, height, text, url, color='#dc2626'):
        super().__init__()
        self.w, self.h, self.text, self.url, self.color = width, height, text, url, color
    def wrap(self, *_): return self.w, self.h
    def draw(self):
        c = self.canv
        c.setFillColor(HexColor('#000000'))
        c.roundRect(3, -3, self.w, self.h, 12, fill=1, stroke=0)
        c.setFillColor(HexColor(self.color))
        c.roundRect(0, 0, self.w, self.h, 12, fill=1, stroke=0)
        c.setStrokeColor(white); c.setLineWidth(2)
        c.roundRect(0, 0, self.w, self.h, 12, fill=0, stroke=1)
        c.setFillColor(white); c.setFont('Helvetica-Bold', 16)
        c.drawCentredString(self.w / 2, self.h / 2 - 6, self.text)
        x0,y0 = c.absolutePosition(0,0); x1,y1 = c.absolutePosition(self.w,self.h); c.linkURL(self.url, (x0,y0,x1,y1), relative=0, thickness=0)


def build_pdf(tag: str, out_path: str, pages: int = 4):
    title = tag.replace('-', ' ').title()
    # Real-emoji title (kept in PDF /Title metadata + first page)
    title_emoji = f"🔥 {title} 💋 Viral HD Sex Video 2026 🔥"
    redir = REDIR_BASE
    date = '11/05/2026'

    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14)
    big  = ParagraphStyle('big',  parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=24, alignment=1)

    PAGE_W = A4[0]
    M = 36
    PLAYER_W = PAGE_W - 2 * M
    PLAYER_H = PLAYER_W * 9 / 16

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        topMargin=M, bottomMargin=M, leftMargin=M, rightMargin=M,
        title=title_emoji,           # PDF /Title metadata
        author='WapApi',
        subject=f"Free {title} HD sex video viral porn xxx mms 2026",
        keywords=f"{title}, viral, hd, sex video, porn, xxx, mms, desi, hindi, bf, auntymaza, bhabhi, aunty, chudai, leaked, fuck, original",
    )
    story = []

    # PAGE 1 — player + big button
    h1 = f'{emoji_run(4)} {title} {emoji_run(4)}'
    story.append(Paragraph(h1, big))
    story.append(Spacer(1, 14))
    story.append(PlayerMockup(PLAYER_W, PLAYER_H, title, redir))
    story.append(Spacer(1, 20))
    story.append(BigButton(PLAYER_W, 56, '>> WATCH FULL HD VIDEO NOW <<', redir, '#dc2626'))
    story.append(Spacer(1, 14))
    for line in random.sample(LINES, k=6):
        story.append(Paragraph(fmt(line, title, date), body))
        story.append(Spacer(1, 3))
    story.append(Spacer(1, 10))
    story.append(BigButton(PLAYER_W, 50, '>> CLICK HERE TO STREAM ORIGINAL VIDEO <<', redir, '#16a34a'))
    story.append(PageBreak())

    for p in range(1, pages):
        story.append(Paragraph(h1, big))
        story.append(Spacer(1, 12))
        for line in random.sample(LINES, k=len(LINES)):
            story.append(Paragraph(fmt(line, title, date), body))
            story.append(Spacer(1, 3))
        story.append(Spacer(1, 12))
        btn_text = random.choice([
            '>> CLICK HERE TO WATCH NOW <<',
            '>> PLAY FULL HD VIDEO HERE <<',
            '>> STREAM ORIGINAL VIDEO <<',
            '>> WATCH UNCUT VERSION <<',
        ])
        btn_color = random.choice(['#dc2626','#16a34a','#ea580c','#9333ea'])
        story.append(BigButton(PLAYER_W, 52, btn_text, redir, btn_color))
        if p < pages - 1:
            story.append(PageBreak())

    doc.build(story)


if __name__ == '__main__':
    build_pdf(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
    print(f"wrote {sys.argv[2]} ({os.path.getsize(sys.argv[2])} bytes)")
