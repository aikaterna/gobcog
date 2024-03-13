# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from string import ascii_letters, digits
from typing import Optional, Union

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_number, pagify

from .abc import AdventureMixin
from .bank import bank
from .cart import Trader
from .charsheet import Character
from .constants import DEV_LIST, Rarities, Slot
from .converters import RarityConverter, SlotConverter
from .helpers import escape, is_dev
from .menus import BaseMenu, SimpleSource
from .rng import GameSeed, Random

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class DevCommands(AdventureMixin):
    """This class will handle dealing with developer only commands"""

    async def no_dev_prompt(self, ctx: commands.Context) -> bool:
        if ctx.author.id in DEV_LIST:
            return True
        confirm_token = "".join(random.choices((*ascii_letters, *digits), k=16))
        await ctx.send(
            "**__You should not be running this command.__** "
            "Any issues that arise from you running this command will not be supported. "
            "If you wish to continue, enter this token as your next message."
            f"\n\n{confirm_token}"
        )
        try:
            message = await ctx.bot.wait_for(
                "message",
                check=lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id,
                timeout=60,
            )
        except asyncio.TimeoutError:
            await ctx.send(_("Did not get confirmation, cancelling."))
            return False
        else:
            if message.content.strip() == confirm_token:
                return True
            else:
                await ctx.send(_("Did not get a matching confirmation, cancelling."))
                return False

    @commands.command(name="devcooldown")
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def _devcooldown(self, ctx: commands.Context):
        """[Dev] Resets the after-adventure cooldown in this server."""
        if not await self.no_dev_prompt(ctx):
            return
        await self.config.guild(ctx.guild).cooldown.set(0)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def makecart(self, ctx: commands.Context, stockcount: Optional[int] = None):
        """[Dev] Force a cart to appear."""
        if not await self.no_dev_prompt(ctx):
            return
        trader = Trader(60, ctx, self)
        await trader.start(ctx, bypass=True, stockcount=stockcount)
        await asyncio.sleep(60)
        trader.stop()
        await trader.on_timeout()

    @commands.command()
    @commands.is_owner()
    async def genitems(
        self,
        ctx: commands.Context,
        rarity: RarityConverter,
        slot: SlotConverter,
        num: int = 1,
    ):
        """[Dev] Generate random items."""
        if not await self.no_dev_prompt(ctx):
            return
        user = ctx.author
        slot = slot.lower()
        async with self.get_lock(user):
            try:
                c = await Character.from_json(ctx, self.config, user, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            for _loop_counter in range(num):
                await c.add_to_backpack(await self._genitem(ctx, rarity, slot))
            await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
        await ctx.invoke(self._backpack)

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def copyuser(self, ctx: commands.Context, user_id: int):
        """[Owner] Copy another members data to yourself.

        Note this overrides your current data.
        """
        user_data = await self.config.user_from_id(user_id).all()
        await self.config.user(ctx.author).set(user_data)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devrebirth(
        self,
        ctx: commands.Context,
        rebirth_level: int = 1,
        character_level: int = 1,
        users: commands.Greedy[discord.Member] = None,
    ):
        """[Dev] Set multiple users rebirths and level."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        if not is_dev(ctx.author):
            if rebirth_level > 100:
                await ctx.send("Rebirth is too high.")
                await ctx.send_help()
                return
            elif character_level > 1000:
                await ctx.send("Level is too high.")
                await ctx.send_help()
                return
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                bal = await bank.get_balance(target)
                if bal >= 1000:
                    withdraw = bal - 1000
                    await bank.withdraw_credits(target, withdraw)
                else:
                    withdraw = bal
                    await bank.set_balance(target, 0)
                character_data = await c.rebirth(dev_val=rebirth_level)
                await self.config.user(target).set(character_data)
                await ctx.send(
                    content=box(
                        _("{c}, congratulations on your rebirth.\nYou paid {bal}.").format(
                            c=escape(target.display_name), bal=humanize_number(withdraw)
                        ),
                        lang="ansi",
                    )
                )
            await self._add_rewards(ctx, target, int((character_level) ** 3.5) + 1, 0, False)
        await ctx.tick()

    @commands.command()
    @commands.bot_has_permissions(add_reactions=True)
    @commands.is_owner()
    async def devreset(self, ctx: commands.Context, users: commands.Greedy[Union[discord.Member, discord.User]]):
        """[Dev] Reset the skill cooldown for multiple users."""
        if not await self.no_dev_prompt(ctx):
            return
        targets = users or [ctx.author]
        for target in targets:
            async with self.get_lock(target):
                try:
                    c = await Character.from_json(ctx, self.config, target, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    continue
                c.heroclass["ability"] = False
                c.heroclass["cooldown"] = 0
                if "catch_cooldown" in c.heroclass:
                    c.heroclass["catch_cooldown"] = 0
                await self.config.user(target).set(await c.to_json(ctx, self.config))
        await ctx.tick()

    @commands.command(name="adventureseed")
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.is_owner()
    async def _adventureseed(self, ctx: commands.Context, seed: Union[str, int]):
        """[Owner] Shows information about an adventure seed"""
        if isinstance(seed, str):
            seed = int(seed, 16)
        gameseed = GameSeed.from_int(int(seed))
        rng = Random(gameseed)
        c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        monster_roster, monster_stats, transcended = await self.update_monster_roster(c=c, rng=rng)
        challenge = await self.get_challenge(monster_roster, rng)
        attribute = rng.choice(list(self.ATTRIBS.keys()))
        monster = monster_roster[challenge].copy()
        seed_box = box(hex(rng.internal_seed)[2:].upper())

        hp = monster["hp"]
        dipl = monster["dipl"]
        pdef = monster["pdef"]
        mdef = monster["mdef"]
        cdef = monster.get("cdef", 1.0)
        boss = monster["boss"]
        miniboss = monster["miniboss"]
        base_stats = f"HP: {hp}\nCHA: {dipl}\nPDEF: {pdef:0.2f}\nMDEF: {mdef:0.2f}\nCDEF: {cdef:0.2f}"

        dynamic_stats = self._dynamic_monster_stats(monster.copy(), rng)
        state = rng.getstate()
        easy_mode = bool(rng.getrandbits(1))
        no_monster_30 = rng.randint(0, 100) == 25
        rng.setstate(state)
        no_monster = rng.randint(0, 100) == 25

        dhp = dynamic_stats["hp"]
        ddipl = dynamic_stats["dipl"]
        dpdef = dynamic_stats["pdef"]
        dmdef = dynamic_stats["mdef"]
        dcdef = dynamic_stats.get("cdef", 1.0)
        d_stats = f"HP: {dhp}\nCHA: {ddipl}\nPDEF: {dpdef:0.2f}\nMDEF: {dmdef:0.2f}\nCDEF: {dcdef:0.2f}"

        attribute_stats = self.ATTRIBS[attribute]
        true_hp = max(int(dhp * attribute_stats[0] * monster_stats), 1)
        true_dipl = max(int(ddipl * attribute_stats[1] * monster_stats), 1)
        embed = discord.Embed(
            title=f"a{attribute} {challenge}",
            description=(
                f"HP: **{true_hp}**\nCHA: **{true_dipl}**"
                f"\nHP Mod: **{attribute_stats[0]}**\nCHA Mod: **{attribute_stats[1]}**"
            ),
        )
        embed.add_field(name="Base Stats", value=base_stats)
        embed.add_field(name="Dynamic Stats", value=d_stats)

        embed.add_field(name="Seed Stats", value=f"{str(gameseed.stat_range)}")
        embed.add_field(name="Seed", value=seed_box)
        embed.add_field(
            name="Easy Mode under 30 rebirths",
            value=str(easy_mode),
        )
        if no_monster:
            embed.add_field(name="No Monster", value=str(no_monster))
        if no_monster_30:
            embed.add_field(name="No Monster under 30 rebirths", value=str(no_monster_30))
        if boss:
            embed.add_field(name="Boss", value=str(boss))
        if miniboss:
            requirements = ", ".join(i for i in miniboss.get("requirements", []))
            embed.add_field(name="Miniboss", value=f"{requirements}")
        if transcended:
            embed.add_field(name="Transcended", value=str(transcended))
        if monster.get("image", None):
            embed.set_image(url=monster["image"])
        await ctx.send(embed=embed)

    @commands.command(name="adventurestats")
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.is_owner()
    async def _adventurestats(self, ctx: commands.Context, guild: Optional[discord.Guild] = None):
        """[Owner] Show all current adventures."""
        msg = bold(_("Active Adventures\n"))
        embed_list = []
        if guild is None:
            guild: discord.Guild = ctx.guild
        if guild is None:
            return await ctx.send_help()
        if len(self._sessions) > 0:
            for server_id, adventure in self._sessions.items():
                server = self.bot.get_guild(server_id)
                if server is None:
                    # should not happen but the type checker is happier
                    continue
                pdef = adventure.monster_modified_stats["pdef"]
                mdef = adventure.monster_modified_stats["mdef"]
                cdef = adventure.monster_modified_stats.get("cdef", 1.0)
                hp = adventure.monster_hp()
                dipl = adventure.monster_dipl()
                seed = hex(adventure.rng.internal_seed)[2:].upper()
                msg += (
                    f"{server.name} - "
                    f"[{adventure.challenge}]({adventure.message.jump_url})\n"
                    f"(hp:**{hp}**-char:**{dipl}**-pdef:**{pdef:0.2f}**-mdef:**{mdef:0.2f}**-cdef:**{cdef:0.2f}**)\n"
                    f"{box(seed)}\n\n"
                )
        else:
            msg += "None.\n\n"
        stats = self._adv_results.get_stat_range(guild)
        stats_msg = _("Stats for {guild_name}\n{stats}").format(guild_name=guild.name, stats=str(stats))
        for page in pagify(msg, delims=["\n\n"], page_length=2048):
            embed = discord.Embed(description=page)
            embed.add_field(name=_("Guild Stats"), value=stats_msg)
            embed_list.append(embed)
        await BaseMenu(
            source=SimpleSource(embed_list),
            delete_message_after=True,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)
