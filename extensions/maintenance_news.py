import json
import os
import re
import xml.etree.ElementTree as ET
from html import unescape
import aiohttp
import discord
from discord.ext import commands, tasks
from constants import MAINTENANCE_FEED_URL, NOSTALE_NEWS_CHANNEL_ID, ANNOUNCE_ROLE_IDS
from extensions.translate import MultiFlagsView, FLAG_FOOTER, _translate_free
ORANGE = 0xE67E22
AMBER = 0xF1C40F
POLL_SECONDS = 900
STATE_PATH = "maintenance_seen.json"
ROLE_ID = ANNOUNCE_ROLE_IDS.get("maintenance")
BANNER_FILE = os.path.join(os.path.dirname(__file__), "assets", "banner_maintenance.png")
BANNER_NAME = "banner_maintenance.png"
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_DATE_RE = re.compile(r"\d{1,2}[.\/]\d{1,2}[.\/]\d{4}")
_BODY_RE = re.compile(r'<div class="messageText">(.*?)</div>\s*</div>', re.S)
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
def _trim(t: str, n: int = 1700) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"
def _parse_maintenances(xml_text: str) -> list:
    out = []
    for it in ET.fromstring(xml_text).iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if "maintenance" not in title.lower():
            continue
        gid = (re.search(r"/thread/(\d+)", link) or [None, ""])[1] if "/thread/" in link else link
        if not (title and gid):
            continue
        out.append({"gid": str(gid), "title": title, "link": link,
                    "desc": it.findtext("description") or ""})
    return out
async def _fetch(url: str) -> "str | None":
    for _ in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        return await r.text()
        except Exception:
            pass
    return None
async def _en(text: str) -> str:
    if not text:
        return text
    return (await _translate_free(text, "en")) or text
class MaintenanceNews(commands.Cog):
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
            print(f"[maintenance] save échec: {e!r}", flush=True)
    async def cog_load(self):
        if not self.poll_loop.is_running():
            self.poll_loop.start()
    def cog_unload(self):
        self.poll_loop.cancel()
    async def _build(self, item: dict):
        page = await _fetch(item["link"])
        body_html = ""
        img = (_IMG_RE.search(item["desc"]) or [None, ""])[1] if _IMG_RE.search(item["desc"]) else ""
        if page:
            mb = _BODY_RE.search(page) or re.search(r'<div[^>]*messageText[^>]*>(.*?)</div>', page, re.S)
            if mb:
                body_html = mb.group(1)
            if not img:
                og = re.search(r'<meta property="og:image" content="([^"]+)"', page)
                img = og.group(1).replace("&amp;", "&") if og else ""
        body_fr = _to_md(body_html) if body_html else _to_md(item["desc"])
        en_title = await _en(_to_md(item["title"]))
        d = _DATE_RE.search(item["title"])
        if d:
            en_title = _DATE_RE.sub(d.group(), en_title)
        en_body = await _en(body_fr)
        desc = _trim(en_body) + f"\n\n[**▶ Read on GameForge**]({item['link']})"
        banner = discord.Embed(color=ORANGE).set_image(url=f"attachment://{BANNER_NAME}")
        content = discord.Embed(title=en_title[:256], url=item["link"],
                                description=desc[:4096], color=AMBER).set_footer(text=FLAG_FOOTER)
        if img:
            content.set_image(url=img)
        file = discord.File(BANNER_FILE, filename=BANNER_NAME) if os.path.exists(BANNER_FILE) else None
        return banner, content, file
    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_loop(self):
        xml_text = await _fetch(MAINTENANCE_FEED_URL)
        if not xml_text:
            return
        try:
            items = _parse_maintenances(xml_text)
        except Exception as e:
            print(f"[maintenance] parse KO: {e!r}", flush=True)
            return
        if not items:
            return
        if not self.seen:
            self.seen = {i["gid"] for i in items}
            self._save()
            print(f"[maintenance] amorçage : {len(self.seen)} GID marqués vus", flush=True)
            return
        channel = self.bot.get_channel(NOSTALE_NEWS_CHANNEL_ID)
        if channel is None:
            return
        role = channel.guild.get_role(ROLE_ID) if (channel.guild and ROLE_ID) else None
        for item in [i for i in reversed(items) if i["gid"] not in self.seen]:
            try:
                banner, content, file = await self._build(item)
                msg = await channel.send(
                    content=(f"{role.mention} {item['link']}" if role else item["link"]),
                    embeds=[banner, content],
                    file=file,
                    view=MultiFlagsView(),
                    allowed_mentions=discord.AllowedMentions(roles=[role] if role else []),
                )
                try:
                    await msg.publish()
                except Exception:
                    pass
            except Exception as e:
                print(f"[maintenance] post échec {item['gid']}: {e!r}", flush=True)
                continue
            self.seen.add(item["gid"])
            self._save()
    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
    @commands.command(name="maintenance_test")
    @commands.is_owner()
    async def maintenance_test(self, ctx: commands.Context):
        xml_text = await _fetch(MAINTENANCE_FEED_URL)
        items = _parse_maintenances(xml_text) if xml_text else []
        if not items:
            await ctx.send("Flux GameForge indisponible ou aucune maintenance.")
            return
        role = ctx.guild.get_role(ROLE_ID) if (ctx.guild and ROLE_ID) else None
        banner, content, file = await self._build(items[0])
        await ctx.send(content=(role.mention if role else None), embeds=[banner, content],
                       file=file, view=MultiFlagsView(),
                       allowed_mentions=discord.AllowedMentions(roles=[role] if role else []))
async def setup(bot: commands.Bot):
    await bot.add_cog(MaintenanceNews(bot))