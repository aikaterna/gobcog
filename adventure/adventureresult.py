from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Literal, MutableMapping, TypedDict

from redbot.core import commands

log = logging.getLogger("red.cogs.adventure")


@dataclass
class StatRange:
    stat_type: Literal["hp", "dipl"]
    min_stat: float
    max_stat: float
    win_percent: float

    def __getitem__(self, name: str):
        return getattr(self, name)

    def get(self, name: str, default=None):
        return getattr(self, name, default)


class GameSeed:
    """
    This class represents a game Seed.
    It takes a message ID and a StatRange and provides an integer to be used
    for random number generation.
    This seed encodes the min and max stat range to reduce the pool size of monsters
    which is critical to making the monster RNG deterministic based on some seed.

    The premise is similar to discord unique ID's. Encoding a timestamp after 30 bits.
    The 21st bit contains whether to prefer hp or diplomacy for the monster stats.
    The next 20 bits contain the min and max. These are limited to 16383 bits.
    Since the base monsters cap at 560 stat this should be good enough.
    Custom monsters with higher stats will break this if they go above 16383.
    """

    TIMESTAMP_SHIFT = 30
    # This number should always be a multiple of 2
    HP_SHIFT = TIMESTAMP_SHIFT - 1
    # Since this is essentially true or false for hp or dipl just 1 bit is needed
    MIN_STAT_SHIFT = HP_SHIFT // 2
    # We want to encode the min and max stat within half of what is left
    # all of these variables are included to more easily adjust this
    # If any value is changed past adventure results RNG will differ

    def __init__(self, message_id: int, stats: StatRange):
        self.stat_range = stats
        self.message_id = message_id

    def __int__(self):
        ret = self.timestamp() << self.TIMESTAMP_SHIFT
        # Store the timestamp in the same place as discord leaving 22 bits left
        hp = self.hp_or_diplo() << self.HP_SHIFT
        # Store whether or not to prefer hp or dipl as the 21st bit
        min_s = self.min_stat() << self.MIN_STAT_SHIFT
        # Store the min stat 10 bits in leaving the last 10 bits for the max stat
        max_s = self.max_stat()
        ret += hp + min_s + max_s
        return ret

    def __index__(self):
        return int(self)

    def hp_or_diplo(self):
        return 1 if self.stat_range.stat_type == "hp" else 0

    def min_stat(self):
        return max(int(self.stat_range.min_stat), 0)

    def max_stat(self):
        return min(int(self.stat_range.max_stat), 16383)

    def timestamp(self):
        # Strip the timestamp from the message ID
        return self.message_id >> self.TIMESTAMP_SHIFT

    @classmethod
    def from_int(cls, number: int) -> GameSeed:

        message_id = number >> cls.TIMESTAMP_SHIFT
        # strip the stats data
        number ^= message_id << cls.TIMESTAMP_SHIFT

        message_id = message_id << cls.TIMESTAMP_SHIFT
        # xor the timestamp to get the remaining stats
        hp_or_diplo = number >> cls.HP_SHIFT
        # strip the min and max stats to get whether to prioritize hp or dipl
        number ^= hp_or_diplo << cls.HP_SHIFT
        # xor the hp value to get just min and max
        min_stat = number >> cls.MIN_STAT_SHIFT
        # Strip the min stat from the data
        number ^= min_stat << cls.MIN_STAT_SHIFT
        max_stat = number
        # Leaving us with just the max stat as the last 10 bits of data
        stat_type = "hp" if hp_or_diplo else "dipl"
        stats = StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=0.0)
        return cls(message_id, stats)


class Raid(TypedDict):
    main_action: str
    amount: float
    num_ppl: int
    success: bool


class AdventureResults:
    """Object to store recent adventure results."""

    def __init__(self, num_raids: int):
        self._num_raids: int = num_raids
        self._last_raids: MutableMapping[int, List[Raid]] = {}

    def add_result(self, ctx: commands.Context, main_action: str, amount: float, num_ppl: int, success: bool):
        """Add result to this object.
        :main_action: Main damage action taken by the adventurers
            (highest amount dealt). Should be either "attack" or
            "talk". Running will just be notated by a 0 amount.
        :amount: Amount dealt.
        :num_ppl: Number of people in adventure.
        :success: Whether adventure was successful or not.
        """
        if ctx.guild.id not in self._last_raids:
            self._last_raids[ctx.guild.id] = []

        if len(self._last_raids.get(ctx.guild.id, [])) >= self._num_raids:
            try:
                self._last_raids[ctx.guild.id].pop(0)
            except IndexError:
                pass

        self._last_raids[ctx.guild.id].append(
            Raid(main_action=main_action, amount=amount, num_ppl=num_ppl, success=success)
        )

    def get_stat_range(self, ctx: commands.Context) -> StatRange:
        """Return reasonable stat range for monster pool to have based
        on last few raids' damage.

        :returns: Dict with stat_type, min_stat and max_stat.
        """
        # how much % to increase damage for solo raiders so that they
        # can't just solo every monster based on their own average
        # damage
        if ctx.guild.id not in self._last_raids:
            self._last_raids[ctx.guild.id] = []
        SOLO_RAID_SCALE: float = 0.25
        min_stat: float = 0.0
        max_stat: float = 0.0
        stat_type: str = "hp"
        win_percent: float = 0.0
        if len(self._last_raids.get(ctx.guild.id, [])) == 0:
            return StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=win_percent)

        # tally up stats for raids
        num_attack = 0
        dmg_amount = 0
        num_talk = 0
        talk_amount = 0
        num_wins = 0
        stat_type = "hp"
        avg_amount = 0
        raids = self._last_raids.get(ctx.guild.id, [])
        raid_count = len(raids)
        if raid_count == 0:
            num_wins = self._num_raids // 2
            raid_count = self._num_raids
            win_percent = 0.5
        else:
            for raid in raids:
                if raid["main_action"] == "attack":
                    num_attack += 1
                    dmg_amount += raid["amount"]
                    if raid["num_ppl"] == 1:
                        dmg_amount += raid["amount"] * SOLO_RAID_SCALE
                else:
                    num_talk += 1
                    talk_amount += raid["amount"]
                    if raid["num_ppl"] == 1:
                        talk_amount += raid["amount"] * SOLO_RAID_SCALE
                log.debug(f"raid dmg: {raid['amount']}")
                if raid["success"]:
                    num_wins += 1
            if num_attack > 0:
                avg_amount = dmg_amount / num_attack
            if dmg_amount < talk_amount:
                stat_type = "dipl"
                avg_amount = talk_amount / num_talk
            win_percent = num_wins / raid_count
            min_stat = avg_amount * 0.75
            max_stat = avg_amount * 2
            # want win % to be at least 50%, even when solo
            # if win % is below 50%, scale back min/max for easier mons
            if win_percent < 0.5:
                min_stat = avg_amount * win_percent
                max_stat = avg_amount * 1.5
        return StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=win_percent)

    def __str__(self):
        return str(self._last_raids)
