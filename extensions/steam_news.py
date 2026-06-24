import json
import os
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
import aiohttp
import discord
from discord.ext import commands, tasks
from constants import NOSTALE_NEWS_CHANNEL_ID, ANNOUNCE_ROLE_IDS
from extensions import site_api
from extensions.translate import FLAG_LANGS, FLAG_FOOTER
ORANGE = 0xE67E22
POLL_SECONDS = 300
STATE_PATH = "steam_news_seen.json"
STEAM_ROLE_ID = ANNOUNCE_ROLE_IDS.get("steam")
STEAM_APPID = "550470"
STEAM_NEWS_URL = "https://store.steampowered.com/news/app/550470"
STEAM_LANG = {"fr": "french", "en": "english", "de": "german", "it": "italian",
              "es": "spanish", "pl": "polish", "ru": "russian", "cs": "czech", "tr": "turkish"}
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
STEAM_SLATE = 0x607D8B
BANNER_FILE = os.path.join(os.path.dirname(__file__), "assets", "banner_steam.png")
BANNER_NAME = "banner_steam.png"
def _to_md(html: str) -> str:
    s = html or ""
    s = re.sub(r"<img[^>]*>", "", s, flags=re.I)
    s = re.sub(r'<div[^>]*bb_h[1-6][^>]*>(.*?)</div>', r"\n\n**\1**\n", s, flags=re.S | re.I)
    s = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", s, flags=re.S | re.I)
    s = re.sub(r"</?(?:b|strong)\s*>", "**", s, flags=re.I)
    s = re.sub(r"</?(?:i|em)\s*>", "*", s, flags=re.I)
    s = re.sub(r"<li[^>]*>(.*?)</li>", r"• \1\n", s, flags=re.S | re.I)
    s = re.sub(r"</?(?:ul|ol|p|div|h[1-6])[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
def _clean(desc_html: str):
    mi = _IMG_RE.search(desc_html or "")
    return _to_md(desc_html), (mi.group(1) if mi else "")
def _parse_feed(xml_text: str) -> list:
    items = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        gid = link.rstrip("/").split("/")[-1] if "/view/" in link else (it.findtext("guid") or "").strip()
        title = (it.findtext("title") or "").strip()
        if not (title and gid):
            continue
        text, img = _clean(it.findtext("description") or "")
        items.append({"gid": gid, "title": title[:256], "desc": text, "image": img,
                      "link": link, "date": (it.findtext("pubDate") or "").strip()})
    return items
async def _http_text(url: str) -> "str | None":
    for _ in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        return await r.text()
        except Exception:
            pass
    return None
async def _fetch_lang(lang_code: str) -> list:
    steam_lang = STEAM_LANG.get(lang_code, "english")
    xml_text = await _http_text(f"https://store.steampowered.com/feeds/news/app/{STEAM_APPID}/?l={steam_lang}")
    if xml_text:
        try:
            return _parse_feed(xml_text)
        except Exception as e:
            print(f"[steam_news] parse {steam_lang} KO: {e!r}", flush=True)
    if lang_code == "en":
        return await site_api.steam_news_recent()
    item_list = []
    return item_list
_CTA_BY_LANG = {
    "en": "Read the full news on Steam", "fr": "Lire la news complète sur Steam",
    "de": "Die vollständige News auf Steam lesen", "it": "Leggi la notizia completa su Steam",
    "es": "Leer la noticia completa en Steam", "pl": "Przeczytaj pełną wiadomość na Steam",
    "ru": "Читать полную новость в Steam", "cs": "Přečíst celou novinku na Steamu",
    "tr": "Haberin tamamını Steam'de oku",
}
_FOOTER_BY_LANG = {
    "en": "🎮 Tap a flag below to read this in your language",
    "fr": "🎮 Touchez un drapeau pour lire dans votre langue",
    "de": "🎮 Tippe auf eine Flagge, um in deiner Sprache zu lesen",
    "it": "🎮 Tocca una bandiera per leggere nella tua lingua",
    "es": "🎮 Toca una bandera para leerlo en tu idioma",
    "pl": "🎮 Kliknij flagę, aby przeczytać w swoim języku",
    "ru": "🎮 Нажмите флаг, чтобы читать на своём языке",
    "cs": "🎮 Klikni na vlajku pro čtení ve svém jazyce",
    "tr": "🎮 Kendi dilinde okumak için bir bayrağa dokun",
}
def _trim(text: str, n: int = 1700) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"
def _news_embed(item: dict, lang: str = "en", with_flags: bool = True) -> discord.Embed:
    link = item.get("link")
    body = _trim(item.get("desc"))
    if link:
        body += f"\n\n[**▶ Read on Steam**]({link})"
    e = discord.Embed(title=(item.get("title") or "News")[:256], url=link or None,
                      description=body[:4096], color=STEAM_SLATE)
    if item.get("image"):
        e.set_image(url=item["image"])
    if item.get("date"):
        try:
            e.timestamp = parsedate_to_datetime(item["date"])
        except Exception:
            pass
    if with_flags:
        e.set_footer(text=FLAG_FOOTER)
    return e
class SteamFlagsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i, (code, flag, _name) in enumerate(FLAG_LANGS):
            btn = discord.ui.Button(emoji=flag, style=discord.ButtonStyle.secondary,
                                    custom_id=f"steamflag:{code}", row=i // 4)
            btn.callback = self._make_cb(code)
            self.add_item(btn)
    def _make_cb(self, code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            embeds = interaction.message.embeds if interaction.message else []
            url = next((e.url for e in embeds if e.url), "")
            gid = url.rstrip("/").split("/")[-1] if "/view/" in (url or "") else ""
            if not gid:
                await interaction.followup.send("Nothing to translate here.", ephemeral=True)
                return
            item = next((i for i in await _fetch_lang(code) if i["gid"] == gid), None)
            if not item:
                item = await site_api.steam_news_item(gid, code)
            if not item:
                await interaction.followup.send("Translation unavailable right now.", ephemeral=True)
                return
            await interaction.followup.send(embed=_news_embed(item, code, with_flags=False), ephemeral=True)
        return callback
class SteamNews(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.seen = self._load()
    def _load(self) -> set:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()
    def _save(self):
        try:
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(self.seen), f)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            print(f"[steam_news] save échec: {e!r}", flush=True)
    async def cog_load(self):
        self.bot.add_view(SteamFlagsView())
        if not self.poll_loop.is_running():
            self.poll_loop.start()
    def cog_unload(self):
        self.poll_loop.cancel()
    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_loop(self):
        items = await _fetch_lang("en")
        if not items:
            return
        if not self.seen:
            self.seen = {i["gid"] for i in items}
            self._save()
            print(f"[steam_news] amorçage : {len(self.seen)} GID marqués vus", flush=True)
            return
        channel = self.bot.get_channel(NOSTALE_NEWS_CHANNEL_ID)
        if channel is None:
            return
        role = channel.guild.get_role(STEAM_ROLE_ID) if (channel.guild and STEAM_ROLE_ID) else None
        for item in [i for i in reversed(items) if i["gid"] not in self.seen]:
            try:
                content = f"{role.mention} {item['link']}" if role else item.get("link")
                kwargs = {"content": content, "view": SteamFlagsView(),
                          "allowed_mentions": discord.AllowedMentions(roles=[role] if role else [])}
                if os.path.exists(BANNER_FILE):
                    banner = discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}")
                    kwargs["embeds"] = [banner, _news_embed(item)]
                    kwargs["file"] = discord.File(BANNER_FILE, filename=BANNER_NAME)
                else:
                    kwargs["embed"] = _news_embed(item)
                msg = await channel.send(**kwargs)
                try:
                    await msg.publish()
                except Exception:
                    pass
            except Exception as e:
                print(f"[steam_news] post échec {item['gid']}: {e!r}", flush=True)
                continue
            self.seen.add(item["gid"])
            self._save()
    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
    @commands.command(name="steam_news_test")
    @commands.is_owner()
    async def steam_news_test(self, ctx: commands.Context):
        items = await _fetch_lang("en")
        if not items:
            await ctx.send("Flux Steam indisponible (egress ?).")
            return
        role = ctx.guild.get_role(STEAM_ROLE_ID) if (ctx.guild and STEAM_ROLE_ID) else None
        it = items[0]
        content = f"{role.mention} {it['link']}" if role else it.get("link")
        kwargs = {"content": content, "view": SteamFlagsView(),
                  "allowed_mentions": discord.AllowedMentions(roles=[role] if role else [])}
        if os.path.exists(BANNER_FILE):
            banner = discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}")
            kwargs["embeds"] = [banner, _news_embed(it)]
            kwargs["file"] = discord.File(BANNER_FILE, filename=BANNER_NAME)
        else:
            kwargs["embed"] = _news_embed(it)
        await ctx.send(**kwargs)
async def setup(bot: commands.Bot):
    await bot.add_cog(SteamNews(bot))