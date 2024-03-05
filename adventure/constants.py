from __future__ import annotations

import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

if TYPE_CHECKING:
    from .charsheet import Character, Item

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")

ANSI_ESCAPE = "\u001b"
ANSI_CLOSE = "\u001b[0m"


class Slot(Enum):
    head = "head"
    neck = "neck"
    chest = "chest"
    gloves = "gloves"
    belt = "belt"
    legs = "legs"
    boots = "boots"
    left = "left"
    right = "right"
    two_handed = "two handed"
    ring = "ring"
    charm = "charm"

    @classmethod
    def from_list(cls, data: List[str]) -> Slot:
        if len(data) > 1:
            return cls.two_handed
        return cls(data[0])

    def __str__(self):
        return self.names()[self]

    @property
    def char_slot(self):
        if self is Slot.two_handed:
            return "right"
        return self.name

    @classmethod
    def get_from_name(cls, name: str) -> Slot:
        if name.lower() == "twohanded":
            return Slot.two_handed
        for i in cls:
            if " " in name:
                name = name.replace(" ", "_")
            if i.name.lower() == name.lower():
                return i
            elif name.lower() == i.get_name().lower():
                return i
        raise KeyError(
            _("{slot} is not a valid slot, select one of {slots}").format(
                slot=name, slots=humanize_list([i.get_name() for i in Slot])
            )
        )

    def get_item_slot(self, character: Character) -> Optional[Item]:
        if self is Slot.two_handed:
            return None
        return getattr(character, self.name, None)

    def order(self) -> int:
        return {
            Slot.head: 0,
            Slot.neck: 1,
            Slot.chest: 2,
            Slot.gloves: 3,
            Slot.belt: 4,
            Slot.legs: 5,
            Slot.boots: 6,
            Slot.left: 7,
            Slot.right: 8,
            Slot.two_handed: 9,
            Slot.ring: 10,
            Slot.charm: 11,
        }.get(self, -1)

    @staticmethod
    def names() -> Dict[Slot, str]:
        return {
            Slot.head: _("Head"),
            Slot.neck: _("Neck"),
            Slot.chest: _("Chest"),
            Slot.gloves: _("Gloves"),
            Slot.belt: _("Belt"),
            Slot.legs: _("Legs"),
            Slot.boots: _("Boots"),
            Slot.left: _("Left"),
            Slot.right: _("Right"),
            Slot.two_handed: _("Two Handed"),
            Slot.ring: _("Ring"),
            Slot.charm: _("Charm"),
        }

    @staticmethod
    def short_names() -> Dict[Slot, str]:
        return {
            Slot.head: _("H"),
            Slot.neck: _("N"),
            Slot.chest: _("C"),
            Slot.gloves: _("G"),
            Slot.belt: _("B"),
            Slot.legs: _("L"),
            Slot.boots: _("F"),
            Slot.left: _("LH"),
            Slot.right: _("RH"),
            Slot.two_handed: _("2H"),
            Slot.ring: _("R"),
            Slot.charm: _("CH"),
        }

    def get_short_name(self) -> Optional[str]:
        return self.short_names().get(self)

    def get_name(self) -> Optional[str]:
        return self.names().get(self)

    def to_json(self) -> List[str]:
        if self is Slot.two_handed:
            return ["left", "right"]
        return [self.name]


class Rarities(Enum):
    # Our standard rarities
    normal = 0
    rare = 1
    epic = 2
    legendary = 3
    ascended = 4
    set = 5
    # Special rarities so we leave room for more in between
    forged = 16
    event = 32
    pet = 64

    def __str__(self):
        return self.names()[self]

    @classmethod
    def get_from_name(cls, name: str) -> Rarities:
        for i in cls:
            if i.name == name:
                return i
            elif name == i.get_name():
                return i
        raise KeyError(
            _("{rarity} is not a valid rarity, select one of {rarities}").format(
                rarity=name, rarities=humanize_list([i.get_name() for i in Rarities])
            )
        )

    @staticmethod
    def emojis():
        return {
            Rarities.normal: "\N{WHITE LARGE SQUARE}",
            Rarities.rare: "\N{LARGE GREEN SQUARE}",
            Rarities.epic: "\N{LARGE BLUE SQUARE}",
            Rarities.legendary: "\N{LARGE YELLOW SQUARE}",
            Rarities.ascended: "\N{UP-POINTING SMALL RED TRIANGLE}",
            Rarities.set: "\N{LARGE RED SQUARE}",
            Rarities.forged: "\N{HAMMER AND PICK}\N{VARIATION SELECTOR-16}",
            Rarities.event: "\N{PARTY POPPER}",
            Rarities.pet: "\N{CAT FACE}",
        }

    @staticmethod
    def names():
        return {
            Rarities.normal: _("Normal"),
            Rarities.rare: _("Rare"),
            Rarities.epic: _("Epic"),
            Rarities.legendary: _("Legendary"),
            Rarities.ascended: _("Ascended"),
            Rarities.set: _("Set"),
            Rarities.forged: _("Forged"),
            Rarities.event: _("Event"),
            Rarities.pet: _("Pet"),
        }

    def prefix_chance(self) -> Optional[float]:
        return {
            Rarities.rare: 0.5,
            Rarities.epic: 0.75,
            Rarities.legendary: 0.9,
            Rarities.ascended: 1.0,
            Rarities.set: 0.0,
        }.get(self)

    def suffix_chance(self) -> Optional[float]:
        return {
            Rarities.epic: 0.5,
            Rarities.legendary: 0.75,
            Rarities.ascended: 0.5,
        }.get(self)

    def get_name(self) -> str:
        return self.names().get(self, _("Normal"))

    @property
    def ansi(self) -> str:
        return f"{ANSI_ESCAPE}[{self.rarity_colour.value}m{self.get_name()}{ANSI_CLOSE}"

    def as_ansi(self, name: str, maxwidth: Optional[int] = None) -> str:
        if maxwidth is None:
            return f"{ANSI_ESCAPE}[{self.rarity_colour.value}m{self.as_str(name)}{ANSI_CLOSE}"
        ret = []
        for page in pagify(self.as_str(name), delims=[" "], page_length=maxwidth):
            ret.append(f"{ANSI_ESCAPE}[{self.rarity_colour.value}m{page}{ANSI_CLOSE}")
        return "\n".join(i for i in ret)

    @staticmethod
    def open_strings() -> Dict[Rarities, str]:
        return {
            Rarities.normal: "",
            Rarities.rare: ".",
            Rarities.epic: "",
            Rarities.legendary: r"{Legendary:'",
            Rarities.ascended: r"{Ascended:'",
            Rarities.set: r"{Set:'",
            Rarities.forged: r"{.:'",
            Rarities.event: r"{Event:''",
        }

    @staticmethod
    def close_strings() -> Dict[Rarities, str]:
        return {
            Rarities.normal: "",
            Rarities.rare: "",
            Rarities.epic: "",
            Rarities.legendary: r"'}",
            Rarities.ascended: r"'}",
            Rarities.set: r"'}",
            Rarities.forged: r"':.}",
            Rarities.event: r"''}",
        }

    def get_open_str(self) -> str:
        return self.open_strings().get(self, "")

    def get_close_str(self) -> str:
        return self.close_strings().get(self, "")

    def as_str(self, name: str) -> str:
        open_str = self.get_open_str()
        close_str = self.get_close_str()
        if self is Rarities.rare:
            name = name.replace(" ", "_")
        if self is Rarities.forged:
            name = name.replace("'", "’")
        return f"{open_str}{name}{close_str}"

    @property
    def is_chest(self) -> bool:
        return self.value < Rarities.forged.value

    @property
    def slot(self) -> int:
        """Returns the index of rarity for players chests"""
        return {
            "normal": 0,
            "rare": 1,
            "epic": 2,
            "legendary": 3,
            "ascended": 4,
            "set": 5,
        }[self.name]

    @property
    def emoji(self):
        return self.emojis().get(self)

    @property
    def rarity_colour(self) -> ANSITextColours:
        return {
            "normal": ANSITextColours.normal,
            "rare": ANSITextColours.green,
            "epic": ANSITextColours.blue,
            "legendary": ANSITextColours.yellow,
            "ascended": ANSITextColours.cyan,
            "set": ANSITextColours.red,
            "event": ANSITextColours.normal,
            "forged": ANSITextColours.pink,
        }.get(self.name, ANSITextColours.normal)


class TreasureChest:
    def __init__(self, number: int, rarity: Rarities):
        self.number = number
        if not rarity.is_chest:
            raise TypeError("Rarity of type %s cannot be made into a chest", rarity)
        self.rarity = rarity

    def __repr__(self):
        return f"<{self.rarity.get_name()} Chest number={self.number}>"

    def __int__(self):
        return self.number

    def __str__(self):
        return f"{self.number} {self.rarity.get_name()}"

    def __add__(self, chest: Union[TreasureChest, int]) -> TreasureChest:
        if isinstance(chest, int):
            self.number += chest
            print(f"adding {chest}")
            return self
        if chest.rarity is not self.rarity:
            raise TypeError(
                "Treasure Chest of rarity %s cannot add Treasure Chest of rarity %s", self.rarity, chest.rarity
            )
        self.number += chest.number
        return self

    def __sub__(self, chest: Union[TreasureChest, int]) -> TreasureChest:
        if isinstance(chest, int):
            self.number -= chest
            return self
        if chest.rarity is not self.rarity:
            raise TypeError(
                "Treasure Chest of rarity %s cannot add Treasure Chest of rarity %s", self.rarity, chest.rarity
            )
        self.number -= chest.number
        return self

    def __eq__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return other == self.number
        return other.number == self.number and other.rarity is self.rarity

    def __ne__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return other != self.number
        return other.number != self.number and other.rarity is not self.rarity

    def __lt__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return self.number < other
        if self.rarity is not other.rarity:
            raise TypeError("Cannot compare Treasure chests of different rarities.")
        return self.number < other.number

    def __le__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return self.number <= other
        if self.rarity is not other.rarity:
            raise TypeError("Cannot compare Treasure chests of different rarities.")
        return self.number <= other.number

    def __gt__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return self.number > other
        if self.rarity is not other.rarity:
            raise TypeError("Cannot compare Treasure chests of different rarities.")
        return self.number > other.number

    def __ge__(self, other: Union[TreasureChest, int]) -> bool:
        if isinstance(other, int):
            return self.number >= other
        if self.rarity is not other.rarity:
            raise TypeError("Cannot compare Treasure chests of different rarities.")
        return self.number >= other.number

    @property
    def ansi(self) -> str:
        return f"{ANSI_ESCAPE}[{self.rarity.rarity_colour}m{self.number} {self.rarity.get_name()}{ANSI_CLOSE}"


class Treasure:
    def __init__(
        self, normal: int = 0, rare: int = 0, epic: int = 0, legendary: int = 0, ascended: int = 0, _set: int = 0
    ):
        self.normal: TreasureChest = TreasureChest(normal, Rarities.normal)
        self.rare: TreasureChest = TreasureChest(rare, Rarities.rare)
        self.epic: TreasureChest = TreasureChest(epic, Rarities.epic)
        self.legendary: TreasureChest = TreasureChest(legendary, Rarities.legendary)
        self.ascended: TreasureChest = TreasureChest(ascended, Rarities.ascended)
        self.set: TreasureChest = TreasureChest(_set, Rarities.set)

    def __repr__(self):
        return (
            "<Treasure "
            f"normal={self.normal} "
            f"rare={self.rare} "
            f"epic={self.epic} "
            f"legendary={self.legendary} "
            f"ascended={self.ascended} "
            f"set={self.set}"
            ">"
        )

    def __len__(self):
        return sum(getattr(self, i).number for i in self.list)

    def get_ansi(self):
        """Returns ansi formatted list of all chests only if the number
        of chests is greater than zero
        """
        return humanize_list([i.ansi for i in self if i.number > 0])

    @property
    def list(self):
        return (
            "normal",
            "rare",
            "epic",
            "legendary",
            "ascended",
            "set",
        )

    def __str__(self) -> str:
        """
        Returns a list of all chests available.
        """
        return humanize_list([str(i) for i in self])

    @property
    def ansi(self) -> str:
        """
        Returns a list of all chests available ansi formatted
        """
        return humanize_list([i.ansi for i in self])

    def __iter__(self):
        for x in self.list:
            yield getattr(self, x)

    def __getitem__(self, item: Union[int, str]) -> TreasureChest:
        if isinstance(item, int):
            return getattr(self, self.list[item])
        elif isinstance(item, str):
            if item.lower() not in [i.name for i in Rarities]:
                raise KeyError
            return getattr(self, item.lower())

    def __setitem__(self, key: Union[int, str], newvalue: Union[int, TreasureChest]):
        if isinstance(key, int):
            return getattr(self, self.list[key])
        elif isinstance(key, str):
            if key.lower() not in [i.name for i in Rarities]:
                raise KeyError
            return getattr(self, key.lower())

    def __add__(self, treasure: Treasure) -> Treasure:
        self.normal += treasure.normal
        self.rare += treasure.rare
        self.epic += treasure.epic
        self.legendary += treasure.legendary
        self.ascended += treasure.ascended
        self.set += treasure.set
        return self

    def __sub__(self, treasure: Treasure) -> Treasure:
        self.normal -= treasure.normal
        self.rare -= treasure.rare
        self.epic -= treasure.epic
        self.legendary -= treasure.legendary
        self.ascended -= treasure.ascended
        self.set -= treasure.set
        return self

    def to_json(self):
        return [i.number for i in self]


class Skills(Enum):
    attack = "attack"
    charisma = "charisma"
    intelligence = "intelligence"
    reset = "reset"


class ANSIBackgroundTextColours:
    def __init__(self, text_colour: ANSITextColours, background_colour: ANSIBackgroundColours):
        self.text_colour = text_colour
        self.background_colour = background_colour

    def as_str(self, value: str) -> str:
        return f"{ANSI_ESCAPE}[{self.text_colour.value};{self.background_colour.value}m{value}{ANSI_CLOSE}"


class ANSITextColours(Enum):
    normal = 0
    gray = 30
    grey = 30
    red = 31
    green = 32
    yellow = 33
    blue = 34
    pink = 35
    cyan = 36
    white = 37

    def __str__(self):
        return str(self.value)

    def as_str(self, value: str) -> str:
        return f"{ANSI_ESCAPE}[{self.value}m{value}{ANSI_CLOSE}"


class ANSIBackgroundColours(Enum):
    dark_blue = 40
    orange = 41
    marble_blue = 42
    turquoise = 43
    gray = 44
    indigo = 45
    light_gray = 46
    white = 47

    def __str__(self):
        return str(self.value)

    def as_str(self, value: str) -> str:
        return f"{ANSI_ESCAPE}[{self.value}m{value}{ANSI_CLOSE}"


class HeroClasses(Enum):
    hero = "hero"
    wizard = "wizard"
    tinkerer = "tinkerer"
    berserker = "berserker"
    cleric = "cleric"
    ranger = "ranger"
    bard = "bard"
    psychic = "psychic"

    @classmethod
    def from_name(cls, current_name: str) -> HeroClasses:
        """This basically exists for i18n support and finding the
        Correct HeroClasses enum for people who may have added locales
        to change the theme of some classes.
        """
        if current_name.lower() in [i.name for i in HeroClasses]:
            return cls(current_name.lower())
        for key, value in cls.class_names().items():
            log.debug("key %s value %s", key, _(value))
            if current_name.lower() == value.lower():
                log.debug("Returning %s", key)
                return cls(key)
        return HeroClasses.hero

    @property
    def class_name(self):
        return self.class_names()[self.value]

    @property
    def has_action(self):
        return self not in [HeroClasses.hero, HeroClasses.tinkerer, HeroClasses.ranger]

    @staticmethod
    def class_names():
        return {
            "hero": _("Hero"),
            "wizard": _("Wizard"),
            "tinkerer": _("Tinkerer"),
            "berserker": _("Berserker"),
            "cleric": _("Cleric"),
            "ranger": _("Ranger"),
            "bard": _("Bard"),
            "psychic": _("Psychic"),
        }

    @property
    def class_colour(self) -> ANSITextColours:
        return {
            "hero": ANSITextColours.normal,
            "wizard": ANSITextColours.blue,
            "tinkerer": ANSITextColours.pink,
            "berserker": ANSITextColours.red,
            "cleric": ANSITextColours.white,
            "ranger": ANSITextColours.green,
            "bard": ANSITextColours.yellow,
            "psychic": ANSITextColours.cyan,
        }[self.value]

    @property
    def ansi(self) -> str:
        return f"{ANSI_ESCAPE}[{self.class_colour.value}m{self.class_name}{ANSI_CLOSE}"

    def desc(self):
        return {
            "hero": _("Your basic adventuring hero."),
            "wizard": _(
                "Wizards have the option to focus and add large bonuses to their magic, "
                "but their focus can sometimes go astray...\n"
                "Use the focus command when attacking in an adventure."
            ),
            "tinkerer": _(
                "Tinkerers can forge two different items into a device "
                "bound to their very soul.\nUse the forge command."
            ),
            "berserker": _(
                "Berserkers have the option to rage and add big bonuses to attacks, "
                "but fumbles hurt.\nUse the rage command when attacking in an adventure."
            ),
            "cleric": _(
                "Clerics can bless the entire group when praying.\n"
                "Use the bless command when fighting in an adventure."
            ),
            "ranger": _(
                "Rangers can gain a special pet, which can find items and give "
                "reward bonuses.\nUse the pet command to see pet options."
            ),
            "bard": _(
                "Bards can perform to aid their comrades in diplomacy.\n"
                "Use the music command when being diplomatic in an adventure."
            ),
            "psychic": _(
                "Psychics can show the enemy's weaknesses to their group "
                "allowing them to target the monster's weak-points.\n"
                "Use the insight command in an adventure."
            ),
        }[self.value]

    def to_json(self) -> dict:
        ret = {
            "name": self.name,
            "ability": False,
            "desc": self.desc(),
            "cooldown": time.time(),
        }
        if self is HeroClasses.ranger:
            ret["pet"] = {}
            ret["catch_cooldown"] = time.time()
        return ret


DEV_LIST = (208903205982044161, 154497072148643840, 218773382617890828)
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
RARITIES = ("normal", "rare", "epic", "legendary", "ascended", "set", "event", "forged")
REBIRTH_LVL = 20
REBIRTH_STEP = 10
