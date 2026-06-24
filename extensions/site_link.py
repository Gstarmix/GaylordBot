import json
import os
import discord
from discord.ext import commands
from pathlib import Path
from constants import SITE_NOSTAR_CHANNEL_ID, NOSTAR_PUBLIC_URL
from extensions.translate import FLAG_LANGS, LANG_LABEL
from extensions import site_api
from extensions.rules import SEPARATOR
ORANGE = 0xE67E22
STATE_PATH = "site_link_state.json"
B = NOSTAR_PUBLIC_URL.rstrip("/")
BANNER_FILE = Path(__file__).resolve().parent / "assets" / "banner_site.png"
BANNER_NAME = "banner_site.png"
TERMS = {
    "en": {"title": "📚 Your NosTale Toolbox",
        "intro": f"**[nostar.fr]({B})** is the GSTAR community's NosTale hub: lists, simulators and detailed guides for the whole game.",
        "note": "🇫🇷 Originally a French site. Tap a flag below to read this index in your language.",
        "Questions": "Questions", "qdesc": "the community questions forum.",
        "Lists": "Lists", "Simulators": "Simulators", "Guides": "Guides", "Contents": "Contents",
        "Equipment": "Equipment", "Runes": "Runes", "Specialists": "Specialists", "Bestiary": "Bestiary",
        "Buffs": "Buffs", "Environments": "Environments", "Shortcuts": "Shortcuts", "Tattoos": "Tattoos",
        "Fairies": "Fairies", "Damage": "Damage", "Gold": "Gold", "CharEval": "Evaluation",
        "Communities": "Communities", "Instances": "Instances", "Progression": "Progression",
        "Classes": "Classes", "RaidGuides": "Raids", "PCSetup": "PC",
        "footer": "Index based on nostar.fr · use the flags to translate"},
    "fr": {"title": "📚 Ta boîte à outils NosTale",
        "intro": f"**[nostar.fr]({B})** est le compagnon NosTale tout-en-un de la communauté GSTAR : listes, simulateurs et guides détaillés pour tout le jeu.",
        "note": "🇫🇷 Site à l'origine français. Touche un drapeau ci-dessous pour lire ce sommaire dans ta langue.",
        "Questions": "Questions", "qdesc": "le forum de questions de la communauté.",
        "Lists": "Listes", "Simulators": "Simulateurs", "Guides": "Guides", "Contents": "Contenus",
        "Equipment": "Équipements", "Runes": "Runes", "Specialists": "Spécialistes", "Bestiary": "Bestiaire",
        "Buffs": "Buffs", "Environments": "Environnements", "Shortcuts": "Raccourcis", "Tattoos": "Tatouages",
        "Fairies": "Fées", "Damage": "Dégâts", "Gold": "Or", "CharEval": "Évaluation",
        "Communities": "Communautés", "Instances": "Instances", "Progression": "Progression",
        "Classes": "Classes", "RaidGuides": "Raids", "PCSetup": "PC",
        "footer": "Sommaire basé sur nostar.fr · utilise les drapeaux pour traduire"},
    "de": {"title": "📚 Dein NosTale-Werkzeugkasten",
        "intro": f"**[nostar.fr]({B})** ist der All-in-one-NosTale-Begleiter der GSTAR-Community: Listen, Simulatoren und ausführliche Guides für das ganze Spiel.",
        "note": "🇫🇷 Ursprünglich eine französische Seite. Tippe unten auf eine Flagge, um dieses Inhaltsverzeichnis in deiner Sprache zu lesen.",
        "Questions": "Fragen", "qdesc": "das Fragen-Forum der Community.",
        "Lists": "Listen", "Simulators": "Simulatoren", "Guides": "Guides", "Contents": "Inhalte",
        "Equipment": "Ausrüstung", "Runes": "Runen", "Specialists": "Spezialisten", "Bestiary": "Bestiarium",
        "Buffs": "Buffs", "Environments": "Umgebungen", "Shortcuts": "Tastenkürzel", "Tattoos": "Tattoos",
        "Fairies": "Feen", "Damage": "Schaden", "Gold": "Gold", "CharEval": "Bewertung",
        "Communities": "Gemeinschaften", "Instances": "Instanzen", "Progression": "Fortschritt",
        "Classes": "Klassen", "RaidGuides": "Raids", "PCSetup": "PC",
        "footer": "Inhaltsverzeichnis basiert auf nostar.fr · nutze die Flaggen zum Übersetzen"},
    "it": {"title": "📚 La tua cassetta degli attrezzi NosTale",
        "intro": f"**[nostar.fr]({B})** è il compagno NosTale tutto-in-uno della community GSTAR: liste, simulatori e guide dettagliate per tutto il gioco.",
        "note": "🇫🇷 Sito originariamente in francese. Tocca una bandiera qui sotto per leggere questo indice nella tua lingua.",
        "Questions": "Domande", "qdesc": "il forum delle domande della community.",
        "Lists": "Liste", "Simulators": "Simulatori", "Guides": "Guide", "Contents": "Contenuti",
        "Equipment": "Equipaggiamento", "Runes": "Rune", "Specialists": "Specialisti", "Bestiary": "Bestiario",
        "Buffs": "Buff", "Environments": "Ambienti", "Shortcuts": "Scorciatoie", "Tattoos": "Tatuaggi",
        "Fairies": "Fate", "Damage": "Danni", "Gold": "Oro", "CharEval": "Valutazione",
        "Communities": "Comunità", "Instances": "Istanze", "Progression": "Progressione",
        "Classes": "Classi", "RaidGuides": "Raid", "PCSetup": "PC",
        "footer": "Indice basato su nostar.fr · usa le bandiere per tradurre"},
    "es": {"title": "📚 Tu kit de herramientas de NosTale",
        "intro": f"**[nostar.fr]({B})** es el compañero NosTale todo en uno de la comunidad GSTAR: listas, simuladores y guías detalladas para todo el juego.",
        "note": "🇫🇷 Sitio originalmente en francés. Toca una bandera abajo para leer este índice en tu idioma.",
        "Questions": "Preguntas", "qdesc": "el foro de preguntas de la comunidad.",
        "Lists": "Listas", "Simulators": "Simuladores", "Guides": "Guías", "Contents": "Contenidos",
        "Equipment": "Equipamiento", "Runes": "Runas", "Specialists": "Especialistas", "Bestiary": "Bestiario",
        "Buffs": "Buffs", "Environments": "Entornos", "Shortcuts": "Atajos", "Tattoos": "Tatuajes",
        "Fairies": "Hadas", "Damage": "Daño", "Gold": "Oro", "CharEval": "Evaluación",
        "Communities": "Comunidades", "Instances": "Instancias", "Progression": "Progresión",
        "Classes": "Clases", "RaidGuides": "Raids", "PCSetup": "PC",
        "footer": "Índice basado en nostar.fr · usa las banderas para traducir"},
    "pl": {"title": "📚 Twój zestaw narzędzi NosTale",
        "intro": f"**[nostar.fr]({B})** to kompleksowy przewodnik NosTale społeczności GSTAR: listy, symulatory i szczegółowe poradniki do całej gry.",
        "note": "🇫🇷 Strona pierwotnie francuska. Dotknij flagi poniżej, aby przeczytać ten spis treści w swoim języku.",
        "Questions": "Pytania", "qdesc": "społecznościowe forum pytań.",
        "Lists": "Listy", "Simulators": "Symulatory", "Guides": "Poradniki", "Contents": "Zawartość",
        "Equipment": "Ekwipunek", "Runes": "Runy", "Specialists": "Specjaliści", "Bestiary": "Bestiariusz",
        "Buffs": "Buffy", "Environments": "Środowiska", "Shortcuts": "Skróty", "Tattoos": "Tatuaże",
        "Fairies": "Wróżki", "Damage": "Obrażenia", "Gold": "Złoto", "CharEval": "Ocena",
        "Communities": "Społeczności", "Instances": "Instancje", "Progression": "Progresja",
        "Classes": "Klasy", "RaidGuides": "Rajdy", "PCSetup": "PC",
        "footer": "Spis treści oparty na nostar.fr · użyj flag, aby przetłumaczyć"},
    "ru": {"title": "📚 Ваш набор инструментов NosTale",
        "intro": f"**[nostar.fr]({B})** это универсальный NosTale-помощник сообщества GSTAR: списки, симуляторы и подробные гайды по всей игре.",
        "note": "🇫🇷 Изначально французский сайт. Нажмите флаг ниже, чтобы прочитать это оглавление на своём языке.",
        "Questions": "Вопросы", "qdesc": "форум вопросов сообщества.",
        "Lists": "Списки", "Simulators": "Симуляторы", "Guides": "Гайды", "Contents": "Содержание",
        "Equipment": "Снаряжение", "Runes": "Руны", "Specialists": "Специалисты", "Bestiary": "Бестиарий",
        "Buffs": "Баффы", "Environments": "Окружение", "Shortcuts": "Горячие клавиши", "Tattoos": "Татуировки",
        "Fairies": "Феи", "Damage": "Урон", "Gold": "Золото", "CharEval": "Оценка",
        "Communities": "Сообщества", "Instances": "Инстансы", "Progression": "Прогресс",
        "Classes": "Классы", "RaidGuides": "Рейды", "PCSetup": "PC",
        "footer": "Оглавление на основе nostar.fr · используйте флаги для перевода"},
    "cs": {"title": "📚 Tvoje sada nástrojů NosTale",
        "intro": f"**[nostar.fr]({B})** je all-in-one NosTale průvodce komunity GSTAR: seznamy, simulátory a podrobné návody pro celou hru.",
        "note": "🇫🇷 Původně francouzský web. Klepni na vlajku níže a přečti si tento obsah ve svém jazyce.",
        "Questions": "Otázky", "qdesc": "komunitní fórum otázek.",
        "Lists": "Seznamy", "Simulators": "Simulátory", "Guides": "Návody", "Contents": "Obsah",
        "Equipment": "Vybavení", "Runes": "Runy", "Specialists": "Specialisté", "Bestiary": "Bestiář",
        "Buffs": "Buffy", "Environments": "Prostředí", "Shortcuts": "Zkratky", "Tattoos": "Tetování",
        "Fairies": "Víly", "Damage": "Poškození", "Gold": "Zlato", "CharEval": "Hodnocení",
        "Communities": "Komunity", "Instances": "Instance", "Progression": "Postup",
        "Classes": "Třídy", "RaidGuides": "Raidy", "PCSetup": "PC",
        "footer": "Obsah založen na nostar.fr · k překladu použij vlajky"},
    "tr": {"title": "📚 NosTale Araç Kutun",
        "intro": f"**[nostar.fr]({B})**, GSTAR topluluğunun hepsi bir arada NosTale rehberidir: listeler, simülatörler ve tüm oyun için ayrıntılı kılavuzlar.",
        "note": "🇫🇷 Aslen Fransızca bir site. Bu içindekiler listesini kendi dilinde okumak için aşağıdaki bir bayrağa dokun.",
        "Questions": "Sorular", "qdesc": "topluluk soru forumu.",
        "Lists": "Listeler", "Simulators": "Simülatörler", "Guides": "Kılavuzlar", "Contents": "İçerikler",
        "Equipment": "Ekipman", "Runes": "Rünler", "Specialists": "Uzmanlar", "Bestiary": "Bestiyer",
        "Buffs": "Buff'lar", "Environments": "Ortamlar", "Shortcuts": "Kısayollar", "Tattoos": "Dövmeler",
        "Fairies": "Periler", "Damage": "Hasar", "Gold": "Altın", "CharEval": "Değerlendirme",
        "Communities": "Topluluklar", "Instances": "Zindanlar", "Progression": "İlerleme",
        "Classes": "Sınıflar", "RaidGuides": "Baskınlar", "PCSetup": "PC",
        "footer": "İçindekiler nostar.fr temel alınarak · çevirmek için bayrakları kullan"},
}
def _sommaire(t: dict) -> str:
    return (
        f"{t['intro']}\n\n"
        f"**💬 [{t['Questions']}]({B}/forum)** : {t['qdesc']}\n\n"
        f"**📋 {t['Lists']}**\n"
        f"[{t['Equipment']}]({B}/stuffs/list) · [{t['Runes']}]({B}/stuffs/runelist) · [{t['Specialists']}]({B}/sp/list) · "
        f"[{t['Bestiary']}]({B}/monsters) · [{t['Buffs']}]({B}/buffs) · [XP]({B}/xp/list) · "
        f"[{t['Environments']}]({B}/quests) · [{t['Shortcuts']}]({B}/shortcut)\n\n"
        f"**🧪 {t['Simulators']}**\n"
        f"[{t['Equipment']}]({B}/stuffs/simulator) · [{t['Specialists']}]({B}/sp/simulator) · [{t['Tattoos']}]({B}/tattoos/simulator) · "
        f"[{t['Fairies']}]({B}/fairies/upgrade) · [XP]({B}/xp/simulator) · [{t['Damage']}]({B}/dmg/simulator) · "
        f"[{t['Gold']}]({B}/gold) · [{t['CharEval']}]({B}/evaluation)\n\n"
        f"**📖 {t['Guides']}**\n"
        f"[{t['Equipment']}]({B}/stuffs/upgrade) · [{t['Specialists']}]({B}/sp/guide) · [{t['Tattoos']}]({B}/tattoos/guide) · "
        f"[{t['Fairies']}]({B}/fairies/guide) · [{t['Communities']}]({B}/community/family) · [{t['Instances']}]({B}/instances/ic) · "
        f"[XP]({B}/xp/guide) · [{t['Gold']}]({B}/gold/guide) · [{t['Progression']}]({B}/progress/a1) · "
        f"[{t['Classes']}]({B}/class/adventurer) · [FAQ]({B}/faq/overview) · "
        f"[{t['RaidGuides']}]({B}/raids/guide) · [{t['PCSetup']}]({B}/pc/gstar-config)"
    )
def _embed(code: str) -> discord.Embed:
    t = TERMS[code]
    embed = discord.Embed(title=t["title"], url=B, color=ORANGE, description=_sommaire(t))
    embed.set_image(url=SEPARATOR)
    embed.set_footer(text=t["footer"])
    return embed
def _parse_unix(iso: str):
    if not iso:
        return None
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None
def _recent_embed(status: dict) -> discord.Embed:
    items = (status or {}).get("recent") or []
    if not items:
        return discord.Embed(title="🆕 Recent updates", color=ORANGE,
                             description="No recent updates to show right now.")
    lines = []
    for it in items[:10]:
        title = it.get("title") or it.get("page") or "?"
        url = it.get("url")
        tu = _parse_unix(it.get("modified_at", ""))
        when = f" · <t:{tu}:R>" if tu else ""
        lines.append(f"• [{title}]({url}){when}" if url else f"• {title}{when}")
    return discord.Embed(title="🆕 Recent updates", color=ORANGE,
                         description="\n".join(lines)[:4000])
class SiteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        recent = discord.ui.Button(label="Recent updates", emoji="🆕",
                      style=discord.ButtonStyle.secondary, custom_id="site:recent", row=0)
        recent.callback = self._recent
        self.add_item(recent)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"siteflag:{code}", row=1 + i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    async def _recent(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = await site_api.get_site_status()
        await interaction.followup.send(embed=_recent_embed(status), ephemeral=True)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(embed=_embed(code), ephemeral=True)
        return callback
class SiteLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    def _save_state(self):
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            print(f"[site_link] save_state échec: {e!r}", flush=True)
    async def cog_load(self):
        self.bot.add_view(SiteView())
    async def _publish(self):
        channel = self.bot.get_channel(SITE_NOSTAR_CHANNEL_ID)
        if channel is None:
            return
        for key in ("banner_id", "message_id"):
            mid = self.state.get(key)
            if not mid:
                continue
            try:
                m = await channel.fetch_message(int(mid))
                await m.delete()
            except Exception:
                pass
        new = {}
        try:
            if BANNER_FILE.exists():
                bm = await channel.send(
                    embed=discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}"),
                    file=discord.File(BANNER_FILE, filename=BANNER_NAME),
                )
                new["banner_id"] = bm.id
            msg = await channel.send(embed=_embed("en"), view=SiteView())
            new["message_id"] = msg.id
        except Exception as e:
            print(f"[site_link] publish échec: {e!r}", flush=True)
            return
        self.state = new
        self._save_state()
    @commands.command(name="site_refresh")
    @commands.is_owner()
    async def site_refresh(self, ctx: commands.Context):
        await self._publish()
        await ctx.send("Sommaire du site republié.")
async def setup(bot: commands.Bot):
    await bot.add_cog(SiteLink(bot))