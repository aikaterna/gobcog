from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Literal, MutableMapping, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

if TYPE_CHECKING:
    from .adventureset import TaxesConverter
    from .charsheet import BackpackFilterParser, Character
    from .converters import (
        DayConverter,
        EquipableItemConverter,
        EquipmentConverter,
        ItemConverter,
        ItemsConverter,
        PercentageConverter,
        RarityConverter,
        SlotConverter,
        Stats,
        ThemeSetMonterConverter,
        ThemeSetPetConverter,
    )
    from .game_session import GameSession


class AdventureMixin(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.
    """

    def __init__(self, *_args):
        self.config: Config
        self.bot: Red
        self.settings: Dict[Any, Any]
        self._ready: asyncio.Event
        self._adventure_countdown: dict
        self._rewards: dict
        self._reward_message: dict
        self._loss_message = {}
        self._trader_countdown = {}
        self._current_traders = {}
        self._curent_trader_stock = {}
        self._sessions: MutableMapping[int, GameSession] = {}
        self._react_messaged = []
        self.tasks = {}
        self.locks: MutableMapping[int, asyncio.Lock] = {}
        self.gb_task = None

        self.RAISINS: list = None
        self.THREATEE: list = None
        self.TR_GEAR_SET: dict = None
        self.ATTRIBS: dict = None
        self.MONSTERS: dict = None
        self.AS_MONSTERS: dict = None
        self.MONSTER_NOW: dict = None
        self.LOCATIONS: list = None
        self.PETS: dict = None

    #######################################################################
    # adventure.py                                                        #
    #######################################################################

    @abstractmethod
    async def _clear_react(self, msg: discord.Message):
        raise NotImplementedError()

    @abstractmethod
    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord", "owner", "user", "user_strict"],
        user_id: int,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def cog_before_invoke(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def initialize(self):
        raise NotImplementedError()

    @abstractmethod
    async def cleanup_tasks(self):
        raise NotImplementedError()

    @abstractmethod
    async def _migrate_config(self, from_version: int, to_version: int) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def allow_in_dm(self, ctx):
        raise NotImplementedError()

    @abstractmethod
    async def _garbage_collection(self):
        raise NotImplementedError()

    @abstractmethod
    async def _adventure(self, ctx: commands.Context, *, challenge=None):
        raise NotImplementedError()

    @abstractmethod
    async def _error_handler(self, ctx: commands.Context, error: Exception) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_challenge(self, ctx: commands.Context, monsters):
        raise NotImplementedError()

    @abstractmethod
    async def update_monster_roster(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _simple(self, ctx: commands.Context, adventure_msg, challenge: str = None, attribute: str = None):
        raise NotImplementedError()

    @abstractmethod
    async def _choice(self, ctx: commands.Context, adventure_msg):
        raise NotImplementedError()

    @abstractmethod
    async def has_perm(self, user: Union[discord.Member, discord.User]):
        raise NotImplementedError()

    @abstractmethod
    async def on_reaction_add(self, reaction, user):
        raise NotImplementedError()

    @abstractmethod
    async def _handle_adventure(self, reaction: discord.Reaction, user: discord.Member):
        raise NotImplementedError()

    @abstractmethod
    async def _result(self, ctx: commands.Context, message: discord.Message):
        raise NotImplementedError()

    @abstractmethod
    async def handle_run(self, guild_id, attack, diplomacy, magic, shame=False):
        raise NotImplementedError()

    @abstractmethod
    async def handle_fight(self, guild_id, fumblelist, critlist, attack, magic):
        raise NotImplementedError()

    @abstractmethod
    async def handle_pray(self, guild_id, fumblelist, attack, diplomacy, magic):
        raise NotImplementedError()

    @abstractmethod
    async def handle_talk(self, guild_id, fumblelist, critlist, diplomacy):
        raise NotImplementedError()

    @abstractmethod
    async def handle_basilisk(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _add_rewards(self, ctx: commands.Context, user, exp, cp, special):
        raise NotImplementedError()

    @abstractmethod
    async def _adv_countdown(self, ctx: commands.Context, seconds, title) -> asyncio.Task:
        raise NotImplementedError()

    @abstractmethod
    async def _cart_countdown(self, ctx: commands.Context, seconds, title, room=None) -> asyncio.Task:
        raise NotImplementedError()

    @abstractmethod
    async def _data_check(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def on_message_without_command(self, message):
        raise NotImplementedError()

    @abstractmethod
    async def _roll_chest(self, chest_type: str, c: Character):
        raise NotImplementedError()

    @abstractmethod
    async def _reward(self, ctx: commands.Context, userlist, amount, modif, special):
        raise NotImplementedError()

    #######################################################################
    # adventureset.py                                                     #
    #######################################################################

    @abstractmethod
    async def adventureset(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def rebirthcost(self, ctx: commands.Context, percentage: float):
        raise NotImplementedError()

    @abstractmethod
    async def cartroom(self, ctx: commands.Context, room: discord.TextChannel = None):
        raise NotImplementedError()

    @abstractmethod
    async def adventureset_locks(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def adventureset_locks_user(self, ctx: commands.Context, users: commands.Greedy[discord.User]):
        raise NotImplementedError()

    @abstractmethod
    async def adventureset_daily_bonus(self, ctx: commands.Context, day: DayConverter, percentage: PercentageConverter):
        raise NotImplementedError()

    @abstractmethod
    async def adventureset_locks_adventure(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def restrict(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def easymode(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def sepcurrency(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def commands_adventureset_economy(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def commands_adventureset_economy_tax(self, ctx: commands.Context, *, taxes: TaxesConverter):
        raise NotImplementedError()

    @abstractmethod
    async def commands_adventureset_economy_conversion_rate(self, ctx: commands.Context, rate_in: int, rate_out: int):
        raise NotImplementedError()

    @abstractmethod
    async def commands_adventureset_economy_maxwithdraw(self, ctx: commands.Context, *, amount: int):
        raise NotImplementedError()

    @abstractmethod
    async def commands_adventureset_economy_withdraw(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def advcooldown(self, ctx: commands.Context, *, time_in_seconds: int):
        raise NotImplementedError()

    @abstractmethod
    async def version(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def god(self, ctx: commands.Context, *, name):
        raise NotImplementedError()

    @abstractmethod
    async def globalgod(self, ctx: commands.Context, *, name):
        raise NotImplementedError()

    @abstractmethod
    async def embeds(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def cartchests(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def cartname(self, ctx: commands.Context, *, name):
        raise NotImplementedError()

    @abstractmethod
    async def carttime(self, ctx: commands.Context, *, time: str):
        raise NotImplementedError()

    @abstractmethod
    async def clear_user(self, ctx: commands.Context, users: commands.Greedy[discord.User]):
        raise NotImplementedError()

    @abstractmethod
    async def remove_item(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], *, full_item_name: str
    ):
        raise NotImplementedError()

    @abstractmethod
    async def globalcartname(self, ctx: commands.Context, *, name):
        raise NotImplementedError()

    @abstractmethod
    async def theme(self, ctx: commands.Context, *, theme):
        raise NotImplementedError()

    @abstractmethod
    async def cart(self, ctx: commands.Context, *, channel: discord.TextChannel = None):
        raise NotImplementedError()

    @abstractmethod
    async def adventuresettings(self, ctx: commands.Context):
        raise NotImplementedError()

    #######################################################################
    # backpack.py                                                         #
    #######################################################################

    @abstractmethod
    async def _backpack(
        self,
        ctx: commands.Context,
        show_diff: Optional[bool] = False,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_equip(self, ctx: commands.Context, *, equip_item: EquipableItemConverter):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_eset(self, ctx: commands.Context, *, set_name: str):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_disassemble(self, ctx: commands.Context, *, backpack_items: ItemsConverter):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_sellall(
        self,
        ctx: commands.Context,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_sell(self, ctx: commands.Context, *, item: ItemConverter):
        raise NotImplementedError()

    @abstractmethod
    async def _backpack_sell_button_action(self, ctx, emoji, page, item, price_shown, character):
        raise NotImplementedError()

    @abstractmethod
    async def backpack_trade(
        self,
        ctx: commands.Context,
        buyer: discord.Member,
        asking: Optional[int] = 1000,
        *,
        item: ItemConverter,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def commands_equipable_backpack(
        self,
        ctx: commands.Context,
        show_diff: Optional[bool] = False,
        rarity: Optional[RarityConverter] = None,
        *,
        slot: Optional[SlotConverter] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def commands_cbackpack(
        self,
        ctx: commands.Context,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def commands_cbackpack_show(
        self,
        ctx: commands.Context,
        *,
        query: BackpackFilterParser,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def commands_cbackpack_disassemble(self, ctx: commands.Context, *, query: BackpackFilterParser):
        raise NotImplementedError()

    @abstractmethod
    async def commands_cbackpack_sell(self, ctx: commands.Context, *, query: BackpackFilterParser):
        raise NotImplementedError()

    #######################################################################
    # cart.py                                                             #
    #######################################################################

    @abstractmethod
    async def _handle_cart(self, reaction: discord.Reaction, user: discord.Member):
        raise NotImplementedError()

    @abstractmethod
    async def _trader(self, ctx: commands.Context, bypass=False):
        raise NotImplementedError()

    @abstractmethod
    async def _trader_get_items(self, howmany: int):
        raise NotImplementedError()

    #######################################################################
    # character.py                                                        #
    #######################################################################

    @abstractmethod
    async def skill(self, ctx: commands.Context, spend: str = None, amount: int = 1):
        raise NotImplementedError()

    @abstractmethod
    async def set_show(self, ctx: commands.Context, *, set_name: str = None):
        raise NotImplementedError()

    @abstractmethod
    async def stats(self, ctx: commands.Context, *, user: Union[discord.Member, discord.User] = None):
        raise NotImplementedError()

    @abstractmethod
    async def _build_loadout_display(
        self, ctx: commands.Context, userdata, loadout=True, rebirths: int = None, index: int = None
    ):
        raise NotImplementedError()

    @abstractmethod
    async def unequip(self, ctx: commands.Context, *, item: EquipmentConverter):
        raise NotImplementedError()

    @abstractmethod
    async def equip(self, ctx: commands.Context, *, item: EquipableItemConverter):
        raise NotImplementedError()

    #######################################################################
    # class_abilities.py                                                  #
    #######################################################################

    @abstractmethod
    async def heroclass(self, ctx: commands.Context, clz: str = None, action: str = None):
        raise NotImplementedError()

    @abstractmethod
    async def pet(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _forage(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _free(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def bless(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def insight(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def rage(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def focus(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def music(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def forge(self, ctx):
        raise NotImplementedError()

    @abstractmethod
    async def _to_forge(self, ctx: commands.Context, consumed, character):
        raise NotImplementedError()

    #######################################################################
    # dev.py                                                              #
    #######################################################################

    @abstractmethod
    async def no_dev_prompt(ctx: commands.Context) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def _devcooldown(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def makecart(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _genitem(self, ctx: commands.Context, rarity: str = None, slot: str = None):
        raise NotImplementedError()

    @abstractmethod
    async def genitems(self, ctx: commands.Context, rarity: str, slot: str, num: int = 1):
        raise NotImplementedError()

    @abstractmethod
    async def copyuser(self, ctx: commands.Context, user_id: int):
        raise NotImplementedError()

    @abstractmethod
    async def devrebirth(
        self,
        ctx: commands.Context,
        rebirth_level: int = 1,
        character_level: int = 1,
        users: commands.Greedy[discord.Member] = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def devreset(self, ctx: commands.Context, users: commands.Greedy[Union[discord.Member, discord.User]]):
        raise NotImplementedError()

    @abstractmethod
    async def _adventurestats(self, ctx: commands.Context):
        raise NotImplementedError()

    #######################################################################
    # economy.py                                                          #
    #######################################################################

    @abstractmethod
    async def commands_atransfer(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def commands_atransfer_deposit(self, ctx: commands.Context, *, amount: int):
        raise NotImplementedError()

    @abstractmethod
    async def commands_atransfer_withdraw(self, ctx: commands.Context, *, amount: int):
        raise NotImplementedError()

    @abstractmethod
    async def commands_atransfer_player(self, ctx: commands.Context, amount: int, *, player: discord.Member):
        raise NotImplementedError()

    @abstractmethod
    async def commands_atransfer_give(self, ctx: commands.Context, amount: int, *players: discord.Member):
        raise NotImplementedError()

    @abstractmethod
    async def commands_mysets(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def commands_apayday(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def give(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def _give_item(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User], item_name: str, *, stats: Stats
    ):
        raise NotImplementedError()

    @abstractmethod
    async def _give_loot(
        self,
        ctx: commands.Context,
        loot_type: str,
        users: commands.Greedy[Union[discord.Member, discord.User]] = None,
        number: int = 1,
    ):
        raise NotImplementedError()

    #######################################################################
    # adventure/leaderboards.py                                           #
    #######################################################################

    @abstractmethod
    async def get_leaderboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        raise NotImplementedError()

    @abstractmethod
    async def aleaderboard(self, ctx: commands.Context, show_global: bool = False):
        raise NotImplementedError()

    @abstractmethod
    async def get_global_scoreboard(
        self, positions: int = None, guild: discord.Guild = None, keyword: str = None
    ) -> List[tuple]:
        raise NotImplementedError()

    @abstractmethod
    async def get_global_negaverse_scoreboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        raise NotImplementedError()

    @abstractmethod
    async def scoreboard(self, ctx: commands.Context, show_global: bool = False):
        raise NotImplementedError()

    @abstractmethod
    async def nvsb(self, ctx: commands.Context, show_global: bool = False):
        raise NotImplementedError()

    @abstractmethod
    async def wscoreboard(self, ctx: commands.Context, show_global: bool = False):
        raise NotImplementedError()

    @abstractmethod
    async def get_weekly_scoreboard(self, positions: int = None, guild: discord.Guild = None) -> List[tuple]:
        raise NotImplementedError()

    #######################################################################
    # loadouts.py                                                         #
    #######################################################################

    @abstractmethod
    async def loadout(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def save_loadout(self, ctx: commands.Context, name: str):
        raise NotImplementedError()

    @abstractmethod
    async def remove_loadout(self, ctx: commands.Context, name: str):
        raise NotImplementedError()

    @abstractmethod
    async def show_loadout(self, ctx: commands.Context, name: str = None):
        raise NotImplementedError()

    @abstractmethod
    async def equip_loadout(self, ctx: commands.Context, name: str):
        raise NotImplementedError()

    #######################################################################
    # loot.py                                                             #
    #######################################################################

    @abstractmethod
    async def loot(self, ctx: commands.Context, box_type: str = None, number: int = 1):
        raise NotImplementedError()

    @abstractmethod
    async def convert(self, ctx: commands.Context, box_rarity: str, amount: int = 1):
        raise NotImplementedError()

    @abstractmethod
    async def _open_chests(
        self,
        ctx: commands.Context,
        chest_type: str,
        amount: int,
        character: Character,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def _open_chest(self, ctx: commands.Context, user, chest_type, character):
        raise NotImplementedError()

    #######################################################################
    # negaverse.py                                                        #
    #######################################################################

    @abstractmethod
    async def _negaverse(
        self,
        ctx: commands.Context,
        offering: int = None,
        roll: Optional[int] = -1,
        nega: Union[discord.Member, discord.User] = None,
    ):
        raise NotImplementedError()

    #######################################################################
    # rebirth.py                                                          #
    #######################################################################

    @abstractmethod
    async def rebirth(self, ctx: commands.Context):
        raise NotImplementedError()

    #######################################################################
    # themeset.py                                                         #
    #######################################################################

    @abstractmethod
    async def themeset(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_add(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_add_monster(self, ctx: commands.Context, *, theme_data: ThemeSetMonterConverter):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_add_pet(self, ctx: commands.Context, *, pet_data: ThemeSetPetConverter):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_delete(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_delete_monster(self, ctx: commands.Context, theme: str, *, monster: str):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_delete_pet(self, ctx: commands.Context, theme: str, *, pet: str):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_list(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_list_monster(self, ctx: commands.Context, *, theme: str):
        raise NotImplementedError()

    @abstractmethod
    async def themeset_list_pet(self, ctx: commands.Context, *, theme: str):
        raise NotImplementedError()
