import verifiers as vf
from typing import List, Dict, Tuple, Any
import random
import copy
import re
from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    # Optional: use Hugging Face datasets if available for convenience
    from datasets import Dataset as HFDataset
except Exception:  # pragma: no cover - optional dependency at runtime
    HFDataset = None  # type: ignore

# Support import both as a package and as standalone module
try:  # when imported as a package module (environments.blackjack_env)
    from . import strategy  # type: ignore
except Exception:  # when loaded directly by path (no parent package)
    try:
        import strategy  # type: ignore
    except Exception:
        # Load sibling strategy.py by path
        import importlib.util, os  # type: ignore
        here = os.path.dirname(__file__)
        strategy_path = os.path.join(here, "strategy.py")
        spec = importlib.util.spec_from_file_location("blackjack_env_strategy", strategy_path)
        strategy = importlib.util.module_from_spec(spec)  # type: ignore
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(strategy)  # type: ignore


# System prompts inspired by the Wordle environment style
THINK_ANSWER_SYSTEM_PROMPT = (
    "You are a competitive game player. "
    "Make sure you read the game instructions carefully, and always follow the required format.\n\n"
    "In each turn of Blackjack, think step-by-step inside <think>...</think> tags, "
    "then give only the action inside <answer>...</answer> tags."
)

NO_THINK_SYSTEM_PROMPT = (
    "You are a competitive game player. "
    "Make sure you read the game instructions carefully, and always follow the required format.\n\n"
    "In this task, give only the action inside <answer>...</answer> tags."
)


ACTIONS = ("HIT", "STAND", "DOUBLE", "SPLIT")


def _xml_parser(use_think: bool) -> vf.Parser:
    """Configure an XML parser, mirroring Wordle env style."""
    if use_think:
        return vf.XMLParser(fields=["think", "answer"], answer_field="answer")
    else:
        return vf.XMLParser(fields=["answer"], answer_field="answer")


def _infer_action_from_text(text: str, allowed: List[str]) -> str:
    """Best-effort fallback extractor for an action from raw text.

    Handles common formatting mistakes like `<answer-STAND</answer>` and
    also falls back to searching for a single allowed token.
    """
    allowed_upper = [a.upper() for a in allowed]
    t = text.upper()
    # Proper tag
    m = re.search(r"<ANSWER\s*>\s*(HIT|STAND|DOUBLE|SPLIT)\s*</ANSWER>", t)
    if m and m.group(1) in allowed_upper:
        return m.group(1)
    # Mistyped tag like <answer-STAND</answer>
    m = re.search(r"<ANSWER[-:\s]*\s*(HIT|STAND|DOUBLE|SPLIT)\s*</ANSWER>", t)
    if m and m.group(1) in allowed_upper:
        return m.group(1)
    # As a last resort, look for a single allowed token in text
    hits = {tok for tok in ("HIT", "STAND", "DOUBLE", "SPLIT") if re.search(rf"\b{tok}\b", t)}
    hits = [h for h in hits if h in allowed_upper]
    if len(hits) == 1:
        return hits[0]
    return ""


def _build_prompt(player: Tuple[str, str], dealer: str, rules: Dict) -> str:
    s17 = rules.get("s17", True)
    das = rules.get("das", True)
    return (
        "You are playing Blackjack. Choose the optimal basic-strategy action.\n\n"
        f"Rules: Multi-deck, dealer {'stands' if s17 else 'hits'} on soft 17, "
        f"double after split {'allowed' if das else 'not allowed'}, no surrender.\n"
        f"Your hand: {player[0]} and {player[1]}. Dealer upcard: {dealer}."
    )


##########################
# Multi-step Blackjack   #
##########################

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]


def _new_shoe(num_decks: int, rng: random.Random) -> Dict[str, int]:
    counts = {r: 0 for r in RANKS}
    for _ in range(num_decks):
        # 4 of each per deck, but for 10s include 10,J,Q,K → 16 tens
        for r in RANKS:
            if r == "10":
                counts[r] += 16
            elif r == "A":
                counts[r] += 4
            else:
                counts[r] += 4
    return counts


def _draw(shoe: Dict[str, int], rng: random.Random) -> str:
    total = sum(shoe.values())
    assert total > 0
    k = rng.randrange(total)
    cum = 0
    for r, c in shoe.items():
        if c <= 0:
            continue
        cum += c
        if k < cum:
            shoe[r] -= 1
            return r
    # Fallback (shouldn't hit)
    for r in RANKS:
        if shoe[r] > 0:
            shoe[r] -= 1
            return r
    raise RuntimeError("Empty shoe")


def _hand_totals(cards: List[str]) -> Tuple[int, bool]:
    # returns (best_total, is_blackjack_initial)
    vals = []
    total = 0
    aces = 0
    for c in cards:
        if c == "A":
            aces += 1
            total += 11
        else:
            total += 10 if c == "10" else int(c)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    is_bj = (len(cards) == 2) and (set(cards) == {"A", "10"})
    return total, is_bj


def _allowed_actions(cards: List[str], can_double: bool, can_split: bool) -> List[str]:
    acts = ["HIT", "STAND"]
    if can_double:
        acts.append("DOUBLE")
    if can_split:
        acts.append("SPLIT")
    return acts


def _dealer_play(shoe: Dict[str, int], up: str, hole: str, s17: bool, rng: random.Random) -> List[str]:
    cards = [up, hole]
    while True:
        total, _ = _hand_totals(cards)
        # Soft detection: if an ace counted as 11 currently
        soft = False
        t = 0
        aces = 0
        for c in cards:
            if c == "A":
                aces += 1
                t += 11
            else:
                t += 10 if c == "10" else int(c)
        while t > 21 and aces > 0:
            t -= 10
            aces -= 1
        soft = (aces > 0 and t == total)
        if total > 21:
            return cards
        if total > 17:
            return cards
        if total == 17:
            if s17 and soft:
                return cards
            if not s17:
                # H17 hits soft 17
                if soft:
                    cards.append(_draw(shoe, rng))
                    continue
                else:
                    return cards
            else:
                return cards
        # total < 17
        cards.append(_draw(shoe, rng))


def _compare(player_total: int, dealer_total: int, player_bj: bool, dealer_bj: bool, bet: float, bj_payout: float = 1.5) -> float:
    if player_bj and not dealer_bj:
        return bj_payout * bet
    if dealer_bj and not player_bj:
        return -bet
    if player_total > 21:
        return -bet
    if dealer_total > 21:
        return bet
    if player_total > dealer_total:
        return bet
    if player_total < dealer_total:
        return -bet
    return 0.0


def _settle_all_hands(
    shoe: Dict[str, int],
    hands: List[List[str]],
    doubled: List[bool],
    dealer_up: str,
    dealer_hole: str,
    rules: Dict,
    rng: random.Random,
) -> tuple[float, List[str]]:
    local_shoe = copy.deepcopy(shoe)
    dealer_cards = _dealer_play(local_shoe, dealer_up, dealer_hole, rules.get("s17", True), rng)
    dealer_total, dealer_bj = _hand_totals(dealer_cards)
    total_return = 0.0
    for i, hand in enumerate(hands):
        pt, pbj = _hand_totals(hand)
        bet = 2.0 if doubled[i] else 1.0
        # After a double, treat as non-BJ even if 2-card 21
        use_pbj = False if doubled[i] else pbj
        total_return += _compare(pt, dealer_total, use_pbj, dealer_bj, bet)
    return total_return, dealer_cards


def _play_hand_policy(
    shoe: Dict[str, int],
    player_cards: List[str],
    dealer_up: str,
    rules: Dict,
    rng: random.Random,
    allow_double: bool,
    allow_split: bool,
) -> float:
    # Play a single hand to completion under basic strategy returns net profit (bet=1)
    bet = 1.0
    s17 = rules.get("s17", True)
    das = rules.get("das", True)
    double_11_vs_ace = rules.get("double_11_vs_ace", False)

    # Check initial blackjack (no action needed)
    total, is_bj = _hand_totals(player_cards)
    # Draw dealer hole first to correctly evaluate dealer BJ outcomes
    # Here we delay dealer hole draw until settlement; simulate at the end

    # action loop (simplified policy)
    can_double = allow_double
    while True:
        total, is_bj = _hand_totals(player_cards)
        if total >= 21:
            break
        act = strategy.policy_action_general(
            player_cards, dealer_up, s17=s17, das=das, double_11_vs_ace=double_11_vs_ace
        )
        if act == "SPLIT" and allow_split and len(player_cards) == 2 and player_cards[0] == player_cards[1]:
            # Split into two hands and play each
            left = [player_cards[0]]
            right = [player_cards[1]]
            # draw one card to each
            shoe_a = shoe
            left.append(_draw(shoe_a, rng))
            right.append(_draw(shoe_a, rng))
            # after split, double allowed only if das
            ev_left = _play_hand_policy(copy.deepcopy(shoe_a), left, dealer_up, rules, rng, allow_double=das, allow_split=False)
            ev_right = _play_hand_policy(copy.deepcopy(shoe_a), right, dealer_up, rules, rng, allow_double=das, allow_split=False)
            return ev_left + ev_right
        elif act == "DOUBLE" and can_double:
            player_cards.append(_draw(shoe, rng))
            total, _ = _hand_totals(player_cards)
            # Dealer play
            hole = _draw(shoe, rng)
            dealer_cards = _dealer_play(shoe, dealer_up, hole, s17, rng)
            dealer_total, dealer_bj = _hand_totals(dealer_cards)
            # Note: double doubles the bet
            return 2.0 * _compare(total, dealer_total, False, dealer_bj, bet)
        elif act == "HIT":
            player_cards.append(_draw(shoe, rng))
            can_double = False
            continue
        else:  # STAND or invalid
            break

    # Stand or natural end
    hole = _draw(shoe, rng)
    dealer_cards = _dealer_play(shoe, dealer_up, hole, s17, rng)
    dealer_total, dealer_bj = _hand_totals(dealer_cards)
    total, is_bj = _hand_totals(player_cards)
    return _compare(total, dealer_total, is_bj, dealer_bj, bet)


def _ev_of_action(
    action: str,
    shoe: Dict[str, int],
    player_cards: List[str],
    dealer_up: str,
    rules: Dict,
    rng: random.Random,
    samples: int,
) -> float:
    # Monte Carlo EV estimate for chosen action; continuation uses basic strategy
    ev = 0.0
    for _ in range(samples):
        local_shoe = copy.deepcopy(shoe)
        cards = list(player_cards)
        if action == "HIT":
            cards.append(_draw(local_shoe, rng))
            ev += _play_hand_policy(local_shoe, cards, dealer_up, rules, rng, allow_double=False, allow_split=False)
        elif action == "STAND":
            hole = _draw(local_shoe, rng)
            dealer_cards = _dealer_play(local_shoe, dealer_up, hole, rules.get("s17", True), rng)
            dealer_total, dealer_bj = _hand_totals(dealer_cards)
            total, is_bj = _hand_totals(cards)
            ev += _compare(total, dealer_total, is_bj, dealer_bj, 1.0)
        elif action == "DOUBLE":
            # Allowed only if exactly two cards in real env; here we still compute
            cards.append(_draw(local_shoe, rng))
            total, _ = _hand_totals(cards)
            hole = _draw(local_shoe, rng)
            dealer_cards = _dealer_play(local_shoe, dealer_up, hole, rules.get("s17", True), rng)
            dealer_total, dealer_bj = _hand_totals(dealer_cards)
            ev += 2.0 * _compare(total, dealer_total, False, dealer_bj, 1.0)
        elif action == "SPLIT" and len(cards) == 2 and cards[0] == cards[1]:
            # Simulate split two hands; one draw each, then policy finish
            left = [cards[0], _draw(local_shoe, rng)]
            right = [cards[1], _draw(local_shoe, rng)]
            das = rules.get("das", True)
            ev_left = _play_hand_policy(copy.deepcopy(local_shoe), left, dealer_up, rules, rng, allow_double=das, allow_split=False)
            ev_right = _play_hand_policy(copy.deepcopy(local_shoe), right, dealer_up, rules, rng, allow_double=das, allow_split=False)
            ev += ev_left + ev_right
        else:
            # Invalid action → large negative penalty to reflect mistake
            ev += -1.0
    return ev / float(samples)


def _format_state_message(active_cards: List[str], dealer_up: str, rules: Dict, allowed: List[str]) -> str:
    total, is_bj = _hand_totals(active_cards)
    soft = False
    t = 0
    aces = 0
    for c in active_cards:
        if c == "A":
            aces += 1
            t += 11
        else:
            t += 10 if c == "10" else int(c)
    while t > 21 and aces > 0:
        t -= 10
        aces -= 1
    soft = (aces > 0 and t == total)
    soft_str = " (soft)" if soft and total <= 21 else ""
    details = (
        "Rules details: Double only on two cards; Split only on identical pairs; one split max; "
        "Double after split only if DAS; No surrender; Blackjack pays 3:2."
    )
    return (
        f"Blackjack — dealer {'stands' if rules.get('s17', True) else 'hits'} on soft 17; "
        f"DAS {'allowed' if rules.get('das', True) else 'not allowed'}; shoe: {rules.get('num_decks', 6)} deck(s).\n"
        f"Your active hand: {', '.join(active_cards)} (total: {total}{soft_str}). Dealer upcard: {dealer_up}.\n"
        f"Allowed actions: {', '.join(allowed)}. Respond with one of these inside <answer>...</answer>.\n"
        f"{details}"
    )


class BlackjackMultiEnv(vf.MultiTurnEnv):
    def __init__(self, ev_samples: int = 200, **kwargs):
        super().__init__(**kwargs)
        self.ev_samples = ev_samples

    async def is_completed(self, messages, state, **kwargs) -> bool:  # type: ignore
        return bool(state.get("done", False))

    async def setup_state(self, state, **kwargs):  # type: ignore
        # The dataset's info holds initial setup
        info = state.get("info", {}) or {}
        rng = random.Random(info.get("seed", random.randrange(1 << 30)))
        state["rng"] = rng
        state["rules"] = {
            "s17": info.get("s17", True),
            "das": info.get("das", True),
            "double_11_vs_ace": info.get("double_11_vs_ace", False),
            "num_decks": info.get("num_decks", 6),
        }
        state["shoe"] = copy.deepcopy(info["shoe"]) if "shoe" in info else _new_shoe(state["rules"]["num_decks"], rng)
        state["dealer_up"] = info.get("dealer_up")
        state["dealer_hole"] = info.get("dealer_hole")
        state["hands"] = [list(info.get("player_cards", []))]
        state["active_i"] = 0
        state["can_double"] = [True]
        state["can_split"] = [len(state["hands"][0]) == 2 and state["hands"][0][0] == state["hands"][0][1]]
        state["doubled"] = [False]
        state["first_action"] = None
        state["delta_ev_sum"] = 0.0
        state["format_salvaged"] = False
        state["first_state"] = {
            "shoe": copy.deepcopy(state["shoe"]),
            "player": list(state["hands"][0]),
            "dealer_up": state["dealer_up"],
            "rules": dict(state["rules"]),
        }
        state["done"] = False
        return state

    async def env_response(self, messages, state, **kwargs):  # type: ignore
        rng: random.Random = state["rng"]
        parser: vf.Parser = self.parser
        last_msg = [m for m in messages if m.get("role") == "assistant"][-1]
        action = (parser.parse_answer(messages) or "").strip().upper()
        i = state["active_i"]
        hand = state["hands"][i]
        can_double = state["can_double"][i]
        can_split = state["can_split"][i]
        rules = state["rules"]

        # Record first action for EV reward
        if state["first_action"] is None and action in ACTIONS:
            state["first_action"] = action

        # Validate and compute marginal EV shaping
        allowed_now = _allowed_actions(hand, can_double, can_split)
        if action not in ACTIONS or action not in allowed_now:
            # Try to salvage from raw text content (common formats like <answer-STAND</answer>)
            raw = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
            fallback = _infer_action_from_text(raw, allowed_now)
            if fallback in ACTIONS and fallback in allowed_now:
                action = fallback
                state["format_salvaged"] = True
            else:
                examples = " | ".join([f"<answer>{a}</answer>" for a in allowed_now])
                msg = (
                    f"Invalid action. Allowed: {', '.join(allowed_now)}.\n"
                    f"Reply exactly with one of: {examples}"
                )
                return [{"role": "user", "content": msg}], state

        # Compute per-turn delta EV: Q(action|state) - V(policy|state)
        try:
            baseline = strategy.policy_action_general(
                hand,
                state["dealer_up"],
                s17=rules.get("s17", True),
                das=rules.get("das", True),
                double_11_vs_ace=rules.get("double_11_vs_ace", False),
            )
            if baseline not in allowed_now:
                baseline = "STAND" if "STAND" in allowed_now else ("HIT" if "HIT" in allowed_now else allowed_now[0])
            crn_seed = 12345
            Q = _ev_of_action(
                action=action,
                shoe=copy.deepcopy(state["shoe"]),
                player_cards=list(hand),
                dealer_up=state["dealer_up"],
                rules=dict(rules),
                rng=random.Random(crn_seed),
                samples=self.ev_samples,
            )
            V = _ev_of_action(
                action=baseline,
                shoe=copy.deepcopy(state["shoe"]),
                player_cards=list(hand),
                dealer_up=state["dealer_up"],
                rules=dict(rules),
                rng=random.Random(crn_seed),
                samples=self.ev_samples,
            )
            state["delta_ev_sum"] = float(state.get("delta_ev_sum", 0.0)) + float(Q - V)
        except Exception:
            pass

        shoe = state["shoe"]
        dealer_up = state["dealer_up"]

        # Resolve action
        if action == "HIT":
            hand.append(_draw(shoe, rng))
            state["can_double"][i] = False
            state["can_split"][i] = False
            total, _ = _hand_totals(hand)
            if total > 21:
                # Bust, move to next hand or finish
                next_i = i + 1
                if next_i < len(state["hands"]):
                    state["active_i"] = next_i
                else:
                    # Settle and finish
                    payoff, dealer_cards = _settle_all_hands(
                        state["shoe"], state["hands"], state["doubled"], state["dealer_up"], state["dealer_hole"], state["rules"], rng
                    )
                    state["realized_return"] = payoff
                    state["dealer_final"] = dealer_cards
                    state["done"] = True
                    return [
                        {
                            "role": "user",
                            "content": f"Bust. Dealer: {', '.join(dealer_cards)}. Result: {payoff:+.1f} bets. Hand over.",
                        }
                    ], state
            allowed = _allowed_actions(hand, state["can_double"][i], state["can_split"][i])
            return [{"role": "user", "content": _format_state_message(hand, dealer_up, rules, allowed)}], state

        if action == "STAND":
            # Move to next hand or finish
            next_i = i + 1
            if next_i < len(state["hands"]):
                state["active_i"] = next_i
                j = next_i
                allowed = _allowed_actions(state["hands"][j], state["can_double"][j], state["can_split"][j])
                return [{"role": "user", "content": _format_state_message(state["hands"][j], dealer_up, rules, allowed)}], state
            else:
                payoff, dealer_cards = _settle_all_hands(
                    state["shoe"], state["hands"], state["doubled"], state["dealer_up"], state["dealer_hole"], state["rules"], rng
                )
                state["realized_return"] = payoff
                state["dealer_final"] = dealer_cards
                state["done"] = True
                return [
                    {
                        "role": "user",
                        "content": f"Standing. Dealer: {', '.join(dealer_cards)}. Result: {payoff:+.1f} bets. Hand over.",
                    }
                ], state

        if action == "DOUBLE":
            if not can_double:
                return [{"role": "user", "content": "Double not allowed. Choose another action."}], state
            hand.append(_draw(shoe, rng))
            state["doubled"][i] = True
            # After double, hand stands
            next_i = i + 1
            if next_i < len(state["hands"]):
                state["active_i"] = next_i
                j = next_i
                allowed = _allowed_actions(state["hands"][j], state["can_double"][j], state["can_split"][j])
                return [{"role": "user", "content": _format_state_message(state["hands"][j], dealer_up, rules, allowed)}], state
            else:
                payoff, dealer_cards = _settle_all_hands(
                    state["shoe"], state["hands"], state["doubled"], state["dealer_up"], state["dealer_hole"], state["rules"], rng
                )
                state["realized_return"] = payoff
                state["dealer_final"] = dealer_cards
                state["done"] = True
                return [
                    {
                        "role": "user",
                        "content": f"Double: drew one card and stood. Dealer: {', '.join(dealer_cards)}. Result: {payoff:+.1f} bets. Hand over.",
                    }
                ], state

        if action == "SPLIT":
            if not can_split or len(hand) != 2 or hand[0] != hand[1]:
                return [{"role": "user", "content": "Split not allowed. Choose another action."}], state
            # Split into two hands
            left = [hand[0], _draw(shoe, rng)]
            right = [hand[1], _draw(shoe, rng)]
            # Replace current hand with left, insert right after
            state["hands"][i] = left
            state["hands"].insert(i + 1, right)
            das = rules.get("das", True)
            state["can_double"][i] = das
            state["can_double"].insert(i + 1, das)
            state["can_split"][i] = False
            state["can_split"].insert(i + 1, False)
            state["doubled"][i] = False
            state["doubled"].insert(i + 1, False)
            allowed = _allowed_actions(state["hands"][i], state["can_double"][i], state["can_split"][i])
            return [{"role": "user", "content": _format_state_message(state["hands"][i], dealer_up, rules, allowed)}], state


def _generate_multistep_examples(
    total: int,
    rng: random.Random,
    forced_rules: Dict[str, Any] | None = None,
    randomize_rules: bool = True,
) -> List[Dict[str, Any]]:
    examples: List[Dict[str, Any]] = []
    forced_rules = forced_rules or {}
    for _ in range(total):
        if randomize_rules:
            num_decks = forced_rules.get("num_decks", rng.choice([1, 2, 4, 6, 8]))
            s17 = forced_rules.get("s17", rng.choice([True, False]))
            das = forced_rules.get("das", rng.choice([True, False]))
            double_11_vs_ace = forced_rules.get("double_11_vs_ace", rng.choice([False, True]))
        else:
            num_decks = forced_rules.get("num_decks", 6)
            s17 = forced_rules.get("s17", True)
            das = forced_rules.get("das", True)
            double_11_vs_ace = forced_rules.get("double_11_vs_ace", False)
        rules = {"s17": s17, "das": das, "double_11_vs_ace": double_11_vs_ace, "num_decks": num_decks}
        shoe = _new_shoe(num_decks, rng)
        # Initial deal
        player = [_draw(shoe, rng), _draw(shoe, rng)]
        dealer_up = _draw(shoe, rng)
        dealer_hole = _draw(shoe, rng)
        # Build initial message now (so the first assistant turn sees state)
        allowed = _allowed_actions(player, can_double=True, can_split=(len(set(player)) == 1))
        question = _format_state_message(player, dealer_up, rules, allowed)
        examples.append(
            {
                "question": question,
                "answer": "",  # not used
                "info": {
                    "seed": rng.randrange(1 << 30),
                    "s17": s17,
                    "das": das,
                    "double_11_vs_ace": rules["double_11_vs_ace"],
                    "num_decks": num_decks,
                    "shoe": shoe,
                    "player_cards": player,
                    "dealer_up": dealer_up,
                    "dealer_hole": dealer_hole,
                },
            }
        )
    return examples


def load_environment(**kwargs) -> vf.Environment:
    """
    Blackjack basic-strategy evaluation environment.

    Environment args (via -a/--env-args JSON):
      - max_examples: int = -1
      - rules: dict = {"s17": True, "das": True, "double_11_vs_ace": False}
    """
    # Print installed package version for easier debugging
    _version = "unknown"
    for dist_name in ("blackjack-env", "blackjack_env"):
        try:
            _version = _pkg_version(dist_name)
            break
        except PackageNotFoundError:
            continue
    try:
        print(f"[blackjack-env] package version: {_version}")
    except Exception:
        pass
    # Support being called with either env_args dict or flattened kwargs
    env_args: Dict = (kwargs.get("env_args") if "env_args" in kwargs else kwargs) or {}
    max_examples: int = int(env_args.get("max_examples", -1))
    rules: Dict = env_args.get("rules", {}) or {}
    use_think: bool = bool(env_args.get("use_think", True))
    ev_samples: int = int(env_args.get("ev_samples", 200))
    randomize_rules: bool = bool(env_args.get("randomize_rules", True))
    # Defaults
    rules = {
        "s17": bool(rules.get("s17", True)),
        "das": bool(rules.get("das", True)),
        "double_11_vs_ace": bool(rules.get("double_11_vs_ace", False)),
    }

    # Build dataset: multi-step random scenarios
    rng = random.Random(env_args.get("seed", None))
    default_total = 200
    total = max_examples if max_examples and max_examples > 0 else default_total
    examples = _generate_multistep_examples(total, rng, forced_rules=rules, randomize_rules=randomize_rules)
    if max_examples and max_examples > 0:
        examples = examples[: max_examples]

    if HFDataset is not None:
        dataset = HFDataset.from_list(examples)
    else:
        # Fallback: verifiers supports HF datasets; if unavailable, pass raw list
        # (SingleTurnEnv will attempt to read 'prompt' / 'answer' keys from items)
        dataset = examples  # type: ignore

    # Parser and rubric
    parser = _xml_parser(use_think)

    # Reward: EV of the first action under Monte Carlo continuation policy
    rubric = vf.Rubric(parser=parser)

    async def ev_reward(parser, completion, state, info, **_):  # type: ignore
        # Use the first recorded action if available; fallback to last parsed
        action = (state.get("first_action") or (parser.parse_answer(completion) or "")).strip().upper()
        # Use initial state snapshot stored at setup
        first_state = state.get("first_state", {})
        if not action:
            return -1.0
        ev = _ev_of_action(
            action=action,
            shoe=copy.deepcopy(first_state.get("shoe", {})),
            player_cards=list(first_state.get("player", [])),
            dealer_up=str(first_state.get("dealer_up", "10")),
            rules=dict(first_state.get("rules", {})),
            rng=random.Random(42),
            samples=ev_samples,
        )
        return float(ev)

    # Keep first-action EV as a logged metric (weight 0)
    rubric.add_reward_func(ev_reward, weight=0.0)
    
    # Marginal EV across all assistant turns (main reward)
    def delta_ev_sum(state, **_):  # type: ignore
        try:
            return float(state.get("delta_ev_sum", 0.0))
        except Exception:
            return 0.0
    rubric.add_reward_func(delta_ev_sum, weight=1.0)
    # Also report realized return (overall score of the played hand)
    async def realized_return_metric(state, **_):  # type: ignore
        try:
            return float(state.get("realized_return", 0.0))
        except Exception:
            return 0.0
    rubric.add_reward_func(realized_return_metric, weight=0.0)

    # Strict format reward: give credit only if parser format passes AND we did not salvage
    base_format_fn = parser.get_format_reward_func()

    def strict_format_reward(parser, completion, state, answer=None, **_):  # type: ignore
        try:
            base = float(base_format_fn(parser=parser, completion=completion, answer=answer))
        except TypeError:
            # Some implementations may not require all args
            try:
                base = float(base_format_fn(completion))
            except Exception:
                base = 0.0
        if state.get("format_salvaged", False):
            return 0.0
        return base

    rubric.add_reward_func(strict_format_reward, weight=0.1)

    # System prompt mirrors Wordle phrasing and keeps formatting guidance out of example prompts
    system_prompt = (
        THINK_ANSWER_SYSTEM_PROMPT if use_think else NO_THINK_SYSTEM_PROMPT
    ) + f"\n\nValid actions: {', '.join(ACTIONS)}."

    return BlackjackMultiEnv(
        dataset=dataset,
        system_prompt=system_prompt,
        parser=parser,
        rubric=rubric,
        ev_samples=ev_samples,
        max_turns=int(env_args.get("max_turns", 12)),
    )
