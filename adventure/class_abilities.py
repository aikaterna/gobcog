# -*- coding: utf-8 -*-
import asyncio
import contextlib
import logging
import random
import time
from math import ceil
from typing import Literal, Optional

import discord
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number, humanize_timedelta
from redbot.core.utils.predicates import MessagePredicate

from .abc import AdventureMixin
from .bank import bank
from .charsheet import Character, Item
from .constants import HeroClasses, Rarities, Slot
from .converters import HeroClassConverter, ItemConverter
from .helpers import ConfirmView, escape, is_dev, smart_embed
from .menus import BaseMenu, SimpleSource

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class ClassAbilities(AdventureMixin):
    """This class will handle class abilities"""

    @commands.hybrid_command(cooldown_after_parsing=True)
    @commands.bot_has_permissions(add_reactions=True)
    @commands.cooldown(rate=1, per=7200, type=commands.BucketType.user)
    @discord.app_commands.rename(clz="class")
    async def heroclass(
        self, ctx: commands.Context, clz: Optional[HeroClassConverter] = None, action: Optional[Literal["info"]] = None
    ):
        """Allows you to select a class if you are level 10 or above.

        For information on class use: `[p]heroclass classname info`.
        """
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("The monster ahead growls menacingly, and will not let you leave."))
        if not await self.allow_in_dm(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))

        if clz is None:
            ctx.command.reset_cooldown(ctx)
            classes = box(
                "\n".join(c.class_colour.as_str(c.class_name) for c in HeroClasses),
                lang="ansi",
            )
            await smart_embed(
                ctx,
                _(
                    "So you feel like taking on a class, {author}?\n"
                    "Available classes are: {classes}\n"
                    "Use `{prefix}heroclass name-of-class` to choose one."
                ).format(author=bold(ctx.author.display_name), classes=classes, prefix=ctx.prefix),
            )

        else:
            if action == "info":
                ctx.command.reset_cooldown(ctx)
                class_desc = clz.desc()
                msg = box(clz.class_colour.as_str(class_desc), lang="ansi")
                return await smart_embed(ctx, msg)
            async with self.get_lock(ctx.author):
                bal = await bank.get_balance(ctx.author)
                currency_name = await bank.get_currency_name(
                    ctx.guild,
                )
                if str(currency_name).startswith("<"):
                    currency_name = "credits"
                spend = round(bal * 0.2)
                try:
                    c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    ctx.command.reset_cooldown(ctx)
                    return
                current_class = c.hc
                if current_class is clz:
                    ctx.command.reset_cooldown(ctx)
                    return await smart_embed(ctx, _("You already are a {}.").format(clz.class_name))
                if clz is HeroClasses.psychic and c.rebirths < 20:
                    ctx.command.reset_cooldown(ctx)
                    return await smart_embed(ctx, _("You are too inexperienced to become a {}.").format(clz.class_name))
                view = ConfirmView(60, ctx.author)
                class_msg = await ctx.send(
                    box(
                        _("This will cost {spend} {currency_name}. Do you want to continue, {author}?").format(
                            spend=humanize_number(spend),
                            currency_name=currency_name,
                            author=escape(ctx.author.display_name),
                        ),
                        lang="ansi",
                    ),
                    view=view,
                )
                broke = box(
                    _("You don't have enough {currency_name} to train to be a {clz}.").format(
                        currency_name=currency_name, clz=clz.ansi
                    ),
                    lang="ansi",
                )
                await view.wait()
                if not view.confirmed:
                    await class_msg.edit(
                        content=box(
                            _("{author} decided to continue being a {h_class}.").format(
                                author=escape(ctx.author.display_name),
                                h_class=current_class.ansi,
                            ),
                            lang="ansi",
                        ),
                        view=None,
                    )
                    ctx.command.reset_cooldown(ctx)
                    return await self._clear_react(class_msg)
                if bal < spend:
                    await class_msg.edit(content=broke, view=None)
                    ctx.command.reset_cooldown(ctx)
                    return await self._clear_react(class_msg)
                if not await bank.can_spend(ctx.author, spend):
                    return await class_msg.edit(content=broke, view=None)
                try:
                    c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return
                now_class_msg = _("Congratulations, {author}.\nYou are now a {clz}.").format(
                    author=escape(ctx.author.display_name), clz=clz.ansi
                )
                if c.lvl >= 10:
                    if current_class in [HeroClasses.tinkerer, HeroClasses.ranger]:
                        view = ConfirmView(60, ctx.author)
                        if current_class is HeroClasses.tinkerer:
                            await self._clear_react(class_msg)
                            await class_msg.edit(
                                content=box(
                                    _(
                                        "{}, you will lose your forged "
                                        "device if you change your class.\nShall I proceed?"
                                    ).format(escape(ctx.author.display_name)),
                                    lang="ansi",
                                ),
                                view=view,
                            )
                        else:
                            await self._clear_react(class_msg)
                            await class_msg.edit(
                                content=box(
                                    _("{}, you will lose your pet if you change your class.\nShall I proceed?").format(
                                        escape(ctx.author.display_name)
                                    ),
                                    lang="ansi",
                                ),
                                view=view,
                            )
                        await view.wait()
                        if view.confirmed is None:
                            ctx.command.reset_cooldown(ctx)
                            return
                        if view.confirmed:  # user reacted with Yes.
                            tinker_wep = []
                            for item in c.get_current_equipment():
                                if item.rarity is Rarities.forged:
                                    c = await c.unequip_item(item)
                            for name, item in c.backpack.items():
                                if item.rarity is Rarities.forged:
                                    tinker_wep.append(item)
                            for item in tinker_wep:
                                del c.backpack[item.name]
                            if current_class is HeroClasses.tinkerer:
                                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                                if tinker_wep:
                                    await class_msg.edit(
                                        content=box(
                                            _("{} has run off to find a new master.").format(humanize_list(tinker_wep)),
                                            lang="ansi",
                                        ),
                                        view=None,
                                    )

                            else:
                                c.heroclass["ability"] = False
                                c.heroclass["pet"] = {}
                                c.heroclass = clz.to_json()

                                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                                await self._clear_react(class_msg)
                                await class_msg.edit(
                                    content=box(
                                        _("{} released their pet into the wild.\n").format(
                                            escape(ctx.author.display_name)
                                        ),
                                        lang="ansi",
                                    ),
                                    view=None,
                                )
                            await class_msg.edit(content=class_msg.content + box(now_class_msg, lang="ansi"), view=None)
                        else:
                            await self._clear_react(class_msg)
                            await class_msg.edit(
                                content=box(
                                    _("{}, you will remain a {}").format(
                                        escape(ctx.author.display_name), c.hc.class_name
                                    ),
                                    lang="ansi",
                                ),
                                view=None,
                            )
                            ctx.command.reset_cooldown(ctx)
                            return
                    if c.skill["pool"] < 0:
                        c.skill["pool"] = 0
                    c.heroclass = clz.to_json()
                    if c.hc in [HeroClasses.wizard, HeroClasses.cleric]:
                        c.heroclass["cooldown"] = max(300, (1200 - max((c.luck + c.total_int) * 2, 0))) + time.time()
                    elif c.hc is HeroClasses.ranger:
                        c.heroclass["cooldown"] = max(1800, (7200 - max(c.luck * 2 + c.total_int * 2, 0))) + time.time()
                        c.heroclass["catch_cooldown"] = (
                            max(600, (3600 - max(c.luck * 2 + c.total_int * 2, 0))) + time.time()
                        )
                    elif c.hc is HeroClasses.berserker:
                        c.heroclass["cooldown"] = max(300, (1200 - max((c.luck + c.total_att) * 2, 0))) + time.time()
                    elif c.hc is HeroClasses.bard:
                        c.heroclass["cooldown"] = max(300, (1200 - max((c.luck + c.total_cha) * 2, 0))) + time.time()
                    elif c.hc is HeroClasses.tinkerer:
                        c.heroclass["cooldown"] = max(900, (3600 - max((c.luck + c.total_int) * 2, 0))) + time.time()
                    elif c.hc is HeroClasses.psychic:
                        c.heroclass["cooldown"] = max(300, (900 - max((c.luck - c.total_cha) * 2, 0))) + time.time()
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    await self._clear_react(class_msg)
                    await class_msg.edit(content=box(now_class_msg, lang="ansi"), view=None)
                    try:
                        await bank.withdraw_credits(ctx.author, spend)
                    except ValueError:
                        return await class_msg.edit(content=broke, view=None)
                else:
                    ctx.command.reset_cooldown(ctx)
                    await smart_embed(
                        ctx,
                        _("{user}, you need to be at least level 10 to choose a class.").format(
                            user=bold(ctx.author.display_name)
                        ),
                    )

    @commands.hybrid_group(autohelp=False, fallback="find")
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def pet(self, ctx: commands.Context):
        """[Ranger Class Only]

        This allows a Ranger to tame or set free a pet or send it foraging.
        """
        if ctx.invoked_subcommand is None:
            if self.in_adventure(ctx):
                return await smart_embed(ctx, _("You're too distracted with the monster you are facing."))

            if not await self.allow_in_dm(ctx):
                return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
            async with self.get_lock(ctx.author):
                try:
                    c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
                except Exception as exc:
                    log.exception("Error with the new character sheet", exc_info=exc)
                    return
                if c.hc is not HeroClasses.ranger:
                    return await smart_embed(
                        ctx,
                        _("{user}, you need to be a Ranger to do this.").format(user=bold(ctx.author.display_name)),
                    )
                if c.heroclass["pet"]:
                    ctx.command.reset_cooldown(ctx)
                    return await ctx.send(
                        box(
                            _("{author}, you already have a pet. Try foraging ({prefix}pet forage).").format(
                                author=escape(ctx.author.display_name), prefix=ctx.prefix
                            ),
                            lang="ansi",
                        )
                    )
                else:
                    cooldown_time = max(600, (3600 - max((c.luck + c.total_int) * 2, 0)))
                    if "catch_cooldown" not in c.heroclass:
                        c.heroclass["catch_cooldown"] = cooldown_time + 1
                    if c.heroclass["catch_cooldown"] > time.time():
                        cooldown_time = c.heroclass["catch_cooldown"] - time.time()
                        return await smart_embed(
                            ctx,
                            _(
                                "You caught a pet recently, or you are a brand new Ranger. "
                                "You will be able to go hunting in {}."
                            ).format(
                                humanize_timedelta(seconds=int(cooldown_time))
                                if int(cooldown_time) >= 1
                                else _("1 second")
                            ),
                        )
                    theme = await self.config.theme()
                    extra_pets = await self.config.themes.all()
                    extra_pets = extra_pets.get(theme, {}).get("pets", {})
                    pet_list = {**self.PETS, **extra_pets}
                    pet_choices = list(pet_list.keys())
                    pet = random.choice(pet_choices)
                    roll = random.randint(1, 50)
                    dipl_value = c.total_cha + (c.total_int // 3) + (c.luck // 2)
                    pet_reqs = pet_list[pet].get("bonuses", {}).get("req", {})
                    pet_msg4 = ""
                    can_catch = True
                    force_catch = False
                    if any(x in c.sets for x in ["The Supreme One", "Ainz Ooal Gown"]):
                        can_catch = True
                        pet = random.choice(
                            [
                                "Albedo",
                                "Rubedo",
                                "Guardians of Nazarick",
                                *random.choices(pet_choices, k=10),
                            ]
                        )
                        if pet in ["Albedo", "Rubedo", "Guardians of Nazarick"]:
                            force_catch = True
                    elif pet_reqs.get("bonuses", {}).get("req"):
                        if pet_reqs.get("set", None) in c.sets:
                            can_catch = True
                        else:
                            can_catch = False
                            pet_msg4 = _("\nPerhaps you're missing some requirements to tame {pet}.").format(pet=pet)
                    pet_msg = box(
                        _("{c} is trying to tame a pet.").format(c=escape(ctx.author.display_name)),
                        lang="ansi",
                    )
                    user_msg = await ctx.send(pet_msg)
                    await asyncio.sleep(2)
                    pet_msg2 = box(
                        _("{author} started tracking a wild {pet_name} with a roll of {dice}({roll}).").format(
                            dice=self.emojis.dice,
                            author=escape(ctx.author.display_name),
                            pet_name=pet,
                            roll=roll,
                        ),
                        lang="ansi",
                    )
                    await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}")
                    await asyncio.sleep(2)
                    bonus = ""
                    if roll == 1:
                        bonus = _("But they stepped on a twig and scared it away.")
                    elif roll in [50, 25]:
                        bonus = _("They happen to have its favorite food.")
                    if force_catch or (dipl_value > pet_list[pet]["cha"] and roll > 1 and can_catch):
                        if force_catch:
                            roll = 0
                        else:
                            roll = random.randint(0, (2 if roll in [50, 25] else 5))
                        if roll == 0:
                            if force_catch and any(x in c.sets for x in ["The Supreme One", "Ainz Ooal Gown"]):
                                msg = random.choice(
                                    [
                                        _("{author} commands {pet} into submission.").format(
                                            pet=pet, author=escape(ctx.author.display_name)
                                        ),
                                        _("{pet} swears allegiance to the Supreme One.").format(
                                            pet=pet, author=escape(ctx.author.display_name)
                                        ),
                                        _("{pet} takes an Oath of Allegiance to the Supreme One.").format(
                                            pet=pet, author=escape(ctx.author.display_name)
                                        ),
                                    ]
                                )
                                pet_msg3 = box(
                                    msg,
                                    lang="ansi",
                                )
                            else:
                                pet_msg3 = box(
                                    _("{bonus}\nThey successfully tamed the {pet}.").format(bonus=bonus, pet=pet),
                                    lang="ansi",
                                )
                            await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")
                            c.heroclass["pet"] = pet_list[pet]
                            c.heroclass["catch_cooldown"] = time.time() + cooldown_time
                            await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                        elif roll == 1:
                            bonus = _("But they stepped on a twig and scared it away.")
                            pet_msg3 = box(
                                _("{bonus}\nThe {pet} escaped.").format(bonus=bonus, pet=pet),
                                lang="ansi",
                            )
                            await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")
                        else:
                            bonus = ""
                            pet_msg3 = box(
                                _("{bonus}\nThe {pet} escaped.").format(bonus=bonus, pet=pet),
                                lang="ansi",
                            )
                            await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")
                    else:
                        pet_msg3 = box(
                            _("{bonus}\nThe {pet} escaped.").format(bonus=bonus, pet=pet),
                            lang="ansi",
                        )
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")

    @pet.command(name="forage")
    @commands.bot_has_permissions(add_reactions=True)
    async def _forage(self, ctx: commands.Context):
        """Use your pet to forage for items!"""
        if self.in_adventure(ctx):
            return await smart_embed(ctx, _("You're too distracted with the monster you are facing."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.ranger:
                return
            if not c.heroclass["pet"]:
                return await smart_embed(
                    ctx,
                    _("{user}, you need to have a pet to do this.").format(user=bold(ctx.author.display_name)),
                )
            if c.is_backpack_full(is_dev=is_dev(ctx.author)):
                await ctx.send(
                    _("{author}, Your backpack is currently full.").format(author=bold(ctx.author.display_name))
                )
                return
            cooldown_time = max(1800, (7200 - max((c.luck + c.total_int) * 2, 0)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] <= time.time():
                await self._open_chest(ctx, c.heroclass["pet"]["name"], Rarities.pet, character=c)
                c.heroclass["cooldown"] = time.time() + cooldown_time
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
            else:
                cooldown_time = c.heroclass["cooldown"] - time.time()
                return await smart_embed(
                    ctx,
                    _("This command is on cooldown. Try again in {}.").format(
                        humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                    ),
                )

    @pet.command(name="free")
    async def _free(self, ctx: commands.Context):
        """Free your pet :cry:"""
        if self.in_adventure(ctx):
            return await smart_embed(ctx, _("You're too distracted with the monster you are facing."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.ranger:
                return await smart_embed(
                    ctx,
                    _("{user}, you need to be a Ranger to do this.").format(user=bold(ctx.author.display_name)),
                )
            if c.heroclass["pet"]:
                c.heroclass["pet"] = {}
                await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                return await smart_embed(
                    ctx,
                    _("{user} released their pet into the wild..").format(user=bold(ctx.author.display_name)),
                )
            else:
                return await ctx.send(box(_("You don't have a pet."), lang="ansi"))

    @commands.hybrid_command()
    async def bless(self, ctx: commands.Context):
        """[Cleric Class Only]

        This allows a praying Cleric to add substantial bonuses for heroes fighting the battle.
        """
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.cleric:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("{user}, you need to be a Cleric to do this.").format(user=bold(ctx.author.display_name)),
                )
            else:
                if c.heroclass["ability"]:
                    return await smart_embed(
                        ctx,
                        _("{user}, ability already in use.").format(user=bold(ctx.author.display_name)),
                    )
                cooldown_time = max(300, (1200 - max((c.luck + c.total_int) * 2, 0)))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if c.heroclass["cooldown"] <= time.time():
                    c.heroclass["ability"] = True
                    c.heroclass["cooldown"] = time.time() + cooldown_time
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))

                    await smart_embed(
                        ctx,
                        _("{bless} {c} is starting an inspiring sermon. {bless}").format(
                            c=bold(ctx.author.display_name), bless=self.emojis.skills.bless
                        ),
                    )
                else:
                    cooldown_time = c.heroclass["cooldown"] - time.time()
                    return await smart_embed(
                        ctx,
                        _(
                            "Your hero is currently recovering from the last time "
                            "they used this skill or they have just changed their heroclass. "
                            "Try again in {}."
                        ).format(
                            humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                        ),
                    )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=30, type=commands.BucketType.user)
    async def insight(self, ctx: commands.Context):
        """[Psychic Class Only]
        This allows a Psychic to expose the current enemy's weakeness to the party.
        """
        try:
            c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
        except Exception:
            log.exception("Error with the new character sheet")
            ctx.command.reset_cooldown(ctx)
            return
        if c.hc is not HeroClasses.psychic:
            return await smart_embed(
                ctx,
                _("{user}, you need to be a Psychic to do this.").format(user=bold(ctx.author.display_name)),
            )
        else:
            if ctx.guild.id not in self._sessions:
                return await smart_embed(
                    ctx,
                    _("There are no active adventures."),
                )
            if not self.in_adventure(ctx):
                return await smart_embed(
                    ctx,
                    _("You tried to expose the enemy's weaknesses, but you aren't in an adventure."),
                )
            if c.heroclass["ability"]:
                return await smart_embed(
                    ctx,
                    _("{user}, ability already in use.").format(user=bold(ctx.author.display_name)),
                )
            cooldown_time = max(300, (900 - max((c.luck + c.total_cha) * 2, 0)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] + cooldown_time <= time.time():
                max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
                roll = random.randint(min(c.rebirths - 25 // 2, (max_roll // 2)), max_roll) / max_roll
                if ctx.guild.id in self._sessions and self._sessions[ctx.guild.id].insight[0] < roll:
                    self._sessions[ctx.guild.id].insight = roll, c
                    good = True
                else:
                    good = False
                    await smart_embed(ctx, _("Another hero has already done a better job than you."))
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time()
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    if good:
                        await smart_embed(
                            ctx,
                            _("{skill} {c} is focusing on the monster ahead...{skill}").format(
                                c=bold(ctx.author.display_name),
                                skill=self.emojis.skills.psychic,
                            ),
                        )
                if good:
                    session = self._sessions[ctx.guild.id]
                    if roll <= 0.4:
                        return await smart_embed(ctx, _("You suck."))
                    msg = ""
                    if session.no_monster:
                        if roll >= 0.4:
                            msg += _("You are struggling to find anything in your current adventure.")
                    else:
                        pdef = session.monster_modified_stats["pdef"]
                        mdef = session.monster_modified_stats["mdef"]
                        cdef = session.monster_modified_stats.get("cdef", 1.0)
                        hp = session.monster_modified_stats["hp"]
                        diplo = session.monster_modified_stats["dipl"]
                        choice = random.choice(["physical", "magic", "diplomacy"])
                        if choice == "physical":
                            physical_roll = 0.4
                            magic_roll = 0.6
                            diplo_roll = 0.8
                        elif choice == "magic":
                            physical_roll = 0.8
                            magic_roll = 0.4
                            diplo_roll = 0.6
                        else:
                            physical_roll = 0.8
                            magic_roll = 0.6
                            diplo_roll = 0.4

                        if roll == 1:
                            hp = int(hp * self.ATTRIBS[session.attribute][0] * session.monster_stats)
                            dipl = int(diplo * self.ATTRIBS[session.attribute][1] * session.monster_stats)
                            msg += _(
                                "This monster is **a{attr} {challenge}** ({hp_symbol} {hp}/{dipl_symbol} {dipl}){trans}.\n"
                            ).format(
                                challenge=session.challenge,
                                attr=session.attribute,
                                hp_symbol=self.emojis.hp,
                                hp=humanize_number(int(hp)),
                                dipl_symbol=self.emojis.dipl,
                                dipl=humanize_number(int(dipl)),
                                trans=f" (**Transcended**) {self.emojis.skills.psychic}"
                                if session.transcended
                                else f"{self.emojis.skills.psychic}",
                            )
                            self._sessions[ctx.guild.id].exposed = True
                        elif roll >= 0.95:
                            hp = hp * self.ATTRIBS[session.attribute][0] * session.monster_stats
                            dipl = diplo * self.ATTRIBS[session.attribute][1] * session.monster_stats
                            msg += _(
                                "This monster is **a{attr} {challenge}** ({hp_symbol} {hp}/{dipl_symbol} {dipl}).\n"
                            ).format(
                                challenge=session.challenge,
                                attr=session.attribute,
                                hp_symbol=self.emojis.hp,
                                hp=humanize_number(int(hp)),
                                dipl_symbol=self.emojis.dipl,
                                dipl=humanize_number(int(dipl)),
                            )
                            self._sessions[ctx.guild.id].exposed = True
                        elif roll >= 0.90:
                            hp = hp * self.ATTRIBS[session.attribute][0] * session.monster_stats
                            msg += _("This monster is **a{attr} {challenge}** ({hp_symbol} {hp}).\n").format(
                                challenge=session.challenge,
                                attr=session.attribute,
                                hp_symbol=self.emojis.hp,
                                hp=humanize_number(int(hp)),
                            )
                            self._sessions[ctx.guild.id].exposed = True
                        elif roll > 0.75:
                            msg += _("This monster is **a{attr} {challenge}**.\n").format(
                                challenge=session.challenge,
                                attr=session.attribute,
                            )
                            self._sessions[ctx.guild.id].exposed = True
                        elif roll > 0.5:
                            msg += _("This monster is **a {challenge}**.\n").format(
                                challenge=session.challenge,
                            )
                            self._sessions[ctx.guild.id].exposed = True

                        if roll >= physical_roll:
                            if pdef >= 1.5:
                                msg += _("Swords bounce off this monster as it's skin is **almost impenetrable!**\n")
                            elif pdef >= 1.25:
                                msg += _("This monster has **extremely tough** armour!\n")
                            elif pdef > 1:
                                msg += _("Swords don't cut this monster **quite as well!**\n")
                            elif pdef > 0.75:
                                msg += _("This monster is **soft and easy** to slice!\n")
                            else:
                                msg += _("Swords slice through this monster like a **hot knife through butter!**\n")
                        if roll >= magic_roll:
                            if mdef >= 1.5:
                                msg += _("Magic? Pfft, magic is **no match** for this creature!\n")
                            elif mdef >= 1.25:
                                msg += _("This monster has **substantial magic resistance!**\n")
                            elif mdef > 1:
                                msg += _("This monster has increased **magic resistance!**\n")
                            elif mdef > 0.75:
                                msg += _("This monster's hide **melts to magic!**\n")
                            else:
                                msg += _("Magic spells are **hugely effective** against this monster!\n")
                        if roll >= diplo_roll:
                            if cdef >= 1.5:
                                msg += _(
                                    "You think you are charismatic? Pfft, this creature **couldn't care less** for what you want to say!\n"
                                )
                            elif cdef >= 1.25:
                                msg += _("Any attempts to communicate with this creature will be **very difficult!**\n")
                            elif cdef > 1:
                                msg += _("Any attempts to talk to this creature will be **difficult!**\n")
                            elif cdef > 0.75:
                                msg += _("This creature **can be reasoned** with!\n")
                            else:
                                msg += _("This monster can be **easily influenced!**\n")

                    if msg:
                        image = None
                        if roll >= 0.4 and not session.no_monster:
                            image = session.monster["image"]
                        return await smart_embed(ctx, msg, image=image)
                    else:
                        return await smart_embed(ctx, _("You have failed to discover anything about this monster."))
            else:
                cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                return await smart_embed(
                    ctx,
                    _(
                        "Your hero is currently recovering from the last time "
                        "they used this skill or they have just changed their heroclass. "
                        "Try again in {}."
                    ).format(
                        humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                    ),
                )

    @commands.hybrid_command()
    async def rage(self, ctx: commands.Context):
        """[Berserker Class Only]

        This allows a Berserker to add substantial attack bonuses for one battle.
        """
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.berserker:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("{user}, you need to be a Berserker to do this.").format(user=bold(ctx.author.display_name)),
                )
            else:
                if c.heroclass["ability"] is True:
                    return await smart_embed(
                        ctx,
                        _("{user}, ability already in use.").format(user=bold(ctx.author.display_name)),
                    )
                cooldown_time = max(300, (1200 - max((c.luck + c.total_att) * 2, 0)))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if c.heroclass["cooldown"] <= time.time():
                    c.heroclass["ability"] = True
                    c.heroclass["cooldown"] = time.time() + cooldown_time
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    await smart_embed(
                        ctx,
                        _("{skill} {c} is starting to froth at the mouth... {skill}").format(
                            c=bold(ctx.author.display_name),
                            skill=self.emojis.skills.berserker,
                        ),
                    )
                else:
                    cooldown_time = c.heroclass["cooldown"] - time.time()
                    return await smart_embed(
                        ctx,
                        _(
                            "Your hero is currently recovering from the last time "
                            "they used this skill or they have just changed their heroclass. "
                            "Try again in {}."
                        ).format(
                            humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                        ),
                    )

    @commands.hybrid_command()
    async def focus(self, ctx: commands.Context):
        """[Wizard Class Only]

        This allows a Wizard to add substantial magic bonuses for one battle.
        """
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.wizard:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("{user}, you need to be a Wizard to do this.").format(user=bold(ctx.author.display_name)),
                )
            else:
                if c.heroclass["ability"] is True:
                    return await smart_embed(
                        ctx,
                        _("{user}, ability already in use.").format(user=bold(ctx.author.display_name)),
                    )
                cooldown_time = max(300, (1200 - max((c.luck + c.total_int) * 2, 0)))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if c.heroclass["cooldown"] <= time.time():
                    c.heroclass["ability"] = True
                    c.heroclass["cooldown"] = time.time() + cooldown_time

                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    await smart_embed(
                        ctx,
                        _("{skill} {c} is focusing all of their energy... {skill}").format(
                            c=bold(ctx.author.display_name),
                            skill=self.emojis.skills.wizzard,
                        ),
                    )
                else:
                    cooldown_time = c.heroclass["cooldown"] - time.time()
                    return await smart_embed(
                        ctx,
                        _(
                            "Your hero is currently recovering from the "
                            "last time they used this skill. Try again in {}."
                        ).format(
                            humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                        ),
                    )

    @commands.hybrid_command()
    async def music(self, ctx: commands.Context):
        """[Bard Class Only]

        This allows a Bard to add substantial diplomacy bonuses for one battle.
        """
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.bard:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx,
                    _("{user}, you need to be a Bard to do this.").format(user=bold(ctx.author.display_name)),
                )
            else:
                if c.heroclass["ability"]:
                    return await smart_embed(
                        ctx,
                        _("{user}, ability already in use.").format(user=bold(ctx.author.display_name)),
                    )
                cooldown_time = max(300, (1200 - max((c.luck + c.total_cha) * 2, 0)))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if c.heroclass["cooldown"] <= time.time():
                    c.heroclass["ability"] = True
                    c.heroclass["cooldown"] = time.time() + cooldown_time
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    await smart_embed(
                        ctx,
                        _("{skill} {c} is whipping up a performance... {skill}").format(
                            c=bold(ctx.author.display_name), skill=self.emojis.skills.bard
                        ),
                    )
                else:
                    cooldown_time = c.heroclass["cooldown"] - time.time()
                    return await smart_embed(
                        ctx,
                        _(
                            "Your hero is currently recovering from the last time "
                            "they used this skill or they have just changed their heroclass. "
                            "Try again in {}."
                        ).format(
                            humanize_timedelta(seconds=int(cooldown_time)) if int(cooldown_time) >= 1 else _("1 second")
                        ),
                    )

    @commands.max_concurrency(1, per=commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(add_reactions=True)
    async def forge(self, ctx: commands.Context):
        """[Tinkerer Class Only]

        This allows a Tinkerer to forge two items into a device. (1h cooldown)
        """
        if self.in_adventure(ctx):
            return await smart_embed(ctx, _("You tried to forge an item but there were no forges nearby."))
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(ctx, self.config, ctx.author, self._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                return
            if c.hc is not HeroClasses.tinkerer:
                return await smart_embed(
                    ctx,
                    _("{}, you need to be a Tinkerer to do this.").format(bold(ctx.author.display_name)),
                )
            else:
                cooldown_time = max(1800, (7200 - max((c.luck + c.total_int) * 2, 0)))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if c.heroclass["cooldown"] > time.time():
                    cooldown_time = c.heroclass["cooldown"] - time.time()
                    return await smart_embed(
                        ctx,
                        _("This command is on cooldown. Try again in {}").format(
                            humanize_timedelta(seconds=int(cooldown_time)) if cooldown_time >= 1 else _("1 second")
                        ),
                    )
                ascended_forge_msg = ""
                ignored_rarities = [Rarities.forged, Rarities.set, Rarities.event]
                if c.rebirths < 30:
                    ignored_rarities.append(Rarities.ascended)
                    ascended_forge_msg += _("\n\nAscended items will be forgeable after 30 rebirths.")
                consumed = []
                forgeables_items = [str(i) for n, i in c.backpack.items() if i.rarity not in ignored_rarities]
                if len(forgeables_items) <= 1:
                    return await smart_embed(
                        ctx,
                        _("{}, you need at least two forgeable items in your backpack to forge.{}").format(
                            bold(ctx.author.display_name), ascended_forge_msg
                        ),
                    )
                pages = await c.get_backpack(forging=True, clean=True)
                if not pages:
                    await smart_embed(
                        ctx,
                        _("{}, you need at least two forgeable items in your backpack to forge.").format(
                            bold(ctx.author.display_name)
                        ),
                    )
                    return
                await BaseMenu(
                    source=SimpleSource(pages),
                    delete_message_after=True,
                    clear_reactions_after=True,
                    timeout=180,
                ).start(ctx=ctx)
                await smart_embed(
                    ctx,
                    _(
                        "Reply with the full or partial name of item 1 to select for forging. "
                        "Try to be specific. (Say `cancel` to exit){}".format(ascended_forge_msg)
                    ),
                )
                try:
                    item = None
                    while not item:
                        reply = await ctx.bot.wait_for(
                            "message",
                            check=MessagePredicate.same_context(user=ctx.author),
                            timeout=30,
                        )
                        new_ctx = await self.bot.get_context(reply)
                        new_ctx.command = self.forge
                        if reply.content.lower() in ["cancel", "exit"]:
                            return await smart_embed(ctx, _("Forging process has been cancelled."))
                        with contextlib.suppress(BadArgument):
                            item = None
                            item = await ItemConverter().convert(new_ctx, reply.content)
                            if str(item) not in forgeables_items:
                                item = None

                        if not item:
                            wrong_item = _("{c}, I could not find that item - check your spelling.").format(
                                c=bold(ctx.author.display_name)
                            )
                            await smart_embed(ctx, wrong_item)
                        elif not c.can_equip(item):
                            wrong_item = _("{c}, this item is too high level for you to reforge it.").format(
                                c=bold(ctx.author.display_name)
                            )
                            await smart_embed(ctx, wrong_item)
                            item = None
                            continue
                        else:
                            break
                    consumed.append(item)
                except asyncio.TimeoutError:
                    timeout_msg = _("I don't have all day you know, {}.").format(bold(ctx.author.display_name))
                    return await smart_embed(ctx, timeout_msg)
                if item.rarity in [Rarities.forged, Rarities.set]:
                    return await smart_embed(
                        ctx,
                        _("{c}, {item.rarity} items cannot be reforged.").format(
                            c=bold(ctx.author.display_name), item=item
                        ),
                    )
                await smart_embed(
                    ctx,
                    _(
                        "Reply with the full or partial name of item 2 to select for forging. "
                        "Try to be specific. (Say `cancel` to exit)"
                    ),
                )
                try:
                    item = None
                    while not item:
                        reply = await ctx.bot.wait_for(
                            "message",
                            check=MessagePredicate.same_context(user=ctx.author),
                            timeout=30,
                        )
                        if reply.content.lower() in ["cancel", "exit"]:
                            return await smart_embed(ctx, _("Forging process has been cancelled."))
                        new_ctx = await self.bot.get_context(reply)
                        new_ctx.command = self.forge
                        with contextlib.suppress(BadArgument):
                            item = None
                            item = await ItemConverter().convert(new_ctx, reply.content)
                            if str(item) not in forgeables_items:
                                item = None
                        if item and consumed[0].owned <= 1 and str(consumed[0]) == str(item):
                            wrong_item = _(
                                "{c}, you only own 1 copy of this item and you've already selected it."
                            ).format(c=bold(ctx.author.display_name))
                            await smart_embed(ctx, wrong_item)

                            continue
                        if not item:
                            wrong_item = _("{c}, I could not find that item - check your spelling.").format(
                                c=bold(ctx.author.display_name)
                            )
                            await smart_embed(ctx, wrong_item)
                        elif not c.can_equip(item):
                            wrong_item = _("{c}, this item is too high level for you to reforge it.").format(
                                c=bold(ctx.author.display_name)
                            )
                            await smart_embed(ctx, wrong_item)
                            item = None
                            continue
                        else:
                            break
                    consumed.append(item)
                except asyncio.TimeoutError:
                    timeout_msg = _("I don't have all day you know, {}.").format(bold(ctx.author.display_name))
                    return await smart_embed(ctx, timeout_msg)
                if item.rarity in [Rarities.forged, Rarities.set]:
                    return await smart_embed(
                        ctx,
                        _("{c}, {item.rarity} items cannot be reforged.").format(
                            c=bold(ctx.author.display_name), item=item
                        ),
                    )
                newitem = await self._to_forge(ctx, consumed, c)
                for x in consumed:
                    c.backpack[x.name].owned -= 1
                    if c.backpack[x.name].owned <= 0:
                        del c.backpack[x.name]
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                # save so the items are eaten up already
                for item in c.get_current_equipment():
                    if item.rarity is Rarities.forged:
                        c = await c.unequip_item(item)
                lookup = list(i for n, i in c.backpack.items() if i.rarity is Rarities.forged)
                if len(lookup) > 0:
                    forge_str = box(
                        _("{author}, you already have a device. Do you want to replace {replace}?").format(
                            author=escape(ctx.author.display_name),
                            replace=", ".join([str(x) for x in lookup]),
                        ),
                        lang="ansi",
                    )
                    view = ConfirmView(60, ctx.author)
                    forge_msg = await ctx.send(forge_str, view=view)
                    await view.wait()
                    with contextlib.suppress(discord.HTTPException):
                        await forge_msg.delete()
                    if view.confirmed:  # user reacted with Yes.
                        c.heroclass["cooldown"] = time.time() + cooldown_time
                        created_item = box(
                            _("{author}, your new {newitem} consumed {lk} and is now lurking in your backpack.").format(
                                author=escape(ctx.author.display_name),
                                newitem=newitem,
                                lk=", ".join([str(x) for x in lookup]),
                            ),
                            lang="ansi",
                        )
                        for item in lookup:
                            del c.backpack[item.name]
                        await ctx.send(created_item)
                        c.backpack[newitem.name] = newitem
                        await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    else:
                        c.heroclass["cooldown"] = time.time() + cooldown_time
                        await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                        mad_forge = box(
                            _("{author}, {newitem} got mad at your rejection and blew itself up.").format(
                                author=escape(ctx.author.display_name), newitem=newitem
                            ),
                            lang="ansi",
                        )
                        return await ctx.send(mad_forge)
                else:
                    c.heroclass["cooldown"] = time.time() + cooldown_time
                    c.backpack[newitem.name] = newitem
                    await self.config.user(ctx.author).set(await c.to_json(ctx, self.config))
                    forged_item = box(
                        _("{author}, your new {newitem} is lurking in your backpack.").format(
                            author=escape(ctx.author.display_name), newitem=newitem
                        ),
                        lang="ansi",
                    )
                    await ctx.send(forged_item)

    async def _to_forge(self, ctx: commands.Context, consumed, character):
        item1 = consumed[0]
        item2 = consumed[1]

        roll = random.randint(1, 20)
        modifier = (roll / 20) + 0.3
        base_cha = max(character._cha, 1)
        base_int = character._int
        base_luck = character._luck
        base_att = max(character._att, 1)
        modifier_bonus_luck = 0.01 * base_luck // 10
        modifier_bonus_int = 0.01 * base_int // 20
        modifier_penalty_str = 0.01 * base_att // 20
        modifier_penalty_cha = 0.01 * base_cha // 20
        modifier = sum([modifier_bonus_int, modifier_bonus_luck, modifier_penalty_cha, modifier_penalty_str, modifier])
        modifier = max(0.001, modifier)

        base_int = int(item1.int) + int(item2.int)
        base_cha = int(item1.cha) + int(item2.cha)
        base_att = int(item1.att) + int(item2.att)
        base_dex = int(item1.dex) + int(item2.dex)
        base_luck = int(item1.luck) + int(item2.luck)
        newatt = int((base_att * modifier) + base_att)
        newdip = int((base_cha * modifier) + base_cha)
        newint = int((base_int * modifier) + base_int)
        newdex = int((base_dex * modifier) + base_dex)
        newluck = int((base_luck * modifier) + base_luck)
        newslot = random.choice([i for i in Slot])

        if newslot is Slot.two_handed:  # two handed weapons add their bonuses twice
            hand = "two handed"
        else:
            if newslot is Slot.right or newslot is Slot.left:
                hand = newslot.get_name() + " handed"
            else:
                hand = newslot.get_name() + " slot"
        if newslot is Slot.two_handed:
            two_handed_msg = box(
                _(
                    "{author}, your forging roll was {dice}({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_cha} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=escape(ctx.author.display_name),
                    roll=roll,
                    dice=self.emojis.dice,
                    new_att=(newatt * 2),
                    new_cha=(newdip * 2),
                    new_int=(newint * 2),
                    new_dex=(newdex * 2),
                    new_luck=(newluck * 2),
                    hand=hand,
                ),
                lang="ansi",
            )
            await ctx.send(two_handed_msg)
        else:
            reg_item = box(
                _(
                    "{author}, your forging roll was {dice}({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_dip} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=escape(ctx.author.display_name),
                    roll=roll,
                    dice=self.emojis.dice,
                    new_att=newatt,
                    new_dip=newdip,
                    new_int=newint,
                    new_dex=newdex,
                    new_luck=newluck,
                    hand=hand,
                ),
                lang="ansi",
            )
            await ctx.send(reg_item)
        get_name = _(
            "{}, please respond with "
            "a name for your creation within 30s.\n"
            "(You will not be able to change it afterwards. 40 characters maximum.)"
        ).format(bold(ctx.author.display_name))
        await smart_embed(ctx, get_name)
        reply = None
        name = _("Unnamed Artifact")
        try:
            reply = await ctx.bot.wait_for("message", check=MessagePredicate.same_context(user=ctx.author), timeout=30)
        except asyncio.TimeoutError:
            name = _("Unnamed Artifact")
        if reply is None:
            name = _("Unnamed Artifact")
        else:
            if hasattr(reply, "content"):
                if len(reply.content) > 40:
                    name = _("Long-winded Artifact")
                else:
                    name = reply.content.lower()
        item = {
            name: {
                "slot": newslot.to_json(),
                "att": newatt,
                "cha": newdip,
                "int": newint,
                "dex": newdex,
                "luck": newluck,
                "rarity": "forged",
            }
        }
        item = Item.from_json(ctx, item)
        return item
