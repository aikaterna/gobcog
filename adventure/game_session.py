import logging
import random
import time
from datetime import datetime
from math import ceil
from typing import List, Mapping, MutableMapping, Optional, Set, Tuple

import discord
from redbot.core.commands import Context
from redbot.core.i18n import Translator, set_contextual_locales_from_guild
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number

from .abc import AdventureMixin
from .charsheet import Character, has_funds
from .constants import HeroClasses
from .helpers import escape, smart_embed

# This is split into its own file for future buttons usage
# We will have game sessions inherit discord.ui.View and then we can send a message
# with the buttons required. For now this will sit in its own file.

_ = Translator("Adventure", __file__)
log = logging.getLogger("red.cogs.adventure")


class AttackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Attack", style=style, row=row)
        self.style = style
        self.emoji = "\N{DAGGER KNIFE}\N{VARIATION SELECTOR-16}"
        self.action_type = "fight"
        self.label_name = "Attack {}"

    async def send_response(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            pass
        choices = self.view.cog.ACTION_RESPONSE.get(self.action_type, {})
        heroclass = c.hc.name
        pet = ""
        if c.hc is HeroClasses.ranger:
            pet = c.heroclass.get("pet", {}).get("name", _("pet you would have if you had a pet"))

        choice = random.choice(choices[heroclass] + choices["hero"])
        choice = choice.replace("$pet", pet)
        choice = choice.replace("$monster", self.view.challenge)
        weapon = c.get_weapons()
        choice = choice.replace("$weapon", weapon)
        god = await self.view.cog.config.god_name()
        if await self.view.cog.config.guild(interaction.guild).god_name():
            god = await self.view.cog.config.guild(interaction.guild).god_name()
        choice = choice.replace("$god", god)
        await interaction.response.send_message(box(choice, lang="ansi"), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        for x in ["magic", "talk", "pray", "run"]:
            if user in getattr(self.view, x, []):
                getattr(self.view, x).remove(user)
        if user not in self.view.fight:
            self.view.fight.append(user)
            await self.send_response(interaction)
            await self.view.update()
        else:
            await interaction.response.send_message("You are already fighting this monster.", ephemeral=True)


class MagicButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Magic", style=style, row=row)
        self.style = style
        self.emoji = "\N{SPARKLES}"
        self.action_type = "magic"
        self.label_name = "Magic {}"

    async def send_response(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            pass
        choices = self.view.cog.ACTION_RESPONSE.get(self.action_type, {})
        heroclass = c.hc.name
        pet = ""
        if c.hc is HeroClasses.ranger:
            pet = c.heroclass.get("pet", {}).get("name", _("pet you would have if you had a pet"))

        choice = random.choice(choices[heroclass] + choices["hero"])
        choice = choice.replace("$pet", pet)
        choice = choice.replace("$monster", self.view.challenge)
        weapon = c.get_weapons()
        choice = choice.replace("$weapon", weapon)
        god = await self.view.cog.config.god_name()
        if await self.view.cog.config.guild(interaction.guild).god_name():
            god = await self.view.cog.config.guild(interaction.guild).god_name()
        choice = choice.replace("$god", god)
        await interaction.response.send_message(box(choice, lang="ansi"), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        for x in ["fight", "talk", "pray", "run"]:
            if user in getattr(self.view, x, []):
                getattr(self.view, x).remove(user)
        if user not in self.view.magic:
            self.view.magic.append(user)
            await self.send_response(interaction)
            await self.view.update()
        else:
            await interaction.response.send_message("You have already cast a spell at this monster.", ephemeral=True)


class TalkButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Talk", style=style, row=row)
        self.style = style
        self.emoji = "\N{LEFT SPEECH BUBBLE}\N{VARIATION SELECTOR-16}"
        self.action_type = "talk"
        self.label_name = "Talk {}"

    async def send_response(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            pass
        choices = self.view.cog.ACTION_RESPONSE.get(self.action_type, {})
        heroclass = c.hc.name
        pet = ""
        if c.hc is HeroClasses.ranger:
            pet = c.heroclass.get("pet", {}).get("name", _("pet you would have if you had a pet"))

        choice = random.choice(choices[heroclass] + choices["hero"])
        choice = choice.replace("$pet", pet)
        choice = choice.replace("$monster", self.view.challenge)
        weapon = c.get_weapons()
        choice = choice.replace("$weapon", weapon)
        god = await self.view.cog.config.god_name()
        if await self.view.cog.config.guild(interaction.guild).god_name():
            god = await self.view.cog.config.guild(interaction.guild).god_name()
        choice = choice.replace("$god", god)
        await interaction.response.send_message(box(choice, lang="ansi"), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        for x in ["fight", "magic", "pray", "run"]:
            if user in getattr(self.view, x, []):
                getattr(self.view, x).remove(user)
        if user not in self.view.talk:
            self.view.talk.append(user)
            await self.send_response(interaction)
            await self.view.update()
        else:
            await interaction.response.send_message("You are already talking to this monster.", ephemeral=True)


class PrayButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Pray", style=style, row=row)
        self.style = style
        self.emoji = "\N{PERSON WITH FOLDED HANDS}"
        self.action_type = "pray"
        self.label_name = "Pray {}"

    async def send_response(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            pass
        choices = self.view.cog.ACTION_RESPONSE.get(self.action_type, {})
        heroclass = c.hc.name
        pet = ""
        if c.hc is HeroClasses.ranger:
            pet = c.heroclass.get("pet", {}).get("name", _("pet you would have if you had a pet"))

        choice = random.choice(choices[heroclass] + choices["hero"])
        choice = choice.replace("$pet", pet)
        choice = choice.replace("$monster", self.view.challenge)
        weapon = c.get_weapons()
        choice = choice.replace("$weapon", weapon)
        god = await self.view.cog.config.god_name()
        if await self.view.cog.config.guild(interaction.guild).god_name():
            god = await self.view.cog.config.guild(interaction.guild).god_name()
        choice = choice.replace("$god", god)
        await interaction.response.send_message(box(choice, lang="ansi"), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        for x in ["fight", "magic", "talk", "run"]:
            if user in getattr(self.view, x, []):
                getattr(self.view, x).remove(user)
        if user not in self.view.pray:
            self.view.pray.append(user)
            await self.send_response(interaction)
            await self.view.update()
        else:
            await interaction.response.send_message(
                "You are already praying for help against this monster.", ephemeral=True
            )


class RunButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Run", style=style, row=row)
        self.style = style
        self.emoji = "\N{RUNNER}\N{ZERO WIDTH JOINER}\N{MALE SIGN}\N{VARIATION SELECTOR-16}"
        self.action_type = "run"
        self.label_name = "Run {}"

    async def send_response(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            pass
        choices = self.view.cog.ACTION_RESPONSE.get(self.action_type, {})
        heroclass = c.hc.name
        pet = ""
        if c.hc is HeroClasses.ranger:
            pet = c.heroclass.get("pet", {}).get("name", _("pet you would have if you had a pet"))

        choice = random.choice(choices[heroclass] + choices["hero"])
        choice = choice.replace("$pet", pet)
        choice = choice.replace("$monster", self.view.challenge)
        weapon = c.get_weapons()
        choice = choice.replace("$weapon", weapon)
        god = await self.view.cog.config.god_name()
        if await self.view.cog.config.guild(interaction.guild).god_name():
            god = await self.view.cog.config.guild(interaction.guild).god_name()
        choice = choice.replace("$god", god)
        await interaction.response.send_message(box(choice, lang="ansi"), ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        for x in ["fight", "magic", "talk", "pray"]:
            if user in getattr(self.view, x, []):
                getattr(self.view, x).remove(user)
        if user not in self.view.run:
            self.view.run.append(user)
            await self.send_response(interaction)
            await self.view.update()
        else:
            await interaction.response.send_message("You have already run from this monster.", ephemeral=True)


class SpecialActionButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int] = None,
    ):
        super().__init__(label="Special Action", style=style, row=row)
        self.style = style
        self.emoji = "\N{ATOM SYMBOL}\N{VARIATION SELECTOR-16}"
        self.action_type = "special_action"
        self.label_name = "Special Action"

    async def send_cooldown(self, interaction: discord.Interaction, c: Character, cooldown_time: int):
        cooldown_time = int((c.heroclass["cooldown"]) + cooldown_time)
        msg = _(
            "Your hero is currently recovering from the last time "
            "they used this skill or they have just changed their heroclass. "
            "Try again in {cooldown}."
        ).format(cooldown=f"<t:{cooldown_time}:R>")
        await smart_embed(interaction=interaction, message=msg, success=False, ephemeral=True, cog=self.view.cog)

    async def send_in_use(self, interaction: discord.Interaction):
        user = interaction.user
        msg = _("**{}**, ability already in use.").format(escape(user.display_name))
        await smart_embed(interaction=interaction, message=msg, success=False, ephemeral=True, cog=self.view.cog)

    async def send_cleric(self, interaction: discord.Interaction, c: Character):
        user = interaction.user
        if c.heroclass["ability"]:
            await self.send_in_use(interaction)
            return
        else:
            cooldown_time = max(300, (1200 - max((c.luck + c.total_int) * 2, 0)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] <= time.time():
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time() + cooldown_time
                await self.view.cog.config.user(user).set(await c.to_json(self.view.ctx, self.view.cog.config))
                msg = _("{bless} **{c}** is starting an inspiring sermon. {bless}").format(
                    c=escape(user.display_name), bless=self.view.cog.emojis.skills.bless
                )
                await smart_embed(interaction=interaction, message=msg, cog=self.view.cog)
            else:
                await self.send_cooldown(interaction, c, cooldown_time)

    async def send_insight(self, interaction: discord.Interaction, c: Character):
        user = interaction.user
        if c.heroclass["ability"]:
            await self.send_in_use(interaction)
            return
        cooldown_time = max(300, (900 - max((c.luck + c.total_cha) * 2, 0)))
        if "cooldown" not in c.heroclass:
            c.heroclass["cooldown"] = cooldown_time + 1
        if c.heroclass["cooldown"] + cooldown_time <= time.time():
            max_roll = 100 if c.rebirths >= 30 else 50 if c.rebirths >= 15 else 20
            roll = random.randint(min(c.rebirths - 25 // 2, (max_roll // 2)), max_roll) / max_roll
            if self.view.insight[0] < roll:
                self.view.insight = roll, c
                good = True
            else:
                good = False
                msg = _("Another hero has already done a better job than you.")
                await smart_embed(
                    interaction,
                    _("Another hero has already done a better job than you."),
                    ephemeral=True,
                    cog=self.view.cog,
                )
            c.heroclass["ability"] = True
            c.heroclass["cooldown"] = time.time()
            async with self.view.cog.get_lock(c.user):
                await self.view.cog.config.user(user).set(await c.to_json(self.view.ctx, self.view.cog.config))
                if good:
                    msg = _("{skill} **{c}** is focusing on the monster ahead...{skill}").format(
                        c=escape(user.display_name),
                        skill=self.view.cog.emojis.skills.psychic,
                    )
                    await smart_embed(interaction=interaction, message=msg, cog=self.view.cog)
            if good:
                session = self.view
                if roll <= 0.4:
                    return await smart_embed(interaction, _("You suck."), cog=self.view.cog)
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
                    if roll == 1:
                        hp = int(hp * self.ATTRIBS[session.attribute][0] * session.monster_stats)
                        dipl = int(diplo * self.ATTRIBS[session.attribute][1] * session.monster_stats)
                        msg += _(
                            "This monster is **a{attr} {challenge}** ({hp_symbol} {hp}/{dipl_symbol} {dipl}){trans}.\n"
                        ).format(
                            challenge=session.challenge,
                            attr=session.attribute,
                            hp_symbol=self.emojis.hp,
                            hp=humanize_number(ceil(hp)),
                            dipl_symbol=self.emojis.dipl,
                            dipl=humanize_number(ceil(dipl)),
                            trans=f" (**Transcended**) {self.view.cog.emojis.skills.psychic}"
                            if session.transcended
                            else f"{self.view.cog.emojis.skills.psychic}",
                        )
                        self.view.exposed = True
                    elif roll >= 0.95:
                        hp = hp * self.ATTRIBS[session.attribute][0] * session.monster_stats
                        dipl = diplo * self.ATTRIBS[session.attribute][1] * session.monster_stats
                        msg += _(
                            "This monster is **a{attr} {challenge}** ({hp_symbol} {hp}/{dipl_symbol} {dipl}).\n"
                        ).format(
                            challenge=session.challenge,
                            attr=session.attribute,
                            hp_symbol=self.emojis.hp,
                            hp=humanize_number(ceil(hp)),
                            dipl_symbol=self.emojis.dipl,
                            dipl=humanize_number(ceil(dipl)),
                        )
                        self.view.exposed = True
                    elif roll >= 0.90:
                        hp = hp * self.ATTRIBS[session.attribute][0] * session.monster_stats
                        msg += _("This monster is **a{attr} {challenge}** ({hp_symbol} {hp}).\n").format(
                            challenge=session.challenge,
                            attr=session.attribute,
                            hp_symbol=self.emojis.hp,
                            hp=humanize_number(ceil(hp)),
                        )
                        self.view.exposed = True
                    elif roll > 0.75:
                        msg += _("This monster is **a{attr} {challenge}**.\n").format(
                            challenge=session.challenge,
                            attr=session.attribute,
                        )
                        self.view.exposed = True
                    elif roll > 0.5:
                        msg += _("This monster is **a {challenge}**.\n").format(
                            challenge=session.challenge,
                        )
                        self.view.exposed = True
                    if roll >= 0.4:
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
                    if roll >= 0.6:
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
                    if roll >= 0.8:
                        if cdef >= 1.5:
                            msg += _(
                                "You think you are charismatic? Pfft, this creature couldn't care less for what you want to say!\n"
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
                    if roll >= 0.4:
                        image = session.monster["image"]
                    return await smart_embed(
                        ctx=None,
                        message=msg,
                        success=True,
                        image=image,
                        cog=self.view.cog,
                        interaction=interaction,
                    )
                else:
                    return await smart_embed(
                        ctx=None,
                        message=_("You have failed to discover anything about this monster."),
                        success=False,
                        cog=self.view.cog,
                        interaction=interaction,
                    )
            else:
                await self.send_cooldown(interaction, c, cooldown_time)

    async def send_rage(self, interaction: discord.Interaction, c: Character):
        user = interaction.user
        if c.heroclass["ability"] is True:
            await self.send_in_use(interaction)
            return
        cooldown_time = max(300, (1200 - max((c.luck + c.total_att) * 2, 0)))
        if "cooldown" not in c.heroclass:
            c.heroclass["cooldown"] = cooldown_time + 1
        if c.heroclass["cooldown"] <= time.time():
            c.heroclass["ability"] = True
            c.heroclass["cooldown"] = time.time() + cooldown_time
            await self.view.cog.config.user(user).set(await c.to_json(self.view.ctx, self.view.cog.config))
            await smart_embed(
                None,
                _("{skill} **{c}** is starting to froth at the mouth... {skill}").format(
                    c=escape(user.display_name),
                    skill=self.view.cog.emojis.skills.berserker,
                ),
                cog=self.view.cog,
                interaction=interaction,
            )
        else:
            await self.send_cooldown(interaction, c, cooldown_time)

    async def send_focus(self, interaction: discord.Interaction, c: Character):
        user = interaction.user
        if c.heroclass["ability"] is True:
            await self.send_in_use(interaction)
            return
        cooldown_time = max(300, (1200 - max((c.luck + c.total_int) * 2, 0)))
        if "cooldown" not in c.heroclass:
            c.heroclass["cooldown"] = cooldown_time + 1
        if c.heroclass["cooldown"] <= time.time():
            c.heroclass["ability"] = True
            c.heroclass["cooldown"] = time.time() + cooldown_time

            await self.view.cog.config.user(user).set(await c.to_json(self.view.ctx, self.view.cog.config))
            await smart_embed(
                None,
                _("{skill} **{c}** is focusing all of their energy... {skill}").format(
                    c=escape(user.display_name),
                    skill=self.view.cog.emojis.skills.wizzard,
                ),
                cog=self.view.cog,
                interaction=interaction,
            )
        else:
            await self.send_cooldown(interaction, c, cooldown_time)

    async def send_music(self, interaction: discord.Interaction, c: Character):
        user = interaction.user
        if c.heroclass["ability"]:
            await self.send_in_use(interaction)
            return
        cooldown_time = max(300, (1200 - max((c.luck + c.total_cha) * 2, 0)))
        if "cooldown" not in c.heroclass:
            c.heroclass["cooldown"] = cooldown_time + 1
        if c.heroclass["cooldown"] <= time.time():
            c.heroclass["ability"] = True
            c.heroclass["cooldown"] = time.time() + cooldown_time
            await self.view.cog.config.user(user).set(await c.to_json(self.view.ctx, self.view.cog.config))
            await smart_embed(
                None,
                _("{skill} **{c}** is whipping up a performance... {skill}").format(
                    c=escape(user.display_name), skill=self.view.cog.emojis.skills.bard
                ),
                cog=self.view.cog,
                interaction=interaction,
            )
        else:
            await self.send_cooldown(interaction, c, cooldown_time)

    async def not_in_adventure(self, interaction: discord.Interaction):
        msg = _("**{user}**, you need to be participating in this adventure to use this ability.").format(
            user=interaction.user.display_name
        )
        await smart_embed(None, msg, success=False, ephemeral=True, cog=self.view.cog, interaction=interaction)
        return

    async def callback(self, interaction: discord.Interaction):
        """Skip to previous track"""
        user = interaction.user
        if not self.view.in_adventure(user):
            await self.not_in_adventure(interaction)
            return
        async with self.view.cog.get_lock(user):
            try:
                c = await Character.from_json(self.view.ctx, self.view.cog.config, user, self.view.cog._daily_bonus)
            except Exception as exc:
                log.exception("Error with the new character sheet", exc_info=exc)
                await interaction.response.send_message(_("There was an error loading your character."), ephemeral=True)
                return
            if not c.hc.has_action:
                available_classes = humanize_list([c.class_name for c in HeroClasses if c.has_action], style="or")
                msg = _("**{user}**, you need to be a {available_classes} to use this ability.").format(
                    user=interaction.user.display_name, available_classes=available_classes
                )
                await smart_embed(None, msg, ephemeral=True, cog=self.view.cog, interaction=interaction)
                return
            if c.hc is HeroClasses.cleric:
                await self.send_cleric(interaction, c)
            if c.hc is HeroClasses.psychic:
                await self.send_insight(interaction, c)
            if c.hc is HeroClasses.berserker:
                await self.send_rage(interaction, c)
            if c.hc is HeroClasses.wizard:
                await self.send_focus(interaction, c)
            if c.hc is HeroClasses.bard:
                await self.send_music(interaction, c)


class GameSession(discord.ui.View):
    """A class to represent and hold current game sessions per server."""

    ctx: Context
    cog: AdventureMixin
    challenge: str
    attribute: dict
    timer: int
    guild: discord.Guild
    boss: bool
    miniboss: dict
    monster: dict
    message_id: int
    reacted: bool = False
    participants: Set[discord.Member] = set()
    monster_modified_stats: MutableMapping = {}
    fight: List[discord.Member] = []
    magic: List[discord.Member] = []
    talk: List[discord.Member] = []
    pray: List[discord.Member] = []
    run: List[discord.Member] = []
    message: discord.Message = None
    transcended: bool = False
    insight: Tuple[float, Character] = (0, None)
    start_time: datetime = datetime.now()
    easy_mode: bool = False
    insight = (0, None)
    no_monster: bool = False
    exposed: bool = False
    finished: bool = False

    def __init__(self, **kwargs):
        self.ctx: Context = kwargs.pop("ctx")
        self.cog: AdventureMixin = kwargs.pop("cog")
        self.challenge: str = kwargs.pop("challenge")
        self.attribute: dict = kwargs.pop("attribute")
        self.guild: discord.Guild = kwargs.pop("guild")
        self.boss: bool = kwargs.pop("boss")
        self.miniboss: dict = kwargs.pop("miniboss")
        self.timer: int = kwargs.pop("timer")
        self.monster: dict = kwargs.pop("monster")
        self.monsters: Mapping[str, Mapping] = kwargs.pop("monsters", [])
        self.monster_stats: int = kwargs.pop("monster_stats", 1)
        self.monster_modified_stats = kwargs.pop("monster_modified_stats", self.monster)
        self.message = kwargs.pop("message", 1)
        self.message_id: int = 0
        self.reacted = False
        self.participants: Set[discord.Member] = set()
        self.fight: List[discord.Member] = []
        self.magic: List[discord.Member] = []
        self.talk: List[discord.Member] = []
        self.pray: List[discord.Member] = []
        self.run: List[discord.Member] = []
        self.transcended: bool = kwargs.pop("transcended", False)
        self.start_time = datetime.now()
        self.easy_mode = kwargs.get("easy_mode", False)
        self.no_monster = kwargs.get("no_monster", False)
        super().__init__(timeout=self.timer)
        self.attack_button = AttackButton(discord.ButtonStyle.grey)
        self.talk_button = TalkButton(discord.ButtonStyle.grey)
        self.magic_button = MagicButton(discord.ButtonStyle.grey)
        self.talk_button = TalkButton(discord.ButtonStyle.grey)
        self.pray_button = PrayButton(discord.ButtonStyle.grey)
        self.run_button = RunButton(discord.ButtonStyle.grey)
        self.special_button = SpecialActionButton(discord.ButtonStyle.blurple)
        self.add_item(self.attack_button)
        self.add_item(self.talk_button)
        self.add_item(self.magic_button)
        self.add_item(self.pray_button)
        self.add_item(self.run_button)
        self.add_item(self.special_button)

    async def update(self):
        self.attack_button.label = self.attack_button.label_name.format(f"({len(self.fight)})")
        self.talk_button.label = self.talk_button.label_name.format(f"({len(self.talk)})")
        self.magic_button.label = self.magic_button.label_name.format(f"({len(self.magic)})")
        self.pray_button.label = self.pray_button.label_name.format(f"({len(self.pray)})")
        self.run_button.label = self.run_button.label_name.format(f"({len(self.run)})")
        await self.message.edit(view=self)

    def in_adventure(self, user: discord.Member) -> bool:
        participants_ids = set(
            p.id
            for p in [
                *self.fight,
                *self.magic,
                *self.pray,
                *self.talk,
                *self.run,
            ]
        )
        return bool(user.id in participants_ids)

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.guild is not None:
            await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        log.debug("Checking interaction")
        has_fund = await has_funds(interaction.user, 250)
        if not has_fund:
            await interaction.response.send_message(
                _(
                    "You contemplate going on an adventure with your friends, so "
                    "you go to your bank to get some money to prepare and they "
                    "tell you that your bank is empty!\n"
                    "You run home to look for some spare coins and you can't "
                    "even find a single one, so you tell your friends that you can't "
                    "join them as you already have plans... as you are too embarrassed "
                    "to tell them you are broke!"
                ),
                ephemeral=True,
            )
            return False
        if await self.cog.config.restrict():
            user = interaction.user
            all_users = []
            in_adventure = False
            for guild_session in self.cog._sessions.values():
                if guild_session.in_adventure(user):
                    in_adventure = True

            if in_adventure:
                user_id = f"{user.id}-{user.guild.id}"
                # iterating through reactions here and removing them seems to be expensive
                # so they can just keep their react on the adventures they can't join
                if user_id not in self.cog._react_messaged:
                    await interaction.response.send_message(
                        _(
                            "**{c}**, you are already in an existing adventure. "
                            "Wait for it to finish before joining another one."
                        ).format(c=escape(user.display_name)),
                        ephemeral=True,
                    )
                    self.cog._react_messaged.append(user_id)
                    return
        return True
