from __future__ import annotations

import random

from .adventureresult import StatRange


class Random(random.Random):
    """
    This is a simple subclass of python's Random class to store the initial seed
    so we can extract it later.

    This could later be used to adjust rng in some way if we want.
    For now we just want determinism and reproducability.
    """

    def __init__(self, seed: GameSeed):
        self.internal_seed = seed
        super().__init__(int(seed))


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

    TIMESTAMP_SHIFT = 38
    # This number should always be a multiple of 2
    HP_SHIFT = TIMESTAMP_SHIFT - 1
    # Since this is essentially true or false for hp or dipl just 1 bit is needed
    MIN_STAT_SHIFT = HP_SHIFT - 14
    MAX_STAT_SHIFT = MIN_STAT_SHIFT - 14
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
        max_s = self.max_stat() << self.MAX_STAT_SHIFT
        win_pct = round(self.win_pct() * 100)
        # Python doesn't like converting some values to a float and casting to int
        # will cause it to round down even though it should round up
        ret += hp + min_s + max_s + win_pct
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

    def win_pct(self):
        return self.stat_range.win_percent

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
        max_stat = number >> cls.MAX_STAT_SHIFT

        number ^= max_stat << cls.MAX_STAT_SHIFT
        win_percent = number / 100
        # Leaving us with just the max stat as the last 10 bits of data
        stat_type = "hp" if hp_or_diplo else "dipl"
        stats = StatRange(stat_type=stat_type, min_stat=min_stat, max_stat=max_stat, win_percent=win_percent)
        return cls(message_id, stats)
