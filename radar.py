#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar de eventos da Região Metropolitana de Belo Horizonte -> Telegram.

- Só usa a biblioteca padrão do Python (nada para instalar).
- O token do bot vem do Secret TELEGRAM_BOT_TOKEN do GitHub (nunca escreva o token aqui).
- Roda no GitHub Actions a cada ~15 min e guarda o que já viu em state/seen.json.
"""
import gzip
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# =============================== CONFIGURAÇÃO ===============================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
DRY_RUN = os.environ.get("RADAR_DRY_RUN", "") == "1"
FORCE_PROBE = os.environ.get("FORCE_PROBE", "").strip().lower() in ("1", "true", "yes")
STATE_FILE = Path("state/seen.json")

# Canal que recebe os avisos de problema, o relatório da primeira execução e o
# "estou vivo" semanal. Por enquanto usa o canal Metal; quando criar um canal só
# para status, troque pelo ID dele.
STATUS_CHAT = "-1003901653814"

CHANNELS = {
    "metal": {
        "id": "-1003901653814", "emoji": "🤘",
        "palavras": ["metal", "heavy metal", "rock", "underground", "punk", "hardcore", "thrash", "hard rock"],
    },
    "eletronica": {
        "id": "-1003920893409", "emoji": "🎛",
        "palavras": ["rave", "eletronica", "edm", "techno", "psytrance", "trance", "house"],
    },
    "automotivo": {
        "id": "-1004441721197", "emoji": "🏍",
        "palavras": ["automotivo", "motociclismo", "encontro de motos", "encontro de carros", "carros",
                     "trackday", "motoclube", "moto clube", "motocicleta", "motos"],
    },
    "meliponicultura": {
        "id": "-1004468872560", "emoji": "🐝",
        "palavras": ["meliponicultura", "apicultura", "abelhas sem ferrao", "abelha", "abelhas",
                     "jatai", "mandacaia", "meliponario"],
    },
    "botanica_micologia": {
        "id": "-1004463228234", "emoji": "🍄",
        "palavras": ["botanica", "micologia", "agronomia", "cultivo", "fungos", "cogumelo", "cogumelos",
                     "sementes", "jardinagem", "orquidea", "orquideas", "bonsai", "agroecologia"],
    },
    "pubs": {
        "id": "-1004477614363", "emoji": "🍻",
        "palavras": ["pub", "vida noturna", "musica ao vivo", "craft beer", "cerveja artesanal",
                     "cervejaria", "happy hour"],
    },
    "ceasa_insumos": {
        "id": "-1004303054565", "emoji": "🌾",
        "palavras": ["ceasa", "feira de produtores", "feira de insumos", "insumos", "agroindustria", "agricultura"],
    },
    "rll": {
        "id": "-1004463824122", "emoji": "🔴",
        "palavras": ["liberal", "red light", "swing", "bdsm", "fetiche", "secreta", "rll"],
    },
    "country": {
        "id": "-1004174888002", "emoji": "🤠",
        "palavras": ["rodeio", "agropecuaria", "peao", "cavalgada", "mangalarga", "leilao",
                     "sertanejo", "country", "vaquejada"],
    },
}

# Palavras que só valem se vierem junto de outra do grupo (evita "house" = casa).
COMPANION = {"house": ["techno", "rave", "eletronica", "edm", "trance", "psytrance"]}

# Região Metropolitana de BH (34 municípios). Acrescente outras cidades aqui se quiser.
RMBH = [
    "Baldim", "Belo Horizonte", "Betim", "Brumadinho", "Caeté", "Capim Branco", "Confins", "Contagem",
    "Esmeraldas", "Florestal", "Ibirité", "Igarapé", "Itaguara", "Itatiaiuçu", "Jaboticatubas", "Juatuba",
    "Lagoa Santa", "Mário Campos", "Mateus Leme", "Matozinhos", "Nova Lima", "Nova União", "Pedro Leopoldo",
    "Raposos", "Ribeirão das Neves", "Rio Acima", "Rio Manso", "Sabará", "Santa Luzia",
    "São Joaquim de Bicas", "São José da Lapa", "Sarzedo", "Taquaraçu de Minas", "Vespasiano",
]
# Cidades com nome repetido em outros estados: só aceita se a página disser "- MG".
AMBIGUAS = {"santa luzia", "nova uniao"}

# Cidades do Shotgun a tentar (a página só conta se o título dela citar a cidade).
SHOTGUN_CITIES = {
    "belo-horizonte": "Belo Horizonte", "contagem": "Contagem", "betim": "Betim",
    "nova-lima": "Nova Lima", "sabara": "Sabará", "santa-luzia": "Santa Luzia",
    "lagoa-santa": "Lagoa Santa", "ribeirao-das-neves": "Ribeirão das Neves",
}
SHOTGUN_BASE = "https://shotgun.live/en"
SHOTGUN_MAX_PAGES = 8
MIN_SHOTGUN_BH = 5            # menos que isso em BH = leitor provavelmente quebrado

SYMPLA_SITEMAP = "https://www.sympla.com.br/sitemap-eventos.xml"
SYMPLA_MAX_PAGES_PER_RUN = 300
SYMPLA_MIN_IDS = 200

BAD_RUNS_ALERT = 3            # avisa depois de 3 execuções seguidas com problema
MAX_SEND_PER_RUN = 60
PROBES = {
    "Sympla": "https://www.sympla.com.br",
    "Shotgun": "https://shotgun.live",
    "Ingresse": "https://www.ingresse.com",
    "Lets": "https://lets.events",
    "Central dos Eventos": "https://www.centraldoseventos.com.br",
    "Nenety": "https://www.nenety.com.br",
    "BaladAPP": "https://www.baladapp.com.br",
    "Q2 Ingressos": "https://www.q2ingressos.com.br",
}
# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
    "Accept-Encoding": "gzip",
}


class FetchError(Exception):
    pass


# ------------------------------- utilidades --------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def visible_text(page):
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page or "")
    return clean_text(page)


def http_get(url, timeout=30, retries=2, raise_on_error=True):
    last = "erro"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    data = gzip.decompress(data)
                charset = r.headers.get_content_charset() or "utf-8"
                return r.status, data.decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, ""
            last = f"HTTP {e.code}"
            if not raise_on_error and attempt == retries:
                return e.code, ""
        except Exception as e:  # rede, timeout, SSL...
            last = type(e).__name__
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    if raise_on_error:
        raise FetchError(f"{urllib.parse.urlparse(url).netloc}: {last}")
    return 0, ""


def tg_send(chat_id, text):
    if len(text) > 4000:
        text = text[:4000].rsplit("\n", 1)[0]
    if DRY_RUN:
        print(f"[DRY -> {chat_id}]\n{text}\n")
        return True
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    plain = False
    for _ in range(5):
        fields = {"chat_id": chat_id, "text": clean_text(text) if plain else text}
        if not plain:
            fields["parse_mode"] = "HTML"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode()),
                                        timeout=30):
                return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429:
                m = re.search(r'"retry_after":\s*(\d+)', body)
                time.sleep(int(m.group(1)) + 1 if m else 5)
                continue
            if e.code == 400 and "parse" in body.lower() and not plain:
                plain = True  # tenta de novo como texto simples
                continue
            print(f"Telegram recusou ({e.code}) para {chat_id}: {body[:160]}")
            return False
        except Exception as e:
            print(f"Telegram falhou: {type(e).__name__}")
            time.sleep(2)
    return False


def notify_status(text):
    tg_send(STATUS_CHAT, text)


def run_url():
    repo = os.environ.get("GITHUB_REPOSITORY")
    return f"https://github.com/{repo}/actions" if repo else ""


# ------------------------- filtro por tema e região -------------------------
_RMBH_NORM = {norm(c): c for c in RMBH}


def rmbh_city(name):
    """Devolve o nome oficial se 'name' for da RMBH, senão None."""
    key = norm(re.sub(r"\s*[-,/]\s*mg\s*$", "", name or "", flags=re.I))
    return _RMBH_NORM.get(key)


def _kw_regex(kw):
    return re.compile(r"(?<![a-z0-9])" + re.escape(norm(kw)) + r"(?![a-z0-9])")


_KW = {ch: [(kw, _kw_regex(kw)) for kw in cfg["palavras"]] for ch, cfg in CHANNELS.items()}
_COMP = {k: [_kw_regex(w) for w in v] for k, v in COMPANION.items()}


def match_channels(text):
    t = norm(text).replace("pop rock", " ")
    hits = []
    for ch, kws in _KW.items():
        for kw, rx in kws:
            if rx.search(t):
                if kw in _COMP and not any(c.search(t) for c in _COMP[kw]):
                    continue
                hits.append(ch)
                break
    return hits


# ---------------------------------- Shotgun ----------------------------------
ANCHOR_RE = re.compile(r'<a\b[^>]*?href="([^"]*?/events/[^"?#]+)[^"]*"[^>]*>(.*?)</a>', re.S | re.I)
DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\b"
                     r"(?:\s*\|?\s*(\d{1,2}:\d{2}\s*[AP]M))?")
PRICE_RE = re.compile(r"R\$\s?[\d.,]+|\bFree\b|\bGrátis\b|\bPre-registration\b")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def split_title(before):
    """O Shotgun repete o título antes do bairro: 'A B A B Bairro'."""
    words = before.split(" ")
    for k in range(len(words) // 2, 0, -1):
        if words[:k] == words[k:2 * k]:
            return " ".join(words[:k]), " ".join(words[2 * k:])
    return before, ""


def shotgun_url(slug, page):
    return f"{SHOTGUN_BASE}/concerts/{slug}" + ("" if page == 1 else f"/-/-/{page}")


def parse_shotgun_list(page, base_url):
    items = {}
    for m in ANCHOR_RE.finditer(page):
        url = urllib.parse.urljoin(base_url, html.unescape(m.group(1)))
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        raw = clean_text(m.group(2))
        if not slug or slug == "events" or not raw:
            continue
        if slug in items and len(items[slug]["raw"]) >= len(raw):
            continue
        idx = raw.find(", Brazil")
        before = raw[:idx] if idx != -1 else raw
        title, place = split_title(before)
        after = raw[idx:] if idx != -1 else raw
        dm = DATE_RE.search(after)
        date = f"{dm.group(2)} {dm.group(1)}" + (f" · {dm.group(3)}" if dm.group(3) else "") if dm else ""
        pm = PRICE_RE.search(after[dm.end():] if dm else after)
        items[slug] = {
            "slug": slug, "url": url, "raw": raw, "title": title, "place": place,
            "date": date, "price": pm.group(0) if pm else "",
        }
    return items


def shotgun_city(slug, nome):
    items = {}
    for page in range(1, SHOTGUN_MAX_PAGES + 1):
        url = shotgun_url(slug, page)
        try:
            status, body = http_get(url, retries=1)
        except FetchError:
            if slug == "belo-horizonte" and page == 1:
                raise
            break
        if status != 200 or not body:
            break
        if page == 1:
            tm = TITLE_RE.search(body)
            if norm(nome) not in norm(clean_text(tm.group(1)) if tm else ""):
                return {}, False
        fresh = {k: v for k, v in parse_shotgun_list(body, url).items() if k not in items}
        if not fresh:
            break
        items.update(fresh)
        time.sleep(1)
    return items, bool(items)


def run_shotgun(state, report):
    seen = set(state.get("shotgun_seen", []))
    found, avail = {}, {}
    for slug, nome in SHOTGUN_CITIES.items():
        items, ok = shotgun_city(slug, nome)
        avail[nome] = ok
        for s, it in items.items():
            it["city"] = nome
            found.setdefault(s, it)
        time.sleep(1)
    bh = sum(1 for it in found.values() if it["city"] == "Belo Horizonte")
    if bh < MIN_SHOTGUN_BH:
        raise RuntimeError(f"só {bh} eventos lidos em BH (esperado bem mais)")
    out = []
    baselined = state.setdefault("baselined", {}).get("shotgun", False)
    if not baselined:
        sample = "; ".join(f"{it['title']} | {it['place'] or '?'} | {it['date'] or '?'} | {it['price'] or '?'}"
                           for it in list(found.values())[:3])
        report.append(f"Shotgun: {len(found)} eventos lidos (BH {bh}). Cidades com página: "
                      + ", ".join(n for n, ok in avail.items() if ok) + f". Amostra: {sample}")
        state["baselined"]["shotgun"] = True
    else:
        for slug, it in found.items():
            if slug in seen:
                continue
            chans = match_channels(f"{it['title']} {it['raw']}")
            if chans:
                lines = [f"<b>{html.escape(it['title'])}</b>"]
                meta = " · ".join(x for x in [it["city"], it["place"]] if x)
                lines.append(f"📍 {html.escape(meta)}")
                if it["date"]:
                    lines.append(f"🗓 {html.escape(it['date'])}")
                if it["price"]:
                    lines.append(f"🎟 {html.escape(it['price'])}")
                lines.append(html.escape(it["url"]))
                lines.append("<i>via Shotgun</i>")
                out.append({"channels": chans, "text": "\n".join(lines)})
    state["shotgun_seen"] = sorted(seen | set(found))[-5000:]
    return out, len(found)


# ---------------------------------- Sympla -----------------------------------
META_RE = re.compile(r"<meta\b([^>]*)>", re.I)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def meta_map(page):
    out = {}
    for m in META_RE.finditer(page):
        attrs = {}
        for a in ATTR_RE.finditer(m.group(1)):
            attrs[a.group(1).lower()] = html.unescape(a.group(2) if a.group(2) is not None else a.group(3))
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        if key and "content" in attrs and key not in out:
            out[key] = attrs["content"]
    return out


def parse_sympla_event(page):
    """None = página que não deu para ler (parser quebrado). Senão um dict (city pode ser None)."""
    meta = meta_map(page)
    tm = TITLE_RE.search(page)
    title_tag = clean_text(tm.group(1)) if tm else ""
    title = (meta.get("og:title") or re.sub(r"\s*[-|–]\s*Sympla\s*$", "", title_tag)).strip()
    if not title:
        return None
    city = date = None
    m = re.search(r"Compre ingressos para (.+) em (.+?) dia (\d{1,2}/\d{1,2})", meta.get("description", ""))
    if m:
        city, date = m.group(2).strip(), m.group(3)
    else:
        m2 = re.search(r"\sem\s+(.+?)\s*[-–]\s*Sympla\s*$", title_tag)
        if m2:
            city = m2.group(1).strip()
    official = rmbh_city(city) if city else None
    body = norm(visible_text(page))
    if official and norm(official) in AMBIGUAS:
        if not re.search(re.escape(norm(official)) + r"\s*[-,/]\s*mg\b", body):
            official = None
    ended = "o evento ja encerrou" in body or "evento encerrado" in body
    return {
        "title": title, "city": city, "official": official, "date": date, "ended": ended,
        "text": f"{title} {meta.get('og:description', '')[:400]}",
    }


def fetch_sympla_event(item):
    sid, url = item
    try:
        status, body = http_get(url, timeout=25, retries=1)
    except FetchError:
        return sid, url, None, "erro"
    if status != 200 or not body:
        return sid, url, None, "gone" if status in (404, 410) else "erro"
    return sid, url, parse_sympla_event(body), "ok"


def sympla_ids():
    status, xml = http_get(SYMPLA_SITEMAP, timeout=120)
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    if "<sitemapindex" in xml:
        children, urls = urls[:20], []
        for c in children:
            urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", http_get(c, timeout=120)[1])
    ids = {}
    for u in urls:
        m = re.search(r"__(\d+)(?:[?#]|$)", u) or re.search(r"/evento/[^/]+/(\d+)", u)
        if m:
            ids[m.group(1)] = html.unescape(u)
    return ids


def sympla_lastmod():
    """Data de atualização do sitemap de eventos, segundo o índice do Sympla."""
    try:
        _, idx = http_get("https://www.sympla.com.br/sitemap.xml", timeout=30, retries=1)
        m = re.search(r"<loc>[^<]*sitemap-eventos\.xml</loc>\s*<lastmod>([^<]+)</lastmod>", idx)
        return datetime.fromisoformat(m.group(1).strip()) if m else None
    except Exception:
        return None


def run_sympla(state, report):
    ids = sympla_ids()
    lastmod = sympla_lastmod()
    if lastmod:
        age = (datetime.now(timezone.utc) - lastmod).total_seconds() / 86400
        if age > 3 and not state.get("sympla_stale"):
            state["sympla_stale"] = True
            notify_status(f"⚠️ Radar: o sitemap da Sympla não é atualizado há {age:.0f} dias. "
                          "Os avisos da Sympla vão atrasar até voltar. O Shotgun continua normal.")
        elif age <= 3 and state.get("sympla_stale"):
            state["sympla_stale"] = False
            notify_status("✅ Radar: o sitemap da Sympla voltou a ser atualizado.")
        state["sympla_lastmod"] = lastmod.isoformat(timespec="minutes")
    last = state.get("health", {}).get("sympla", {}).get("last_count") or 0
    if len(ids) < SYMPLA_MIN_IDS or (last and len(ids) < 0.3 * last):
        raise RuntimeError(f"sitemap com {len(ids)} eventos (antes {last})")
    seen = set(state.get("sympla_seen", []))
    baselined = state.setdefault("baselined", {}).get("sympla", False)
    out = []
    if not baselined:
        ordered = sorted(ids, key=int)
        step = max(1, len(ordered) // 8)
        sample_ids = ordered[::step][:8]
        with ThreadPoolExecutor(6) as pool:
            res = list(pool.map(fetch_sympla_event, [(i, ids[i]) for i in sample_ids]))
        okc = sum(1 for r in res if r[2])
        desc = "; ".join(f"{r[2]['title'][:40]} | {r[2]['city'] or 'sem cidade'} | {r[2]['date'] or '?'}"
                         for r in res if r[2])
        report.append(f"Sympla: {len(ids)} eventos no sitemap (atualizado em {state.get('sympla_lastmod', '?')}); "
                      f"{okc}/{len(res)} páginas de teste lidas. Amostra espalhada pelo sitemap: {desc}")
        state["baselined"]["sympla"] = True
        state["sympla_seen"] = sorted(ids)
        return out, len(ids)
    todo = sorted((i for i in ids if i not in seen), key=int, reverse=True)[:SYMPLA_MAX_PAGES_PER_RUN]
    fails = state.setdefault("sympla_fail", {})
    done, parsed_ok, ended_n = set(), 0, 0
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(fetch_sympla_event, [(i, ids[i]) for i in todo]))
    for sid, url, ev, st in results:
        if st == "gone":
            done.add(sid)
        elif st == "erro" or ev is None:
            fails[sid] = fails.get(sid, 0) + 1
            if fails[sid] >= 3:
                done.add(sid)
        else:
            parsed_ok += 1
            ended_n += 1 if ev["ended"] else 0
            done.add(sid)
            if ev["official"] and not ev["ended"]:
                chans = match_channels(ev["text"])
                if chans:
                    lines = [f"<b>{html.escape(ev['title'])}</b>", f"📍 {html.escape(ev['official'])}"]
                    if ev["date"]:
                        lines.append(f"🗓 {ev['date']}")
                    lines += [html.escape(url), "<i>via Sympla</i>"]
                    out.append({"channels": chans, "text": "\n".join(lines)})
    if len(todo) >= 25 and parsed_ok == 0:
        raise RuntimeError(f"{len(todo)} páginas abertas e nenhuma foi entendida (layout mudou ou bloqueio)")
    if parsed_ok >= 10 and ended_n == parsed_ok:
        raise RuntimeError("todas as páginas lidas parecem 'encerradas' (detecção suspeita)")
    for sid in done:
        fails.pop(sid, None)
    state["sympla_fail"] = {k: v for k, v in fails.items() if k in ids}
    state["sympla_seen"] = sorted((seen & set(ids)) | done)
    return out, len(ids)


# ----------------------------- saúde / diagnóstico ----------------------------
def health_ok(state, name, count):
    h = state.setdefault("health", {}).setdefault(name, {})
    was_alerted = h.get("alerted")
    h.update({"bad_runs": 0, "alerted": False, "last_ok": now_iso(), "last_count": count})
    h.pop("last_error", None)
    if was_alerted:
        notify_status(f"✅ Radar: o leitor da {name} voltou a funcionar.")


def health_bad(state, name, detail):
    h = state.setdefault("health", {}).setdefault(name, {})
    h["bad_runs"] = h.get("bad_runs", 0) + 1
    h["last_error"] = detail[:200]
    print(f"[{name}] problema ({h['bad_runs']}): {detail}")
    if h["bad_runs"] >= BAD_RUNS_ALERT and not h.get("alerted"):
        h["alerted"] = True
        notify_status(f"⚠️ Radar: o leitor da {name} está com problema há {h['bad_runs']} execuções seguidas.\n"
                      f"Detalhe: {html.escape(detail[:200])}\n"
                      f"Volte ao Claude e cole esta mensagem para ajustar.\n{run_url()}")


def probe():
    lines = ["🔎 <b>Diagnóstico das plataformas</b> (visto de dentro do GitHub)"]
    for name, base in PROBES.items():
        try:
            st, body = http_get(base + "/", timeout=20, retries=0, raise_on_error=False)
            marks = [m for m, k in (("NEXT", "__NEXT_DATA__"), ("ld+json", "application/ld+json"),
                                    ("sitemap", "sitemap")) if k in body]
            low = body[:4000].lower()
            if "just a moment" in low or "cf-chl" in low or "captcha" in low:
                marks.append("DESAFIO-ANTIBOT")
            rs, rb = http_get(base + "/robots.txt", timeout=15, retries=0, raise_on_error=False)
            maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rb)[:3]
            lines.append(f"• {name}: home {st or 'sem resposta'} ({len(body) // 1024} KB; {', '.join(marks) or '-'}) "
                         f"| robots {rs or '-'} | sitemaps: {html.escape(', '.join(maps)) or '-'}")
        except Exception as e:
            lines.append(f"• {name}: erro {type(e).__name__}")
    return "\n".join(lines)


def maybe_heartbeat(state, force=False):
    last = state.get("last_heartbeat")
    now = datetime.now(timezone.utc)
    if last and not force and (now - datetime.fromisoformat(last)).days < 7:
        return
    if last or force:
        parts = [f"{n}: ok em {h.get('last_ok', '?')[:16].replace('T', ' ')} UTC ({h.get('last_count', '?')} itens)"
                 for n, h in state.get("health", {}).items()]
        parts.append(f"sitemap Sympla atualizado em {state.get('sympla_lastmod', '?')}")
        notify_status(f"💚 Radar vivo. Avisos enviados na semana: {state.get('sent_week', 0)}.\n" + "\n".join(parts))
    state["sent_week"] = 0
    state["last_heartbeat"] = now.isoformat(timespec="seconds")


# ----------------------------------- main -----------------------------------
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            print("state/seen.json ilegível; começando do zero")
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main():
    if not TOKEN and not DRY_RUN:
        print("Falta o Secret TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    state = load_state()
    first = not state.get("probe_sent")
    report, events, ok_sources = [], [], 0
    for name, fn in (("Shotgun", run_shotgun), ("Sympla", run_sympla)):
        try:
            evs, count = fn(state, report)
            events += evs
            health_ok(state, name, count)
            ok_sources += 1
        except Exception as e:
            health_bad(state, name, f"{type(e).__name__}: {e}")
            if first or FORCE_PROBE:
                report.append(f"{name}: FALHOU - {type(e).__name__}: {e}")
    sent = 0
    for ev in events[:MAX_SEND_PER_RUN]:
        for ch in ev["channels"]:
            if tg_send(CHANNELS[ch]["id"], f"{CHANNELS[ch]['emoji']} {ev['text']}"):
                sent += 1
            time.sleep(1.2)
    if len(events) > MAX_SEND_PER_RUN:
        notify_status(f"ℹ️ Radar: {len(events) - MAX_SEND_PER_RUN} eventos novos ficaram sem aviso neste ciclo (limite de envio).")
    state["sent_week"] = state.get("sent_week", 0) + sent
    need_probe = first or FORCE_PROBE
    if report:
        notify_status("🚀 <b>Radar ligado</b>\n" + "\n".join(html.escape(r) for r in report))
    if need_probe:
        notify_status(probe())
    state["probe_sent"] = True
    maybe_heartbeat(state)  # na 1a vez só grava a data; depois avisa 1x por semana
    save_state(state)
    if ok_sources == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
