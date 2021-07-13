from datetime import datetime
from typing import List, Mapping, MutableMapping, Set, Tuple

import discord
from redbot.core.commands import Context

from .charsheet import Character

# This is split into its own file for future buttons usage
# We will have game sessions inherit discord.ui.View and then we can send a message
# with the buttons required. For now this will sit in its own file.


class GameSession:
    """A class to represent and hold current game sessions per server."""

    ctx: Context
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
        self.ctx: Context = kwargs.pop("ctx")
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
