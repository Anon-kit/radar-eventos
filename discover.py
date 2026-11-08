#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico profundo (roda só quando você manda). Descobre, visto de dentro do GitHub:
 1) se o bloqueio do Shotgun/Ingresse some quando o acesso imita um navegador de verdade;
 2) por onde a Sympla entrega a lista de eventos (endereços internos);
 3) como Lets, Q2, Nenety, BaladAPP e Central dos Eventos organizam seus eventos.
Manda o resultado para o canal de status. Não altera nada.
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

try:
    from curl_cffi import requests as cffi
except Exception:
    cffi = None


def get(url, chrome=False, timeout=25):
    """(status, texto). chrome=True imita a 'impressão digital' de um Chrome real (curl_cffi)."""
    if chrome:
        if not cffi:
            return -1, ""
        try:
            r = cffi.get(url, impersonate="chrome", timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            return 0, f"ERR {type(e).__name__}"
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


def same_site_paths(page, base, limit=12):
    host = urllib.parse.urlparse(base).netloc.replace("www.", "")
    allp, evt = [], []
    for h in re.findall(r'href="([^"#]+)"', page):
        u = urllib.parse.urlparse(urllib.parse.urljoin(base, html.unescape(h)))
        if u.netloc.replace("www.", "") != host:
            continue
        path = u.path + (("?" + u.query) if u.query else "")
        if len(path) > 1 and path not in allp:
            allp.append(path)
            if re.search(r"/(e|eventos?|events?|ingressos?|festa|show|agenda)\b", path, re.I):
                evt.append(path)
    return len(allp), (evt or allp)[:limit]


def next_data(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def find_lists(obj, path="", depth=0, out=None):
    out = [] if out is None else out
    if depth > 7 or len(out) >= 4:
        return out
    if isinstance(obj, list) and len(obj) >= 3 and all(isinstance(x, dict) for x in obj[:3]):
        out.append((path, len(obj), list(obj[0].keys())[:14]))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_lists(v, f"{path}.{k}", depth + 1, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:2]):
            find_lists(v, f"{path}[{i}]", depth + 1, out)
    return out


def section_unblock():
    lines = ["🔓 <teste de bloqueio> (urllib puro | imitando Chrome)"]
    lines[0] = "🔓 Teste de bloqueio (acesso comum | imitando Chrome)"
    tests = [("Shotgun BH", "https://shotgun.live/en/concerts/belo-horizonte"),
             ("Shotgun home", "https://shotgun.live/"),
             ("Shotgun sitemap", "https://shotgun.live/sitemap.xml"),
             ("Ingresse home", "https://www.ingresse.com/"),
             ("Ingresse robots", "https://www.ingresse.com/robots.txt")]
    for name, url in tests:
        a, _ = get(url)
        b, body = get(url, chrome=True)
        lines.append(f"• {name}: {a} | {b if b != -1 else 'curl_cffi ausente'}"
                     + (f" ({len(body) // 1024} KB)" if b == 200 else ""))
    return "\n".join(lines)


def section_sympla():
    url = "https://www.sympla.com.br/eventos/belo-horizonte-mg"
    st, page = get(url)
    lines = [f"🎟 Sympla (lista de BH): HTTP {st}, {len(page) // 1024} KB"]
    if st != 200:
        return "\n".join(lines)
    nd = next_data(page)
    lines.append("__NEXT_DATA__: " + ("sim" if nd is not None else "não"))
    if nd:
        for p, n, keys in find_lists(nd):
            lines.append(f"  lista em {p} ({n} itens) campos: {', '.join(keys)}")
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', page)
    srcs = [urllib.parse.urljoin(url, s) for s in srcs if "sympla" in urllib.parse.urljoin(url, s) or s.startswith("/")]
    lines.append(f"scripts da página: {len(srcs)}")
    found = {}
    pats = [re.compile(r"[\"'](/api/[A-Za-z0-9_\-/.]{3,80})[\"']"),
            re.compile(r"https?://[a-z0-9.\-]*sympla\.com\.br/[A-Za-z0-9_\-/.]*(?:search|event|discover|listing|city|cidade)"
                       r"[A-Za-z0-9_\-/.?=&%,]{0,60}"),
            re.compile(r"[\"']([A-Za-z0-9_\-/.]*(?:search|discover|listing)[A-Za-z0-9_\-/.]*\?[A-Za-z0-9_\-=&{}$.]{0,60})[\"']")]
    for s in srcs[:45]:
        c, js = get(s, timeout=30)
        if c != 200:
            continue
        for rx in pats:
            for m in rx.findall(js):
                found.setdefault(m, s.rsplit("/", 1)[-1][:30])
    lines.append(f"endereços internos encontrados: {len(found)}")
    for ep, src in list(found.items())[:28]:
        lines.append(f"  {ep[:110]}")
    return "\n".join(lines)


def section_site(name, url):
    st, page = get(url)
    if st != 200:
        return f"🌐 {name}: HTTP {st}"
    total, evt = same_site_paths(page, url)
    nd = next_data(page)
    lines = [f"🌐 {name}: {len(page) // 1024} KB | título: {title_of(page)} | "
             f"NEXT_DATA: {'sim' if nd is not None else 'não'} | ld+json: {'sim' if 'ld+json' in page else 'não'} | "
             f"links internos: {total}"]
    if nd:
        for p, n, keys in find_lists(nd):
            lines.append(f"  lista em {p} ({n} itens) campos: {', '.join(keys)}")
    if evt:
        lines.append("  exemplos: " + " ".join(evt))
    return "\n".join(lines)


def main():
    say(section_unblock())
    say(section_sympla())
    for name, url in (("Lets", "https://lets.events/"), ("Q2 Ingressos", "https://www.q2ingressos.com.br/"),
                      ("Nenety", "https://www.nenety.com.br/"), ("BaladAPP", "https://www.baladapp.com.br/"),
                      ("Central dos Eventos", "https://www.centraldoseventos.com.br/")):
        say(section_site(name, url))
    say("✅ Descoberta terminou.")


if __name__ == "__main__":
    main()
