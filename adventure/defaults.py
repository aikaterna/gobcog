default_user = {
    "exp": 0,
    "lvl": 1,
    "att": 0,
    "cha": 0,
    "int": 0,
    "last_skill_reset": 0,
    "last_known_currency": 0,
    "last_currency_check": 0,
    "treasure": [0, 0, 0, 0, 0, 0],
    "items": {
        "head": {},
        "neck": {},
        "chest": {},
        "gloves": {},
        "belt": {},
        "legs": {},
        "boots": {},
        "left": {},
        "right": {},
        "ring": {},
        "charm": {},
        "backpack": {},
    },
    "loadouts": {},
    "class": {
        "name": "Hero",
        "ability": False,
        "desc": "Your basic adventuring hero.",
        "cooldown": 0,
    },
    "skill": {"pool": 0, "att": 0, "cha": 0, "int": 0},
    "adventures": {
        "wins": 0,
        "loses": 0,
        "fight": 0,
        "spell": 0,
        "talk": 0,
        "pray": 0,
        "run": 0,
        "fumbles": 0,
    },
    "nega": {
        "wins": 0,
        "loses": 0,
        "xp__earnings": 0,
        "gold__losses": 0,
    },
}

default_guild = {
    "cart_channels": [],
    "god_name": "",
    "cart_name": "",
    "embed": True,
    "cooldown": 0,
    "cartroom": None,
    "cart_timeout": 10800,
    "cooldown_timer_manual": 120,
    "rebirth_cost": 100.0,
    "disallow_withdraw": True,
    "max_allowed_withdraw": 50000,
}
default_global = {
    "god_name": "Herbert",
    "cart_name": "Hawl's brother",
    "theme": "default",
    "restrict": False,
    "embed": True,
    "enable_chests": True,
    "currentweek": 0,
    "schema_version": 1,
    "rebirth_cost": 100.0,
    "themes": {},
    "daily_bonus": {"1": 0, "2": 0, "3": 0.5, "4": 0, "5": 0.5, "6": 1.0, "7": 1.0},
    "tax_brackets": {},
    "separate_economy": True,
    "to_conversion_rate": 10,
    "from_conversion_rate": 11,
    "max_allowed_withdraw": 50000,
    "disallow_withdraw": False,
    "easy_mode": False,
    "reset_by_age": -1,
    "results_length": 20,
}
