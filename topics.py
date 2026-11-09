# -*- coding: utf-8 -*-
"""
Temas e canais do radar. Este é o arquivo para AJUSTAR palavras: o radar.py só lê daqui.

- "palavras": valem em qualquer lugar do texto do evento (título + descrição).
- "so_titulo": palavras fracas; só valem no título ou no começo da descrição.
- Sem acentos e em minúsculas. Cada canal recebe o evento se bater em qualquer palavra.
"""

# Canal que recebe os avisos de problema, o relatório da primeira execução e o
# "estou vivo" semanal. Por enquanto usa o canal Metal; quando criar um canal só
# para status; hoje é o canal 'Sniffer troubleshooting'.
STATUS_CHAT = "-1004329169711"

CHANNELS = {
    "metal": {
        "id": "-1003901653814", "emoji": "🤘",
        "palavras": ["metal", "heavy metal", "underground", "thrash", "hard rock"],
        "so_titulo": ["rock", "punk", "hardcore"],
    },
    "eletronica": {
        "id": "-1003920893409", "emoji": "🎛",
        "palavras": ["rave", "eletronica", "edm", "techno", "psytrance", "trance", "house"],
    },
    "automotivo": {
        "id": "-1004441721197", "emoji": "🏍",
        "palavras": ["automotivo", "motociclismo", "encontro de motos", "encontro de carros",
                     "trackday", "motoclube", "moto clube", "motocicleta"],
        "so_titulo": ["carros", "motos"],
    },
    "meliponicultura": {
        "id": "-1004468872560", "emoji": "🐝",
        "palavras": ["meliponicultura", "apicultura", "abelhas sem ferrao", "jatai", "mandacaia",
                     "meliponario", "meliponicultor", "meliponicultores", "apicultor", "apicultores"],
    },
    "botanica_micologia": {
        "id": "-1004463228234", "emoji": "🍄",
        "palavras": ["botanica", "micologia", "agronomia", "cultivo", "fungos", "cogumelo", "cogumelos",
                     "sementes", "jardinagem", "orquidea", "orquideas", "bonsai", "agroecologia"],
    },
    "pubs": {
        "id": "-1004477614363", "emoji": "🍻",
        "palavras": ["pub", "vida noturna", "craft beer", "cerveja artesanal", "cervejaria"],
        "so_titulo": ["musica ao vivo", "happy hour", "boteco", "balada", "open bar"],
    },
    "ceasa_insumos": {
        "id": "-1004303054565", "emoji": "🌾",
        "palavras": ["ceasa", "feira de produtores", "feira de insumos", "insumos", "agroindustria", "agricultura"],
    },
    "rll": {
        "id": "-1004463824122", "emoji": "🔴",
        "palavras": ["red light", "bdsm", "fetiche", "rll"],
        "so_titulo": ["liberal", "secreta", "swing"],
    },
    "country": {
        "id": "-1004174888002", "emoji": "🤠",
        "palavras": ["rodeio", "agropecuaria", "peao", "cavalgada", "mangalarga", "leilao", "vaquejada"],
        "so_titulo": ["sertanejo", "country"],
    },
}

# Palavras que só valem se vierem junto de outra do grupo (evita "house" = casa).
COMPANION = {"house": ["techno", "rave", "eletronica", "edm", "trance", "psytrance"]}
