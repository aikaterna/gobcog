# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import re
import shlex
from collections import defaultdict
from copy import copy
from datetime import date, datetime, timedelta
from string import ascii_letters, digits
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Set, Tuple, Union

import discord
from beautifultable import ALIGN_LEFT, BeautifulTable
from discord.ext.commands import check
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import Config, commands
from redbot.core.commands import UserFeedbackCheckFailure
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box, escape, humanize_number
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from . import bank

log = logging.getLogger("red.cogs.adventure")

_ = Translator("Adventure", __file__)


DEV_LIST = [208903205982044161, 154497072148643840, 218773382617890828]

ORDER = [
    "head",
    "neck",
    "chest",
    "gloves",
    "belt",
    "legs",
    "boots",
    "left",
    "right",
    "two handed",
    "ring",
    "charm",
]
TINKER_OPEN = r"{.:'"
TINKER_CLOSE = r"':.}"
LEGENDARY_OPEN = r"{Legendary:'"
ASC_OPEN = r"{Ascended:'"
LEGENDARY_CLOSE = r"'}"
SET_OPEN = r"{Set:'"
EVENT_OPEN = r"{Event:'"

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
RARITIES = ("normal", "rare", "epic", "legendary", "ascended", "set", "event")
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


class ArgParserFailure(UserFeedbackCheckFailure):
    """Raised when parsing an argument fails."""

    def __init__(self, cmd: str, message: str):
        self.cmd = cmd
        super().__init__(message=message)


class Stats(Converter):
    """This will parse a string for specific keywords like attack and dexterity followed by a
    number to create an item object to be added to a users inventory."""

    async def convert(self, ctx: commands.Context, argument: str) -> Dict[str, int]:
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
        possible_stats = dict(
            att=ATT.search(argument),
            cha=CHA.search(argument),
            int=INT.search(argument),
            dex=DEX.search(argument),
            luck=LUCK.search(argument),
            degrade=DEG.search(argument),
            lvl=LEVEL.search(argument),
        )
        try:
            slot = [SLOT.search(argument).group(0)]
            if slot == ["twohanded"]:
                slot = ["left", "right"]
            result["slot"] = slot
        except AttributeError:
            raise BadArgument(_("No slot position was provided."))
        try:
            result["rarity"] = RARITY.search(argument).group(0)
        except AttributeError:
            raise BadArgument(_("No rarity was provided."))
        for (key, value) in possible_stats.items():
            try:
                stat = int(value.group(1))
                if (
                    (key not in ["degrade", "lvl"] and stat > 10) or (key == "lvl" and stat < 50)
                ) and not await ctx.bot.is_owner(ctx.author):
                    raise BadArgument(_("Don't you think that's a bit overpowered? Not creating item."))
                result[key] = stat
            except (AttributeError, ValueError):
                pass
        return result


class Item:
    """An object to represent an item in the game world."""

    def __init__(self, **kwargs):
        if kwargs.get("rarity") in ["event"]:
            self.name: str = kwargs.get("name")
        elif kwargs.get("rarity") in ["set", "legendary", "ascended"]:
            self.name: str = kwargs.get("name").title()
        else:
            self.name: str = kwargs.get("name").lower()
        self.slot: List[str] = kwargs.get("slot")
        self.att: int = kwargs.get("att")
        self.int: int = kwargs.get("int")
        self.cha: int = kwargs.get("cha")
        self.rarity: str = kwargs.get("rarity")
        self.dex: int = kwargs.get("dex")
        self.luck: int = kwargs.get("luck")
        self.owned: int = kwargs.get("owned")
        self.set: bool = kwargs.get("set", False)
        self.parts: int = kwargs.get("parts")
        self.total_stats: int = self.att + self.int + self.cha + self.dex + self.luck
        if len(self.slot) > 2:
            self.total_stats *= 2
        self.max_main_stat = max(self.att, self.int, self.cha, 1)
        self.lvl: int = (
            kwargs.get("lvl") or self.get_equip_level()
        ) if self.rarity == "event" else self.get_equip_level()
        self.degrade = kwargs.get("degrade", 5)

    def __str__(self):
        if self.rarity == "normal":
            return self.name
        elif self.rarity == "rare":
            return f".{self.name.replace(' ', '_')}"
        elif self.rarity == "epic":
            return f"[{self.name}]"
        elif self.rarity == "legendary":
            return f"{LEGENDARY_OPEN}{self.name}{LEGENDARY_CLOSE}"
        elif self.rarity == "ascended":
            return f"{ASC_OPEN}'{self.name}'{LEGENDARY_CLOSE}"
        elif self.rarity == "set":
            return f"{SET_OPEN}'{self.name}'{LEGENDARY_CLOSE}"
        elif self.rarity == "forged":
            name = self.name.replace("'", "’")
            return f"{TINKER_OPEN}{name}{TINKER_CLOSE}"
        elif self.rarity == "event":
            return f"{EVENT_OPEN}'{self.name}'{LEGENDARY_CLOSE}"
        return self.name

    @property
    def formatted_name(self):
        return str(self)

    def get_equip_level(self):
        lvl = 1
        if self.rarity not in ["forged"]:
            # epic and legendary stats too similar so make level req's
            # the same
            rarity_multiplier = max(min(RARITIES.index(self.rarity) if self.rarity in RARITIES else 1, 5), 1)
            mult = 1 + (rarity_multiplier / 10)
            positive_stats = (
                sum([i for i in [self.att, self.int, self.cha, self.dex, self.luck] if i > 0])
                * mult
                * (1.7 if len(self.slot) == 2 else 1)
            )
            negative_stats = (
                sum([i for i in [self.att, self.int, self.cha, self.dex, self.luck] if i < 0])
                / 2
                * (1.7 if len(self.slot) == 2 else 1)
            )
            lvl = positive_stats + negative_stats
        return max(int(lvl), 1)

    @staticmethod
    def remove_markdowns(item):
        if item.startswith(".") or "_" in item:
            item = item.replace("_", " ").replace(".", "")
        if item.startswith("["):
            item = item.replace("[", "").replace("]", "")
        if item.startswith("{Legendary:'"):
            item = item.replace("{Legendary:'", "").replace("'}", "")
        if item.startswith("{legendary:'"):
            item = item.replace("{legendary:'", "").replace("'}", "")
        if item.startswith("{ascended:'"):
            item = item.replace("{ascended:'", "").replace("'}", "")
        if item.startswith("{Ascended:'"):
            item = item.replace("{Ascended:'", "").replace("'}", "")
        if item.startswith("{Gear_Set:'"):
            item = item.replace("{Gear_Set:'", "").replace("'}", "")
        if item.startswith("{gear_set:'"):
            item = item.replace("{gear_set:'", "").replace("'}", "")
        if item.startswith("{Gear Set:'"):
            item = item.replace("{Gear Set:'", "").replace("'}", "")
        if item.startswith("{Set:'"):
            item = item.replace("{Set:''", "").replace("''}", "")
        if item.startswith("{set:'"):
            item = item.replace("{set:''", "").replace("''}", "")
        if item.startswith("{.:'"):
            item = item.replace("{.:'", "").replace("':.}", "")
        if item.startswith("{Event:'"):
            item = item.replace("{Event:'", "").replace("'}", "")
        return item

    @classmethod
    def from_json(cls, data: dict):
        name = "".join(data.keys())
        data = data[name]
        rarity = "normal"
        if name.startswith("."):
            name = name.replace("_", " ").replace(".", "")
            rarity = "rare"
        elif name.startswith("["):
            name = name.replace("[", "").replace("]", "")
            rarity = "epic"
        elif name.startswith("{Legendary:'"):
            name = name.replace("{Legendary:'", "").replace("'}", "")
            rarity = "legendary"
        elif name.startswith("{legendary:'"):
            name = name.replace("{legendary:'", "").replace("'}", "")
            rarity = "legendary"
        elif name.startswith("{Ascended:'"):
            name = name.replace("{Ascended:'", "").replace("'}", "")
            rarity = "ascended"
        elif name.startswith("{ascended:'"):
            name = name.replace("{ascended:'", "").replace("'}", "")
            rarity = "ascended"
        elif name.startswith("{Gear_Set:'"):
            name = name.replace("{Gear_Set:'", "").replace("'}", "")
            rarity = "set"
        elif name.startswith("{Gear Set:'"):
            name = name.replace("{Gear Set:'", "").replace("'}", "")
            rarity = "set"
        elif name.startswith("{gear_set:'"):
            name = name.replace("{gear_set:'", "").replace("'}", "")
            rarity = "set"
        elif name.startswith("{Set:'"):
            name = name.replace("{Set:''", "").replace("''}", "")
            rarity = "set"
        elif name.startswith("{set:'"):
            name = name.replace("{set:''", "").replace("''}", "")
            rarity = "set"
        elif name.startswith("{.:'"):
            name = name.replace("{.:'", "").replace("':.}", "")
            rarity = "forged"
        elif name.startswith("{Event:'"):
            name = name.replace("{Event:'", "").replace("''}", "")
            rarity = "event"
        rarity = data["rarity"] if "rarity" in data else rarity
        att = data["att"] if "att" in data else 0
        dex = data["dex"] if "dex" in data else 0
        inter = data["int"] if "int" in data else 0
        cha = data["cha"] if "cha" in data else 0
        luck = data["luck"] if "luck" in data else 0
        owned = data["owned"] if "owned" in data else 1
        lvl = data["lvl"] if "lvl" in data else 1
        _set = data["set"] if "set" in data else False
        slots = data["slot"]
        degrade = data["degrade"] if "degrade" in data else 3
        parts = data["parts"] if "parts" in data else 0
        db = get_item_db(rarity)
        if db and rarity == "set":
            item = db.get(name, {})
            if item:
                parts = item.get("parts", parts)
                _set = item.get("set", _set)
                att = item.get("att", att)
                inter = item.get("int", inter)
                cha = item.get("cha", cha)
                dex = item.get("dex", dex)
                luck = item.get("luck", luck)
                slots = item.get("slot", slots)
        if rarity not in ["legendary", "event", "ascended"]:
            degrade = 3
        if rarity not in ["event"]:
            lvl = 1

        item_data = {
            "name": name,
            "slot": slots,
            "att": att,
            "int": inter,
            "cha": cha,
            "rarity": rarity,
            "dex": dex,
            "luck": luck,
            "owned": owned,
            "set": _set,
            "lvl": lvl,
            "parts": parts,
            "degrade": degrade,
        }
        return cls(**item_data)

    def to_json(self) -> dict:
        db = get_item_db(self.rarity)
        if db and self.rarity == "set":
            updated_set = db.get(self.name)
            if updated_set:
                self.att = updated_set.get("att", self.att)
                self.int = updated_set.get("int", self.int)
                self.cha = updated_set.get("cha", self.cha)
                self.dex = updated_set.get("dex", self.dex)
                self.luck = updated_set.get("luck", self.luck)
                self.set = updated_set.get("set", self.set)
                self.parts = updated_set.get("parts", self.parts)
        data = {
            self.name: {
                "slot": self.slot,
                "att": self.att,
                "int": self.int,
                "cha": self.cha,
                "rarity": self.rarity,
                "dex": self.dex,
                "luck": self.luck,
                "owned": self.owned,
            }
        }
        if self.rarity in ["legendary", "ascended"]:
            data[self.name]["degrade"] = self.degrade
        elif self.rarity == "set":
            data[self.name]["parts"] = self.parts
            data[self.name]["set"] = self.set
            data[self.name].pop("att", None)
            data[self.name].pop("int", None)
            data[self.name].pop("cha", None)
            data[self.name].pop("dex", None)
            data[self.name].pop("luck", None)
        elif self.rarity == "event":
            data[self.name]["degrade"] = self.degrade
            data[self.name]["lvl"] = self.lvl
        return data


class GameSession:
    """A class to represent and hold current game sessions per server."""

    challenge: str
    attribute: str
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


class Character(Item):
    """An class to represent the characters stats."""

    def __init__(self, **kwargs):
        self.exp: int = kwargs.pop("exp")
        self.lvl: int = kwargs.pop("lvl")
        self.treasure: List[int] = kwargs.pop("treasure")
        self.head: Item = kwargs.pop("head")
        self.neck: Item = kwargs.pop("neck")
        self.chest: Item = kwargs.pop("chest")
        self.gloves: Item = kwargs.pop("gloves")
        self.belt: Item = kwargs.pop("belt")
        self.legs: Item = kwargs.pop("legs")
        self.boots: Item = kwargs.pop("boots")
        self.left: Item = kwargs.pop("left")
        self.right: Item = kwargs.pop("right")
        self.ring: Item = kwargs.pop("ring")
        self.charm: Item = kwargs.pop("charm")
        self.backpack: dict = kwargs.pop("backpack")
        self.loadouts: dict = kwargs.pop("loadouts")
        self.heroclass: dict = kwargs.pop("heroclass")
        self.skill: dict = kwargs.pop("skill")
        self.bal: int = kwargs.pop("bal")
        self.user: discord.Member = kwargs.pop("user")
        self.sets = []
        self.rebirths = kwargs.pop("rebirths", 0)
        self.last_known_currency = kwargs.get("last_known_currency")
        self.last_currency_check = kwargs.get("last_currency_check")
        self.gear_set_bonus = {}
        self.get_set_bonus()
        self.maxlevel = self.get_max_level()
        self.lvl = self.lvl if self.lvl < self.maxlevel else self.maxlevel
        self.set_items = self.get_set_item_count()
        self.att, self._att = self.get_stat_value("att")
        self.cha, self._cha = self.get_stat_value("cha")
        self.int, self._int = self.get_stat_value("int")
        self.dex, self._dex = self.get_stat_value("dex")
        self.luck, self._luck = self.get_stat_value("luck")
        if self.lvl >= self.maxlevel and self.rebirths < 1:
            self.att = min(self.att, 5)
            self.cha = min(self.cha, 5)
            self.int = min(self.int, 5)
            self.dex = min(self.dex, 5)
            self.luck = min(self.luck, 5)
            self.skill["att"] = 1
            self.skill["int"] = 1
            self.skill["cha"] = 1
            self.skill["pool"] = 0
        self.total_att = self.att + self.skill["att"]
        self.total_int = self.int + self.skill["int"]
        self.total_cha = self.cha + self.skill["cha"]
        self.total_stats = self.total_att + self.total_int + self.total_cha + self.dex + self.luck
        self.remove_restrictions()
        self.adventures: dict = kwargs.pop("adventures")
        self.nega: dict = kwargs.pop("nega")
        self.weekly_score: dict = kwargs.pop("weekly_score")
        self.pieces_to_keep: dict = {
            "head": {},
            "neck": {},
            "chest": {},
            "gloves": {},
            "belt": {},
            "legs": {},
            "boots": {},
            "left": {},
            "right": {},
            "ring": {},
            "charm": {},
        }
        self.last_skill_reset: int = kwargs.pop("last_skill_reset", 0)
        self.daily_bonus = kwargs.pop(
            "daily_bonus_mapping", {"1": 0, "2": 0, "3": 0.5, "4": 0, "5": 0.5, "6": 1.0, "7": 1.0}
        )

    def remove_restrictions(self):
        if self.heroclass["name"] == "Ranger" and self.heroclass["pet"]:
            requirements = PETS.get(self.heroclass["pet"]["name"], {}).get("bonuses", {}).get("req", {})
            if any(x in self.sets for x in ["The Supreme One", "Ainz Ooal Gown"]) and self.heroclass["pet"]["name"] in [
                "Albedo",
                "Rubedo",
                "Guardians of Nazarick",
            ]:
                return

            if self.heroclass["pet"]["cha"] > (self.total_cha + (self.total_int // 3) + (self.luck // 2)):
                self.heroclass["pet"] = {}
                return

            if requirements:
                if requirements.get("set") and requirements.get("set") not in self.sets:
                    self.heroclass["pet"] = {}

    def get_stat_value(self, stat: str):
        """Calculates the stats dynamically for each slot of equipment."""
        extrapoints = 0
        rebirths = copy(self.rebirths)
        extrapoints += rebirths // 10 * 5

        for _loop_counter in range(rebirths):
            if rebirths >= 30:
                extrapoints += 3
            elif rebirths >= 20:
                extrapoints += 5
            elif rebirths >= 10:
                extrapoints += 1
            elif rebirths < 10:
                extrapoints += 2
            rebirths -= 1

        extrapoints = int(extrapoints)

        stats = 0 + extrapoints
        for slot in ORDER:
            if slot == "two handed":
                continue
            try:
                item = getattr(self, slot)
                if item:
                    stats += int(getattr(item, stat))
            except Exception as exc:
                log.error(f"error calculating {stat}", exc_info=exc)
        return (
            int(stats * self.gear_set_bonus.get("statmult", 1)) + self.gear_set_bonus.get(stat, 0),
            stats,
        )

    async def get_set_count(self, return_items: bool = False, set_name: str = None):
        set_names = {}
        returnable_items = []
        item_names = set()
        async for item in AsyncIter(self.backpack, steps=100):
            item = self.backpack[item]
            if item.rarity != "set":
                continue
            if item.name in item_names:
                continue
            if set_name and set_name != item.set:
                continue
            if item.set and item.set not in set_names:
                returnable_items.append(item)
                item_names.add(item.name)
                set_names.update({item.set: (item.parts, 1)})
            elif item.set and item.set in set_names:
                returnable_items.append(item)
                item_names.add(item.name)
                parts, count = set_names[item.set]
                set_names[item.set] = (parts, count + 1)
        if return_items:
            return returnable_items
        for set_name in SET_BONUSES:
            if set_name in set_names:
                continue
            set_names[set_name] = (max(bonus["parts"] for bonus in SET_BONUSES[set_name]), 0)
        return set_names

    def get_set_bonus(self):
        set_names = {}
        last_slot = ""
        base = {
            "att": 0,
            "cha": 0,
            "int": 0,
            "dex": 0,
            "luck": 0,
            "statmult": 1,
            "xpmult": 1,
            "cpmult": 1,
        }
        added = []
        for slots in ORDER:
            if slots == "two handed":
                continue
            if last_slot == "two handed":
                last_slot = slots
                continue
            item = getattr(self, slots)
            if item is None or item.name in added:
                continue
            if item.set and item.set not in set_names:
                added.append(item.name)
                set_names.update({item.set: (item.parts, 1, SET_BONUSES.get(item.set, []))})
            elif item.set and item.set in set_names:
                added.append(item.name)
                parts, count, bonus = set_names[item.set]
                set_names[item.set] = (parts, count + 1, bonus)
        full_sets = [(s, v[1]) for s, v in set_names.items() if v[1] >= v[0]]
        partial_sets = [(s, v[1]) for s, v in set_names.items()]
        self.sets = [s for s, _ in full_sets if s]
        for (_set, parts) in partial_sets:
            set_bonuses = SET_BONUSES.get(_set, [])
            for bonus in set_bonuses:
                required_parts = bonus.get("parts", 100)
                if required_parts > parts:
                    continue
                for (key, value) in bonus.items():
                    if key == "parts":
                        continue
                    if key not in ["cpmult", "xpmult", "statmult"]:
                        base[key] += value
                    elif key in ["cpmult", "xpmult", "statmult"]:
                        if value > 1:
                            base[key] += value - 1
                        elif value >= 0:
                            base[key] -= 1 - value
        self.gear_set_bonus = base
        self.gear_set_bonus["cpmult"] = max(0, self.gear_set_bonus["cpmult"])
        self.gear_set_bonus["xpmult"] = max(0, self.gear_set_bonus["xpmult"])
        self.gear_set_bonus["statmult"] = max(-0.25, self.gear_set_bonus["statmult"])

    def __str__(self):
        """Define str to be our default look for the character sheet :thinkies:"""
        next_lvl = int((self.lvl + 1) ** 3.5)
        max_level_xp = int((self.maxlevel + 1) ** 3.5)

        if self.heroclass != {} and "name" in self.heroclass:
            class_desc = self.heroclass["name"] + "\n\n" + self.heroclass["desc"]
            if self.heroclass["name"] == "Ranger":
                if not self.heroclass["pet"]:
                    class_desc += _("\n\n- Current pet: [None]")
                elif self.heroclass["pet"]:
                    if any(x in self.sets for x in ["The Supreme One", "Ainz Ooal Gown"]) and self.heroclass["pet"][
                        "name"
                    ] in ["Albedo", "Rubedo", "Guardians of Nazarick",]:
                        class_desc += _("\n\n- Current servant: [{}]").format(self.heroclass["pet"]["name"])
                    else:
                        class_desc += _("\n\n- Current pet: [{}]").format(self.heroclass["pet"]["name"])
        else:
            class_desc = _("Hero.")

        daymult = self.daily_bonus.get(str(datetime.today().isoweekday()), 0)
        statmult = self.gear_set_bonus.get("statmult") - 1
        xpmult = (self.gear_set_bonus.get("xpmult") + daymult) - 1
        cpmult = (self.gear_set_bonus.get("cpmult") + daymult) - 1
        return _(
            "{user}'s Character Sheet\n\n"
            "{{Rebirths: {rebirths}, \n Max Level: {maxlevel}}}\n"
            "{rebirth_text}"
            "A level {lvl} {class_desc} \n\n- "
            "ATTACK: {att} [+{att_skill}] - "
            "CHARISMA: {cha} [+{cha_skill}] - "
            "INTELLIGENCE: {int} [+{int_skill}]\n\n - "
            "DEXTERITY: {dex} - "
            "LUCK: {luck} \n\n- "
            "Backpack: {bp}/{bptotal} \n- "
            "Currency: {bal} \n- "
            "Experience: {xp}/{next_lvl} \n- "
            "Unspent skillpoints: {skill_points}\n\n"
            "Active bonus: {set_bonus}\n"
            "{daily}"
        ).format(
            user=self.user.display_name,
            rebirths=self.rebirths,
            lvl=self.lvl if self.lvl < self.maxlevel else self.maxlevel,
            rebirth_text="\n"
            if self.lvl < self.maxlevel
            else _("You have reached max level. To continue gaining levels and xp, you will have to rebirth.\n\n"),
            maxlevel=self.maxlevel,
            class_desc=class_desc,
            att=humanize_number(self.att),
            att_skill=humanize_number(self.skill["att"]),
            int=humanize_number(self.int),
            int_skill=humanize_number(self.skill["int"]),
            cha=humanize_number(self.cha),
            cha_skill=humanize_number(self.skill["cha"]),
            dex=humanize_number(self.dex),
            luck=humanize_number(self.luck),
            bal=humanize_number(self.bal),
            xp=humanize_number(round(self.exp)),
            next_lvl=humanize_number(next_lvl) if self.lvl < self.maxlevel else humanize_number(max_level_xp),
            skill_points=0 if self.skill["pool"] < 0 else self.skill["pool"],
            set_bonus=(
                f"( {self.gear_set_bonus.get('att'):<2} | "
                f"{self.gear_set_bonus.get('cha'):<2} | "
                f"{self.gear_set_bonus.get('int'):<2} | "
                f"{self.gear_set_bonus.get('dex'):<2} | "
                f"{self.gear_set_bonus.get('luck'):<2} ) "
                f"Stats: {round(statmult * 100)}% | "
                f"EXP: {round(xpmult * 100)}% | "
                f"Credits: {round(cpmult * 100)}%"
            ),
            daily="" if daymult == 0 else _("* Daily bonus active"),
            bp=len(self.backpack),
            bptotal=self.get_backpack_slots(),
        )

    def get_equipment(self):
        """Define a secondary like __str__ to show our equipment."""
        form_string = ""
        last_slot = ""
        rjust = max([len(str(getattr(self, i, 1))) for i in ORDER if i != "two handed"])
        for slots in ORDER:
            if slots == "two handed":
                continue
            if last_slot == "two handed":
                last_slot = slots
                continue
            item = getattr(self, slots)
            if item is None:
                last_slot = slots
                form_string += _("\n\n {} slot").format(slots.title())
                continue
            settext = ""
            slot_name = item.slot[0] if len(item.slot) < 2 else "two handed"
            form_string += _("\n\n {} slot").format(slot_name.title())
            last_slot = slot_name
            att = int(
                ((item.att * 2 if slot_name == "two handed" else item.att) * self.gear_set_bonus.get("statmult", 1))
            )
            inter = int(
                ((item.int * 2 if slot_name == "two handed" else item.int) * self.gear_set_bonus.get("statmult", 1))
            )
            cha = int(
                ((item.cha * 2 if slot_name == "two handed" else item.cha) * self.gear_set_bonus.get("statmult", 1))
            )
            dex = int(
                ((item.dex * 2 if slot_name == "two handed" else item.dex) * self.gear_set_bonus.get("statmult", 1))
            )
            luck = int(
                ((item.luck * 2 if slot_name == "two handed" else item.luck) * self.gear_set_bonus.get("statmult", 1))
            )
            att_space = " " if len(str(att)) >= 1 else ""
            cha_space = " " if len(str(cha)) >= 1 else ""
            int_space = " " if len(str(inter)) >= 1 else ""
            dex_space = " " if len(str(dex)) >= 1 else ""
            luck_space = " " if len(str(luck)) >= 1 else ""

            owned = ""
            if item.rarity in ["legendary", "event", "ascended"] and item.degrade >= 0:
                owned += f" | [{item.degrade}#]"
            if item.set:
                settext += f" | Set `{item.set}` ({item.parts}pcs)"
            form_string += (
                f"\n{str(item):<{rjust}} - "
                f"({att_space}{att:<3} |"
                f"{cha_space}{cha:<3} |"
                f"{int_space}{inter:<3} |"
                f"{dex_space}{dex:<3} |"
                f"{luck_space}{luck:<3} )"
                f" | Lvl { equip_level(self, item):<5}"
                f"{owned}{settext}"
            )

        return form_string + "\n"

    def get_max_level(self) -> int:
        rebirths = max(self.rebirths, 0)

        if rebirths == 0:
            maxlevel = 5
        else:
            maxlevel = REBIRTH_LVL

        for _loop_counter in range(rebirths):
            if rebirths >= 20:
                maxlevel += REBIRTH_STEP
            elif rebirths >= 10:
                maxlevel += 10
            elif rebirths < 10:
                maxlevel += 5
            rebirths -= 1
        return min(maxlevel, 10000)

    @staticmethod
    def get_slot_index(slot):
        if slot not in ORDER:
            return float("inf")
        return ORDER.index(slot)

    @staticmethod
    def get_rarity_index(rarity):
        if rarity not in RARITIES:
            return float("inf")
        reverse_rarities = list(reversed(RARITIES))
        return reverse_rarities.index(rarity)

    async def get_sorted_backpack(self, backpack: dict, slot=None, rarity=None):
        tmp = {}

        def _sort(item):
            return self.get_rarity_index(item[1].rarity), item[1].lvl, item[1].total_stats

        async for item in AsyncIter(backpack, steps=100):
            slots = backpack[item].slot
            slot_name = slots[0]
            if len(slots) > 1:
                slot_name = "two handed"
            if slot is not None and slot_name != slot:
                continue
            if rarity is not None and rarity != backpack[item].rarity:
                continue

            if slot_name not in tmp:
                tmp[slot_name] = []
            tmp[slot_name].append((item, backpack[item]))
        slots = sorted(list(tmp.keys()), key=self.get_slot_index)
        final = []
        async for (idx, slot_name) in AsyncIter(slots, steps=100).enumerate():
            if tmp[slot_name]:
                final.append(sorted(tmp[slot_name], key=_sort))
        return final

    async def looted(self, how_many: int = 1) -> List[Tuple[str, int]]:
        items = [i for n, i in self.backpack.items() if i.rarity not in ["normal", "rare", "epic", "forged"]]
        looted_so_far = 0
        looted = []
        if not items:
            return looted
        count = 0
        while how_many > looted_so_far:
            if looted_so_far >= how_many:
                break
            if count >= 5:
                break
            item = random.choice(items)
            if not bool(random.getrandbits(1)):
                continue
            if item.name not in self.backpack:
                count += 1
                continue
            loot_number = random.randint(1, min(item.owned, how_many - looted_so_far))
            looted_so_far += loot_number
            looted.append((str(item), loot_number))
            item.owned -= loot_number
            if item.owned <= 0:
                del self.backpack[item.name]
            else:
                self.backpack[item.name] = item
        return looted

    async def get_backpack(
        self,
        forging: bool = False,
        consumed=None,
        rarity=None,
        slot=None,
        show_delta=False,
        equippable=False,
        set_name: str = None,
        clean: bool = False,
    ):
        if consumed is None:
            consumed = []
        bkpk = await self.get_sorted_backpack(self.backpack, slot=slot, rarity=rarity)
        if not forging:
            msg = _("{author}'s backpack\n\n").format(author=escape(self.user.display_name, formatting=True))
        else:
            msg = _("{author}'s forgeables\n\n").format(author=escape(self.user.display_name, formatting=True))
        msg_len = len(msg)
        table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
        table.set_style(BeautifulTable.STYLE_RST)
        tables = []
        table.columns.header = [
            "Name",
            "Slot",
            "ATT",
            "CHA",
            "INT",
            "DEX",
            "LUC",
            "LVL",
            "QTY",
            "DEG",
            "SET",
        ]
        consumed_list = consumed
        remainder = False
        async for slot_group in AsyncIter(bkpk, steps=100):
            slot_name_org = slot_group[0][1].slot
            slot_name = slot_name_org[0] if len(slot_name_org) < 2 else "two handed"
            if slot is not None and slot != slot_name:
                continue
            if clean and not slot_group:
                continue
            current_equipped = getattr(self, slot_name if slot != "two handed" else "left", None)
            async for item_name, item in AsyncIter(slot_group, steps=100):
                if forging and (item.rarity in ["forged", "set"] or item in consumed_list):
                    continue
                if forging and item.rarity == "ascended":
                    if self.rebirths < 30:
                        continue
                if rarity is not None and rarity != item.rarity:
                    continue
                if equippable and not can_equip(self, item):
                    continue
                if set_name is not None and set_name != item.set:
                    continue
                if len(str(table)) > 1500:
                    remainder = False
                    tables.append(box(msg + str(table) + f"\nPage {len(tables) + 1}", lang="css"))
                    table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
                    table.set_style(BeautifulTable.STYLE_RST)
                    table.columns.header = [
                        "Name",
                        "Slot",
                        "ATT",
                        "CHA",
                        "INT",
                        "DEX",
                        "LUC",
                        "LVL",
                        "QTY",
                        "DEG",
                        "SET",
                    ]
                if show_delta:
                    att = self.get_equipped_delta(current_equipped, item, "att")
                    cha = self.get_equipped_delta(current_equipped, item, "cha")
                    int = self.get_equipped_delta(current_equipped, item, "int")
                    dex = self.get_equipped_delta(current_equipped, item, "dex")
                    luck = self.get_equipped_delta(current_equipped, item, "luck")
                else:
                    att = item.att if len(slot_name_org) < 2 else item.att * 2
                    cha = item.cha if len(slot_name_org) < 2 else item.cha * 2
                    int = item.int if len(slot_name_org) < 2 else item.int * 2
                    dex = item.dex if len(slot_name_org) < 2 else item.dex * 2
                    luck = item.luck if len(slot_name_org) < 2 else item.luck * 2
                remainder = True
                table.rows.append(
                    (
                        str(item),
                        slot_name,
                        att,
                        cha,
                        int,
                        dex,
                        luck,
                        f"[{r}]" if (r := equip_level(self, item)) is not None and r > self.lvl else f"{r}",
                        item.owned,
                        f"[{item.degrade}]"
                        if item.rarity in ["legendary", "event", "ascended"] and item.degrade >= 0
                        else "N/A",
                        item.set or "N/A",
                    )
                )
        if remainder:
            tables.append(box(msg + str(table) + f"\nPage {len(tables) + 1}", lang="css"))
        return tables

    async def get_sorted_backpack_arg_parse(
        self,
        backpack: dict,
        slots: List[str],
        rarities: List[str],
        sets: List[str],
        equippable: bool,
        _except: bool,
        strength: MutableMapping[str, Any],
        intelligence: MutableMapping[str, Any],
        charisma: MutableMapping[str, Any],
        luck: MutableMapping[str, Any],
        dexterity: MutableMapping[str, Any],
        level: MutableMapping[str, Any],
        degrade: MutableMapping[str, Any],
        ignore_case: bool,
        match: Optional[str],
        no_match: Optional[str],
        rarity_exclude: List[str] = None,
    ):
        tmp = {}

        def _sort(item):
            return self.get_rarity_index(item), item[1].lvl, item[1].total_stats

        if not _except:
            async for item_name in AsyncIter(backpack, steps=100):
                item = backpack[item_name]
                item_slots = item.slot
                slot_name = item_slots[0]
                if rarity_exclude is not None and item.rarity in rarity_exclude:
                    continue

                if len(item_slots) > 1:
                    slot_name = "two handed"
                if no_match:
                    actual_item_name = str(item)
                    if ignore_case:
                        if no_match.lower() in actual_item_name.lower():
                            continue
                    elif no_match in actual_item_name:
                        continue
                if match:
                    actual_item_name = str(item)
                    if ignore_case:
                        if match.lower() not in actual_item_name.lower():
                            continue
                    elif match not in actual_item_name:
                        continue
                if slots and slot_name not in slots:
                    continue
                if sets and item.rarity != "set":
                    continue
                elif rarities and item.rarity not in rarities:
                    continue
                if sets and item.set not in sets:
                    continue
                e_level = equip_level(self, item)
                if equippable and self.lvl < e_level:
                    continue
                if degrade and item.rarity in ["legendary", "ascended", "event"]:
                    if (d := degrade.get("equal")) is not None:
                        if item.degrade != d:
                            continue
                    elif not degrade["min"] < item.degrade < degrade["max"]:
                        continue
                if level:
                    if (d := level.get("equal")) is not None:
                        if e_level != d:
                            continue
                    elif not level["min"] < e_level < level["max"]:
                        continue
                if dexterity:
                    if (d := dexterity.get("equal")) is not None:
                        if item.dex != d:
                            continue
                    elif not dexterity["min"] < item.dex < dexterity["max"]:
                        continue
                if luck:
                    if (d := luck.get("equal")) is not None:
                        if item.luck != d:
                            continue
                    elif not luck["min"] < item.luck < luck["max"]:
                        continue
                if charisma:
                    if (d := charisma.get("equal")) is not None:
                        if item.cha != d:
                            continue
                    elif not charisma["min"] < item.cha < charisma["max"]:
                        continue
                if intelligence:
                    if (d := intelligence.get("equal")) is not None:
                        if item.int != d:
                            continue
                    elif not intelligence["min"] < item.int < intelligence["max"]:
                        continue
                if strength:
                    if (d := strength.get("equal")) is not None:
                        if item.att != d:
                            continue
                    elif not strength["min"] < item.att <= strength["max"]:
                        continue

                if slot_name not in tmp:
                    tmp[slot_name] = []
                tmp[slot_name].append((item_name, item))
        else:
            rarities = [] if rarities == RARITIES else rarities
            slots = [] if slots == ORDER else slots
            async for item_name in AsyncIter(backpack, steps=100):
                item = backpack[item_name]
                item_slots = item.slot
                slot_name = item_slots[0]
                if rarity_exclude is not None and item.rarity in rarity_exclude:
                    continue

                if len(item_slots) > 1:
                    slot_name = "two handed"
                if no_match:
                    actual_item_name = str(item)
                    if ignore_case:
                        if no_match.lower() not in actual_item_name.lower():
                            continue
                    elif no_match not in actual_item_name:
                        continue
                if match:
                    actual_item_name = str(item)
                    if ignore_case:
                        if match.lower() in actual_item_name.lower():
                            continue
                    elif match in actual_item_name:
                        continue
                if slots and slot_name in slots:
                    continue
                elif rarities and item.rarity in rarities:
                    continue
                if sets and item.set in sets:
                    continue
                e_level = equip_level(self, item)
                if equippable and self.lvl >= e_level:
                    continue
                if degrade and item.rarity in ["legendary", "ascended", "event"]:
                    if (d := degrade.get("equal")) is not None:
                        if item.degrade == d:
                            continue
                    elif degrade["min"] < item.degrade < degrade["max"]:
                        continue
                if level:
                    if (d := level.get("equal")) is not None:
                        if e_level == d:
                            continue
                    elif level["min"] < e_level < level["max"]:
                        continue
                if dexterity:
                    if (d := dexterity.get("equal")) is not None:
                        if item.dex == d:
                            continue
                    elif dexterity["min"] < item.dex < dexterity["max"]:
                        continue
                if luck:
                    if (d := luck.get("equal")) is not None:
                        if item.luck == d:
                            continue
                    elif luck["min"] < item.luck < luck["max"]:
                        continue
                if charisma:
                    if (d := charisma.get("equal")) is not None:
                        if item.cha == d:
                            continue
                    elif charisma["min"] < item.cha < charisma["max"]:
                        continue
                if intelligence:
                    if (d := intelligence.get("equal")) is not None:
                        if item.int == d:
                            continue
                    elif intelligence["min"] < item.int < intelligence["max"]:
                        continue
                if strength:
                    if (d := strength.get("equal")) is not None:
                        if item.att == d:
                            continue
                    elif strength["min"] < item.att <= strength["max"]:
                        continue
                if slot_name not in tmp:
                    tmp[slot_name] = []
                tmp[slot_name].append((item_name, item))

        slots = sorted(list(tmp.keys()), key=self.get_slot_index)
        final = []
        async for (idx, slot_name) in AsyncIter(slots, steps=100).enumerate():
            if tmp[slot_name]:
                final.append((slot_name, sorted(tmp[slot_name], key=_sort)))
        return final

    async def get_argparse_backpack(self, query: MutableMapping[str, Any]) -> List[str]:
        delta = query.pop("delta", False)
        equippable = query.pop("equippable", False)
        sets = query.pop("set", [])
        rarities = query.pop("rarity", [])
        slots = query.pop("slot", [])
        strength = query.pop("strength", {})
        intelligence = query.pop("intelligence", {})
        charisma = query.pop("charisma", {})
        luck = query.pop("luck", {})
        dexterity = query.pop("dexterity", {})
        level = query.pop("level", {})
        degrade = query.pop("degrade", {})
        ignore_case = query.pop("icase", False)
        match = query.pop("match", None)
        no_match = query.pop("no_match", None)
        _except = query.pop("except", False)

        bkpk = await self.get_sorted_backpack_arg_parse(
            self.backpack,
            slots=slots,
            rarities=rarities,
            sets=sets,
            equippable=equippable,
            strength=strength,
            intelligence=intelligence,
            charisma=charisma,
            luck=luck,
            dexterity=dexterity,
            level=level,
            degrade=degrade,
            match=match,
            no_match=no_match,
            ignore_case=ignore_case,
            _except=_except,
        )

        msg = _("{author}'s backpack\n\n").format(author=escape(self.user.display_name, formatting=True))
        table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
        table.set_style(BeautifulTable.STYLE_RST)
        tables = []
        headers = [
            "Name",
            "Slot",
            "ATT",
            "CHA",
            "INT",
            "DEX",
            "LUC",
            "LVL",
            "QTY",
        ]
        if not rarities or any(x in rarities for x in ["legendary", "event", "ascended"]):
            headers.append("DEG")

        if sets or not rarities or "set" in rarities:
            headers.append("SET")

        table.columns.header = headers

        remainder = False
        async for slot_name, slot_group in AsyncIter(bkpk, steps=100):
            slot_name_org = slot_group[0][1].slot
            current_equipped = getattr(self, slot_name if slot_name != "two handed" else "left", None)
            async for item_name, item in AsyncIter(slot_group, steps=100):
                if len(str(table)) > 1500:
                    tables.append(box(msg + str(table) + f"\nPage {len(tables) + 1}", lang="css"))
                    table = BeautifulTable(default_alignment=ALIGN_LEFT, maxwidth=500)
                    table.set_style(BeautifulTable.STYLE_RST)
                    table.columns.header = headers
                    remainder = False
                if delta:
                    att = self.get_equipped_delta(current_equipped, item, "att")
                    cha = self.get_equipped_delta(current_equipped, item, "cha")
                    int = self.get_equipped_delta(current_equipped, item, "int")
                    dex = self.get_equipped_delta(current_equipped, item, "dex")
                    luck = self.get_equipped_delta(current_equipped, item, "luck")
                else:
                    att = item.att if len(slot_name_org) < 2 else item.att * 2
                    cha = item.cha if len(slot_name_org) < 2 else item.cha * 2
                    int = item.int if len(slot_name_org) < 2 else item.int * 2
                    dex = item.dex if len(slot_name_org) < 2 else item.dex * 2
                    luck = item.luck if len(slot_name_org) < 2 else item.luck * 2
                data = [
                    str(item),
                    slot_name,
                    att,
                    cha,
                    int,
                    dex,
                    luck,
                    f"[{r}]" if (r := equip_level(self, item)) is not None and r > self.lvl else f"{r}",
                    item.owned,
                ]
                if "DEG" in headers:
                    data.append(
                        f"[{item.degrade}]"
                        if item.rarity in ["legendary", "event", "ascended"] and item.degrade >= 0
                        else "N/A"
                    )
                if "SET" in headers:
                    data.append(item.set or "N/A",)
                table.rows.append(data)
                remainder = True
        if remainder:
            tables.append(box(msg + str(table) + f"\nPage {len(tables) + 1}", lang="css"))
        return tables

    async def get_argparse_backpack_items(
        self, query: MutableMapping[str, Any], rarity_exclude: List[str] = None
    ) -> List[Item]:
        equippable = query.pop("equippable", False)
        sets = query.pop("set", [])
        rarities = query.pop("rarity", [])
        slots = query.pop("slot", [])
        strength = query.pop("strength", {})
        intelligence = query.pop("intelligence", {})
        charisma = query.pop("charisma", {})
        luck = query.pop("luck", {})
        dexterity = query.pop("dexterity", {})
        level = query.pop("level", {})
        degrade = query.pop("degrade", {})
        ignore_case = query.pop("icase", False)
        match = query.pop("match", None)
        no_match = query.pop("no_match", None)
        _except = query.pop("except", False)

        bkpk = await self.get_sorted_backpack_arg_parse(
            self.backpack,
            slots=slots,
            rarities=rarities,
            sets=sets,
            equippable=equippable,
            strength=strength,
            intelligence=intelligence,
            charisma=charisma,
            luck=luck,
            dexterity=dexterity,
            level=level,
            degrade=degrade,
            match=match,
            no_match=no_match,
            ignore_case=ignore_case,
            _except=_except,
        )
        return bkpk

    def get_equipped_delta(self, equiped: Item, to_compare: Item, stat_name: str) -> str:
        if (equiped and len(equiped.slot) == 2) and (to_compare and len(to_compare.slot) == 2):
            equipped_stat = getattr(equiped, stat_name, 0) * 2
            comparing_to_stat = getattr(to_compare, stat_name, 0) * 2
        elif to_compare and len(to_compare.slot) == 2:
            equipped_left_stat = getattr(self.left, stat_name, 0)
            equipped_right_stat = getattr(self.right, stat_name, 0)
            equipped_stat = equipped_left_stat + equipped_right_stat
            comparing_to_stat = getattr(to_compare, stat_name, 0) * 2
        elif (equiped and len(equiped.slot) == 2) and (to_compare and len(to_compare.slot) != 2):
            equipped_stat = getattr(equiped, stat_name, 0) * 2
            comparing_to_stat = getattr(to_compare, stat_name, 0)
        else:
            equipped_stat = getattr(equiped, stat_name, 0)
            comparing_to_stat = getattr(to_compare, stat_name, 0)

        diff = int(comparing_to_stat - equipped_stat)
        return f"[{diff}]" if diff < 0 else f"+{diff}" if diff > 0 else "0"

    async def equip_item(self, item: Item, from_backpack: bool = True, dev=False):
        """This handles moving an item from backpack to equipment."""
        equiplevel = equip_level(self, item)
        if equiplevel > self.lvl:
            if not dev:
                if not from_backpack:
                    await self.add_to_backpack(item)
                return self
        if from_backpack and item.name in self.backpack:
            if self.backpack[item.name].owned > 1:
                self.backpack[item.name].owned -= 1
            else:
                del self.backpack[item.name]
        for slot in item.slot:
            current = getattr(self, slot)
            if current:
                await self.unequip_item(current)
            setattr(self, slot, item)
        return self

    def get_backpack_slots(self, is_dev: bool = False):
        if is_dev:
            return "N/A"
        else:
            return humanize_number((50 + (self.rebirths * 5)))

    def is_backpack_full(self, is_dev: bool = False):
        if is_dev:
            return False
        return len(self.backpack) > (50 + (self.rebirths * 5))

    async def add_to_backpack(self, item: Item, number: int = 1):
        if item:
            if item.name in self.backpack:
                self.backpack[item.name].owned += number
            else:
                self.backpack[item.name] = item

    async def equip_loadout(self, loadout_name):
        loadout = self.loadouts[loadout_name]
        for (slot, item) in loadout.items():
            name_unformatted = "".join(item.keys())
            name = Item.remove_markdowns(name_unformatted)
            current = getattr(self, slot)
            if current and current.name == name_unformatted:
                continue
            if current and current.name != name_unformatted:
                await self.unequip_item(current)
            if name not in self.backpack:
                setattr(self, slot, None)
            else:
                if item.get("rarity", "common") == "event":
                    equiplevel = item.get(
                        "lvl", max((item.get("lvl", 1) - min(max(self.rebirths // 2 - 1, 0), 50)), 1),
                    )
                else:
                    equiplevel = max((item.get("lvl", 1) - min(max(self.rebirths // 2 - 1, 0), 50)), 1)
                if equiplevel > self.lvl:
                    continue

                await self.equip_item(self.backpack[name], True)

        return self

    @staticmethod
    async def save_loadout(char):
        """Return a dict of currently equipped items for loadouts."""
        return {
            "head": char.head.to_json() if char.head else {},
            "neck": char.neck.to_json() if char.neck else {},
            "chest": char.chest.to_json() if char.chest else {},
            "gloves": char.gloves.to_json() if char.gloves else {},
            "belt": char.belt.to_json() if char.belt else {},
            "legs": char.legs.to_json() if char.legs else {},
            "boots": char.boots.to_json() if char.boots else {},
            "left": char.left.to_json() if char.left else {},
            "right": char.right.to_json() if char.right else {},
            "ring": char.ring.to_json() if char.ring else {},
            "charm": char.charm.to_json() if char.charm else {},
        }

    def get_current_equipment(self, return_place_holder: bool = False) -> List[Item]:
        """returns a list of Items currently equipped."""
        equipped = []
        for slot in ORDER:
            if slot == "two handed":
                continue
            item = getattr(self, slot)
            if item:
                equipped.append(item)
            elif return_place_holder:
                equipped.append(get_place_holder(slot))
        return equipped

    async def unequip_item(self, item: Item):
        """This handles moving an item equipment to backpack."""
        if item.name in self.backpack:
            self.backpack[item.name].owned += 1
        else:
            self.backpack[item.name] = item
        for slot in item.slot:
            setattr(self, slot, None)
        return self

    @classmethod
    async def from_json(cls, config: Config, user: discord.Member, daily_bonus_mapping: Dict[str, float]):
        """Return a Character object from config and user."""
        data = await config.user(user).all()
        balance = await bank.get_balance(user)
        equipment = {k: Item.from_json(v) if v else None for k, v in data["items"].items() if k != "backpack"}
        if "int" not in data["skill"]:
            data["skill"]["int"] = 0
            # auto update old users with new skill slot
            # likely unnecessary since this worked without it but this prevents
            # potential issues
        loadouts = data["loadouts"]
        heroclass = {
            "name": "Hero",
            "ability": False,
            "desc": "Your basic adventuring hero.",
            "cooldown": 0,
        }
        if "class" in data:
            # to move from old data to new data
            heroclass = data["class"]
        if "heroclass" in data:
            # we're saving to new data to avoid keyword conflicts
            heroclass = data["heroclass"]
        if "backpack" not in data:
            # helps move old data to new format
            backpack = {}
            for (n, i) in data["items"]["backpack"].items():
                item = Item.from_json({n: i})
                backpack[item.name] = item
        else:
            backpack = {n: Item.from_json({n: i}) for n, i in data["backpack"].items()}
        while len(data["treasure"]) < 5:
            data["treasure"].append(0)

        if len(data["treasure"]) == 5:
            data["treasure"].insert(4, 0)

        if heroclass["name"] == "Ranger":
            if heroclass.get("pet"):
                theme = await config.theme()
                extra_pets = await config.themes.all()
                extra_pets = extra_pets.get(theme, {}).get("pets", {})
                pet_list = {**PETS, **extra_pets}
                heroclass["pet"] = pet_list.get(heroclass["pet"]["name"], heroclass["pet"])

        if "adventures" in data:
            adventures = data["adventures"]
        else:
            adventures = {
                "wins": 0,
                "loses": 0,
                "fight": 0,
                "spell": 0,
                "talk": 0,
                "pray": 0,
                "run": 0,
                "fumbles": 0,
            }
        if "nega" in data:
            nega = data["nega"]
        else:
            nega = {
                "wins": 0,
                "loses": 0,
                "xp__earnings": 0,
                "gold__losses": 0,
            }
        current_week = date.today().isocalendar()[1]
        if "weekly_score" in data and data["weekly_score"]["week"] >= current_week:
            weekly = data["weekly_score"]
        else:
            weekly = {"adventures": 0, "rebirths": 0, "week": current_week}

        hero_data = {
            "adventures": adventures,
            "nega": nega,
            "weekly_score": weekly,
            "exp": max(data["exp"], 0),
            "lvl": data["lvl"],
            "att": data["att"],
            "int": data["int"],
            "cha": data["cha"],
            "treasure": data["treasure"],
            "backpack": backpack,
            "loadouts": loadouts,
            "heroclass": heroclass,
            "skill": data["skill"],
            "bal": balance,
            "user": user,
            "rebirths": data.pop("rebirths", 0),
            "set_items": data.get("set_items", 0),
        }
        for (k, v) in equipment.items():
            hero_data[k] = v
        hero_data["last_skill_reset"] = data.get("last_skill_reset", 0)
        hero_data["last_known_currency"] = data.get("last_known_currency", 0)
        hero_data["last_currency_check"] = data.get("last_currency_check", 0)
        return cls(**hero_data, daily_bonus_mapping=daily_bonus_mapping)

    def get_set_item_count(self):
        count_set = 0
        last_slot = ""
        for slots in ORDER:
            if slots == "two handed":
                continue
            if last_slot == "two handed":
                last_slot = slots
                continue
            item = getattr(self, slots)
            if item is None:
                continue
            if item.rarity in ["set"]:
                count_set += 1
        for (k, v) in self.backpack.items():
            for (n, i) in v.to_json().items():
                if i.get("rarity", False) in ["set"]:
                    count_set += v.owned
        return count_set

    async def to_json(self, config) -> dict:
        backpack = {}
        for (k, v) in self.backpack.items():
            for (n, i) in v.to_json().items():
                backpack[n] = i

        if self.heroclass["name"] == "Ranger" and self.heroclass.get("pet"):
            theme = await config.theme()
            extra_pets = await config.themes.all()
            extra_pets = extra_pets.get(theme, {}).get("pets", {})
            pet_list = {**PETS, **extra_pets}
            self.heroclass["pet"] = pet_list.get(self.heroclass["pet"]["name"], self.heroclass["pet"])

        return {
            "adventures": self.adventures,
            "nega": self.nega,
            "weekly_score": self.weekly_score,
            "exp": self.exp,
            "lvl": self.lvl,
            "att": self._att,
            "int": self._int,
            "cha": self._cha,
            "treasure": self.treasure,
            "items": {
                "head": self.head.to_json() if self.head else {},
                "neck": self.neck.to_json() if self.neck else {},
                "chest": self.chest.to_json() if self.chest else {},
                "gloves": self.gloves.to_json() if self.gloves else {},
                "belt": self.belt.to_json() if self.belt else {},
                "legs": self.legs.to_json() if self.legs else {},
                "boots": self.boots.to_json() if self.boots else {},
                "left": self.left.to_json() if self.left else {},
                "right": self.right.to_json() if self.right else {},
                "ring": self.ring.to_json() if self.ring else {},
                "charm": self.charm.to_json() if self.charm else {},
            },
            "backpack": backpack,
            "loadouts": self.loadouts,  # convert to dict of items
            "heroclass": self.heroclass,
            "skill": self.skill,
            "rebirths": self.rebirths,
            "set_items": self.set_items,
            "last_skill_reset": self.last_skill_reset,
            "last_known_currency": self.last_known_currency,
        }

    async def rebirth(self, dev_val: int = None) -> dict:
        if dev_val is None:
            self.rebirths += 1
        else:
            self.rebirths = dev_val
        self.keep_equipped()
        backpack = {}
        for item in [
            self.head,
            self.chest,
            self.gloves,
            self.belt,
            self.legs,
            self.boots,
            self.left,
            self.right,
            self.ring,
            self.charm,
            self.neck,
        ]:
            if item and item.to_json() not in list(self.pieces_to_keep.values()):
                await self.add_to_backpack(item)
        forged = 0
        for (k, v) in self.backpack.items():
            for (n, i) in v.to_json().items():
                if i.get("degrade", 0) == -1 and i.get("rarity", "common") == "event":
                    backpack[n] = i
                elif i.get("rarity", False) in ["set", "forged"] or str(v) in [".mirror_shield"]:
                    if i.get("rarity", False) in ["forged"]:
                        if forged > 0:
                            continue
                        forged += 1
                    backpack[n] = i
                elif self.rebirths < 50 and i.get("rarity", False) in ["legendary", "event", "ascended"]:
                    if "degrade" in i:
                        i["degrade"] -= 1
                        if i.get("degrade", 0) >= 0:
                            backpack[n] = i

        tresure = [0, 0, 0, 0, 0, 0]
        if self.rebirths >= 15:
            tresure[3] += max(int(self.rebirths // 15), 0)
        if self.rebirths >= 10:
            tresure[2] += max(int(self.rebirths // 10), 0)
        if self.rebirths >= 5:
            tresure[1] += max(int(self.rebirths // 5), 0)
        if self.rebirths > 0:
            tresure[0] += max(int(self.rebirths), 0)

        self.weekly_score.update({"rebirths": self.weekly_score.get("rebirths", 0) + 1})

        return {
            "adventures": self.adventures,
            "nega": self.nega,
            "weekly_score": self.weekly_score,
            "exp": 0,
            "lvl": 1,
            "att": 0,
            "int": 0,
            "cha": 0,
            "treasure": tresure,
            "items": {
                "head": self.pieces_to_keep.get("head", {}),
                "neck": self.pieces_to_keep.get("neck", {}),
                "chest": self.pieces_to_keep.get("chest", {}),
                "gloves": self.pieces_to_keep.get("gloves", {}),
                "belt": self.pieces_to_keep.get("belt", {}),
                "legs": self.pieces_to_keep.get("legs", {}),
                "boots": self.pieces_to_keep.get("boots", {}),
                "left": self.pieces_to_keep.get("left", {}),
                "right": self.pieces_to_keep.get("right", {}),
                "ring": self.pieces_to_keep.get("ring", {}),
                "charm": self.pieces_to_keep.get("charm", {}),
            },
            "backpack": backpack,
            "loadouts": self.loadouts,  # convert to dict of items
            "heroclass": self.heroclass,
            "skill": {"pool": 0, "att": 0, "cha": 0, "int": 0},
            "rebirths": self.rebirths,
            "set_items": self.set_items,
            "last_known_currency": 0,
            "last_currency_check": 0,
        }

    def keep_equipped(self):
        items_to_keep = {}
        last_slot = ""
        for slots in ORDER:
            if slots == "two handed":
                continue
            if last_slot == "two handed":
                last_slot = slots
                continue
            item = getattr(self, slots)
            items_to_keep[slots] = item.to_json() if self.rebirths >= 30 and item and item.set else {}
        self.pieces_to_keep = items_to_keep


class ItemsConverter(Converter):
    async def convert(self, ctx, argument) -> Tuple[str, List[Item]]:
        try:
            c = await Character.from_json(
                ctx.bot.get_cog("Adventure").config, ctx.author, ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        try:
            rarity = RARITY.match(argument.lower()).group(0)
        except AttributeError:
            rarity = None

        if argument.lower() == "all":
            rarity = True

        if rarity is None:
            no_markdown = Item.remove_markdowns(argument)
            lookup = list(i for x, i in c.backpack.items() if no_markdown.lower() in x.lower())
            lookup_m = list(i for x, i in c.backpack.items() if argument.lower() == str(i).lower() and str(i))
            lookup_e = list(i for x, i in c.backpack.items() if argument == str(i))
            _temp_items = set()
            for i in lookup:
                _temp_items.add(str(i))
            for i in lookup_m:
                _temp_items.add(str(i))
            for i in lookup_e:
                _temp_items.add(str(i))
        elif rarity is True:
            lookup = list(i for x, i in c.backpack.items())
            return "all", lookup
        else:
            lookup = list(i for x, i in c.backpack.items() if i.rarity == rarity)
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
            lookup = list(i for x, i in c.backpack.items() if str(i) in _temp_items)
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            for (number, item) in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="css")
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


class ItemConverter(Converter):
    async def convert(self, ctx, argument) -> Item:
        try:
            c = await Character.from_json(
                ctx.bot.get_cog("Adventure").config, ctx.author, ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        no_markdown = Item.remove_markdowns(argument)
        lookup = list(i for x, i in c.backpack.items() if no_markdown.lower() in x.lower())
        lookup_m = list(i for x, i in c.backpack.items() if argument.lower() == str(i).lower() and str(i))
        lookup_e = list(i for x, i in c.backpack.items() if argument == str(i))

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
            lookup = list(i for x, i in c.backpack.items() if str(i) in _temp_items)
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            for (number, item) in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="css")
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


class EquipableItemConverter(Converter):
    async def convert(self, ctx, argument) -> Item:
        try:
            c = await Character.from_json(
                ctx.bot.get_cog("Adventure").config, ctx.author, ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        equipped_items = set()
        for slots in ORDER:
            if slots == "two handed":
                continue
            item = getattr(c, slots, None)
            if item:
                equipped_items.add(str(item))
        no_markdown = Item.remove_markdowns(argument)
        lookup = list(
            i for x, i in c.backpack.items() if no_markdown.lower() in x.lower() and str(i) not in equipped_items
        )
        lookup_m = list(
            i for x, i in c.backpack.items() if argument.lower() == str(i).lower() and str(i) not in equipped_items
        )
        lookup_e = list(i for x, i in c.backpack.items() if argument == str(i) and str(i) not in equipped_items)

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
            lookup = list(i for x, i in c.backpack.items() if str(i) in _temp_items)
            if len(lookup) > 10:
                raise BadArgument(
                    _("You have too many items matching the name `{}`, please be more specific.").format(argument)
                )
            items = ""
            for (number, item) in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="css")
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


class EquipmentConverter(Converter):
    async def convert(self, ctx, argument) -> Union[Item, List[Item]]:
        try:
            c = await Character.from_json(
                ctx.bot.get_cog("Adventure").config, ctx.author, ctx.bot.get_cog("Adventure")._daily_bonus,
            )
        except Exception as exc:
            log.exception("Error with the new character sheet", exc_info=exc)
            raise BadArgument
        if argument.lower() == "all":
            items = []
            for slot in ORDER:
                if slot == "two handed":
                    continue
                equipped_item = getattr(c, slot)
                if not equipped_item:
                    continue
                items.append(equipped_item)
            return items

        if argument.lower() in ORDER:
            for slot in ORDER:
                if slot == "two handed":
                    continue
                equipped_item = getattr(c, slot)
                if not equipped_item:
                    continue
                if (equipped_item.slot[0] == argument.lower()) or (
                    len(equipped_item.slot) > 1 and "two handed" == argument.lower()
                ):
                    return equipped_item

        matched = set()
        lookup = list(
            i
            for i in c.get_current_equipment()
            if argument.lower() in str(i).lower()
            if len(i.slot) != 2 or (str(i) not in matched and not matched.add(str(i)))
        )
        matched = set()
        lookup_m = list(
            i
            for i in c.get_current_equipment()
            if argument.lower() == str(i).lower()
            if len(i.slot) != 2 or (str(i) not in matched and not matched.add(str(i)))
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
            for (number, item) in enumerate(lookup):
                items += f"{number}. {str(item)} (owned {item.owned})\n"

            msg = await ctx.send(
                _("Multiple items share that name, which one would you like?\n{items}").format(
                    items=box(items, lang="css")
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


class SlotConverter(Converter):
    async def convert(self, ctx, argument) -> Optional[str]:
        if argument:
            slot = argument.lower()
            if slot not in ORDER:
                raise BadArgument
        return argument


class RarityConverter(Converter):
    async def convert(self, ctx, argument) -> Optional[str]:
        if argument:
            rarity = argument.lower()
            if rarity not in RARITIES:
                raise BadArgument
        return argument


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


def equip_level(char, item, rebirths=None):
    level = getattr(char, "rebirths", rebirths)
    return item.lvl if item.rarity == "event" else max(item.lvl - min(max(level // 2 - 1, 0), 50), 1)


def can_equip(char: Character, item: Item):
    if char.user.id in DEV_LIST:
        return True
    return char.lvl >= equip_level(char, item)


async def calculate_sp(lvl_end: int, c: Character):
    points = c.rebirths * 10
    async for _loop_counter in AsyncIter(range(lvl_end), steps=100):
        if lvl_end >= 300:
            points += 1
        elif lvl_end >= 200:
            points += 5
        elif lvl_end >= 100:
            points += 1
        elif lvl_end >= 0:
            points += 0.5
        lvl_end -= 1

    return int(points)


def get_item_db(rarity):
    if rarity == "set":
        return TR_GEAR_SET


def has_funds_check(cost):
    async def predicate(ctx):
        if not await bank.can_spend(ctx.author, cost):
            currency_name = await bank.get_currency_name(ctx.guild)
            raise commands.CheckFailure(
                _("You need {cost} {currency_name} to be able to take parts in an adventures").format(
                    cost=humanize_number(cost), currency_name=currency_name
                )
            )
        return True

    return check(predicate)


async def has_funds(user, cost):
    return await bank.can_spend(user, cost)


def parse_timedelta(argument: str) -> Optional[timedelta]:
    matches = TIME_RE.match(argument)
    if matches:
        params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
        if params:
            return timedelta(**params)
    return None


async def no_dev_prompt(ctx: commands.Context) -> bool:
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
            "message", check=lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id, timeout=60,
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


class NoExitParser(argparse.ArgumentParser):
    def error(self, message):
        raise commands.BadArgument(message=message)


class BackpackFilterParser(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Mapping[str, Any]:
        argument = argument.replace("—", "--")
        command, *arguments = argument.split(" -- ")
        if arguments:
            argument = " -- ".join(arguments)
        else:
            command = ""
        response = {}
        set_names = set(SET_BONUSES.keys())
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

        parser.add_argument("--slot", nargs="*", dest="slot", default=ORDER, choices=ORDER)

        parser.add_argument("--rarity", nargs="*", dest="rarity", default=RARITIES, choices=RARITIES)

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


def get_place_holder(slot_name) -> Item:
    return Item(
        name="Empty Slot",
        slot=[slot_name] if slot_name != "two handed" else ["left", "right"],
        rarity="N/A",
        att=0,
        int=0,
        cha=0,
        dex=0,
        luck=0,
        owned=0,
        parts=0,
    )
