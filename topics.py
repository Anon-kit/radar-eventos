# -*- coding: utf-8 -*-
"""
Temas e canais do radar. Este é o arquivo para AJUSTAR palavras: o radar.py só lê daqui.

Cada canal recebe o evento se bater em qualquer uma destas listas:
- "palavras":  valem em qualquer lugar do texto (título + descrição).
- "so_inicio": palavras fracas; só valem no título ou nos primeiros 160 caracteres da descrição.
- "so_titulo": palavras muito fracas; só valem se estiverem no TÍTULO do evento.
- "excluir":   se alguma destas aparecer em qualquer lugar do texto, o canal NÃO recebe o evento.
Sem acentos e em minúsculas.
"""

# Canal que recebe avisos de problema, relatórios e o "estou vivo" semanal ('Sniffer troubleshooting').
STATUS_CHAT = "-1004329169711"

CHANNELS = {
    "metal": {
        "id": "-1003901653814", "emoji": "🤘",
        "palavras": ["metal", "heavy metal", "underground", "thrash", "hard rock"],
        "so_inicio": ["rock", "punk", "hardcore"],
        "excluir": ["visita tecnica", "construcao civil", "metalurgia", "steel frame", "light steel",
                    "estrutura metalica", "crea jr", "crea mg"],
    },
    "eletronica": {
        "id": "-1003920893409", "emoji": "🎛",
        "palavras": ["rave", "eletronica", "eletronico", "edm", "techno", "psytrance", "trance", "house",
                     "house music", "tech house", "deep house", "drum and bass", "dnb", "hardstyle", "clubbing"],
        "so_titulo": ["dj", "djs"],
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
        "palavras": ["botanica", "micologia", "agronomia", "fungos", "cogumelo", "cogumelos", "jardinagem",
                     "orquidea", "orquideas", "bonsai", "agroecologia"],
        "so_titulo": ["sementes", "cultivo", "horta", "plantas", "suculentas"],
    },
    "pubs": {
        "id": "-1004477614363", "emoji": "🍻",
        "palavras": ["pub", "vida noturna", "craft beer", "cerveja artesanal", "cervejaria"],
        "so_inicio": ["musica ao vivo", "happy hour", "boteco", "balada", "open bar"],
    },
    "street_food": {
        "id": "-1004498496361", "emoji": "🍔",
        "palavras": ["street food", "streetfood", "food truck", "food trucks", "foodtruck", "comida de rua",
                     "festival de comida", "feira de comida", "feira gastronomica", "festival gastronomico",
                     "comida de boteco"],
        "so_inicio": ["gastronomia", "gastronomico", "gastronomica", "culinaria"],
        "so_titulo": ["burger", "hamburguer", "feijoada", "churrasco", "pizza"],
    },
    "alta_gastronomia": {
        "id": "-1004320965396", "emoji": "🍷",
        "palavras": ["alta gastronomia", "jantar harmonizado", "menu degustacao", "enogastronomia",
                     "wine dinner", "wine tasting"],
        "so_inicio": ["gastronomia", "gastronomico", "gastronomica", "culinaria", "degustacao", "chef",
                      "cafe especial", "cafes especiais"],
        "so_titulo": ["vinho", "vinhos", "queijo", "queijos", "cachaca", "brunch", "wine"],
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
        "so_inicio": ["sertanejo", "country"],
    },
}

# Palavras que só valem se vierem junto de outra do grupo (evita "house" = casa).
COMPANION = {"house": ["techno", "rave", "eletronica", "edm", "trance", "psytrance", "dj", "djs", "deep", "tech"]}

# Grupos em que o evento vai para UM canal só: o de palavra mais forte; empate fraco = o primeiro
# da lista; se bater com palavra forte nos dois, vai para os dois. Evita o mesmo aviso em dois canais.
GRUPOS_EXCLUSIVOS = [("alta_gastronomia", "street_food")]
