#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico profundo, parte 2 (roda só quando você manda; não altera nada).
Procura, visto de dentro do GitHub, de onde cada plataforma tira a lista de eventos.
Manda o resultado para o canal de status.
"""
import gzip
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
DRY = os.environ.get("RADAR_DRY_RUN", "") == "1"
STATUS_CHAT = "-1003901653814"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

NOISE = ("w3.org", "schema.org", "google", "gstatic", "facebook", "twitter", "youtube", "apple.com", "github",
         "mozilla", "reactjs", "npmjs", "sentry", "cloudflare", "jquery", "fontawesome", "cdnjs", "unpkg",
         "instagram", "linkedin", "tiktok", "whatsapp", "zendesk", "stripe", "paypal", "hotjar", "segment",
         "amplitude", "clarity", "doubleclick", "bing.com", "pinterest", "w.org", "example.com")
API_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])(/api/[A-Za-z0-9_\-/.{}$]{2,80})"),
    re.compile(r"https?://[A-Za-z0-9.\-]*(?:api|graphql|search|algolia|elastic|backend|gateway)"
               r"[A-Za-z0-9.\-]*\.[a-z]{2,}(?:/[A-Za-z0-9_\-/.]{0,60})?"),
    re.compile(r"[\"'`](/v[0-9]{1,2}/[A-Za-z0-9_\-/.]{3,60})"),
    re.compile(r"[\"'`](/(?:events?|eventos|search|discover|listing|shows)[A-Za-z0-9_\-/.]{0,50}"
               r"\?[A-Za-z0-9_\-=&{}$.,]{0,60})"),
]


def get(url, timeout=25):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9",
                                                   "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                data = gzip.decompress(data)
            return r.status, data.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, f"ERR {type(e).__name__}"


def say(text):
    parts, cur = [], ""
    for line in text.split("\n"):
        line = line[:600]
        if len(cur) + len(line) + 1 > 3800:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    for p in parts:
        if DRY or not TOKEN:
            print(p)
            continue
        data = urllib.parse.urlencode({"chat_id": STATUS_CHAT, "text": p.strip(),
                                       "disable_web_page_preview": "true"}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                                                          data=data), timeout=30)
        except Exception as e:
            print("Telegram falhou:", type(e).__name__)


def title_of(page):
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()[:80] if m else "-"


def visible(page):
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def paths_of(page, base, limit=14):
    host = urllib.parse.urlparse(base).netloc.replace("www.", "")
    allp, evt = [], []
    for h in re.findall(r'href="([^"#]+)"', page):
        u = urllib.parse.urlparse(urllib.parse.urljoin(base, html.unescape(h)))
        if u.netloc.replace("www.", "") != host:
            continue
        path = u.path + (("?" + u.query) if u.query else "")
        if len(path) > 1 and path not in allp and not re.search(r"\.(css|js|png|ico|svg|webp|jpg|ttf)", path):
            allp.append(path)
            if re.search(r"/(e|eventos?|events?|ingressos?|festa|show|agenda)\b|__\d+", path, re.I):
                evt.append(path)
    return len(allp), (evt or allp)[:limit]


def scan_js(page, base, max_chunks=40):
    srcs = []
    for s in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page):
        u = urllib.parse.urljoin(base, html.unescape(s))
        if u not in srcs:
            srcs.append(u)
    found, scanned = {}, 0
    for u in srcs[:max_chunks]:
        if any(n in urllib.parse.urlparse(u).netloc for n in NOISE):
            continue
        c, js = get(u, timeout=30)
        if c != 200:
            continue
        scanned += 1
        for rx in API_PATTERNS:
            for m in rx.findall(js):
                if not any(n in m for n in NOISE):
                    found.setdefault(m[:120], u.rsplit("/", 1)[-1][:28])
    return len(srcs), scanned, sorted(found, key=len)[:30]


def sitemap_info(base):
    out = []
    for p in ("/sitemap.xml", "/sitemap_index.xml"):
        st, body = get(base + p, timeout=20)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        last = re.findall(r"<lastmod>([^<]+)</lastmod>", body)[:1]
        txt = f"{p}: HTTP {st}"
        if locs:
            ex = " ".join(urllib.parse.urlparse(x).path for x in locs[:3])
            txt += f", {len(locs)} urls, ex.: {ex}, lastmod {last}"
        out.append(txt)
    return out


def next_info(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    try:
        nd = json.loads(m.group(1))
    except Exception:
        return ["  NEXT_DATA ilegível"]
    pp = (nd.get("props") or {}).get("pageProps") or {}
    return [f"  NEXT: buildId={nd.get('buildId')} page={nd.get('page')} pageProps={list(pp.keys())[:12]}"]


def section_sympla():
    url = "https://www.sympla.com.br/eventos/belo-horizonte-mg"
    st, page = get(url)
    lines = [f"🎟 Sympla BH: HTTP {st}, {len(page) // 1024} KB"]
    if st != 200:
        return "\n".join(lines)
    lines.append(f"links /evento/ no HTML: {len(re.findall(r'/evento/', page))} | ids __N: "
                 f"{len(re.findall(r'__[0-9]{5,}', page))} | next_f: {'self.__next_f' in page} | "
                 f"window.__: {sorted(set(re.findall(r'window[.](__[A-Za-z_]+__)', page)))[:5]}")
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", page, re.S | re.I)
    big = sorted(((len(b), a.strip()[:60], b) for a, b in scripts if len(b) > 3000), reverse=True)[:5]
    for n, attrs, body in big:
        keys = {k: body.count(k) for k in ('"startDate"', '"slug"', '"eventId"', '"name"', '"venue"', '"city"',
                                            '"events"', '"title"') if k in body}
        lines.append(f"  script inline {n // 1024} KB [{attrs}] chaves: {keys}")
    done = False
    for n, attrs, body in big:
        for k in ('"startDate"', '"events"', '"slug"'):
            i = body.find(k)
            if i != -1:
                lines.append("  trecho: " + re.sub(r"\s+", " ", body[max(0, i - 150):i + 350]))
                done = True
                break
        if done:
            break
    n, scanned, eps = scan_js(page, url)
    lines.append(f"scripts: {n} (lidos {scanned}); endereços de dados: {len(eps)}")
    lines += [f"  {e}" for e in eps]
    return "\n".join(lines)


def section_platform(name, base, start="/"):
    st, page = get(base + start)
    if st != 200:
        return f"🌐 {name}: HTTP {st}"
    total, evt = paths_of(page, base + start)
    lines = [f"🌐 {name}: {len(page) // 1024} KB | {title_of(page)} | links internos {total}",
             "  caminhos: " + " ".join(evt)]
    lines += next_info(page)
    lines += ["  " + s for s in sitemap_info(base)]
    n, scanned, eps = scan_js(page, base + start, max_chunks=25)
    lines.append(f"  scripts {n} (lidos {scanned}); endereços de dados: {len(eps)}")
    lines += [f"    {e}" for e in eps[:20]]
    return "\n".join(lines)


def section_nenety():
    base = "https://www.nenety.com.br"
    st, page = get(base + "/")
    if st != 200:
        return f"🌐 Nenety: HTTP {st}"
    paths = []
    for h in re.findall(r'href="(/[^"#?]+__[0-9]+)"', page):
        if h not in paths:
            paths.append(h)
    lines = [f"🌐 Nenety: {len(page) // 1024} KB, eventos na home: {len(paths)}", "  " + " ".join(paths[:15])]
    for p in paths[:2]:
        s2, ev = get(base + p)
        meta = {}
        for m in re.finditer(r'<meta\s+(?:name|property)="([^"]+)"\s+content="([^"]*)"', ev):
            meta.setdefault(m.group(1), html.unescape(m.group(2)))
        lines.append(f"  {p}: HTTP {s2} | título: {title_of(ev)} | og:desc: {meta.get('og:description', '-')[:140]}"
                     f" | ld+json: {'ld+json' in ev}")
        lines.append("    texto: " + visible(ev)[:600])
    lines += ["  " + s for s in sitemap_info(base)]
    return "\n".join(lines)


def main():
    jobs = [section_sympla,
            lambda: section_platform("Lets", "https://lets.events"),
            section_nenety,
            lambda: section_platform("BaladAPP", "https://www.baladapp.com.br", "/pt-BR"),
            lambda: section_platform("Central dos Eventos", "https://www.centraldoseventos.com.br"),
            lambda: section_platform("Q2 Ingressos", "https://www.q2ingressos.com.br")]
    for job in jobs:
        try:
            say(job())
        except Exception as e:
            say(f"erro numa seção: {type(e).__name__}: {e}")
    say("✅ Descoberta 2 terminou.")


if __name__ == "__main__":
    main()
