from redbot.core import Config, bank
from redbot.core.utils.chat_formatting import escape
import discord
from typing import Optional, Dict, List
from copy import copy
import logging

log = logging.getLogger("red.adventure")

E = lambda t: escape(t.replace("@&", ""), mass_mentions=True, formatting=True)

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

class Item:
    """An object to represent an item in the game world"""

    def __init__(self, **kwargs):
        self.name: str = kwargs.pop("name")
        self.slot: List[str] = kwargs.pop("slot")
        self.att: int = kwargs.pop("att")
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
        if self.rarity == "forged":
            return f"{TINKER_OPEN}{self.name}{TINKER_CLOSE}"
            # Thanks Sinbad!

    @classmethod
    def _from_json(cls, data:dict):
        name = "".join(data.keys())
        rarity = "normal"
        data = data[name]
        if name.startswith("."):
            name = name.replace("_", " ").replace(".", "")
            rarity = "rare"
        if name.startswith("["):
            name = name.replace("[", "").replace("]", "")
            rarity = "epic"
        if name.startswith("{.:'"):
            name = name.replace("{.:'", "").replace("':.}", "")
            rarity = "forged"

        if "dex" not in data:
            dex = 0
        if "luck" not in data:
            luck = 0
        if "owned" not in data:
            owned = 1
        item_data = {
            "name": name,
            "slot": data["slot"],
            "att": data["att"],
            "cha": data["cha"],
            "rarity": rarity,
            "dex": dex,
            "luck": luck,
            "owned": owned,
        }
        return cls(**item_data)

    def _to_json(self) -> dict:
        return {
            "name": self.name,
            "slot": self.slot,
            "att": self.att,
            "cha": self.cha,
            "rarity": self.rarity,
            "dex": self.dex,
            "luck": self.luck,
            "owned": self.owned,
        }

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
        self.att = self.__att__()
        self.cha = self.__cha__()

    def __att__(self):
        att = 0
        for slot in ORDER:
            if slot == "two handed":
                continue
            try:
                item = getattr(self, slot)
                # log.info(item)
                if item:
                    att += item.att
            except Exception as e:
                log.error("error calculating att", exc_info=True)
                pass
        return att

    def __cha__(self):
        cha = 0
        for slot in ORDER:
            if slot == "two handed":
                continue
            try:
                item = getattr(self, slot)
                # log.info(item)
                if item:
                    cha += item.cha
            except Exception as e:
                log.error("error calculating cha", exc_info=True)
                pass
        return cha

    def __str__(self):
        next_lvl = int((self.lvl + 1) ** 4)
        if self.heroclass != {} and "name" in self.heroclass:
            class_desc = self.heroclass["name"] + "\n\n" + self.heroclass["desc"]
            if self.heroclass["name"] == "Ranger":
                if not self.heroclass["ability"]:
                    class_desc += "\n\n- Current pet: None"
                elif self.heroclass["pet"]:
                    class_desc += f"\n\n- Current pet: {self.heroclass['pet']['name']}"
        else:
            class_desc = "Hero."

        
        return (
            f"[{E(self.user.display_name)}'s Character Sheet]\n\n"
            f"A level {self.lvl} {class_desc} \n\n- ATTACK: {self.att} [+{self.skill['att']}] - "
            f"DIPLOMACY: {self.cha} [+{self.skill['cha']}] -\n\n- Currency: {self.bal} \n- Experience: "
            f"{round(self.exp)}/{next_lvl} \n- Unspent skillpoints: {self.skill['pool']}\n\n"
            f"Items Equipped:{self.__equipment__()}"
        )

    def __equipment__(self):
        form_string = ""
        last_slot = ""
        for slots in ORDER:
            if slots == "two handed":
                continue
            if last_slot == "two handed":
                last_slot = slots
                continue
            item = getattr(self, slots)
            if item is None:
                last_slot = slots
                form_string += f"\n\n {slots.title()} slot"
                continue
            slot_name = item.slot[0] if len(item.slot) < 2 else "two handed"
            form_string += f"\n\n {slot_name.title()} slot"
            last_slot = slot_name
            # rjust = max([len(i) for i in item.name])
            # for name, stats in data.items():
            att = item.att * 2 if slot_name == "two handed" else item.att
            cha = item.cha * 2 if slot_name == "two handed" else item.cha
            form_string += (
                f"\n  - {item} - (ATT: {att} | DPL: {cha})"
            )

        return form_string + "\n"

    @staticmethod
    def _get_rarity(item):
        if item[0][0] == "[":  # epic
            return 0
        elif item[0][0] == ".":  # rare
            return 1
        else:
            return 2  # common / normal

    def _sort_new_backpack(self, backpack: dict):
        tmp = {}
        for item in backpack:
            slots = backpack[item].slot
            if len(slots) == 1:
                slot_name = slots[0]
            else:
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

    def __backpack__(self, forging : bool=False, consumed : list=[]):
        bkpk = self._sort_new_backpack(self.backpack)
        form_string = "Items in Backpack:"
        consumed_list = [i for i in consumed]
        for slot_group in bkpk:

            slot_name = slot_group[0][1].slot
            slot_name = slot_name[0] if len(slot_name) < 2 else "two handed"
            form_string += f"\n\n {slot_name.title()} slot"
            rjust = max([len(str(i[0])) for i in slot_group])
            for item in slot_group:
                if forging and ("{.:" in item[0] or item[0] in consumed_list):
                    continue
                form_string += (
                    f'\n  - {item[0]:<{rjust}} - (ATT: {item[1].att} | DPL: {item[1].cha})'
                )

        return form_string + "\n"

    def _equip_item(self, item: Item, from_backpack:bool=True):
        """This handles moving an item from backpack to equipment"""
        current = getattr(self, item.slot[0])
        if current:
            olditem = copy(current)
            self.att -= olditem.att
            self.cha -= olditem.cha
            if len(olditem.slot) == 2:
                self.att -= olditem.att
                self.cha -= olditem.cha
            if olditem in self.backpack:
                self.backpack[olditem.name].owned += 1
            else:
                self.backpack[olditem.name] = olditem
        self.att += item.att
        self.cha += item.cha
        setattr(self, item.slot[0], item)
        if len(item.slot) == 2:
            self.att += item.att
            self.cha += item.cha
            setattr(self, item.slot[1], item)

    @classmethod
    async def _from_json(cls, config : Config, user : discord.Member):
        """Return a Character object from config and user"""
        data = await config.user(user).all()
        balance = await bank.get_balance(user)
        equipment = {k:Item._from_json(v) if v else None for k,v in data["items"].items() if k != "backpack"}
        loadouts = data["loadouts"]
        backpack = {n:Item._from_json({n:i}) for n, i in data["items"]["backpack"].items()}
        hero_data = {
            "exp": data["exp"],
            "lvl": data["lvl"],
            "att": data["att"],
            "cha": data["cha"],
            "treasure": data["treasure"],
            "backpack": backpack,
            "loadouts": loadouts,
            "heroclass": data["class"],
            "skill": data["skill"],
            "bal": balance,
            "user": user,
        }
        for k, v in equipment.items():
            hero_data[k] = v
        return cls(**hero_data)

    def _to_json(self) -> dict:
        return {
            "exp": self.exp,
            "lvl": self.lvl,
            "att": self.att,
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

            "backpack": {n:i._to_json() for n, i in self.backpack.items()},
            "loadouts": {n:l._to_json() for n, l in self.loadouts.items()}, # convert to dict of items
            "heroclass": self.heroclass,
            "skill": self.skill,
        }