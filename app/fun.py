"""Recuperation d'une blague aleatoire via blagues-api.fr (token requis)."""
import logging
import random
import httpx
from .config import settings
from .text_filter import clean_for_printer

logger = logging.getLogger(__name__)

# Fallback : dictons et proverbes francais classiques si l'API echoue ou
# si aucun token n'est configure. Garde ASCII pur pour eviter tout souci
# d'impression sur l'imprimante thermique.
DICTONS = [
    "En avril, ne te decouvre pas d'un fil; en mai, fais ce qu'il te plait.",
    "Apres la pluie, le beau temps.",
    "Petit a petit, l'oiseau fait son nid.",
    "Qui se ressemble s'assemble.",
    "L'habit ne fait pas le moine.",
    "Il ne faut pas vendre la peau de l'ours avant de l'avoir tue.",
    "Mieux vaut tard que jamais.",
    "L'union fait la force.",
    "A coeur vaillant, rien d'impossible.",
    "Tout vient a point a qui sait attendre.",
    "Qui vivra verra.",
    "La nuit porte conseil.",
    "Chacun voit midi a sa porte.",
    "Les bons comptes font les bons amis.",
    "Loin des yeux, loin du coeur.",
    "Qui ne tente rien n'a rien.",
    "Mieux vaut prevenir que guerir.",
    "Pierre qui roule n'amasse pas mousse.",
    "Vouloir, c'est pouvoir.",
    "A bon entendeur, salut.",
    "Rien ne sert de courir, il faut partir a point.",
    "Une hirondelle ne fait pas le printemps.",
    "C'est en forgeant qu'on devient forgeron.",
    "L'appetit vient en mangeant.",
    "Qui dort dine.",
]

# Categories de blagues-api.fr exclues par defaut (humour sensible / borderline).
# Types disponibles : global, dev, dark, limit, beauf, blondes.
_DISALLOWED_TYPES = ["dark", "limit", "beauf", "blondes"]


async def fetch_joke(timeout_s: float = 5.0) -> str:
    """
    Recupere une blague en francais via blagues-api.fr.
    Si aucun token n'est configure, ou si l'API echoue, retourne un dicton
    francais tire au sort dans la liste locale. Le texte est nettoye pour
    l'imprimante thermique.
    """
    token = settings.blagues_api_token.strip()
    if not token:
        logger.info("Aucun token blagues-api.fr configure, utilisation d'un dicton")
        return random.choice(DICTONS)

    url = "https://www.blagues-api.fr/api/random"
    params = [("disallow", t) for t in _DISALLOWED_TYPES]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        timeout = httpx.Timeout(connect=5.0, read=timeout_s, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        joke = (data.get("joke") or "").strip()
        answer = (data.get("answer") or "").strip()
        if not joke and not answer:
            raise RuntimeError(f"Reponse blagues-api.fr sans contenu: {data}")
        if joke and answer:
            text = f"{joke}\n... {answer}"
        else:
            text = joke or answer
        return clean_for_printer(text)
    except Exception as e:
        logger.warning(f"blagues-api.fr indisponible, fallback dicton: {type(e).__name__}: {e}")
        return random.choice(DICTONS)
