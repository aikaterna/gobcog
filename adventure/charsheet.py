import discord
import asyncio
import logging
import re
from copy import copy
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

import discord
from discord.ext.commands import check
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import Config, bank, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

log = logging.getLogger("red.cogs.adventure")
_ = Translator("Adventure", __file__)

try:
    from redbot.core.utils.chat_formatting import humanize_number
except ImportError:

    def humanize_number(val: int) -> str:
        return "{:,}".format(val)


DEV_LIST = []

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
LEGENDARY_CLOSE = r"'}"
SET_OPEN = r"{Gear_Set:'"

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
REBIRTH_STEP = 5

TR_GEAR_SET = {}
TR_LEGENDARY = {}
TR_EPIC = {}
TR_RARE = {}
TR_COMMON = {}
PETS = {}

ATT = re.compile(r"([\d]*) (att(?:ack)?)")
CHA = re.compile(r"([\d]*) (cha(?:risma)?|dip(?:lo?(?:macy)?)?)")
INT = re.compile(r"([\d]*) (int(?:elligence)?)")
LUCK = re.compile(r"([\d]*) (luck)")
DEX = re.compile(r"([\d]*) (dex(?:terity)?)")
SLOT = re.compile(r"(head|neck|chest|gloves|belt|legs|boots|left|right|ring|charm|twohanded)")
RARITY = re.compile(r"(normal|rare|epic|legend(?:ary)?|set|forged)")


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
        }
        possible_stats = dict(
            att=ATT.search(argument),
            cha=CHA.search(argument),
            int=INT.search(argument),
            dex=DEX.search(argument),
            luck=LUCK.search(argument),
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
        for key, value in possible_stats.items():
            try:
                stat = int(value.group(1))
                if stat > 10 and not await ctx.bot.is_owner(ctx.author):
                    raise BadArgument(
                        _("Don't you think that's a bit overpowered? Not creating item.")
                    )
                result[key] = stat
            except (AttributeError, ValueError):
                pass
        return result


class Item:
    """An object to represent an item in the game world."""

    def __init__(self, **kwargs):
        self.name: str = kwargs.pop("name")
        self.slot: List[str] = kwargs.pop("slot")
        self.att: int = kwargs.pop("att")
        self.int: int = kwargs.pop("int")
        self.cha: int = kwargs.pop("cha")
        self.rarity: str = kwargs.pop("rarity")
        self.dex: int = kwargs.pop("dex")
        self.luck: int = kwargs.pop("luck")
        self.owned: int = kwargs.pop("owned")
        self.set: bool = kwargs.pop("set", False)
        self.bonus: dict = kwargs.pop(
            "bonus",
            {
                "att": 0,
                "cha": 0,
                "int": 0,
                "dex": 0,
                "luck": 0,
                "statmult": 1,
                "xpmult": 1,
                "cpmult": 1,
            },
        )
        self.total_stats: int = self.att + self.int + self.cha + self.dex + self.luck
        self.lvl: int = self.get_equip_level()
        self.parts: int = kwargs.pop("parts")
        self.degrade = kwargs.pop("degrade", 2)

    def __str__(self):
        if self.rarity == "normal":
            return self.name
        elif self.rarity == "rare":
            return "." + self.name.replace(" ", "_")
        elif self.rarity == "epic":
            return f"[{self.name}]"
        elif self.rarity == "legendary":
            return f"{LEGENDARY_OPEN}{self.name}{LEGENDARY_CLOSE}"
        elif self.rarity == "set":
            return f"{SET_OPEN}{self.name}{LEGENDARY_CLOSE}"
        elif self.rarity == "forged":
            name = self.name.replace("'", "’")
            return f"{TINKER_OPEN}{name}{TINKER_CLOSE}"
            # Thanks Sinbad!

    @property
    def name_formated(self):
        return str(self)

    def get_equip_level(self):
        if self.rarity == "normal":
            lvl = 1 + self.total_stats if len(self.slot) < 2 else self.total_stats * 2
        elif self.rarity == "rare":
            lvl = 10 + self.total_stats if len(self.slot) < 2 else self.total_stats * 2
        elif self.rarity == "epic":
            lvl = 30 + self.total_stats if len(self.slot) < 2 else self.total_stats * 2
        elif self.rarity == "legendary":
            lvl = 50 + self.total_stats if len(self.slot) < 2 else self.total_stats * 2
        elif self.rarity == "set":
            lvl = 75 + self.total_stats if len(self.slot) < 2 else self.total_stats * 2
        elif self.rarity == "forged":
            lvl = 1
        else:
            lvl = 1

        return max(round(lvl), 1)

    @staticmethod
    def remove_markdowns(item):
        if item.startswith(".") or "_" in item:
            item = item.replace("_", " ").replace(".", "")
        if item.startswith("["):
            item = item.replace("[", "").replace("]", "")
        if item.startswith("{Legendary:'"):
            item = item.replace("{Legendary:'", "").replace("'}", "")
        if item.startswith("{Gear_Set:'"):
            item = item.replace("{Gear_Set:'", "").replace("'}", "")
        if item.startswith("{.:'"):
            item = item.replace("{.:'", "").replace("':.}", "")
        return item

    @classmethod
    def from_json(cls, data: dict):
        name = "".join(data.keys())
        data = data[name]
        rarity = "normal"
        if name.startswith("."):
            name = name.replace("_", " ").replace(".", "")
            rarity = "rare"
        if name.startswith("["):
            name = name.replace("[", "").replace("]", "")
            rarity = "epic"
        if name.startswith("{Legendary:'"):
            name = name.replace("{Legendary:'", "").replace("'}", "")
            rarity = "legendary"
        if name.startswith("{Gear_Set:'"):
            name = name.replace("{Gear_Set:'", "").replace("'}", "")
            rarity = "set"
        if name.startswith("{.:'"):
            name = name.replace("{.:'", "").replace("':.}", "")
            rarity = "forged"
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
        degrade = data["degrade"] if "degrade" in data else 2
        bonus = (
            data["bonus"]
            if "bonus" in data
            else {
                "att": 0,
                "cha": 0,
                "int": 0,
                "dex": 0,
                "luck": 0,
                "statmult": 1,
                "xpmult": 1,
                "cpmult": 1,
            }
        )
        parts = data["parts"] if "parts" in data else 0
        db = get_item_db(rarity)
        if db:
            item = db.get(f"{get_true_name(rarity, name)}", {})
            parts = item.get("parts", parts)
            bonus = item.get("bonus", bonus)
            _set = item.get("set", _set)
            att = item.get("att", att)
            inter = item.get("int", inter)
            cha = item.get("cha", cha)
            dex = item.get("dex", dex)
            luck = item.get("luck", luck)
            slots = item.get("slot", slots)

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
            "bonus": bonus,
            "lvl": lvl,
            "parts": parts,
            "degrade": degrade,
        }
        return cls(**item_data)

    def to_json(self) -> dict:
        db = get_item_db(self.rarity)
        if db:
            item = db.get(f"{str(self)}", {})
            self.parts = item.get("parts", self.parts)
            self.bonus = item.get("bonus", self.bonus)
            self.set = item.get("set", self.set)
            self.att = item.get("att", self.att)
            self.int = item.get("int", self.int)
            self.cha = item.get("cha", self.cha)
            self.dex = item.get("dex", self.dex)
            self.luck = item.get("luck", self.luck)

        data = {
            self.name_formated: {
                "name": get_true_name(self.rarity, self.name),
                "slot": self.slot,
                "att": self.att,
                "int": self.int,
                "cha": self.cha,
                "rarity": self.rarity,
                "dex": self.dex,
                "luck": self.luck,
                "owned": self.owned,
                "set": self.set,
                "bonus": self.bonus,
                "lvl": self.lvl,
                "parts": self.parts,
            }
        }
        if self.rarity == "legendary":
            data[self.name_formated].update({"degrade": self.degrade})

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
    fight: List[discord.Member] = []
    magic: List[discord.Member] = []
    talk: List[discord.Member] = []
    pray: List[discord.Member] = []
    run: List[discord.Member] = []

    def __init__(self, **kwargs):
        self.challenge: str = kwargs.pop("challenge")
        self.attribute: dict = kwargs.pop("attribute")
        self.guild: discord.Guild = kwargs.pop("guild")
        self.boss: bool = kwargs.pop("boss")
        self.miniboss: dict = kwargs.pop("miniboss")
        self.timer: int = kwargs.pop("timer")
        self.monster: dict = kwargs.pop("monster")
        self.message_id: int = 0
        self.reacted = False
        self.participants: Set[discord.Member] = set()
        self.fight: List[discord.Member] = []
        self.magic: List[discord.Member] = []
        self.talk: List[discord.Member] = []
        self.pray: List[discord.Member] = []
        self.run: List[discord.Member] = []


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
        self.gear_set_bonus = {}
        self.get_set_bonus()
        self.maxlevel = self.get_max_level()
        self.lvl = self.lvl if self.lvl < self.maxlevel else self.maxlevel
        self.get_equipment()
        self.set_items = self.get_set_item_count()
        self.att = self.get_stat_value("att")
        self.cha = self.get_stat_value("cha")
        self.int = self.get_stat_value("int")
        self.dex = self.get_stat_value("dex")
        self.luck = self.get_stat_value("luck")

        self.total_att = self.att + self.skill["att"]
        self.total_int = self.int + self.skill["int"]
        self.total_cha = self.cha + self.skill["cha"]
        self.total_stats = self.total_att + self.total_int + self.total_cha + self.dex + self.luck

        self.adventures: dict = kwargs.pop("adventures")
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

    def get_stat_value(self, stat: str):
        """Calculates the stats dynamically for each slot of equipment."""
        extrapoints = 0
        rebirths = copy(self.rebirths)

        extrapoints += rebirths // 10 * 5

        while rebirths >= 30:
            extrapoints += 3
            rebirths -= 1

        while rebirths >= 20:
            extrapoints += 5
            rebirths -= 1
        while rebirths >= 10:
            extrapoints += 1
            rebirths -= 1
        while 0 < rebirths < 10:
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
                    stats += int(
                        (getattr(item, stat) * self.gear_set_bonus.get("statmult", 1))
                        + self.gear_set_bonus.get(stats, 0)
                    )
            except Exception:
                log.error(f"error calculating {stat}", exc_info=True)
        return stats

    def get_set_bonus(self):
        set_names = {}
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
            if item.set and item.set not in set_names:
                set_names.update({item.set: (item.parts, 1, item.bonus)})
            elif item.set and item.set in set_names:
                parts, count, bonus = set_names[item.set]
                set_names[item.set] = (parts, count + 1, bonus)
        valid_sets = [v[-1] for _, v in set_names.items() if v[1] >= v[0]]
        self.sets = [s for s, _ in set_names.items() if s]
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
        for set_bonus in valid_sets:
            for key, value in set_bonus.items():
                if key not in ["cpmult", "xpmult", "statmult"]:
                    base[key] += value
                elif key in ["cpmult", "xpmult", "statmult"]:
                    if value != 1:
                        base[key] += value - 1
        self.gear_set_bonus = base

    def __str__(self):
        """Define str to be our default look for the character sheet :thinkies:"""
        next_lvl = int((self.lvl + 1) ** 3)

        if self.heroclass != {} and "name" in self.heroclass:
            class_desc = self.heroclass["name"] + "\n\n" + self.heroclass["desc"]
            if self.heroclass["name"] == "Ranger":
                if not self.heroclass["pet"]:
                    class_desc += _("\n\n- Current pet: None")
                elif self.heroclass["pet"]:
                    class_desc += _("\n\n- Current pet: {}").format(self.heroclass["pet"]["name"])
        else:
            class_desc = _("Hero.")
        legend = _("( ATT  |  CHA  |  INT  |  DEX  |  LUCK)")
        return _(
            "[{user}'s Character Sheet]\n\n"
            "{{Rebirths: {rebirths}, \n Max Level: {maxlevel}}}\n\n"
            "A level {lvl} {class_desc} \n\n- "
            "ATTACK: {att} [+{att_skill}] - "
            "CHARISMA: {cha} [+{cha_skill}] - "
            "INTELLIGENCE: {int} [+{int_skill}]\n\n - "
            "DEXTERITY: {dex} - "
            "LUCK: {luck} \n\n "
            "Currency: {bal} \n- "
            "Experience: {xp}/{next_lvl} \n- "
            "Unspent skillpoints: {skill_points}\n\n"
            "Items Equipped:\n{legend}{equip}"
        ).format(
            user=self.user.display_name,
            rebirths=self.rebirths,
            lvl=self.lvl if self.lvl < self.maxlevel else self.maxlevel,
            maxlevel=self.maxlevel,
            class_desc=class_desc,
            att=self.att,
            att_skill=self.skill["att"],
            int=self.int,
            int_skill=self.skill["int"],
            cha=self.cha,
            cha_skill=self.skill["cha"],
            dex=self.dex,
            luck=self.luck,
            bal=humanize_number(self.bal),
            xp=humanize_number(round(self.exp)),
            next_lvl=humanize_number(next_lvl) if self.lvl < self.maxlevel else 0,
            skill_points=0 if self.skill["pool"] < 0 else self.skill["pool"],
            legend=legend,
            equip=self.get_equipment(),
        )

    def get_equipment(self):
        """Define a secondary like __str__ to show our equipment."""
        form_string = ""
        last_slot = ""
        rjust = max([len(str(getattr(self, i))) for i in ORDER if i != "two handed"])
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
                (
                    (item.att * 2 if slot_name == "two handed" else item.att)
                    * self.gear_set_bonus.get("statmult", 1)
                )
                + self.gear_set_bonus.get("att", 0)
            )
            inter = int(
                (
                    (item.int * 2 if slot_name == "two handed" else item.int)
                    * self.gear_set_bonus.get("statmult", 1)
                )
                + self.gear_set_bonus.get("int", 0)
            )
            cha = int(
                (
                    (item.cha * 2 if slot_name == "two handed" else item.cha)
                    * self.gear_set_bonus.get("statmult", 1)
                )
                + self.gear_set_bonus.get("cha", 0)
            )
            dex = int(
                (
                    (item.dex * 2 if slot_name == "two handed" else item.dex)
                    * self.gear_set_bonus.get("statmult", 1)
                )
                + self.gear_set_bonus.get("dex", 0)
            )
            luck = int(
                (
                    (item.luck * 2 if slot_name == "two handed" else item.luck)
                    * self.gear_set_bonus.get("statmult", 1)
                )
                + self.gear_set_bonus.get("luck", 0)
            )
            att_space = " " if len(str(att)) == 1 else ""
            cha_space = " " if len(str(cha)) == 1 else ""
            int_space = " " if len(str(inter)) == 1 else ""
            dex_space = " " if len(str(dex)) == 1 else ""
            luck_space = " " if len(str(luck)) == 1 else ""
            if item.set:
                settext += f" | Set `{item.set}` ({item.parts})"
            form_string += (
                f"\n {item.owned} - Lvl req {equip_level(self, item)} | {str(item):<{rjust}} - "
                f"({att_space}{att}  | "
                f"{cha_space}{cha}  | "
                f"{int_space}{inter}  | "
                f"{dex_space}{dex}  | "
                f"{luck_space}{luck} ){settext}"
            )

        return form_string + "\n"

    def get_max_level(self) -> int:
        rebirths = max(self.rebirths, 0)

        if rebirths == 0:
            maxlevel = 5
        else:
            maxlevel = REBIRTH_LVL

        while rebirths >= 20:
            maxlevel += 5
            rebirths -= 1
        while rebirths >= 10:
            maxlevel += 10
            rebirths -= 1
        while 1 < rebirths < 10:
            rebirths -= 1
            maxlevel += 5

        return min(maxlevel, 255)

    @staticmethod
    def get_item_rarity(item):
        if item[0][0] == "{" and item[0][5] == "_":  # Set
            return 0
        elif item[0][0] == "{":  # legendary
            return 1
        elif item[0][0] == "[":  # epic
            return 2
        elif item[0][0] == ".":  # rare
            return 3
        else:
            return 4  # common / normal

    def get_sorted_backpack(self, backpack: dict):
        tmp = {}
        for item in backpack:
            slots = backpack[item].slot
            slot_name = slots[0]
            if len(slots) > 1:
                slot_name = "two handed"

            if slot_name not in tmp:
                tmp[slot_name] = []
            tmp[slot_name].append((item, backpack[item]))

        final = []
        for idx, slot_name in enumerate(tmp.keys()):
            final.append(sorted(tmp[slot_name], key=self.get_item_rarity))

        final.sort(
            key=lambda i: ORDER.index(i[0][1].slot[0])
            if len(i[0][1].slot) == 1
            else ORDER.index("two handed")
        )
        return final

    def get_backpack(self, forging: bool = False, consumed=None):
        if consumed is None:
            consumed = []
        bkpk = self.get_sorted_backpack(self.backpack)
        form_string = _("Items in Backpack: \n( ATT  |  CHA  |  INT  |  DEX  |  LUCK)")
        consumed_list = [i for i in consumed]
        for slot_group in bkpk:
            slot_name = slot_group[0][1].slot
            slot_name = slot_name[0] if len(slot_name) < 2 else _("two handed")
            form_string += f"\n\n {slot_name.title()} slot"
            rjust = max([len(str(i[1])) for i in slot_group])
            for item in slot_group:
                if forging and (item[1].rarity == "forged" or item[1] in consumed_list):
                    continue
                settext = ""
                att_space = " " if len(str(item[1].att)) == 1 else ""
                cha_space = " " if len(str(item[1].cha)) == 1 else ""
                int_space = " " if len(str(item[1].int)) == 1 else ""
                dex_space = " " if len(str(item[1].dex)) == 1 else ""
                luck_space = " " if len(str(item[1].luck)) == 1 else ""
                if item[1].set:
                    settext += f" | Set `{item[1].set}` ({item[1].parts})"
                form_string += (
                    f"\n {item[1].owned} - Lvl req {equip_level(self, item[1])} | {str(item[1]):<{rjust}} - "
                    f"({att_space}{item[1].att}  | "
                    f"{cha_space}{item[1].cha}  | "
                    f"{int_space}{item[1].int}  | "
                    f"{dex_space}{item[1].dex}  | "
                    f"{luck_space}{item[1].luck} ){settext}"
                )

        return form_string + "\n"

    async def equip_item(self, item: Item, from_backpack: bool = True, dev=False):
        """This handles moving an item from backpack to equipment."""
        equiplevel = equip_level(self, item)
        if equiplevel > self.lvl:
            if not dev:
                await self.add_to_backpack(item)
                return self
        if from_backpack and item.name_formated in self.backpack:
            log.debug("removing from backpack")
            del self.backpack[item.name_formated]
        for slot in item.slot:
            log.debug(f"Equipping {slot}")
            current = getattr(self, slot)
            log.debug(current)
            if current:
                await self.unequip_item(current)
            setattr(self, slot, item)
        return self

    async def add_to_backpack(self, item: Item):
        if item:
            item_name = f"{item.name_formated}"
            if item_name in self.backpack:
                self.backpack[item_name].owned += 1
            else:
                self.backpack[item_name] = item

    async def equip_loadout(self, loadout_name):
        loadout = self.loadouts[loadout_name]
        for slot, item in loadout.items():
            if not item:
                continue
            name_unformatted = "".join(item.keys())
            name = Item.remove_markdowns(name_unformatted)
            current = getattr(self, slot)
            if current and current.name_formated == name_unformatted:
                continue
            if current and current.name_formated != name_unformatted:
                await self.unequip_item(current)
            if name_unformatted not in self.backpack:
                log.debug(f"{name} is missing")
                setattr(self, slot, None)
            else:
                equiplevel = max((item.get("lvl", 1) - min(max(self.rebirths // 2 - 1, 0), 50)), 1)
                if equiplevel < self.lvl:
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

    def get_current_equipment(self):
        """returns a list of Items currently equipped."""
        equipped = []
        for slot in ORDER:
            if slot == "two handed":
                continue
            item = getattr(self, slot)
            if item:
                equipped.append(item)
        return equipped

    async def unequip_item(self, item: Item):
        """This handles moving an item equipment to backpack."""
        if item.name_formated in self.backpack:
            self.backpack[item.name_formated].owned += 1
        else:
            self.backpack[item.name_formated] = item
            log.debug(f"storing {item} in backpack")
        for slot in item.slot:
            log.debug(f"Unequipped {slot} {item}")
            setattr(self, slot, None)
        return self

    @classmethod
    async def from_json(cls, config: Config, user: discord.Member):
        """Return a Character object from config and user."""
        data = await config.user(user).all()
        balance = await bank.get_balance(user)
        equipment = {
            k: Item.from_json(v) if v else None
            for k, v in data["items"].items()
            if k != "backpack"
        }
        if "int" not in data["skill"]:
            data["skill"]["int"] = 0
            # auto update old users with new skill slot
            # likely unnecessary since this worked without it but this prevents
            # potential issues
        loadouts = data["loadouts"]
        heroclass = "Hero"
        if "class" in data:
            # to move from old data to new data
            heroclass = data["class"]
        if "heroclass" in data:
            # we're saving to new data to avoid keyword conflicts
            heroclass = data["heroclass"]
        if "backpack" not in data:
            # helps move old data to new format
            backpack = {}
            for n, i in data["items"]["backpack"].items():
                item = Item.from_json({n: i})
                backpack[item.name_formated] = item
        else:
            backpack = {n: Item.from_json({n: i}) for n, i in data["backpack"].items()}
        while len(data["treasure"]) < 5:
            data["treasure"].append(0)

        if heroclass["name"] == "Ranger":
            if heroclass.get("pet"):
                heroclass["pet"] = PETS.get(heroclass["pet"]["name"], heroclass["pet"])
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
        current_week = date.today().isocalendar()[1]
        if "weekly_score" in data and data["weekly_score"]["week"] >= current_week:
            weekly = data["weekly_score"]
        else:
            weekly = {"adventures": 0, "rebirths": 0, "week": current_week}

        hero_data = {
            "adventures": adventures,
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
        for k, v in equipment.items():
            hero_data[k] = v
        return cls(**hero_data)

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
        for k, v in self.backpack.items():
            for n, i in v.to_json().items():
                if i.get("rarity", False) in ["set"]:
                    count_set += 1
        return count_set

    def to_json(self) -> dict:
        backpack = {}
        for k, v in self.backpack.items():
            for n, i in v.to_json().items():
                backpack[n] = i

        if self.heroclass["name"] == "Ranger":
            if self.heroclass.get("pet"):
                self.heroclass["pet"] = PETS.get(
                    self.heroclass["pet"]["name"], self.heroclass["pet"]
                )

        return {
            "adventures": self.adventures,
            "weekly_score": self.weekly_score,
            "exp": self.exp,
            "lvl": self.lvl,
            "att": self.att,
            "int": self.int,
            "cha": self.cha,
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

        for k, v in self.backpack.items():
            for n, i in v.to_json().items():
                if i.get("rarity", False) in ["set", "forged"] or str(v) in [".mirror_shield"]:
                    backpack[n] = i
                elif self.rebirths < 50 and i.get("rarity", False) in ["legendary"]:
                    if "degrade" in i:
                        i["degrade"] -= 1
                        if i.get("degrade", 0) >= 1:
                            backpack[n] = i

        tresure = [0, 0, 0, 0, 0]
        if self.rebirths >= 50:
            tresure[3] += max(int(self.rebirths // 50), 0)
        if self.rebirths >= 20:
            tresure[2] += max(int(self.rebirths // 20), 0)
        if self.rebirths >= 10:
            tresure[1] += max(int(self.rebirths // 10), 0)
        if self.rebirths >= 5:
            tresure[0] += max(int(self.rebirths // 5), 0)

        self.weekly_score.update({"rebirths": self.weekly_score.get("rebirths", 0) + 1})

        return {
            "adventures": self.adventures,
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
            items_to_keep[slots] = (
                item.to_json() if self.rebirths >= 30 and item and item.set else {}
            )
        self.pieces_to_keep = items_to_keep


class ItemConverter(Converter):
    async def convert(self, ctx, argument) -> Item:
        try:
            c = await Character.from_json(ctx.bot.get_cog("Adventure").config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        no_markdown = Item.remove_markdowns(argument)
        lookup = list(i for x, i in c.backpack.items() if no_markdown.lower() in x.lower())
        lookup_m = list(i for x, i in c.backpack.items() if argument.lower() == str(i).lower())
        if len(lookup) == 1:
            return lookup[0]
        elif len(lookup_m) == 1:
            return lookup_m[0]
        elif len(lookup) == 0 and len(lookup_m) == 0:
            raise BadArgument(_("`{}` doesn't seem to match any items you own.").format(argument))
        else:
            if len(lookup) > 10:
                raise BadArgument(
                    _(
                        "You have too many items matching the name `{}`,"
                        " please be more specific"
                    ).format(argument)
                )
            items = ""
            for number, item in enumerate(lookup):
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


def equip_level(char, item):
    return max((item.lvl - min(max(char.rebirths // 2 - 1, 0), 50)), 1)


def can_equip(char: Character, item: Item):
    if char.user.id in DEV_LIST:
        return True
    return char.lvl >= equip_level(char, item)


def calculate_sp(lvl_end: int, c: Character):
    points = c.rebirths * 10

    while lvl_end >= 200:
        lvl_end -= 1
        points += 5

    while lvl_end >= 100:
        lvl_end -= 1
        points += 1

    while lvl_end > 0:
        lvl_end -= 1
        points += 0.5

    return int(points)


def get_item_db(rarity):
    if rarity == "normal":
        return TR_COMMON
    elif rarity == "rare":
        return TR_RARE
    elif rarity == "epic":
        return TR_EPIC
    elif rarity == "legendary":
        return TR_LEGENDARY
    elif rarity == "set":
        return TR_GEAR_SET


def has_funds_check(cost):
    async def predicate(ctx):
        if not await bank.can_spend(ctx.author, cost):
            currency_name = await bank.get_currency_name(ctx.guild)
            raise commands.CheckFailure(
                _(
                    "You need {cost} {currency_name} to be able to take parts in an adventures"
                ).format(cost=humanize_number(cost), currency_name=currency_name)
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


def get_true_name(rarity, name):
    if rarity == "normal":
        return name
    if rarity == "rare":
        return "." + name.replace(" ", "_")
    if rarity == "epic":
        return f"[{name}]"
    if rarity == "legendary":
        return f"{LEGENDARY_OPEN}{name}{LEGENDARY_CLOSE}"
    if rarity == "set":
        return f"{SET_OPEN}{name}{LEGENDARY_CLOSE}"
    if rarity == "forged":
        return f"{TINKER_OPEN}{name}{TINKER_CLOSE}"


def parse_timedelta(argument: str) -> Optional[timedelta]:
    matches = TIME_RE.match(argument)
    if matches:
        params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
        if params:
            return timedelta(**params)
    return None
