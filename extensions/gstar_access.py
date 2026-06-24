import os
import secrets
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands
from extensions import site_api
NOSTAR_PUBLIC_BASE = os.getenv("NOSTAR_PUBLIC_BASE", "https://preprod.nostar.fr").rstrip("/")
BUDGET_MIN, BUDGET_MAX = 1, 100000
DAYS_MIN, DAYS_MAX = 1, 3650
def _parse_duration(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip().lower()
    if raw in ("", "permanent", "perma", "0"):
        return None
    days = int(raw.rstrip("jd"))
    if not (DAYS_MIN <= days <= DAYS_MAX):
        raise ValueError(f"durée hors bornes : {days}")
    return days
def _fmt_expiry(expires: float | None) -> str:
    if not expires:
        return "permanent"
    return "expire le " + datetime.fromtimestamp(expires, tz=timezone.utc).strftime("%d/%m/%Y")
class GstarAccess(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @commands.hybrid_command(
        name="acces", aliases=["access", "grantaccess"],
        description="Accorde un accès spécial au chat Gstar GPT (lien envoyé en MP).",
    )
    @app_commands.describe(
        utilisateur="Joueur à qui accorder l'accès (ID accepté, même hors serveur en préfixe `!acces <id>`)",
        nombre=f"Nombre TOTAL de messages accordés ({BUDGET_MIN}-{BUDGET_MAX}, pas de reset quotidien)",
        duree="Durée de validité (ex. 7j, 30j ; vide = permanent)",
    )
    @commands.has_permissions(manage_guild=True)
    async def acces(self, ctx: commands.Context, utilisateur: discord.User = None,
                    nombre: int = None, duree: str = None):
        if utilisateur is None or nombre is None:
            await ctx.send(
                "Usage : `acces @utilisateur <nombre> [durée]` — accorde un accès spécial "
                "au Gstar GPT.\n`nombre` = messages au total (ex. `10`, `100`) ; "
                "`durée` = `7j`, `30j`… (vide = permanent).",
                ephemeral=True,
            )
            return
        if not (BUDGET_MIN <= nombre <= BUDGET_MAX):
            await ctx.send(f"`nombre` doit être entre {BUDGET_MIN} et {BUDGET_MAX}.", ephemeral=True)
            return
        try:
            days = _parse_duration(duree)
        except ValueError:
            await ctx.send(
                f"Durée illisible : `{duree}`. Exemples valides : `7j`, `30j`, `permanent` (ou vide).",
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        token = secrets.token_urlsafe(24)
        ok = await site_api.register_access_token(
            token, budget=nombre, days=days,
            discord_id=utilisateur.id, discord_name=str(utilisateur),
        )
        if not ok:
            await ctx.send("Le site n'a pas pu enregistrer l'accès (réessaie plus tard).", ephemeral=True)
            return
        link = f"{NOSTAR_PUBLIC_BASE}/?access={token}"
        validity = (
            f"jusqu'au {(datetime.now(timezone.utc) + timedelta(days=days)).strftime('%d/%m/%Y')}"
            if days else "sans date limite"
        )
        dm = (
            "Tu as reçu un **accès spécial au Gstar GPT** de Nostar ! 🎉\n\n"
            f"Il te donne **{nombre} message{'s' if nombre > 1 else ''}** dans le chat du site, "
            f"{validity}, sans passer par le salon des questions.\n\n"
            "Clique sur le bouton ci-dessous pour l'activer. Garde ce lien pour toi."
        )
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="Activer mon accès", emoji="🔓",
            style=discord.ButtonStyle.link, url=link,
        ))
        recap = f"{nombre} message{'s' if nombre > 1 else ''}, {validity}"
        try:
            await utilisateur.send(dm, view=view)
            await ctx.send(f"✅ Accès spécial accordé à {utilisateur.mention} ({recap}, lien envoyé en MP).",
                           ephemeral=True)
        except discord.HTTPException:
            await ctx.send(
                f"Accès créé ({recap}), mais impossible d'envoyer le MP à {utilisateur.mention} "
                f"(MP fermés ?). Transmets-lui ce lien :\n{link}",
                ephemeral=True,
            )
    @commands.hybrid_command(
        name="acces_liste", aliases=["accesliste", "accesslist"],
        description="Liste les accès spéciaux Gstar GPT actifs (conso, expiration).",
    )
    @commands.has_permissions(manage_guild=True)
    async def acces_liste(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        items = await site_api.list_access_tokens()
        if items is None:
            await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
            return
        if not items:
            await ctx.send("Aucun accès spécial actif.", ephemeral=True)
            return
        lines = []
        for it in items:
            who = it.get("discord_name") or it.get("discord_id") or "?"
            did = it.get("discord_id")
            mention = f"<@{did}>" if did else f"**{who}**"
            used, budget = it.get("used", 0), it.get("budget", 0)
            lines.append(f"• {mention} (`{who}`) — {used}/{budget} message(s) utilisés — {_fmt_expiry(it.get('expires'))}")
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 1900:
                await ctx.send(chunk, ephemeral=True)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            await ctx.send(chunk, ephemeral=True)
    @commands.hybrid_command(
        name="acces_retirer", aliases=["accesretirer", "revokeaccess"],
        description="Retire l'accès spécial Gstar GPT d'un joueur.",
    )
    @app_commands.describe(utilisateur="Joueur dont retirer l'accès (ID accepté en préfixe)")
    @commands.has_permissions(manage_guild=True)
    async def acces_retirer(self, ctx: commands.Context, utilisateur: discord.User = None):
        if utilisateur is None:
            await ctx.send("Usage : `acces_retirer @utilisateur` — retire son accès spécial.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)
        removed = await site_api.revoke_access(utilisateur.id)
        if removed is None:
            await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
        elif removed == 0:
            await ctx.send(f"{utilisateur.mention} n'avait pas d'accès spécial actif.", ephemeral=True)
        else:
            await ctx.send(f"🗑️ Accès spécial de {utilisateur.mention} retiré.", ephemeral=True)
    @commands.hybrid_command(
        name="debloquer", aliases=["deblocage", "unlock", "acces_lien"],
        description="Lève la limite de la conversation derrière un lien de partage Gstar GPT.",
    )
    @app_commands.describe(
        lien="Lien de partage (https://…/gstar-gpt/share/<id>) ou id nu",
        nombre=f"Messages accordés ({BUDGET_MIN}-{BUDGET_MAX} ; vide = défaut site ; 0 = révoquer)",
        duree="Durée de validité (ex. 7j, 30j ; vide = permanent)",
    )
    @commands.has_permissions(manage_guild=True)
    async def debloquer(self, ctx: commands.Context, lien: str = None,
                        nombre: int = None, duree: str = None):
        if lien is None:
            await ctx.send(
                "Usage : `debloquer <lien de partage> [nombre] [durée]` — lève la limite "
                "de la conversation derrière un lien `…/gstar-gpt/share/<id>`.\n"
                f"`nombre` = messages au total (vide = défaut site, `0` = révoquer) ; "
                "`durée` = `7j`, `30j`… (vide = permanent).",
                ephemeral=True,
            )
            return
        if nombre is not None and nombre != 0 and not (BUDGET_MIN <= nombre <= BUDGET_MAX):
            await ctx.send(f"`nombre` doit être entre {BUDGET_MIN} et {BUDGET_MAX} (ou `0` pour révoquer).",
                           ephemeral=True)
            return
        try:
            days = _parse_duration(duree)
        except ValueError:
            await ctx.send(
                f"Durée illisible : `{duree}`. Exemples valides : `7j`, `30j`, `permanent` (ou vide).",
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        data = await site_api.grant_from_share(lien, budget=nombre, days=days, granted_by=str(ctx.author))
        if data is None:
            await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
            return
        if not data.get("ok"):
            if data.get("error") == "no_conversation":
                await ctx.send(
                    "Ce partage n'a pas de conversation rattachée (vieux partage, créé avant la "
                    "fonctionnalité). Impossible de le débloquer : passe par `acces @utilisateur` à la place.",
                    ephemeral=True,
                )
            else:
                await ctx.send("Partage introuvable ou expiré (vérifie le lien).", ephemeral=True)
            return
        title = data.get("title") or "Sans titre"
        live = f"{NOSTAR_PUBLIC_BASE}/gstar-gpt/live/{data.get('cid', '')}"
        if data.get("revoked"):
            await ctx.send(
                (f"🗑️ Déblocage révoqué pour « {title} » (`{data.get('share_id', '?')}`)."
                 if data.get("existed")
                 else f"« {title} » (`{data.get('share_id', '?')}`) n'avait pas de déblocage actif."),
                ephemeral=True,
            )
            return
        budget = data.get("budget", 0)
        validity = (
            f"jusqu'au {(datetime.now(timezone.utc) + timedelta(days=days)).strftime('%d/%m/%Y')}"
            if days else "sans date limite"
        )
        await ctx.send(
            f"🔓 Conversation débloquée : « {title} » ({data.get('turns', 0)} tour(s)).\n"
            f"Budget : **{budget} message{'s' if budget > 1 else ''}**, {validity}.\n"
            "La personne n'a qu'à **continuer sa conversation** sur le site ; si elle ne la "
            "retrouve plus, elle peut rouvrir son propre lien de partage, ça la débloque aussi.\n"
            f"Suivre la conversation en direct : {live}",
            ephemeral=True,
        )
    @commands.hybrid_command(
        name="internet", aliases=["acces_internet", "web"],
        description="Accorde l'accès internet à une conversation Gstar GPT (lien de partage).",
    )
    @app_commands.describe(
        lien="Lien de partage (https://…/gstar-gpt/share/<id>) ou id nu",
        duree="Durée de validité (ex. 7j, 30j ; vide = permanent)",
        revoquer="Mettre à True pour RETIRER l'accès internet de cette conversation",
    )
    @commands.has_permissions(manage_guild=True)
    async def internet(self, ctx: commands.Context, lien: str = None,
                       duree: str = None, revoquer: bool = False):
        try:
            days = _parse_duration(duree)
        except ValueError:
            await ctx.send(
                f"Durée illisible : `{duree}`. Exemples valides : `7j`, `30j`, `permanent` (ou vide).",
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        if lien is None:
            if revoquer:
                await ctx.send(
                    "Pour révoquer, donne le lien de partage : `internet <lien> revoquer:True`.",
                    ephemeral=True,
                )
                return
            data = await site_api.mint_internet_share(days=days, granted_by=str(ctx.author))
            if data is None:
                await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
                return
            if not data.get("ok"):
                await ctx.send("La génération du lien a échoué (réessaie plus tard).", ephemeral=True)
                return
            url = f"{NOSTAR_PUBLIC_BASE}{data.get('path', '')}"
            validity = (
                f"jusqu'au {(datetime.now(timezone.utc) + timedelta(days=days)).strftime('%d/%m/%Y')}"
                if days else "sans date limite"
            )
            await ctx.send(
                f"🌐✨ Lien internet vierge généré, {validity} :\n{url}\n"
                "Donne-le au joueur : il l'ouvre, démarre sa conversation de zéro, et le "
                "bouton 🌐 est **déjà déverrouillé**.",
                ephemeral=True,
            )
            return
        data = await site_api.grant_internet_from_share(
            lien, days=days, revoke=revoquer, granted_by=str(ctx.author))
        if data is None:
            await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
            return
        if not data.get("ok"):
            if data.get("error") == "no_conversation":
                await ctx.send(
                    "Ce partage n'a pas de conversation rattachée (vieux partage). "
                    "Impossible d'y accorder l'accès internet.",
                    ephemeral=True,
                )
            else:
                await ctx.send("Partage introuvable ou expiré (vérifie le lien).", ephemeral=True)
            return
        title = data.get("title") or "Sans titre"
        if data.get("revoked"):
            await ctx.send(
                (f"🌐🗑️ Accès internet retiré pour « {title} » (`{data.get('share_id', '?')}`)."
                 if data.get("existed")
                 else f"« {title} » (`{data.get('share_id', '?')}`) n'avait pas d'accès internet actif."),
                ephemeral=True,
            )
            return
        validity = (
            f"jusqu'au {(datetime.now(timezone.utc) + timedelta(days=days)).strftime('%d/%m/%Y')}"
            if days else "sans date limite"
        )
        await ctx.send(
            f"🌐 Accès internet accordé à « {title} » (`{data.get('share_id', '?')}`), {validity}.\n"
            "La personne verra un **bouton 🌐 déverrouillé** dans son chat : elle l'active quand "
            "elle veut que Gstar GPT cherche sur le web (sources vérifiées). Elle n'a qu'à "
            "**continuer sa conversation** (ou rouvrir son lien de partage).",
            ephemeral=True,
        )
    @commands.hybrid_command(
        name="quota", aliases=["quotas", "modeles"],
        description="État des quotas des modèles IA du Gstar GPT (Gemini + secours).",
    )
    @commands.has_permissions(manage_guild=True)
    async def quota(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        data = await site_api.get_models_status()
        if data is None:
            await ctx.send("Le site n'a pas répondu (réessaie plus tard).", ephemeral=True)
            return
        def model_line(m: dict) -> str:
            label = f"`{m['model']}`" if m["provider"] == "gemini" else f"`{m['provider']}:{m['model']}`"
            last_ok, last_fail, retry_at = m.get("last_ok"), m.get("last_quota_fail"), m.get("retry_at")
            if last_fail and (not last_ok or last_fail >= last_ok):
                kind = m.get("fail_kind") or ""
                limit = m.get("quota_limit")
                unit = "tokens" if m.get("quota_unit") == "tokens" else "req"
                if kind == "not_found":
                    return (f"⚫ {label} — introuvable (404) <t:{int(last_fail)}:R> : "
                            "modèle arrêté/renommé par le fournisseur, à retirer de la chaîne "
                            "(ne reviendra pas au reset)")
                if kind == "quota_minute":
                    line = f"🔴 {label} — cap PAR MINUTE atteint"
                    if limit:
                        line += f" (limite {limit} {unit}/min)"
                    line += f" <t:{int(last_fail)}:R>"
                    if retry_at and retry_at > last_fail:
                        line += f", réessayable <t:{int(retry_at)}:R>"
                    else:
                        line += ", se relâche en ~1 min"
                    return line
                if kind == "quota_day":
                    line = f"🔴 {label} — quota JOURNALIER épuisé"
                    if limit:
                        line += f" (limite {limit} {unit}/jour)"
                    line += f" <t:{int(last_fail)}:R>, reset à minuit heure Pacifique"
                    return line
                line = f"🔴 {label} — quota épuisé / en échec <t:{int(last_fail)}:R>"
                if retry_at and retry_at > last_fail:
                    line += f" (réessayable <t:{int(retry_at)}:R>)"
                if kind == "error" and (m.get("last_error") or "").strip():
                    err = " ".join(m["last_error"].split())
                    line += f"\n　↳ `{err[:90]}`"
                return line
            if last_ok:
                return f"🟢 {label} — OK, dernier succès <t:{int(last_ok)}:R>"
            return f"⚪ {label} — pas encore appelé depuis le dernier restart du site"
        models = data.get("models") or []
        gemini = [m for m in models if m["provider"] == "gemini"]
        secours = [m for m in models if m["provider"] != "gemini"]
        resets = data.get("resets") or {}
        lines = []
        if data.get("serving"):
            lines.append(f"**Modèle qui sert actuellement** : `{data['serving']}`")
        if data.get("last_allfail"):
            lines.append(f"⚠️ Dernier « tous à sec » : <t:{int(data['last_allfail'])}:R>")
        lines.append("")
        lines.append("**Chaîne Gemini**" + (
            f" (reset des quotas journaliers <t:{int(resets['gemini_daily'])}:R>, "
            f"<t:{int(resets['gemini_daily'])}:t> = minuit heure Pacifique) :"
            if resets.get("gemini_daily") else " :"
        ))
        lines.extend(model_line(m) for m in gemini)
        if secours:
            lines.append("")
            lines.append("**Secours (Groq / Mistral / OpenRouter gratuits, DeepSeek payant)** :")
            lines.extend(model_line(m) for m in secours)
            if resets.get("openrouter_daily"):
                lines.append(f"Reset journalier OpenRouter `:free` : <t:{int(resets['openrouter_daily'])}:R> (minuit UTC).")
        bal = data.get("deepseek_balance")
        if bal and bal.get("total") is not None:
            devise = "$" if bal.get("currency") == "USD" else (bal.get("currency") or "")
            line = f"💰 Solde DeepSeek (prépayé) : **{bal['total']} {devise}**"
            if not bal.get("available"):
                line += " ⛔ épuisé : recharge sur platform.deepseek.com/top_up"
            lines.append(line)
        tav = data.get("tavily_usage")
        if tav and tav.get("used") is not None:
            limit = tav.get("limit")
            if limit is None:
                limit = tav.get("plan_limit")
            quota_txt = f"{tav['used']}/{limit}" if limit is not None else f"{tav['used']} (illimité)"
            plan = tav.get("plan")
            line = f"🌐 Tavily (recherche web) : **{quota_txt}** crédits utilisés ce cycle"
            if plan:
                line += f" — plan `{plan}`"
            if limit is not None and isinstance(tav["used"], (int, float)) and tav["used"] >= limit:
                line += " ⛔ quota atteint"
            lines.append(line)
        lines.append("")
        lines.append(
            "ℹ️ Les caps PAR MINUTE se relâchent en ~1 min tout seuls ; les caps "
            "JOURNALIERS aux heures ci-dessus. Aucun fournisseur n'expose de "
            "compteur « restant » : cet état vient des derniers appels réels."
        )
        chunk = ""
        for ln in "\n".join(lines).split("\n"):
            if chunk and len(chunk) + 1 + len(ln) > 1990:
                await ctx.send(chunk, ephemeral=True)
                chunk = ln
            else:
                chunk = f"{chunk}\n{ln}" if chunk else ln
        if chunk:
            await ctx.send(chunk, ephemeral=True)
    @commands.hybrid_command(
        name="help", aliases=["aide", "commandes"],
        description="Liste toutes les commandes Gaylord et leur usage.",
    )
    @commands.has_permissions(manage_guild=True)
    async def help(self, ctx: commands.Context):
        msg = (
            "**Commandes Gaylord — récapitulatif**\n"
            "\n"
            "**Budget de messages Gstar GPT**\n"
            "`acces @user <nombre> [durée]` — accorde un quota de messages (DM avec lien d'activation) ; "
            "re-faire = remplace. Ex : `acces @Gstar 50 7j`\n"
            "`acces_liste` — liste les accès spéciaux actifs (qui, conso, expiration)\n"
            "`acces_retirer @user` — révoque immédiatement l'accès d'un joueur\n"
            "`debloquer <lien> [nombre] [durée]` — lève la limite sur UNE conv précise via son "
            "lien de partage (alias : `acces_lien`). La personne n'a rien à activer, elle continue "
            "juste sa conv. `nombre 0` = révoquer\n"
            "\n"
            "**Accès internet (recherche web dans Gstar GPT)**\n"
            "`internet` — génère un lien vierge avec internet déjà déverrouillé (à donner au joueur)\n"
            "`internet <lien> [durée]` — déverrouille le 🌐 sur UNE conv existante (via son share)\n"
            "`internet <lien> revoquer:True` — retire l'accès internet de cette conv\n"
            "\n"
            "**Quotas & modèles IA**\n"
            "`quota` — état des modèles IA (Gemini, secours) + crédits Tavily (recherche web)\n"
            "\n"
            "**Forum & sujets**\n"
            "`forumpartage <lien> @user` — crée un sujet #questions depuis un lien de partage Gstar GPT\n"
            "`limite_reset @user` — remet à zéro son compteur journalier de sujets #questions\n"
            "\n"
            "**Misc**\n"
            "`sync` — resynchronise les slash-commands Discord (préfixe `!` uniquement)\n"
        )
        await ctx.send(msg, ephemeral=True)
    @acces.error
    @acces_retirer.error
    async def acces_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Commande réservée aux gestionnaires du serveur.", ephemeral=True)
        elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound, commands.BadArgument)):
            await ctx.send("Utilisateur introuvable. Usage : `acces @utilisateur <nombre> [durée]` (ou `acces <id> …`).",
                           ephemeral=True)
    @acces_liste.error
    @quota.error
    @debloquer.error
    async def acces_liste_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Commande réservée aux gestionnaires du serveur.", ephemeral=True)
async def setup(bot: commands.Bot):
    await bot.add_cog(GstarAccess(bot))