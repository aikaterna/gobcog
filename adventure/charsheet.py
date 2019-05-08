import discord
import logging
import re

from typing import List, Set, Dict, Optional
from datetime import timedelta

from redbot.core import commands
from redbot.core import Config, bank
from redbot.core.i18n import Translator, cog_i18n

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

log = logging.getLogger("red.adventure")

_ = Translator("Adventure", __file__)

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

TIME_RE_STRING = r"\s?".join(
    [
        r"((?P<days>\d+?)\s?(d(ays?)?))?",
        r"((?P<hours>\d+?)\s?(hours?|hrs|hr?))?",
        r"((?P<minutes>\d+?)\s?(minutes?|mins?|m))?",
        r"((?P<seconds>\d+?)\s?(seconds?|secs?|s))?",
    ]
)

TIME_RE = re.compile(TIME_RE_STRING, re.I)


class Stats(Converter):
    """
    This will parse a string for specific keywords like attack and dexterity followed by a number
    to create an item object to be added to a users inventory
    """

    ATT = re.compile(r"([\d]*) (att(?:ack)?)")
    CHA = re.compile(r"([\d]*) (cha(?:risma)?|dip(?:lo?(?:macy)?)?)")
    INT = re.compile(r"([\d]*) (int(?:elligence)?)")
    LUCK = re.compile(r"([\d]*) (luck)")
    DEX = re.compile(r"([\d]*) (dex(?:terity)?)")
    SLOT = re.compile(r"(head|neck|chest|gloves|belt|legs|boots|left|right|ring|charm|twohanded)")
    RARITY = re.compile(r"(normal|rare|epic|legend(?:ary)?)")

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
            att=self.ATT.search(argument),
            cha=self.CHA.search(argument),
            int=self.INT.search(argument),
            dex=self.DEX.search(argument),
            luck=self.LUCK.search(argument),
        )
        try:
            slot = [self.SLOT.search(argument).group(0)]
            if slot == ["twohanded"]:
                slot = ["left", "right"]
            result["slot"] = slot
        except AttributeError:
            raise BadArgument("No slot position was provided.")
        try:
            result["rarity"] = self.RARITY.search(argument).group(0)
        except AttributeError:
            raise BadArgument("No rarity was provided.")
        for key, value in possible_stats.items():
            try:
                stat = int(value.group(1))
                if stat > 10 and not await ctx.bot.is_owner(ctx.author):
                    raise BadArgument(
                        "Don't you think that's a bit overpowered? Not creating item."
                    )
                result[key] = stat
            except (AttributeError, ValueError):
                pass
        return result


def parse_timedelta(argument: str) -> Optional[timedelta]:
    matches = TIME_RE.match(argument)
    if matches:
        params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
        if params:
            return timedelta(**params)
    return None


class Item:
    """An object to represent an item in the game world"""

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

    def __str__(self):
        if self.rarity == "normal":
            return self.name
        if self.rarity == "rare":
            return "." + self.name.replace(" ", "_")
        if self.rarity == "epic":
            return f"[{self.name}]"
        if self.rarity == "legendary":
            return f"{LEGENDARY_OPEN}{self.name}{LEGENDARY_CLOSE}"
        if self.rarity == "forged":
            return f"{TINKER_OPEN}{self.name}{TINKER_CLOSE}"
            # Thanks Sinbad!

    @staticmethod
    def _remove_markdowns(item):
        if item.startswith(".") or "_" in item:
            item = item.replace("_", " ").replace(".", "")
        if item.startswith("["):
            item = item.replace("[", "").replace("]", "")
        if item.startswith("{Legendary:'"):
            item = item.replace("{Legendary:'", "").replace("'}", "")
        if item.startswith("{.:'"):
            item = item.replace("{.:'", "").replace("':.}", "")
        return item

    @classmethod
    def _from_json(cls, data: dict):
        # try:
        name = "".join(data.keys())
        data = data[name]
        # except KeyError:
        # return cls(**data)
        rarity = "normal"
        # data = data[name]
        if name.startswith("."):
            name = name.replace("_", " ").replace(".", "")
            rarity = "rare"
        if name.startswith("["):
            name = name.replace("[", "").replace("]", "")
            rarity = "epic"
        if name.startswith("{Legendary:'"):
            name = name.replace("{Legendary:'", "").replace("'}", "")
            rarity = "legendary"
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
        item_data = {
            "name": name,
            "slot": data["slot"],
            "att": att,
            "int": inter,
            "cha": cha,
            "rarity": rarity,
            "dex": dex,
            "luck": luck,
            "owned": owned,
        }
        return cls(**item_data)

    def _to_json(self) -> dict:
        return {
            self.name: {
                "name": self.name,
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


class GameSession:
    """A class to represent and hold current game sessions per server"""

    challenge: str
    attribute: str
    timer: int
    guild: discord.Guild
    boss: bool
    miniboss: dict
    monster: dict
    message_id: int
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
        self.participants: Set[discord.Member] = set()
        self.fight: List[discord.Member] = []
        self.magic: List[discord.Member] = []
        self.talk: List[discord.Member] = []
        self.pray: List[discord.Member] = []
        self.run: List[discord.Member] = []


class Character(Item):
    """An class to represent the characters stats"""

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
        self.att = self.__stat__("att")
        self.cha = self.__stat__("cha")
        self.int = self.__stat__("int")
        self.dex = self.__stat__("dex")
        self.luck = self.__stat__("luck")

    def __stat__(self, stat: str):
        """
        Calculates the stats dynamically for each slot of equipment
        """
        stats = 0
        for slot in ORDER:
            if slot == "two handed":
                continue
            try:
                item = getattr(self, slot)
                # log.debug(item)
                if item:
                    stats += getattr(item, stat)
            except Exception:
                log.error(f"error calculating {stat}", exc_info=True)
                pass
        return stats

    def __str__(self):
        """
            Define str to be our default look for the character sheet :thinkies:
        """
        next_lvl = int((self.lvl + 1) ** 4)
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
            "A level {lvl} {class_desc} \n\n- "
            "ATTACK: {att} [+{att_skill}] - "
            "INTELLIGENCE: {int} [+{int_skill}] - "
            "CHARISMA: {cha} [+{cha_skill}] -\n\n- "
            "DEXTERITY: {dex} - "
            "LUCK: {luck} \n\n "
            "Currency: {bal} \n- "
            "Experience: {xp}/{next_lvl} \n- "
            "Unspent skillpoints: {skill_points}\n\n"
            "Items Equipped:\n{legend}{equip}"
        ).format(
            user=self.user.display_name,
            lvl=self.lvl,
            class_desc=class_desc,
            att=self.att,
            att_skill=self.skill["att"],
            int=self.int,
            int_skill=self.skill["int"],
            cha=self.cha,
            cha_skill=self.skill["cha"],
            dex=self.dex,
            luck=self.luck,
            bal=self.bal,
            xp=round(self.exp),
            next_lvl=next_lvl,
            skill_points=self.skill["pool"],
            legend=legend,
            equip=self.__equipment__(),
        )

    def __equipment__(self):
        """
            Define a secondary like __str__ to show our equipment
        """
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
            slot_name = item.slot[0] if len(item.slot) < 2 else "two handed"
            form_string += _("\n\n {} slot").format(slot_name.title())
            last_slot = slot_name
            # rjust = max([len(i) for i in item.name])
            # for name, stats in data.items():
            att = item.att * 2 if slot_name == "two handed" else item.att
            inter = item.int * 2 if slot_name == "two handed" else item.int
            cha = item.cha * 2 if slot_name == "two handed" else item.cha
            dex = item.dex * 2 if slot_name == "two handed" else item.dex
            luck = item.luck * 2 if slot_name == "two handed" else item.luck
            att_space = " " if len(str(att)) == 1 else ""
            cha_space = " " if len(str(cha)) == 1 else ""
            int_space = " " if len(str(inter)) == 1 else ""
            dex_space = " " if len(str(dex)) == 1 else ""
            luck_space = " " if len(str(luck)) == 1 else ""
            form_string += (
                f"\n {item.owned} - {str(item):<{rjust}} - "
                f"({att_space}{att}  | "
                f"{cha_space}{cha}  | "
                f"{int_space}{inter}  | "
                f"{dex_space}{dex}  | "
                f"{luck_space}{luck} )"
            )

        return form_string + "\n"

    @staticmethod
    def _get_rarity(item):
        if item[0][0] == "{":  # legendary
            return 0
        elif item[0][0] == "[":  # epic
            return 1
        elif item[0][0] == ".":  # rare
            return 2
        else:
            return 3  # common / normal

    def _sort_new_backpack(self, backpack: dict):
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
            final.append(sorted(tmp[slot_name], key=self._get_rarity))

        final.sort(
            key=lambda i: ORDER.index(i[0][1].slot[0])
            if len(i[0][1].slot) == 1
            else ORDER.index("two handed")
        )
        return final

    def __backpack__(self, forging: bool = False, consumed: list = []):
        bkpk = self._sort_new_backpack(self.backpack)
        form_string = _("Items in Backpack: \n( ATT  |  CHA  |  INT  |  DEX  |  LUCK)")
        consumed_list = [i for i in consumed]
        for slot_group in bkpk:

            slot_name = slot_group[0][1].slot
            slot_name = slot_name[0] if len(slot_name) < 2 else _("two handed")
            form_string += f"\n\n {slot_name.title()} slot"
            rjust = max([len(str(i[1])) for i in slot_group])
            for item in slot_group:
                # log.debug(item[1])
                if forging and (item[1].rarity == "forged" or item[1] in consumed_list):
                    continue
                att_space = " " if len(str(item[1].att)) == 1 else ""
                cha_space = " " if len(str(item[1].cha)) == 1 else ""
                int_space = " " if len(str(item[1].int)) == 1 else ""
                dex_space = " " if len(str(item[1].dex)) == 1 else ""
                luck_space = " " if len(str(item[1].luck)) == 1 else ""
                form_string += (
                    f"\n {item[1].owned} - {str(item[1]):<{rjust}} - "
                    f"({att_space}{item[1].att}  | "
                    f"{cha_space}{item[1].cha}  | "
                    f"{int_space}{item[1].int}  | "
                    f"{dex_space}{item[1].dex}  | "
                    f"{luck_space}{item[1].luck} )"
                )

        return form_string + "\n"

    async def _equip_item(self, item: Item, from_backpack: bool = True):
        """This handles moving an item from backpack to equipment"""
        # log.debug(self.backpack)
        if from_backpack and item.name in self.backpack:
            # self.backpack[item.name].owned -= 1
            # log.debug("removing one from backpack")
            log.debug("removing from backpack")
            del self.backpack[item.name]
        # log.debug(item)
        for slot in item.slot:
            log.debug(f"Equipping {slot}")
            current = getattr(self, slot)
            log.debug(current)
            if current:
                await self._unequip_item(current)
            setattr(self, slot, item)
        return self

    async def _equip_loadout(self, loadout_name):
        loadout = self.loadouts[loadout_name]
        for slot, item in loadout.items():
            if not item:
                continue
            name = "".join(item.keys())
            name = Item._remove_markdowns(name)
            current = getattr(self, slot)
            if current and current.name == name:
                continue
            if current and current.name != name:
                await self._unequip_item(current)
            if name not in self.backpack:
                log.debug(f"{name} is missing")
                setattr(self, slot, None)
            else:
                await self._equip_item(self.backpack[name], True)

        return self

    @staticmethod
    async def _save_loadout(char):
        """
            Return a dict of currently equipped items for loadouts
        """
        return {
            "head": char.head._to_json() if char.head else {},
            "neck": char.neck._to_json() if char.neck else {},
            "chest": char.chest._to_json() if char.chest else {},
            "gloves": char.gloves._to_json() if char.gloves else {},
            "belt": char.belt._to_json() if char.belt else {},
            "legs": char.legs._to_json() if char.legs else {},
            "boots": char.boots._to_json() if char.boots else {},
            "left": char.left._to_json() if char.left else {},
            "right": char.right._to_json() if char.right else {},
            "ring": char.ring._to_json() if char.ring else {},
            "charm": char.charm._to_json() if char.charm else {},
        }

    def current_equipment(self):
        """
        returns a list of Items currently equipped
        """
        equipped = []
        for slot in ORDER:
            if slot == "two handed":
                continue
            item = getattr(self, slot)
            if item:
                equipped.append(item)
        return equipped

    async def _unequip_item(self, item: Item):
        """This handles moving an item equipment to backpack"""
        if item.name in self.backpack:
            self.backpack[item.name].owned += 1
        else:
            # item.owned += 1
            self.backpack[item.name] = item
            log.debug(f"storing {item} in backpack")
        for slot in item.slot:
            log.debug(f"Unequipping {slot} {item}")
            setattr(self, slot, None)
        return self

    @classmethod
    async def _from_json(cls, config: Config, user: discord.Member):
        """Return a Character object from config and user"""
        data = await config.user(user).all()
        balance = await bank.get_balance(user)
        equipment = {
            k: Item._from_json(v) if v else None
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
                item = Item._from_json({n: i})
                backpack[item.name] = item
        else:
            backpack = {n: Item._from_json({n: i}) for n, i in data["backpack"].items()}
        # log.debug(data["items"]["backpack"])
        if len(data["treasure"]) < 4:
            data["treasure"].append(0)
        hero_data = {
            "exp": data["exp"],
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
        }
        for k, v in equipment.items():
            hero_data[k] = v
        # log.debug(hero_data)
        return cls(**hero_data)

    def _to_json(self) -> dict:
        backpack = {}
        for k, v in self.backpack.items():
            for n, i in v._to_json().items():
                backpack[n] = i
        return {
            "exp": self.exp,
            "lvl": self.lvl,
            "att": self.att,
            "int": self.int,
            "cha": self.cha,
            "treasure": self.treasure,
            "items": {
                "head": self.head._to_json() if self.head else {},
                "neck": self.neck._to_json() if self.neck else {},
                "chest": self.chest._to_json() if self.chest else {},
                "gloves": self.gloves._to_json() if self.gloves else {},
                "belt": self.belt._to_json() if self.belt else {},
                "legs": self.legs._to_json() if self.legs else {},
                "boots": self.boots._to_json() if self.boots else {},
                "left": self.left._to_json() if self.left else {},
                "right": self.right._to_json() if self.right else {},
                "ring": self.ring._to_json() if self.ring else {},
                "charm": self.charm._to_json() if self.charm else {},
            },
            "backpack": backpack,
            "loadouts": self.loadouts,  # convert to dict of items
            "heroclass": self.heroclass,
            "skill": self.skill,
        }
