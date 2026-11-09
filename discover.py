#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico profundo, parte 4 (roda só quando você manda; não altera nada).
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


def get(url, timeout=25, post=None):
    headers = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9", "Accept-Encoding": "gzip",
               "Accept": "application/json, text/html;q=0.8, */*;q=0.5"}
    data = None
    if post is not None:
        data = json.dumps(post).encode()
        headers["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return r.status, raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body
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


def snip(text, n=240):
    return re.sub(r"\s+", " ", text)[:n]


def ids_in(page):
    return {m.group(2) for m in re.finditer(r"/evento/([A-Za-z0-9%._\-]+)/(\d{4,9})", page)}


def jshape(txt):
    try:
        d = json.loads(txt)
    except Exception:
        return "não é JSON"
    if isinstance(d, dict):
        return f"objeto, chaves: {list(d.keys())[:12]}"
    if isinstance(d, list):
        return f"lista de {len(d)}; 1º item: {json.dumps(d[0], ensure_ascii=False)[:300] if d else '-'}"
    return type(d).__name__


def ctx(text, needle, width=350):
    i = text.find(needle)
    return None if i == -1 else re.sub(r"\s+", " ", text[max(0, i - width // 3):i + width])


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


def section_sympla_pages():
    base = "https://www.sympla.com.br/eventos/belo-horizonte-mg"
    st, p1 = get(base)
    a = ids_in(p1)
    lines = [f"📄 Sympla BH, teste de páginas: lista base HTTP {st}, {len(a)} eventos"]
    for suffix in ("?page=2", "?page=3", "?pagina=2", "/show-musica-festa", "?c=show-musica-festa"):
        s, pg = get(base + suffix)
        b = ids_in(pg)
        lines.append(f"  {suffix}: HTTP {s}, {len(b)} eventos, novos em relação à base: {len(b - a)}")
    return "\n".join(lines)


def section_sympla_search():
    lines = ["🔎 Sympla: busca interna"]
    for u in ("https://api.sympla.com.br/v4/search/query?limit=3&page=0&type=normal&sort=DAY_TRENDING_SCORE",
              "https://www.sympla.com.br/api/v4/search/query?limit=3&page=0&type=normal",
              "https://www.sympla.com.br/api/discovery/v4/search/query?limit=3&page=0&type=normal",
              "https://www.sympla.com.br/api/v1/search?limit=3",
              "https://www.sympla.com.br/api/v4/search?limit=3&page=0"):
        st, body = get(u)
        lines.append(f"• {u.split('//')[1][:90]}: HTTP {st} {snip(body, 200)}")
    page = get("https://www.sympla.com.br/eventos/belo-horizonte-mg")[1]
    for key in ("queryKey", "searchParams", "initialParams", "dehydratedState"):
        c = ctx(page, key, 500)
        if c:
            lines.append(f"[{key} na página] {c}")
            break
    shown = 0
    for u, js in chunks_of(page, "https://www.sympla.com.br/", 45):
        for m in re.finditer(r"service", js):
            seg = js[m.start():m.start() + 900]
            if "fetch(" in seg or "URLSearchParams" in seg or "axios" in seg:
                lines.append(f"[código em {u.rsplit('/', 1)[-1][:24]}] " + snip(js[max(0, m.start() - 200):m.start() + 600], 800))
                shown += 1
                break
        if shown >= 3:
            break
    return "\n".join(lines)


def section_central_api():
    base = "https://api.centraldoseventos.com.br"
    lines = ["🌐 Central dos Eventos: API"]
    for path in ("/v1/public/event/main-events", "/v1/public/event/home-info", "/v3/public/address/cities"):
        st, body = get(base + path)
        lines.append(f"• GET {path}: HTTP {st} ({len(body)} bytes) {jshape(body)} | {snip(body, 200)}")
    for payload in ({}, {"city": "Belo Horizonte"}):
        st, body = get(base + "/v1/public/event/filter", post=payload)
        lines.append(f"• POST filter {json.dumps(payload)}: HTTP {st} ({len(body)} bytes) {jshape(body)} | {snip(body, 200)}")
    return "\n".join(lines)


def section_lets_cfg():
    st, page = get("https://lets.events/")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return f"🌐 Lets: sem NEXT_DATA (HTTP {st})"
    pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    cfg = pp.get("appConfig") or {}
    urls = sorted(set(re.findall(r"https?://[A-Za-z0-9.\-/_]+", json.dumps(cfg, ensure_ascii=False))))
    gql = sorted(set(re.findall(r"https?://[A-Za-z0-9.\-]+/[A-Za-z0-9_\-/]*graphql[A-Za-z0-9_\-/]*", page)))
    return (f"🌐 Lets: chaves do appConfig: {list(cfg.keys())[:15]} | endereços: {' '.join(urls[:15])} | "
            f"graphql: {' '.join(gql[:5])}")


def main():
    for job in (section_sympla_pages, section_sympla_search, section_central_api, section_lets_cfg):
        try:
            say(job())
        except Exception as e:
            say(f"erro numa seção: {type(e).__name__}: {e}")
    say("✅ Descoberta 4 terminou.")


if __name__ == "__main__":
    main()
