# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import enum
import logging
import re
import shlex
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple, Union

import discord
from discord.app_commands import Choice, Transformer
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.commands import UserFeedbackCheckFailure
from redbot.core.i18n import Translator, set_contextual_locales_from_guild
from redbot.core.utils.chat_formatting import box, humanize_list
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .charsheet import Character, Item
from .constants import DEV_LIST, HeroClasses, Rarities, Skills, Slot
from .helpers import smart_embed

log = logging.getLogger("red.cogs.adventure")

_ = Translator("Adventure", __file__)

TIME_RE_STRING = r"\s?".join(
    [
        r"((?P<days>\d+?)\s?(d(ays?)?))?",
        r"((?P<hours>\d+?)\s?(hours?|hrs|hr?))?",
        r"((?P<minutes>\d+?)\s?(minutes?|mins?|m))?",
        r"((?P<seconds>\d+?)\s?(seconds?|secs?|s))?",
    ]
)

TIME_RE = re.compile(TIME_RE_STRING, re.I)
REBIRTHSTATMULT = 2

REBIRTH_LVL = 20
REBIRTH_STEP = 10
SET_BONUSES = {}

TR_GEAR_SET = {}
PETS = {}

ATT = re.compile(r"(-?\d*) (att(?:ack)?)")
CHA = re.compile(r"(-?\d*) (cha(?:risma)?|dip(?:lo?(?:macy)?)?)")
INT = re.compile(r"(-?\d*) (int(?:elligence)?)")
LUCK = re.compile(r"(-?\d*) (luck)")
DEX = re.compile(r"(-?\d*) (dex(?:terity)?)")
SLOT = re.compile(r"(head|neck|chest|gloves|belt|legs|boots|left|right|ring|charm|twohanded)")
RARITY = re.compile(r"(normal|rare|epic|legend(?:ary)?|asc(?:ended)?|set|forged|event)")

DEG = re.compile(r"(-?\d*) degrade")
LEVEL = re.compile(r"(-?\d*) (level|lvl)")
PERCENTAGE = re.compile(r"^(\d*\.?\d+)(%?)")
DAY_REGEX = re.compile(
    r"^(?P<monday>mon(?:day)?|1)$|"
    r"^(?P<tuesday>tue(?:sday)?|2)$|"
    r"^(?P<wednesday>wed(?:nesday)?|3)$|"
    r"^(?P<thursday>th(?:u(?:rs(?:day)?)?)?|4)$|"
    r"^(?P<friday>fri(?:day)?|5)$|"
    r"^(?P<saturday>sat(?:urday)?|6)$|"
    r"^(?P<sunday>sun(?:day)?|7)$",
    re.IGNORECASE,
)

_DAY_MAPPING = {
    "monday": "1",
    "tuesday": "2",
    "wednesday": "3",
    "thursday": "4",
    "friday": "5",
    "saturday": "6",
    "sunday": "7",
}
ARG_OP_REGEX = re.compile(r"(?P<op>>|<)?(?P<value>-?\d+)")


def parse_timedelta(argument: str) -> Optional[timedelta]:
    matches = TIME_RE.match(argument)
    if matches:
        params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
        if params:
            return timedelta(**params)
    return None


class ArgParserFailure(UserFeedbackCheckFailure):
    """Raised when parsing an argument fails."""

    def __init__(self, cmd: str, message: str):
        self.cmd = cmd
        super().__init__(message=message)


class RarityConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Optional[Rarities]:
        try:
            rarity = Rarities.get_from_name(argument)
        except KeyError:
            raise BadArgument(
                _("{rarity} is not a valid rarity, select one of {rarities}").format(
                    rarity=argument, rarities=humanize_list([i.get_name() for i in Rarities if i.is_chest])
                )
            )
        return rarity

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Optional[Rarities]:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        choices = []
        # cog = interaction.client.get_cog("Adventure")
        log.debug(interaction.command)
        for rarity in Rarities:
            if rarity is Rarities.pet:
                continue
            if interaction.command and interaction.command.name in ["loot", "convert"] and not rarity.is_chest:
                continue
            if current.lower() in rarity.get_name().lower():
                choices.append(Choice(name=rarity.get_name(), value=rarity.name))
        return choices


class SlotConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Optional[Slot]:
        if argument:
            try:
                return Slot.get_from_name(argument)
            except ValueError:
                raise BadArgument(
                    _("{provided} is not a valid slot, select one of {slots}").format(
                        provided=argument, slots=humanize_list([i.get_name() for i in Slot])
                    )
                )

        return None

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Optional[Slot]:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        return [Choice(name=i.get_name(), value=i.name) for i in Slot if current.lower() in i.get_name().lower()]


class Stats(commands.FlagConverter, case_insensitive=True):
    attack: Optional[int] = commands.flag(name="att", aliases=["attack"], default=0)
    charisma: Optional[int] = commands.flag(name="cha", aliases=["charisma", "diplomacy", "diplo"], default=0)
    intelligence: Optional[int] = commands.flag(name="int", aliases=["intelligence"], default=0)
    dexterity: Optional[int] = commands.flag(name="dex", aliases=["dexterity"], default=0)
    luck: Optional[int] = commands.flag(name="luck", default=0)
    rarity: Optional[Rarities] = commands.flag(name="rarity", default=Rarities.normal, converter=RarityConverter)
    degrade: Optional[int] = commands.flag(name="degrade", aliases=["deg"], default=3)
    level: Optional[int] = commands.flag(name="level", aliases=["lvl"], default=1)
    slot: Optional[Slot] = commands.flag(name="slot", default=Slot.right, converter=SlotConverter)

    async def to_json(self, ctx: commands.Context) -> Dict[str, Union[List[str], int, str]]:
        result = {
            "slot": ["left"],
            "att": 0,
            "cha": 0,
            "int": 0,
            "dex": 0,
            "luck": 0,
            "rarity": "normal",
            "degrade": 0,
            "lvl": 1,
        }
        possible_stats = {
            "slot": self.slot.to_json() if self.slot else ["left"],
            "att": self.attack,
            "cha": self.charisma,
            "int": self.intelligence,
            "dex": self.dexterity,
            "luck": self.luck,
            "rarity": self.rarity.name if self.rarity else "normal",
            "degrade": self.degrade,
            "lvl": self.level,
        }
        for key, value in possible_stats.items():
            if key in ["slot", "rarity"]:
                if key == "rarity" and value in ("pet", "forged"):
                    raise BadArgument(_("How do you plan to create items with those rarities? Not creating item."))
                result[key] = value
                continue
            try:
                stat = int(value)
                if (
                    (key not in ["degrade", "lvl"] and stat > 10) or (key == "lvl" and stat < 50)
                ) and not await ctx.bot.is_owner(ctx.author):
                    raise BadArgument(_("Don't you think that's a bit overpowered? Not creating item."))
                result[key] = value
            except (AttributeError, ValueError):
                result[key] = value
                pass
        return result


class ItemsConverter(Converter):
    async def convert(self, ctx, argument) -> Tuple[str, List[Item]]:
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        rarity = None
        try:
            rarity_re = "|".join(f"{k}|{v}" for k, v in Rarities.names().items())
            rarity_match = re.match(rarity_re, argument.lower(), flags=re.I)
            if rarity_match:
                try:
                    rarity = Rarities.get_from_name(str(rarity_match.group(0)))
                except KeyError:
                    pass
        except AttributeError:
            pass

        if argument.lower() == "all":
            rarity = True

        if rarity is None:
            no_markdown = Item.remove_markdowns(argument)
            lookup = list(i for x, i in c.backpack.items() if no_markdown.lower() in x.lower())
            lookup_m = list(i for i in c.backpack.values() if argument.lower() == str(i).lower() and str(i))
            lookup_e = list(i for i in c.backpack.values() if argument == str(i))
            _temp_items = set()
            for i in lookup:
                _temp_items.add(str(i))
            for i in lookup_m:
                _temp_items.add(str(i))
            for i in lookup_e:
                _temp_items.add(str(i))
        elif rarity is True:
            lookup = list(i for i in c.backpack.values())
            return "all", lookup
        else:
            lookup = list(i for i in c.backpack.values() if i.rarity is rarity)
            if lookup:
                return "all", lookup
            raise BadArgument(_("You don't own any `{}` items.").format(argument))

        if len(lookup_e) == 1:
            return "single", [lookup_e[0]]
        if len(lookup) == 1:
            return "single", [lookup[0]]
        elif len(lookup_m) == 1:
            return "single", [lookup_m[0]]
        elif len(lookup) == 0 and len(lookup_m) == 0:
            raise BadArgument(_("`{}` doesn't seem to match any items you own.").format(argument))
        else:
            lookup = list(i for i in c.backpack.values() if str(i) in _temp_items)
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            for number, item in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="ansi")
                )
            )
            emojis = ReactionPredicate.NUMBER_EMOJIS[: len(lookup)]
            start_adding_reactions(msg, emojis)
            pred = ReactionPredicate.with_emojis(emojis, msg, user=ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                raise BadArgument(_("Alright then."))
            return "single", [lookup[pred.result]]


class ItemButton(discord.ui.Button):
    def __init__(self, item: Item):
        self.item = item
        super().__init__(label=item.name)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_item = self.item
        self.view.stop()
        await interaction.response.edit_message(view=None)


class ConfirmItemView(discord.ui.View):
    def __init__(self, timeout: float, items: List[Item], author: discord.User):
        super().__init__(timeout=timeout)
        self.selected_item = None
        for item in items:
            self.add_item(ItemButton(item))
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("You are not authorized to interact with this."), ephemeral=True)
            return False
        return True


class ItemConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Item:
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        no_markdown = Item.remove_markdowns(argument)
        lookup = list(i for x, i in c.backpack.items() if no_markdown.lower() in x.lower())
        lookup_m = list(i for i in c.backpack.values() if argument.lower() == str(i).lower() and str(i))
        lookup_e = list(i for i in c.backpack.values() if argument == str(i))

        _temp_items = set()
        for i in lookup:
            _temp_items.add(str(i))
        for i in lookup_m:
            _temp_items.add(str(i))
        for i in lookup_e:
            _temp_items.add(str(i))

        if len(lookup_e) == 1:
            return lookup_e[0]
        if len(lookup) == 1:
            return lookup[0]
        elif len(lookup_m) == 1:
            return lookup_m[0]
        elif len(lookup) == 0 and len(lookup_m) == 0:
            raise BadArgument(_("`{}` doesn't seem to match any items you own.").format(argument))
        else:
            lookup = list(i for i in c.backpack.values() if str(i) in _temp_items)
            if len(lookup) > 25:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            view = ConfirmItemView(60, lookup, ctx.author)
            for number, item in enumerate(lookup):
                items += f"{number}. {item.as_ansi()} (owned {item.owned})\n"

            await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="ansi")
                ),
                view=view,
            )
            await view.wait()
            if not view.selected_item:
                raise BadArgument(_("Alright then."))
            return view.selected_item

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Item:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        ctx = await interaction.client.get_context(interaction)
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            return []
        return [Choice(name=str(x), value=x.name) for x in c.backpack.values() if current.lower() in str(x).lower()][
            :25
        ]


class EquipableItemConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Item:
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        equipped_items = set()
        for slot in Slot:
            if slot is Slot.two_handed:
                continue
            item = slot.get_item_slot(c)
            if item:
                equipped_items.add(str(item))
        no_markdown = Item.remove_markdowns(argument)
        lookup = list(
            i for x, i in c.backpack.items() if no_markdown.lower() in x.lower() and str(i) not in equipped_items
        )
        lookup_m = list(
            i for i in c.backpack.values() if argument.lower() == str(i).lower() and str(i) not in equipped_items
        )
        lookup_e = list(i for i in c.backpack.values() if argument == str(i) and str(i) not in equipped_items)

        already_lookup = list(
            i for x, i in c.backpack.items() if no_markdown.lower() in x.lower() and str(i) in equipped_items
        )
        already_lookup_m = list(
            i for i in c.backpack.values() if argument.lower() == str(i).lower() and str(i) in equipped_items
        )
        already_lookup_e = list(i for i in c.backpack.values() if argument == str(i) and str(i) in equipped_items)

        _temp_items = set()
        for i in lookup:
            _temp_items.add(str(i))
        for i in lookup_m:
            _temp_items.add(str(i))
        for i in lookup_e:
            _temp_items.add(str(i))

        if len(lookup_e) == 1:
            return lookup_e[0]
        if len(lookup) == 1:
            return lookup[0]
        elif len(lookup_m) == 1:
            return lookup_m[0]
        elif len(lookup) == 0 and len(lookup_m) == 0:
            if any(x for x in [already_lookup, already_lookup_m, already_lookup_e]):
                raise BadArgument(_("`{}` matches the name of an item already equipped.").format(argument))
            raise BadArgument(_("`{}` doesn't seem to match any items you own.").format(argument))
        else:
            lookup = list(i for i in c.backpack.values() if str(i) in _temp_items)
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            for number, item in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="ansi")
                )
            )
            emojis = ReactionPredicate.NUMBER_EMOJIS[: len(lookup)]
            start_adding_reactions(msg, emojis)
            pred = ReactionPredicate.with_emojis(emojis, msg, user=ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                raise BadArgument(_("Alright then."))
            return lookup[pred.result]

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Item:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        ctx = await interaction.client.get_context(interaction)
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        equipped_items = set()
        for slot in Slot:
            if slot is Slot.two_handed:
                continue
            item = slot.get_item_slot(c)
            if item:
                equipped_items.add(str(item))
        lookup = [
            Choice(name=str(i), value=i.name)
            for x, i in c.backpack.items()
            if current.lower() in x.lower() and str(i) not in equipped_items
        ]
        return lookup[:25]


class EquipmentConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Union[Item, List[Item]]:
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        if argument.lower() == "all":
            items = []
            for slot in Slot:
                if slot is Slot.two_handed:
                    continue
                equipped_item = getattr(c, slot.name)
                if not equipped_item:
                    continue
                items.append(equipped_item)
            return items

        if argument.lower() in [i.get_name().lower() for i in Slot]:
            for slot in Slot:
                if slot is Slot.two_handed:
                    continue
                equipped_item = getattr(c, slot.name)
                if not equipped_item:
                    continue
                if (equipped_item.slot.get_name().lower() == argument.lower()) or (
                    equipped_item.slot is Slot.two_handed and "two handed" == argument.lower()
                ):
                    return equipped_item

        matched = set()
        lookup = list(
            i
            for i in c.get_current_equipment()
            if argument.lower() in str(i).lower()
            if i.slot is not Slot.two_handed or (str(i) not in matched and not matched.add(str(i)))
        )
        matched = set()
        lookup_m = list(
            i
            for i in c.get_current_equipment()
            if argument.lower() == str(i).lower()
            if i.slot is not Slot.two_handed or (str(i) not in matched and not matched.add(str(i)))
        )

        if len(lookup) == 1:
            return lookup[0]
        elif len(lookup_m) == 1:
            return lookup_m[0]
        elif len(lookup) == 0 and len(lookup_m) == 0:
            raise BadArgument(_("`{}` doesn't seem to match any items you have equipped.").format(argument))
        else:
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific").format(argument)
                )
            items = ""
            for number, item in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="ansi")
                )
            )
            emojis = ReactionPredicate.NUMBER_EMOJIS[: len(lookup)]
            start_adding_reactions(msg, emojis)
            pred = ReactionPredicate.with_emojis(emojis, msg, user=ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                raise BadArgument(_("Alright then."))
            return lookup[pred.result]

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Union[Item, List[Item]]:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        ctx = await interaction.client.get_context(interaction)
        try:
            c = await Character.from_json(
                ctx,
                ctx.bot.get_cog("Adventure").config,
                ctx.author,
                ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        choices = [
            Choice(name=str(i), value=i.name) for i in c.get_current_equipment() if current.lower() in str(i).lower()
        ]
        return choices[:25]


class ThemeSetMonterConverter(Converter):
    async def convert(self, ctx, argument) -> MutableMapping:
        arguments = list(map(str.strip, argument.split("++")))
        try:
            theme = arguments[0]
            name = arguments[1]
            hp = float(arguments[2])
            dipl = float(arguments[3])
            pdef = float(arguments[4])
            mdef = float(arguments[5])
            cdef = float(arguments[6])
            if any([i < 0 for i in [hp, dipl, pdef, mdef]]):
                raise BadArgument(
                    "HP, Charisma, Magical defence, Persuasion defence and Physical defence cannot be negative."
                )

            image = arguments[8]
            boss = True if arguments[7].lower() == "true" else False
            if not image:
                raise Exception
        except BadArgument:
            raise
        except Exception:
            raise BadArgument("Invalid format, Excepted:\n`theme++name++hp++dipl++pdef++mdef++cdef++boss++image`")
        if "transcended" in name.lower() or "ascended" in name.lower():
            raise BadArgument("You are not worthy.")
        return {
            "theme": theme,
            "name": name,
            "hp": hp,
            "pdef": pdef,
            "mdef": mdef,
            "cdef": cdef,
            "dipl": dipl,
            "image": image,
            "boss": boss,
            "miniboss": {},
        }


class ThemeSetPetConverter(Converter):
    async def convert(self, ctx, argument) -> MutableMapping:
        arguments = list(map(str.strip, argument.split("++")))
        try:
            theme = arguments[0]
            name = arguments[1]
            bonus = float(arguments[2])
            cha = int(arguments[3])
            crit = int(arguments[4])
            if not (0 <= crit <= 100):
                raise BadArgument("Critical chance needs to be between 0 and 100")
            if not arguments[5]:
                raise Exception
            always = True if arguments[5].lower() == "true" else False
        except BadArgument:
            raise
        except Exception:
            raise BadArgument(
                "Invalid format, Excepted:\n`theme++name++bonus_multiplier++required_cha++crit_chance++always_crit`"
            )
        if not ctx.cog.is_dev(ctx.author):
            if bonus > 2:
                raise BadArgument("Pet bonus is too high.")
            if always and cha < 500:
                raise BadArgument("Charisma is too low for such a strong pet.")
            if crit > 85 and cha < 500:
                raise BadArgument("Charisma is too low for such a strong pet.")
        return {
            "theme": theme,
            "name": name,
            "bonus": bonus,
            "cha": cha,
            "bonuses": {"crit": crit, "always": always},
        }


class SkillConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Skills:
        ret = None
        att = ["attack", "att", "atk"]
        cha = ["diplomacy", "charisma", "cha", "dipl"]
        intel = ["intelligence", "intellect", "int", "magic"]
        if argument.lower() in att:
            ret = Skills("attack")
        if argument.lower() in cha:
            ret = Skills("charisma")
        if argument.lower() in intel:
            ret = Skills("intelligence")
        if argument.lower() == "reset":
            ret = Skills("reset")
        if ret is None:
            raise BadArgument(_("`{argument}` is not an available skill.").format(argument=argument))
        return ret

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Skills:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        choices = [Choice(name=s.name.title(), value=s.value) for s in Skills if current.lower() in s.name]
        return choices


class ChallengeConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Union[str, int]:
        if ctx.author.id not in (*ctx.bot.owner_ids, *DEV_LIST):
            return ""
        if argument.isnumeric():
            return int(argument)
        cog = ctx.bot.get_cog("Adventure")
        monsters, monster_stats, transcended = await cog.update_monster_roster()
        if argument not in monsters:
            return int(argument, 16)
        return argument

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        if interaction.user.id not in (*interaction.client.owner_ids, *DEV_LIST):
            return []
        cog = interaction.client.get_cog("Adventure")
        monsters, monster_stats, transcended = await cog.update_monster_roster()
        return [Choice(name=m, value=m) for m in monsters if current.lower() in m.lower()][:25]


class HeroClassConverter(Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Optional[HeroClasses]:
        available_classes = HeroClasses.class_names()
        names = list(available_classes.keys()) + list(available_classes.values())
        if argument.lower() not in names:
            return None
        try:
            hc = HeroClasses.from_name(argument)
        except ValueError:
            await smart_embed(ctx, _("{} may be a class somewhere, but not on my watch.").format(argument))
            return None
        return hc

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> Optional[HeroClasses]:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice]:
        if interaction.guild is not None:
            await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return [Choice(name=c.class_name, value=c.value) for c in HeroClasses if current.lower() in c.class_name]


class DayConverter(Converter):
    async def convert(self, ctx, argument) -> Tuple[str, str]:
        matches = DAY_REGEX.match(argument)
        if not matches:
            raise BadArgument(_("Day must be one of:\nMon, Tue, Wed, Thurs, Fri, Sat or Sun"))
        for k, v in matches.groupdict().items():
            if v is None:
                continue
            if (val := _DAY_MAPPING.get(k)) is not None:
                return (val, k)
        raise BadArgument(_("Day must be one of:\nMon,Tue,Wed,Thurs,Fri,Sat or Sun"))


class PercentageConverter(Converter):
    async def convert(self, ctx, argument) -> float:
        arg = argument.lower()
        if arg in {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}:
            raise BadArgument(_("Percentage must be between 0% and 100%"))
        match = PERCENTAGE.match(argument)
        if not match:
            raise BadArgument(_("Percentage must be between 0% and 100%"))
        value = match.group(1)
        pencentage = match.group(2)
        arg = float(value)
        if pencentage:
            arg /= 100
        if arg < 0 or arg > 1:
            raise BadArgument(_("Percentage must be between 0% and 100%"))
        return arg


class NoExitParser(argparse.ArgumentParser):
    def error(self, message):
        raise commands.BadArgument(message=message)


class RarityAction(argparse.Action):
    """
    Handle Enum conversion in argparse
    https://stackoverflow.com/a/60750535
    """

    def __init__(self, **kwargs):
        # Pop off the type value
        enum_type = kwargs.pop("type", None)

        # Ensure an Enum subclass is provided
        if enum_type is None:
            raise ValueError("type must be assigned an Enum when using EnumAction")
        if not issubclass(enum_type, enum.Enum):
            raise TypeError("type must be an Enum when using EnumAction")

        # Generate choices from the Enum
        options = tuple(
            set(
                list(i.name.lower() for i in enum_type.names().keys())
                + list(i.lower() for i in enum_type.names().values())
            )
        )
        kwargs.setdefault("choices", options)

        super().__init__(**kwargs)

        self._enum = enum_type

    def __call__(self, parser, namespace, values, option_string=None):
        # Convert value back into an Enum
        value = []
        if values:
            for v in values:
                try:
                    value.append(self._enum.get_from_name(v))
                except KeyError:
                    pass
        log.debug(value)
        setattr(namespace, self.dest, value)


class BackpackFilterParser(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Mapping[str, Any]:
        argument = argument.replace("—", "--")
        command, *arguments = argument.split(" -- ")
        if arguments:
            argument = " -- ".join(arguments)
        else:
            command = ""
        response = {}
        set_names = set(ctx.cog.SET_BONUSES.keys())
        parser = NoExitParser(description="Backpack Filter Parsing.", add_help=False)
        parser.add_argument("--str", dest="strength", nargs="+")
        parser.add_argument("--strength", dest="strength", nargs="+")

        parser.add_argument("--intelligence", dest="intelligence", nargs="+")
        parser.add_argument("--int", dest="intelligence", nargs="+")

        parser.add_argument("--cha", dest="charisma", nargs="+")
        parser.add_argument("--charisma", dest="charisma", nargs="+")

        parser.add_argument("--luc", dest="luck", nargs="+")
        parser.add_argument("--luck", dest="luck", nargs="+")

        parser.add_argument("--dex", dest="dexterity", nargs="+")
        parser.add_argument("--dexterity", dest="dexterity", nargs="+")

        parser.add_argument("--lvl", dest="level", nargs="+")
        parser.add_argument("--level", dest="level", nargs="+")

        parser.add_argument("--deg", dest="degrade", nargs="+")
        parser.add_argument("--degrade", dest="degrade", nargs="+")

        parser.add_argument("--slot", nargs="*", dest="slot", default=[i for i in Slot], type=Slot, action=RarityAction)

        parser.add_argument(
            "--rarity", nargs="*", dest="rarity", default=[i for i in Rarities], type=Rarities, action=RarityAction
        )

        parser.add_argument("--set", nargs="*", dest="set", choices=set_names, default=[])

        parser.add_argument("--equip", dest="equippable", action="store_true", default=False)
        parser.add_argument("--equippable", dest="equippable", action="store_true", default=False)

        parser.add_argument("--delta", dest="delta", action="store_true", default=False)
        parser.add_argument("--diff", dest="delta", action="store_true", default=False)
        parser.add_argument("--icase", dest="icase", action="store_true", default=False)
        parser.add_argument("--except", dest="except", action="store_true", default=False)

        parser.add_argument("--match", nargs="*", dest="match", default=[])
        parser.add_argument("--no-match", nargs="*", dest="no_match", default=[])

        if not command:
            parser.add_argument("command", nargs="*")
        try:
            arg = shlex.split(argument, posix=True)
            vals = vars(parser.parse_args(arg))
        except argparse.ArgumentError as exc:
            raise ArgParserFailure(exc.argument_name, exc.message)
        except ValueError:
            raise BadArgument()
        response["delta"] = vals["delta"]
        response["equippable"] = vals["equippable"]
        response["set"] = vals["set"]
        if vals["rarity"]:
            response["rarity"] = vals["rarity"]
        if vals["slot"]:
            response["slot"] = vals["slot"]
        response["icase"] = vals["icase"]
        response["except"] = vals["except"]

        if vals["match"]:
            response["match"] = " ".join(vals["match"]).strip()

        if vals["no_match"]:
            response["no_match"] = " ".join(vals["no_match"]).strip()

        response.update(process_argparse_stat(vals, "strength"))
        response.update(process_argparse_stat(vals, "intelligence"))
        response.update(process_argparse_stat(vals, "charisma"))
        response.update(process_argparse_stat(vals, "luck"))
        response.update(process_argparse_stat(vals, "dexterity"))
        response.update(process_argparse_stat(vals, "level"))
        response.update(process_argparse_stat(vals, "degrade"))
        return response


def process_argparse_stat(data: Mapping, stat: str) -> Mapping:
    temp = {}
    temp[stat] = {}
    if variable := data.get(stat):
        temp[stat] = {}
        matches = re.findall(ARG_OP_REGEX, " ".join(variable))
        if matches:
            operands = [(o, int(v)) for o, v in matches if o]
            if not operands:
                exact = [int(v) for o, v in matches if not o]
                if len(exact) == 1:
                    temp[stat]["equal"] = exact[0]
                else:
                    temp[stat]["max"] = max(exact)
                    temp[stat]["min"] = min(exact)
            else:
                if len(operands) == 1:
                    o, v = operands[0]
                    if o in {">"}:
                        temp[stat]["max"] = float("inf")
                        temp[stat]["min"] = v
                    else:
                        temp[stat]["min"] = float("-inf")
                        temp[stat]["max"] = v
                else:
                    d = defaultdict(set)
                    for o, v in operands:
                        d[o].add(v)
                    temp[stat]["max"] = min(float("inf"), *d["<"])
                    temp[stat]["min"] = max(float("-inf"), *d[">"])
    return temp
