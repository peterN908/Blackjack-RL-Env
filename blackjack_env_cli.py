import argparse
import random

from blackjack_env import (
    _new_shoe,
    _draw,
    _hand_totals,
    _dealer_play,
    _format_state_message,
    _allowed_actions,
    _infer_action_from_text,
)


def play_once(args) -> float:
    rng = random.Random(args.seed)
    rules = {
        "s17": args.s17,
        "das": args.das,
        "double_11_vs_ace": args.double_11_vs_ace,
        "num_decks": args.decks,
    }
    shoe = _new_shoe(args.decks, rng)
    player = [_draw(shoe, rng), _draw(shoe, rng)]
    dealer_up = _draw(shoe, rng)
    dealer_hole = _draw(shoe, rng)

    can_double = True
    can_split = len(player) == 2 and player[0] == player[1]

    print("\n=== New Hand ===")
    while True:
        allowed = _allowed_actions(player, can_double, can_split)
        print(_format_state_message(player, dealer_up, rules, allowed))
        raw = input("Your action (HIT/STAND/DOUBLE/SPLIT, or Q to quit hand): ").strip()
        if raw.upper() in ("Q", "QUIT"):
            print("Hand aborted.")
            return 0.0
        # Accept either plain tokens or XML-ish tags
        parsed = _infer_action_from_text(raw, allowed)
        action = parsed if parsed else raw.upper()
        if action not in allowed:
            examples = " | ".join([f"<answer>{a}</answer>" for a in allowed])
            print(
                f"Invalid action. Allowed: {', '.join(allowed)}\n"
                f"Type one of: {', '.join(allowed)} (no tags), or reply exactly with: {examples}\n"
            )
            continue
        if action == "HIT":
            player.append(_draw(shoe, rng))
            can_double = False
            can_split = False
            total, _ = _hand_totals(player)
            if total > 21:
                print(f"You drew and busted with {total}. You lose 1 bet.\n")
                return -1.0
            continue
        elif action == "STAND":
            hole = dealer_hole
            dealer_cards = _dealer_play(shoe, dealer_up, hole, rules["s17"], rng)
            pt, pbj = _hand_totals(player)
            dt, dbj = _hand_totals(dealer_cards)
            if pbj and not dbj:
                print(f"Blackjack! Dealer {dealer_cards}. You win +1.5 bets.\n")
                return 1.5
            if dbj and not pbj:
                print(f"Dealer blackjack {dealer_cards}. You lose 1 bet.\n")
                return -1.0
            if dt > 21:
                print(f"Dealer busts {dealer_cards}. You win +1 bet.\n")
                return 1.0
            if pt > dt:
                print(f"You {pt} vs Dealer {dt}. You win +1 bet.\n")
                return 1.0
            if pt < dt:
                print(f"You {pt} vs Dealer {dt}. You lose 1 bet.\n")
                return -1.0
            print(f"Push {pt} vs {dt}.\n")
            return 0.0
        elif action == "DOUBLE":
            if not can_double:
                print("Double not allowed now.\n")
                continue
            player.append(_draw(shoe, rng))
            hole = dealer_hole
            dealer_cards = _dealer_play(shoe, dealer_up, hole, rules["s17"], rng)
            pt, pbj = _hand_totals(player)
            dt, dbj = _hand_totals(dealer_cards)
            if pt > 21:
                print(f"You doubled and busted with {pt}. Lose 2 bets.\n")
                return -2.0
            if dt > 21 or pt > dt:
                print(f"Double win! You {pt} vs Dealer {dt}. +2 bets.\n")
                return 2.0
            if pt < dt:
                print(f"Double lose. You {pt} vs Dealer {dt}. -2 bets.\n")
                return -2.0
            print(f"Double push. {pt} vs {dt}.\n")
            return 0.0
        elif action == "SPLIT":
            if not can_split:
                print("Split not allowed.\n")
                continue
            left = [player[0], _draw(shoe, rng)]
            right = [player[1], _draw(shoe, rng)]
            das = rules["das"]
            total_res = 0.0
            for idx, hand in enumerate([left, right], start=1):
                print(f"\n-- Split hand {idx} --")
                can_double_h = das
                while True:
                    allowed_h = _allowed_actions(hand, can_double_h, False)
                    print(_format_state_message(hand, dealer_up, rules, allowed_h))
                    act_raw = input("Action for this hand: ").strip()
                    act_parsed = _infer_action_from_text(act_raw, allowed_h)
                    act = act_parsed if act_parsed else act_raw.upper()
                    if act not in allowed_h:
                        examples = " | ".join([f"<answer>{a}</answer>" for a in allowed_h])
                        print(
                            f"Invalid. Allowed: {', '.join(allowed_h)}\n"
                            f"Type one of: {', '.join(allowed_h)} (no tags), or reply exactly with: {examples}\n"
                        )
                        continue
                    if act == "HIT":
                        hand.append(_draw(shoe, rng))
                        can_double_h = False
                        t, _ = _hand_totals(hand)
                        if t > 21:
                            print(f"Busted with {t}. Lose 1 bet.")
                            total_res += -1.0
                            break
                        continue
                    elif act == "STAND":
                        hole = dealer_hole
                        dealer_cards = _dealer_play(shoe, dealer_up, hole, rules["s17"], rng)
                        pt, pbj = _hand_totals(hand)
                        dt, dbj = _hand_totals(dealer_cards)
                        if pbj and not dbj:
                            print("Blackjack on split hand pays 3:2 here.")
                            total_res += 1.5
                        elif dbj and not pbj:
                            total_res += -1.0
                        elif dt > 21 or pt > dt:
                            total_res += 1.0
                        elif pt < dt:
                            total_res += -1.0
                        else:
                            total_res += 0.0
                        break
                    elif act == "DOUBLE" and can_double_h:
                        hand.append(_draw(shoe, rng))
                        hole = dealer_hole
                        dealer_cards = _dealer_play(shoe, dealer_up, hole, rules["s17"], rng)
                        pt, _ = _hand_totals(hand)
                        dt, _ = _hand_totals(dealer_cards)
                        if pt > 21:
                            print(f"Double bust with {pt}. Lose 2 bets.")
                            total_res += -2.0
                        elif dt > 21 or pt > dt:
                            total_res += 2.0
                        elif pt < dt:
                            total_res += -2.0
                        else:
                            total_res += 0.0
                        break
                    else:
                        print("Double not allowed for this hand now.\n")
                        continue
            print(f"\nSplit total result: {total_res:+.1f} bets.\n")
            return total_res


def main():
    p = argparse.ArgumentParser(description="Play heads-up Blackjack in the terminal.")
    p.add_argument("--decks", type=int, default=6, help="Number of decks in shoe (default 6)")
    p.add_argument("--s17", action="store_true", help="Dealer stands on soft 17 (S17)")
    p.add_argument("--h17", dest="s17", action="store_false", help="Dealer hits soft 17 (H17)")
    p.set_defaults(s17=True)
    p.add_argument("--das", action="store_true", help="Double after split allowed")
    p.add_argument("--no-das", dest="das", action="store_false", help="Double after split not allowed")
    p.set_defaults(das=True)
    p.add_argument("--double-11-vs-ace", dest="double_11_vs_ace", action="store_true", help="Treat hard 11 vs Ace as DOUBLE in policy")
    p.add_argument("--seed", type=int, default=None, help="Random seed")
    args = p.parse_args()

    bankroll = 0.0
    try:
        while True:
            res = play_once(args)
            bankroll += res
            print(f"Bankroll change this session: {bankroll:+.1f} bets")
            again = input("Play another hand? (y/n): ").strip().lower()
            if again not in ("y", "yes"):
                break
    except KeyboardInterrupt:
        pass
    print(f"Final bankroll change: {bankroll:+.1f} bets")


if __name__ == "__main__":
    main()
