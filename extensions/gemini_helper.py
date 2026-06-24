import asyncio
import os
import re
try:
    from google import genai as _genai
except ImportError:
    _genai = None
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
_TITLE_LANG = {
    "fr": ("français", "Comment, Pourquoi, Quel, Où, Quand, Combien, Est-ce que, Peut-on, Faut-il"),
    "en": ("anglais", "How, Why, What, Which, Where, When, How many, Can, Should, Is"),
    "de": ("allemand", "Wie, Warum, Was, Welche, Wo, Wann, Wie viele, Kann man, Soll man, Ist"),
    "it": ("italien", "Come, Perché, Quale, Dove, Quando, Quanto, Si può, Bisogna, È"),
    "es": ("espagnol", "Cómo, Por qué, Qué, Cuál, Dónde, Cuándo, Cuánto, Se puede, Hay que, Es"),
    "pl": ("polonais", "Jak, Dlaczego, Co, Który, Gdzie, Kiedy, Ile, Czy można, Czy trzeba"),
    "ru": ("russe", "Как, Почему, Что, Какой, Где, Когда, Сколько, Можно ли, Нужно ли"),
    "cs": ("tchèque", "Jak, Proč, Co, Který, Kde, Kdy, Kolik, Lze, Je třeba"),
    "tr": ("turc", "Nasıl, Neden, Ne, Hangi, Nerede, Ne zaman, Kaç"),
}
_TITLE_PROMPT = (
    "Tu reformules le TITRE d'une question NosTale pour qu'il respecte une "
    "convention stricte, SANS changer le sens voulu par l'auteur.\n\n"
    "Convention du titre :\n"
    "- commence par une majuscule ;\n"
    "- commence par un mot ou une expression interrogative ({examples}, etc.) ;\n"
    "- se termine par un point d'interrogation '?' ;\n"
    "- entre 20 et 100 caractères ;\n"
    "- en {label} (la langue de l'auteur), clair, sans guillemets ni emoji.\n\n"
    "Tu réponds UNIQUEMENT par le titre reformulé, rien d'autre (pas de "
    "préambule, pas de guillemets).\n\n"
    "Titre original : {title}\n"
    "Contenu du message (pour le contexte) : {content}\n\n"
    "Titre reformulé :"
)
def _clean_title(text: str) -> str:
    text = (text or "").strip()
    text = text.splitlines()[0].strip() if text else ""
    text = text.strip(' "\'`«»').strip()
    text = re.sub(r"\s+", " ", text)
    return text
def _sync_suggest_title(title: str, content: str, lang: str = "fr") -> str | None:
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        print("[gemini_helper] GEMINI_API_KEY absente de l'environnement", flush=True)
        return None
    label, examples = _TITLE_LANG.get((lang or "fr").lower(), _TITLE_LANG["fr"])
    try:
        client = _genai.Client(api_key=api_key)
        prompt = _TITLE_PROMPT.format(label=label, examples=examples, title=title[:300], content=(content or "")[:1500])
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.3,
                "max_output_tokens": 80,
                "thinking_config": {"thinking_budget": 0},
            },
        )
        return _clean_title(getattr(resp, "text", "") or "")
    except TypeError:
        try:
            resp = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
                config={"temperature": 0.3, "max_output_tokens": 80},
            )
            return _clean_title(getattr(resp, "text", "") or "")
        except Exception as exc:
            print(f"[gemini_helper] erreur API (retry sans thinking): {exc!r}", flush=True)
            return None
    except Exception as exc:
        print(f"[gemini_helper] erreur API Gemini: {exc!r}", flush=True)
        return None
async def suggest_title(title: str, content: str, lang: str = "fr") -> str | None:
    try:
        from extensions import site_api
        via_site = await site_api.suggest_title(title, content, lang=lang)
        if via_site:
            return via_site
    except Exception as exc:
        print(f"[gemini_helper] suggest via site indispo: {exc!r}", flush=True)
    if _genai is None:
        print("[gemini_helper] site indispo ET lib google-genai absente → pas de reformulation", flush=True)
        return None
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _sync_suggest_title, title, content, lang)
    return result or None