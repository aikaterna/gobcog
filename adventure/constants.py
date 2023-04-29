from __future__ import annotations

import logging
import time
from enum import Enum

from redbot.core.i18n import Translator

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")


class Skills(Enum):
    attack = "attack"
    charisma = "charisma"
    intelligence = "intelligence"
    reset = "reset"


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


class ANSIBackgroundColours(Enum):
    dark_blue = 40
    orange = 41
    marble_blue = 42
    turquoise = 43
    gray = 44
    indigo = 45
    light_gray = 46
    white = 47


class Rarities(Enum):
    normal = "normal"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"
    ascended = "ascended"
    set = "set"
    event = "event"
    forged = "forged"

    @property
    def ansi(self) -> str:
        return f"{ANSI_ESCAPE}[{self.rarity_colour.value}m{self.value.title()}{ANSI_CLOSE}"

    @property
    def is_chest(self) -> bool:
        return self.value in ("normal", "rare", "epic", "legendary", "ascended", "set")

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
        }[self.value]

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
        }[self.value]


class Slots(Enum):
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

ANSI_ESCAPE = "\u001b"
ANSI_CLOSE = "\u001b[0m"
