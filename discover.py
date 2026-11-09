#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico profundo, parte 3 (roda só quando você manda; não altera nada).
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


def ctx(text, needle, width=350):
    i = text.find(needle)
    if i == -1:
        return None
    return re.sub(r"\s+", " ", text[max(0, i - width // 3):i + width])


def chunks_of(page, base, max_chunks=45):
    srcs = []
    for s in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page):
        u = urllib.parse.urljoin(base, html.unescape(s))
        if u not in srcs and not any(n in urllib.parse.urlparse(u).netloc for n in NOISE):
            srcs.append(u)
    for u in srcs[:max_chunks]:
        c, js = get(u, timeout=30)
        if c == 200:
            yield u, js


def section_sympla_api():
    url = "https://www.sympla.com.br/eventos/belo-horizonte-mg"
    st, page = get(url)
    lines = [f"🎟 Sympla (parte 3): HTTP {st}, {len(page) // 1024} KB"]
    if st != 200:
        return "\n".join(lines)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, re.S | re.I)
    for body in sorted(scripts, key=len, reverse=True)[:3]:
        c = ctx(body, "/evento/", 700)
        if c:
            lines.append("trecho dos dados da lista: " + c)
            break
    need = ["/v4/search/query", "/v4/search", "api.sympla.com.br"]
    got = {}
    for u, js in chunks_of(page, url):
        for n in need:
            if n not in got and n in js:
                got[n] = (u.rsplit("/", 1)[-1][:30], ctx(js, n, 500))
        if len(got) == len(need):
            break
    for n, (src, c) in got.items():
        lines.append(f"[{n}] em {src}: {c}")
    return "\n".join(lines)


def section_central():
    base = "https://www.centraldoseventos.com.br/"
    st, page = get(base)
    lines = [f"🌐 Central dos Eventos: HTTP {st}"]
    if st != 200:
        return "\n".join(lines)
    hosts, shown = set(), 0
    for u, js in chunks_of(page, base, 6):
        hosts |= set(re.findall(r"https?://[A-Za-z0-9.\-]*(?:central|eventos|api)[A-Za-z0-9.\-]*\.[a-z]{2,}", js))
        for n in ("/v1/public/event/filter", "/v1/public/event/main-events", "/v1/public/event/home-info"):
            c = ctx(js, n, 600)
            if c and shown < 3:
                lines.append(f"[{n}] {c}")
                shown += 1
    lines.append("hosts vistos: " + " ".join(sorted(h for h in hosts if not any(x in h for x in NOISE))[:12]))
    return "\n".join(lines)


def find_events(obj, path="", depth=0, out=None):
    out = [] if out is None else out
    if depth > 9 or len(out) >= 3:
        return out
    if isinstance(obj, dict):
        ks = set(obj)
        if ({"name", "title"} & ks) and any("date" in k.lower() or "start" in k.lower() for k in ks):
            out.append((path, {k: str(v)[:60] for k, v in list(obj.items())[:14]}))
        for k, v in obj.items():
            find_events(v, f"{path}.{k}", depth + 1, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:30]):
            find_events(v, f"{path}[{i}]", depth + 1, out)
    return out


def section_lets():
    st, page = get("https://lets.events/")
    lines = [f"🌐 Lets: HTTP {st}"]
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return "\n".join(lines + ["sem NEXT_DATA"])
    nd = json.loads(m.group(1))
    pp = (nd.get("props") or {}).get("pageProps") or {}
    ap = pp.get("apolloData")
    lines.append(f"apolloData: {type(ap).__name__}, tamanho {len(json.dumps(ap)) // 1024} KB; "
                 f"chaves: {list(ap.keys())[:10] if isinstance(ap, dict) else '-'}")
    lines.append(f"host={pp.get('host')} path={pp.get('path')} appConfig={str(pp.get('appConfig'))[:200]}")
    for path, sample in find_events(ap):
        lines.append(f"  objeto-evento em {path}: {json.dumps(sample, ensure_ascii=False)[:420]}")
    return "\n".join(lines)


def section_peek():
    lines = ["👀 Espiadas em endereços públicos"]
    for url in ("https://www.baladapp.com.br/api/v3/anuncios", "https://www.baladapp.com.br/api/v3/banners",
                "https://www.q2ingressos.com.br/api/eventgroup"):
        st, body = get(url, timeout=25)
        snip = re.sub(r"\s+", " ", body)[:320]
        lines.append(f"• {url.split('//')[1]}: HTTP {st} ({len(body)} bytes) {snip}")
    return "\n".join(lines)


def main():
    for job in (section_sympla_api, section_central, section_lets, section_peek):
        try:
            say(job())
        except Exception as e:
            say(f"erro numa seção: {type(e).__name__}: {e}")
    say("✅ Descoberta 3 terminou.")


if __name__ == "__main__":
    main()
