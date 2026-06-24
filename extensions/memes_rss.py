import json
import os
import re
import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks
from xml.etree import ElementTree as ET
from constants import MEMES_CHANNEL_ID
ORANGE = 0xE67E22
POST_INTERVAL_MINUTES = 180
MAX_PER_CYCLE = 2
MAX_SEEN_PER_FEED = 400
STATE_PATH = "memes_state.json"
HTTP_UA = "DiscordBot (https://nostar.fr, 1.0) memes-rss"
MEME_FEEDS = [
    ("https://www.reddit.com/r/memes/top/.rss?t=day", "EN", "r/memes"),
    ("https://www.reddit.com/r/wholesomememes/top/.rss?t=day", "EN", "r/wholesomememes"),
    ("https://www.reddit.com/r/Animemes/top/.rss?t=day", "EN", "r/Animemes"),
    ("https://www.reddit.com/r/rance/top/.rss?t=day", "FR", "r/rance"),
]
NSFW_PATTERNS = re.compile(r"\b(nsfw|porn|sex|gore|nude|onlyfans)\b", re.I)
_IMG_URL = re.compile(
    r"https?://[^\s\"'<>]+?\.(?:jpg|jpeg|png|gif|gifv|webp)(?:\?[^\s\"'<>]*)?", re.I)
_THUMB = re.compile(r"thumbs\.redditmedia|external-preview", re.I)
_ATOM = "{http://www.w3.org/2005/Atom}"
_MEDIA = "{http://search.yahoo.com/mrss/}"
def _img_rank(u: str) -> int:
    lu = u.lower()
    if "i.redd.it" in lu:
        return 0
    if "i.imgur" in lu:
        return 1
    if "preview.redd.it" in lu:
        return 2
    if _THUMB.search(lu):
        return 9
    return 5
def _extract_image(blob: str, links: list) -> str | None:
    cands = [m.group(0) for m in _IMG_URL.finditer(blob)]
    for ln in links:
        if ln:
            mm = _IMG_URL.search(ln)
            if mm:
                cands.append(mm.group(0))
    if not cands:
        return None
    cands.sort(key=_img_rank)
    url = cands[0]
    if url.lower().endswith(".gifv"):
        url = url[:-1]
    return url
def _parse_feed(text: str):
    out = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    entries = root.findall(f"{_ATOM}entry")
    if entries:
        for e in entries:
            guid = (e.findtext(f"{_ATOM}id") or "").strip()
            title = (e.findtext(f"{_ATOM}title") or "").strip()
            link = ""
            links = []
            for l in e.findall(f"{_ATOM}link"):
                href = l.get("href")
                if href:
                    links.append(href)
                    if not link:
                        link = href
            thumb = e.find(f"{_MEDIA}thumbnail")
            if thumb is not None and thumb.get("url"):
                links.insert(0, thumb.get("url"))
            content = e.findtext(f"{_ATOM}content") or ""
            image = _extract_image(content + " " + " ".join(links), links)
            if guid:
                out.append({"guid": guid, "title": title, "link": link, "image": image})
        return out
    for item in root.iter("item"):
        guid = (item.findtext("guid") or item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        links = [link]
        enc = item.find("enclosure")
        if enc is not None and enc.get("url"):
            links.insert(0, enc.get("url"))
        mc = item.find(f"{_MEDIA}content")
        if mc is not None and mc.get("url"):
            links.insert(0, mc.get("url"))
        desc = item.findtext("description") or ""
        image = _extract_image(desc + " " + " ".join(links), links)
        if guid:
            out.append({"guid": guid, "title": title, "link": link, "image": image})
    return out
class MemesRSS(commands.Cog):
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
            print(f"[memes_rss] save_state échec: {e!r}", flush=True)
    async def cog_load(self):
        if not self.post_loop.is_running():
            self.post_loop.start()
    def cog_unload(self):
        self.post_loop.cancel()
    async def _fetch(self, session, url):
        try:
            async with session.get(url, headers={"User-Agent": HTTP_UA}) as resp:
                if resp.status != 200:
                    print(f"[memes_rss] {url} -> HTTP {resp.status}", flush=True)
                    return None
                return await resp.text()
        except Exception as e:
            print(f"[memes_rss] fetch {url} échec: {e!r}", flush=True)
            return None
    @tasks.loop(minutes=POST_INTERVAL_MINUTES)
    async def post_loop(self):
        channel = self.bot.get_channel(MEMES_CHANNEL_ID)
        if channel is None:
            return
        posted = 0
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url, lang, label in MEME_FEEDS:
                if posted >= MAX_PER_CYCLE:
                    break
                text = await self._fetch(session, url)
                if not text:
                    continue
                seen = self.state.setdefault(url, [])
                seen_set = set(seen)
                for item in _parse_feed(text):
                    if posted >= MAX_PER_CYCLE:
                        break
                    if item["guid"] in seen_set:
                        continue
                    seen.append(item["guid"])
                    blob = f"{item['title']} {item['link']} {item.get('image') or ''}"
                    if NSFW_PATTERNS.search(blob):
                        continue
                    if not item.get("image"):
                        continue
                    embed = discord.Embed(
                        title=(item["title"] or "Meme")[:256],
                        url=item["link"] or None,
                        color=ORANGE,
                    )
                    embed.set_image(url=item["image"])
                    embed.set_footer(text=f"{label} · {lang}")
                    try:
                        await channel.send(embed=embed)
                        posted += 1
                    except Exception as e:
                        print(f"[memes_rss] send échec: {e!r}", flush=True)
                if len(seen) > MAX_SEEN_PER_FEED:
                    self.state[url] = seen[-MAX_SEEN_PER_FEED:]
                await asyncio.sleep(1)
        self._save_state()
    @post_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
    @commands.command(name="meme_now")
    @commands.is_owner()
    async def meme_now(self, ctx: commands.Context):
        await self.post_loop()
        await ctx.send("Cycle memes déclenché.")
async def setup(bot: commands.Bot):
    await bot.add_cog(MemesRSS(bot))