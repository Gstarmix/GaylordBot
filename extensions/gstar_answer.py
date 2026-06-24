import asyncio
import json
import os
import time
from pathlib import Path
import aiohttp
import discord
from discord.ext import commands
from constants import GATE_FORUM_IDS, GSTAR_CHAT_LOG_CHANNEL_ID
from extensions import forum_tokens, site_api
from extensions.forum_helpers import first_post_is_webhook, post_log, gstar_avatar_url
from extensions.forum_i18n import t, code_for
WATCHED_FORUMS = GATE_FORUM_IDS
VISIT_LOCK_FORUM_IDS = GATE_FORUM_IDS
VISIT_TIMEOUT_SECONDS = 600
_WEBHOOK_NAME = "Gstar GPT Relay"
SITE_BASE = os.getenv("NOSTAR_SITE_INTERNAL_BASE", "http://127.0.0.1:5001").rstrip("/")
PENDING_ENDPOINT = f"{SITE_BASE}/gstar-gpt/forum-pending"
ACK_ENDPOINT = f"{SITE_BASE}/gstar-gpt/forum-pending/ack"
BOT_TOKEN = os.getenv("GSTAR_BOT_TOKEN", "")
SITE_BASIC_AUTH = os.getenv("NOSTAR_SITE_BASIC_AUTH", "").strip()
POLL_SECONDS = 3
REQUEST_TIMEOUT = 30
def _basic_auth():
    if ":" in SITE_BASIC_AUTH:
        user, pwd = SITE_BASIC_AUTH.split(":", 1)
        return aiohttp.BasicAuth(user, pwd)
    return None
_VISIT_LOCKS_PATH = Path(__file__).resolve().parent / "gstar_visit_locks.json"
class GstarAnswer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locked: set[int] = set()
        self._unlocked: set[int] = set()
        self._posted_subs: set[str] = set()
        self._poll_task: asyncio.Task | None = None
        self._visit_tasks: dict[int, asyncio.Task] = {}
        self._visit_deadlines: dict[str, float] = {}
        self._resume_task: asyncio.Task | None = None
        self._webhooks: dict[int, discord.Webhook] = {}
    async def cog_load(self):
        self._visit_deadlines = self._load_locks()
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._resume_task = asyncio.create_task(self._resume_visit_timers())
    async def cog_unload(self):
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()
        for task in list(self._visit_tasks.values()):
            if not task.done():
                task.cancel()
        self._visit_tasks.clear()
    def _load_locks(self) -> dict:
        try:
            data = json.loads(_VISIT_LOCKS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    def _save_locks(self) -> None:
        try:
            _VISIT_LOCKS_PATH.write_text(json.dumps(self._visit_deadlines), encoding="utf-8")
        except OSError as exc:
            print(f"[gstar_answer] échec sauvegarde deadlines : {exc!r}", flush=True)
    def _remember_deadline(self, tid: int, deadline: float) -> None:
        self._visit_deadlines[str(tid)] = deadline
        self._save_locks()
    def _forget_deadline(self, tid: int) -> None:
        if self._visit_deadlines.pop(str(tid), None) is not None:
            self._save_locks()
    async def _resume_visit_timers(self) -> None:
        await self.bot.wait_until_ready()
        if not self._visit_deadlines:
            return
        now = time.time()
        for tid_str, deadline in list(self._visit_deadlines.items()):
            try:
                tid = int(tid_str)
            except (TypeError, ValueError):
                self._visit_deadlines.pop(tid_str, None)
                self._save_locks()
                continue
            thread = await self._get_thread(tid)
            if thread is None:
                self._forget_deadline(tid)
                continue
            if not getattr(thread, "locked", False):
                self._unlocked.add(tid)
                self._forget_deadline(tid)
                continue
            self._locked.add(tid)
            remaining = max(0.0, deadline - now)
            self._visit_tasks[tid] = asyncio.create_task(self._visit_timeout(thread, remaining))
            print(f"[gstar_answer] timer visite repris thread {tid} (reste {int(remaining)}s)", flush=True)
    def _qcog(self):
        return self.bot.get_cog("Question")
    def _title_ok(self, thread: discord.Thread) -> bool:
        qcog = self._qcog()
        if qcog is None:
            return True
        errors = qcog.get_question_error(thread.name, thread.applied_tags) or []
        title_errors = [e for e in errors if "tag" not in e.lower()]
        return not title_errors
    async def _wait_for_reformulation(self, thread: discord.Thread, timeout: float = 15.0) -> None:
        elapsed = 0.0
        while elapsed < timeout:
            try:
                async for m in thread.history(limit=8):
                    for e in m.embeds:
                        if (e.title or "").startswith("✏️"):
                            return
            except discord.HTTPException:
                pass
            await asyncio.sleep(2.0)
            elapsed += 2.0
    @staticmethod
    def _visit_embed(code: str = "en") -> discord.Embed:
        return discord.Embed(
            title=t("visit_title", code),
            description=t("visit_desc", code),
            color=discord.Color.orange(),
        )
    async def _lock_for_visit(self, thread: discord.Thread):
        if thread.parent_id not in VISIT_LOCK_FORUM_IDS:
            return
        if thread.id in self._locked or thread.id in self._unlocked:
            return
        if not self._title_ok(thread):
            return
        self._locked.add(thread.id)
        try:
            await thread.edit(locked=True)
            print(f"[gstar_answer] thread {thread.id} verrouillé (en attente de visite)", flush=True)
        except discord.HTTPException as exc:
            self._locked.discard(thread.id)
            print(f"[gstar_answer] échec verrou thread {thread.id} : {exc!r}", flush=True)
            return
        await self._wait_for_reformulation(thread)
        try:
            member = thread.guild.get_member(thread.owner_id) if thread.guild and thread.owner_id else None
            await thread.send(embed=self._visit_embed(code_for(member)))
        except discord.HTTPException as exc:
            print(f"[gstar_answer] message verrou non posté thread {thread.id} : {exc!r}", flush=True)
        self._remember_deadline(thread.id, time.time() + VISIT_TIMEOUT_SECONDS)
        self._visit_tasks[thread.id] = asyncio.create_task(
            self._visit_timeout(thread, VISIT_TIMEOUT_SECONDS)
        )
    async def _visit_timeout(self, thread: discord.Thread, delay: float):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._visit_tasks.pop(thread.id, None)
        if thread.id in self._unlocked:
            return
        fresh = await self._get_thread(thread.id)
        self._locked.discard(thread.id)
        self._forget_deadline(thread.id)
        if fresh is None:
            return
        print(f"[gstar_answer] thread {thread.id} : pas de visite en {VISIT_TIMEOUT_SECONDS}s -> suppression", flush=True)
        qg = self.bot.get_cog("QuestionGate")
        if qg is not None:
            try:
                await qg._delete_thread(fresh, reason="no_visit", author_id=fresh.owner_id or 0)
                return
            except Exception as exc:
                print(f"[gstar_answer] suppression via QuestionGate échouée thread {thread.id} : {exc!r}", flush=True)
        try:
            await fresh.delete()
        except discord.HTTPException as exc:
            print(f"[gstar_answer] suppression directe échouée thread {thread.id} : {exc!r}", flush=True)
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id not in WATCHED_FORUMS:
            return
        if await first_post_is_webhook(thread):
            return
        await self._lock_for_visit(thread)
    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        if after.parent_id not in WATCHED_FORUMS:
            return
        if await first_post_is_webhook(after):
            return
        await self._lock_for_visit(after)
    async def _poll_loop(self):
        await self.bot.wait_until_ready()
        try:
            await site_api.set_gstar_avatar(gstar_avatar_url(self.bot))
        except Exception as exc:
            print(f"[gstar_answer] push avatar global échoué : {exc!r}", flush=True)
        while not self.bot.is_closed():
            try:
                await self._poll_once()
            except Exception as exc:
                print(f"[gstar_answer] poll en erreur : {exc!r}", flush=True)
            try:
                await self._poll_logs()
            except Exception as exc:
                print(f"[gstar_answer] poll logs en erreur : {exc!r}", flush=True)
            try:
                await self._poll_chat_logs()
            except Exception as exc:
                print(f"[gstar_answer] poll chat-logs en erreur : {exc!r}", flush=True)
            try:
                await self._poll_partage()
            except Exception as exc:
                print(f"[gstar_answer] poll partage en erreur : {exc!r}", flush=True)
            await asyncio.sleep(POLL_SECONDS)
    async def _poll_partage(self):
        items = await site_api.fetch_partage_pending()
        if not items:
            return
        done = []
        for it in items:
            thread = await self._get_thread(it.get("thread_id", 0))
            if thread is None:
                done.append(it["id"])
                continue
            try:
                webhook = await self._get_webhook(thread)
                question = (it.get("question") or "").strip()
                if question and webhook is not None:
                    for chunk in self._split_for_embeds(question, 1900):
                        await webhook.send(
                            content=chunk, username=(it.get("user_name") or "Player"),
                            avatar_url=(it.get("user_avatar") or None), thread=thread,
                            allowed_mentions=discord.AllowedMentions.none(), wait=True,
                        )
                await self._post_answer(thread, it.get("answer") or "")
                done.append(it["id"])
            except discord.HTTPException as exc:
                print(f"[gstar_answer] post partage échoué thread {it.get('thread_id')} : {exc!r}", flush=True)
        if done:
            await site_api.ack_partage(done)
    async def _poll_logs(self):
        logs = await site_api.fetch_pending_logs()
        for line in logs:
            await post_log(self.bot, str(line))
    async def _poll_chat_logs(self):
        logs = await site_api.fetch_chat_logs()
        if not logs:
            return
        channel = self.bot.get_channel(GSTAR_CHAT_LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(GSTAR_CHAT_LOG_CHANNEL_ID)
            except discord.HTTPException:
                return
        for it in logs:
            try:
                embed = discord.Embed(
                    title="📨 Message Gstar GPT",
                    description=(it.get("message") or "(vide)")[:4000],
                    color=discord.Color.blurple(),
                )
                embed.add_field(name="IP", value=f"`{it.get('ip', '?')}`", inline=True)
                embed.add_field(name="Page", value=(it.get("page") or "/")[:100], inline=True)
                if it.get("access"):
                    embed.add_field(name="Accès", value="spécial ✅", inline=True)
                if it.get("n_images"):
                    embed.add_field(name="Images", value=str(it["n_images"]), inline=True)
                if it.get("live"):
                    embed.add_field(name="Conversation", value=f"[Voir en live]({it['live']})", inline=False)
                embed.set_footer(text=f"cid {str(it.get('cid', ''))[:8]} · {it.get('ts', '')}")
                await channel.send(embed=embed)
            except discord.HTTPException as exc:
                print(f"[gstar_answer] chat-log embed échoué : {exc!r}", flush=True)
    async def _poll_once(self):
        items = await self._fetch_pending()
        if not items:
            return
        done_ids: list[str] = []
        for it in items:
            sid = it.get("id")
            token = it.get("token") or ""
            answer = (it.get("answer") or "").strip()
            question = (it.get("question") or "").strip()
            if not sid:
                continue
            if sid in self._posted_subs:
                done_ids.append(sid)
                continue
            entry = forum_tokens.resolve(token)
            if not entry or not answer:
                print(f"[gstar_answer] purge sub {sid} : jeton inconnu ({token[:8]}…) ou réponse vide", flush=True)
                done_ids.append(sid)
                continue
            thread = await self._get_thread(entry["thread_id"])
            if thread is None:
                print(f"[gstar_answer] purge sub {sid} : thread {entry['thread_id']} introuvable (supprimé ?)", flush=True)
                done_ids.append(sid)
                continue
            if question:
                await self._post_user_question(thread, entry.get("author_id", 0), question)
                await site_api.push_forum_turn(thread.id, "user", question)
            if await self._post_answer(thread, answer):
                self._posted_subs.add(sid)
                done_ids.append(sid)
                await self._unlock_once(thread)
                await site_api.push_forum_turn(
                    thread.id, "gstar", answer, avatar=gstar_avatar_url(self.bot)
                )
        if done_ids:
            await self._ack(done_ids)
    async def _get_webhook(self, thread: discord.Thread):
        parent = getattr(thread, "parent", None)
        if parent is None:
            return None
        cached = self._webhooks.get(parent.id)
        if cached is not None:
            return cached
        try:
            for h in await parent.webhooks():
                if h.name == _WEBHOOK_NAME and h.user and self.bot.user and h.user.id == self.bot.user.id:
                    self._webhooks[parent.id] = h
                    return h
            created = await parent.create_webhook(name=_WEBHOOK_NAME)
            self._webhooks[parent.id] = created
            return created
        except discord.HTTPException as exc:
            print(f"[gstar_answer] webhook indispo parent {parent.id} (perm Gérer les webhooks ?) : {exc!r}", flush=True)
            return None
    async def _author_identity(self, author_id: int):
        name, avatar = "Joueur", None
        try:
            user = self.bot.get_user(author_id) or await self.bot.fetch_user(author_id)
            if user:
                name = user.display_name or user.name or "Joueur"
                avatar = user.display_avatar.url if user.display_avatar else None
        except discord.HTTPException:
            pass
        return name, avatar
    async def _post_user_question(self, thread: discord.Thread, author_id: int, question: str):
        webhook = await self._get_webhook(thread)
        if webhook is None:
            return
        name, avatar = await self._author_identity(author_id)
        try:
            await webhook.send(
                content=question[:2000],
                username=name,
                avatar_url=avatar,
                thread=thread,
                allowed_mentions=discord.AllowedMentions.none(),
                wait=True,
            )
        except discord.HTTPException as exc:
            print(f"[gstar_answer] question webhook échouée thread {thread.id} : {exc!r}", flush=True)
    async def _get_thread(self, thread_id: int):
        ch = self.bot.get_channel(thread_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(thread_id)
            except discord.HTTPException:
                return None
        return ch if isinstance(ch, discord.Thread) else None
    @staticmethod
    def _split_for_embeds(text: str, limit: int = 4000) -> list[str]:
        text = text.strip()
        if len(text) <= limit:
            return [text] if text else [""]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > limit:
            cut = remaining.rfind("\n", 0, limit)
            if cut <= 0:
                cut = remaining.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks
    async def _post_answer(self, thread: discord.Thread, answer: str) -> bool:
        webhook = await self._get_webhook(thread)
        gstar_avatar = gstar_avatar_url(self.bot)
        chunks = self._split_for_embeds((answer or "").strip(), 1900)
        try:
            for chunk in chunks:
                if webhook is not None:
                    await webhook.send(
                        content=chunk, username="Gstar GPT", avatar_url=gstar_avatar,
                        thread=thread, allowed_mentions=discord.AllowedMentions.none(), wait=True,
                    )
                else:
                    await thread.send(chunk, allowed_mentions=discord.AllowedMentions.none())
            print(f"[gstar_answer] réponse postée dans le thread {thread.id} ({len(chunks)} message(s))", flush=True)
            return True
        except discord.HTTPException as exc:
            print(f"[gstar_answer] envoi réponse échoué thread {thread.id} : {exc!r}", flush=True)
            return False
    async def _unlock_once(self, thread: discord.Thread):
        if thread.id in self._unlocked:
            return
        self._unlocked.add(thread.id)
        self._locked.discard(thread.id)
        task = self._visit_tasks.pop(thread.id, None)
        if task and not task.done():
            task.cancel()
        self._forget_deadline(thread.id)
        try:
            await thread.edit(locked=False)
            print(f"[gstar_answer] thread {thread.id} déverrouillé (visite confirmée)", flush=True)
        except discord.HTTPException as exc:
            print(f"[gstar_answer] échec déverrou thread {thread.id} : {exc!r}", flush=True)
    def _headers(self) -> dict:
        return {"X-Gstar-Bot-Token": BOT_TOKEN}
    async def _fetch_pending(self) -> list:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    PENDING_ENDPOINT, headers=self._headers(), auth=_basic_auth()
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
        except Exception:
            return []
        if not data.get("ok"):
            return []
        return data.get("items") or []
    async def _ack(self, ids: list[str]):
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    ACK_ENDPOINT, json={"ids": ids}, headers=self._headers(), auth=_basic_auth()
                ) as resp:
                    await resp.read()
        except Exception as exc:
            print(f"[gstar_answer] ack échoué : {exc!r}", flush=True)
async def setup(bot: commands.Bot):
    await bot.add_cog(GstarAnswer(bot))