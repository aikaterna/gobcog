from typing import List, TypedDict


class MiniBoss(TypedDict):
    requirements: List[str]
    defeat: str
    special: str


class Monster(TypedDict):
    hp: int
    pdef: float
    mdef: float
    dipl: int
    image: str
    boss: bool
    miniboss: MiniBoss
    color: str
