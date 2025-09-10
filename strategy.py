from typing import Tuple

# Actions
HIT = "HIT"
STAND = "STAND"
DOUBLE = "DOUBLE"
SPLIT = "SPLIT"


def _is_ace(c: str) -> bool:
    return c.upper() == "A"


def _card_value(c: str) -> int:
    if _is_ace(c):
        return 11
    try:
        return int(c)
    except Exception:
        return 10


def _is_pair(player: Tuple[str, str]) -> bool:
    a, b = player
    return a == b


def _is_soft(player: Tuple[str, str]) -> bool:
    a, b = player
    return _is_ace(a) ^ _is_ace(b)  # exactly one ace


def _hard_total(player: Tuple[str, str]) -> int:
    a, b = player
    if _is_ace(a) and _is_ace(b):
        return 12  # treat A,A as soft pair; will be handled in pair branch
    va, vb = _card_value(a), _card_value(b)
    total = va + vb
    # Convert soft to hard if needed
    if _is_soft(player) and total > 21:
        total -= 10
    return total


def _dealer_val(upcard: str) -> int:
    return 11 if _is_ace(upcard) else int(upcard)


def _pair_action(r: str, dealer: str, *, das: bool) -> str:
    # Basic strategy (multi-deck, S17, DAS-aware). No surrender.
    d = dealer
    dv = _dealer_val(d)
    if r == "A":
        return SPLIT
    if r == "10":
        return STAND
    if r == "9":
        # Split vs 2-6 or 8-9; stand vs 7,10,A
        if 2 <= dv <= 6 or dv in (8, 9):
            return SPLIT
        return STAND
    if r == "8":
        return SPLIT
    if r == "7":
        return SPLIT if 2 <= dv <= 7 else HIT
    if r == "6":
        # Split 6s vs 3-6; with DAS also split vs 2
        if 3 <= dv <= 6 or (das and dv == 2):
            return SPLIT
        return HIT
    if r == "5":
        # Never split 5s; treat as hard 10
        return DOUBLE if 2 <= dv <= 9 else HIT
    if r == "4":
        # Split 4s only if DAS and dealer 5 or 6
        if das and dv in (5, 6):
            return SPLIT
        return HIT
    if r in ("2", "3"):
        # Split 2s/3s vs 4-7; with DAS also vs 2-3
        if 4 <= dv <= 7 or (das and dv in (2, 3)):
            return SPLIT
        return HIT
    # Fallback
    return HIT


def _soft_action(non_ace: str, dealer: str) -> str:
    # non_ace is 2..9 for A,non_ace hands
    dv = _dealer_val(dealer)
    v = int(non_ace)
    # Soft 19-20: stand
    if v >= 9:  # A,9
        return STAND
    if v == 8:  # A,8
        return STAND
    if v == 7:  # A,7 (soft 18)
        if 3 <= dv <= 6:
            return DOUBLE
        if dv in (2, 7, 8):
            return STAND
        return HIT
    if v == 6:  # A,6 (soft 17)
        return DOUBLE if 3 <= dv <= 6 else HIT
    if v == 5:  # A,5 (soft 16)
        return DOUBLE if 4 <= dv <= 6 else HIT
    if v in (3, 4):
        # Soft 14/15: double vs 5-6, else hit
        return DOUBLE if 5 <= dv <= 6 else HIT
    if v in (2,):
        # Soft 13: double vs 5-6, else hit
        return DOUBLE if 5 <= dv <= 6 else HIT
    # Fallback
    return HIT


def _hard_action(total: int, dealer: str, *, double_11_vs_ace: bool) -> str:
    dv = _dealer_val(dealer)
    if total >= 17:
        return STAND
    if total >= 13:
        return STAND if 2 <= dv <= 6 else HIT
    if total == 12:
        return STAND if 4 <= dv <= 6 else HIT
    if total == 11:
        if dv == 11:
            return DOUBLE if double_11_vs_ace else HIT
        return DOUBLE
    if total == 10:
        return DOUBLE if 2 <= dv <= 9 else HIT
    if total == 9:
        return DOUBLE if 3 <= dv <= 6 else HIT
    return HIT  # 5-8


def basic_strategy_action(
    player: Tuple[str, str],
    dealer: str,
    *,
    s17: bool = True,
    das: bool = True,
    double_11_vs_ace: bool = False,
) -> str:
    """Return optimal basic-strategy action for initial two-card hand.

    Assumptions:
      - Multi-deck shoe
      - s17: dealer stands on soft 17 if True (only affects a few edges; not used here)
      - das: double after split allowed
      - double_11_vs_ace: whether to double hard 11 against dealer Ace
    """
    a, b = player
    # Normalize rank strings
    a, b, dealer = a.upper(), b.upper(), dealer.upper()

    # Pairs
    if _is_pair((a, b)):
        return _pair_action(a, dealer, das=das)

    # Soft totals (A,x)
    if _is_soft((a, b)):
        non_ace = b if _is_ace(a) else a
        return _soft_action(non_ace, dealer)

    # Hard totals
    total = _hard_total((a, b))
    return _hard_action(total, dealer, double_11_vs_ace=double_11_vs_ace)


def policy_action_general(
    cards: list[str],
    dealer: str,
    *,
    s17: bool = True,
    das: bool = True,
    double_11_vs_ace: bool = False,
) -> str:
    """Basic-strategy-like policy for arbitrary hand sizes.

    - Split considered only for exactly two cards of same rank.
    - Double allowed only for exactly two cards; after split allowed per `das`.
    - Otherwise falls back to soft/hard rules.
    """
    cards = [c.upper() for c in cards]
    dealer = dealer.upper()
    if len(cards) == 2 and cards[0] == cards[1]:
        return _pair_action(cards[0], dealer, das=das)

    # Identify soft/hard
    has_ace = any(_is_ace(c) for c in cards)
    total = sum(_card_value(c) for c in cards)
    while total > 21 and has_ace and any(_is_ace(c) for c in cards):
        # reduce one ace from 11 to 1
        total -= 10
        # break only if more than one ace? Loop suffices.
        if total <= 21:
            break

    if has_ace and total <= 21 and (11 in [_card_value(c) for c in cards]):
        # treat as soft if an ace counted as 11
        # derive non-ace value for soft decision: total - 11
        non_ace_val = total - 11
        if non_ace_val <= 0:
            non_ace_val = 2
        if len(cards) == 2:
            # Two-card soft cases match initial chart closely
            return _soft_action(str(non_ace_val), dealer)
        # For 3+ card soft totals, use similar rules
        return _soft_action(str(min(9, max(2, non_ace_val))), dealer)

    # Hard total
    if len(cards) == 2:
        return _hard_action(total, dealer, double_11_vs_ace=double_11_vs_ace)
    # For 3+ cards, use same thresholds
    return _hard_action(total, dealer, double_11_vs_ace=double_11_vs_ace)
