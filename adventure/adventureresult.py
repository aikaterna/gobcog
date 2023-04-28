import logging
from typing import List, MutableMapping

from redbot.core import commands

log = logging.getLogger("red.cogs.adventure")


class AdventureResults:
    """Object to store recent adventure results."""

    def __init__(self, num_raids):
        self._num_raids = num_raids
        self._last_raids: MutableMapping[int, List] = {}

    def add_result(self, ctx: commands.Context, main_action, amount, num_ppl, success):
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
            if ctx.guild.id in self._last_raids:
                self._last_raids[ctx.guild.id].pop(0)
        raid_dict = {}
        for var in ("main_action", "amount", "num_ppl", "success"):
            raid_dict[var] = locals()[var]
        self._last_raids[ctx.guild.id].append(raid_dict)

    def get_stat_range(self, ctx: commands.Context):
        """Return reasonable stat range for monster pool to have based
        on last few raids' damage.

        :returns: Dict with stat_type, min_stat and max_stat.
        """
        # how much % to increase damage for solo raiders so that they
        # can't just solo every monster based on their own average
        # damage
        if ctx.guild.id not in self._last_raids:
            self._last_raids[ctx.guild.id] = []
        SOLO_RAID_SCALE = 0.25
        if len(self._last_raids.get(ctx.guild.id, [])) == 0:
            return {"stat_type": "hp", "min_stat": 0, "max_stat": 0, "win_percent": 0}

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

        stats_dict = {}
        for var in ("stat_type", "min_stat", "max_stat", "win_percent"):
            stats_dict[var] = locals()[var]
        return stats_dict

    def __str__(self):
        return str(self._last_raids)
