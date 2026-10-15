"""Replay-compatible seven-bag generator for explicitly configured seeds.

MINSTD and rainbow input ordering are described in the community's direct
client reference: github.com/lemoncove/tetrio-bot-docs/Piece_RNG.md.
Live use is gated on matching the observed current piece and all Nexts.
"""


def seeded_queue(seed, count=700):
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("练习种子必须是整数。")
    state = seed % 2147483647
    if state <= 0:
        state += 2147483646
    result = []
    while len(result) < count:
        bag = list("ZLOSIJT")
        for index in range(6, 0, -1):
            state = state * 16807 % 2147483647
            pick = ((state - 1) * (index + 1)) // 2147483646
            bag[index], bag[pick] = bag[pick], bag[index]
        result.extend(bag)
    return "".join(result[:count])
