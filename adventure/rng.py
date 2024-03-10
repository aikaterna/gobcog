import random

from .adventureresult import GameSeed


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
