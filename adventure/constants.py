from enum import Enum


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

    @property
    def class_name(self):
        return self.value.title()

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

    def ansi(self, class_name: str) -> str:
        return f"{ANSI_ESCAPE}[{self.class_colour.value}m{class_name.title()}{ANSI_CLOSE}"


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
