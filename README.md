# Blackjack Basic Strategy Env

**Source Code Repository:** [https://github.com/peterN908/blackjack_env](https://github.com/peterN908/blackjack_env)

### Overview
- **Environment ID**: `blackjack-env`
- **Short description**: Multi-turn heads-up Blackjack with EV shaping, plus a single-turn mode that scores the marginal EV of the chosen move.
- **Tags**: blackjack, games, multi-turn, single-turn, eval

### Datasets
- **Primary dataset**: Programmatically generated randomized Blackjack states (shoe size, S17/H17, DAS).
  - Multi-turn: initial deal states.
  - Single-turn: initial or mid-hand states (double only on two cards; pairs/split constraints respected).
- **Source**: On-load generator with basic-strategy continuation policy for EV estimation (see `strategy.py`).
- **Size**: Controlled by `max_examples` (defaults to 200 if unspecified). Each evaluation uses fresh random scenarios (optionally fixed by `seed`).

### Task
- **Type**: multi-turn and single-turn (chat)
- **Parser**: XMLParser expecting `<think>` and `<answer>` tags
- **Rubric overview**:
  - Multi-turn: EV of the first action (logged), marginal EV shaping across turns (main), plus format reward.
  - Single-turn: marginal EV of the chosen move relative to basic strategy (main), plus format reward; absolute EV is logged.

### Quickstart
Run an evaluation with default settings:

```bash
uv run vf-eval blackjack-env
```

Defaults when no flags are provided:
- Model: `gpt-4.1-mini`
- Provider: `https://api.openai.com/v1` using `OPENAI_API_KEY`
- Examples (`-n`): `5`
- Repeats (`-r`): `3`
- Max concurrent (`-c`): `32`
- Max tokens (`-t`): unset (use model default)
- Temperature (`-T`): unset (use model default)
- Save: not saved unless `-s` (local) or `-H` (HF Hub) is provided

Configure model and sampling:

```bash
uv run vf-eval blackjack-env \
  -m gpt-4.1-mini \
  -n 10 -r 3 -t 1024 -T 0.5 \
  -a '{"max_examples": 50, "ev_samples": 200, "randomize_rules": true}'
```

Notes:
- Use `-a` / `--env-args` to pass environment-specific configuration as a JSON object.
- The model should output the action inside `<answer>...</answer>` and may include reasoning in `<think>...</think>`.

#### Single-turn Quickstart

Run a single-turn evaluation (one state → one action; reward = marginal EV of the move):

```bash
uv run vf-eval blackjack-env 
  -m gpt-4.1-mini \
  -n 10 -r 3 -t 1024 -T 0.5 \
  -a '{"mode":"single", "ev_samples": 200, "randomize_rules": true}'
```
or equivalently:
```bash
uv run vf-eval blackjack-env -a '{"single_turn": true, "ev_samples": 200}'
```

Parameters (configure model and sampling):
- `-m/--model`: model name on your OpenAI-compatible endpoint (e.g., `gpt-4.1-mini`).
- `-n/--num`: number of examples to evaluate.
- `-r/--repeats`: rollouts per example (sampling repeats; results averaged).
- `-t/--tokens`: max output tokens per generation.
- `-T/--temperature`: sampling temperature.
- `-a/--env-args`: JSON dict of environment-specific args (see table below).

Note: Some models restrict certain knobs (e.g., fixed temperature). If you see a 400 about `temperature`, omit `-T` or set an allowed value.

### Installation
- From repo root, install the environment for local development:

```bash
vf-install blackjack-env
```

- Set your model provider credentials (OpenAI-compatible):
  - Export in shell or create a `.env` and source it.

```bash
export OPENAI_API_KEY=sk-...                 # required
# Optional: custom OpenAI-compatible endpoint
export OPENAI_BASE_URL=https://api.openai.com/v1
```

- Re-run `vf-install blackjack-env` whenever you modify files to pick up changes.

### CLI Play (For Fun)
Install the environment, then launch the interactive CLI:

```bash
uv run blackjack-play
```

Options:
- `--decks 6` set number of decks (default 6)
- `--s17` or `--h17` dealer stands/hits soft 17 (default S17)
- `--das` or `--no-das` double after split allowed (default allowed)
- `--seed N` fix randomness

Gameplay:
- You’ll see the rules, your hand, dealer upcard, allowed actions, and a reminder of constraints:
  - Double only on two cards; Split only on identical pairs; one split max; DAS gates double-after-split; No surrender; Blackjack pays 3:2.
- Type `HIT`, `STAND`, `DOUBLE`, or `SPLIT` (or `q` to quit the hand). Bankroll change is reported in bets.

### Environment Arguments

| Arg | Type | Default | Description |
| --- | ---- | ------- | ----------- |
| `max_examples` | int | `-1` | Limit dataset size (use `-1` for all examples) |
| `rules.s17` | bool | `true` | Dealer stands on soft 17 (S17) if true; otherwise H17 |
| `rules.das` | bool | `true` | Double after split allowed (affects pair strategy for 2s/3s/4s/6s) |
| `rules.double_11_vs_ace` | bool | `false` | If true, double hard 11 vs Ace; otherwise hit |
| `use_think` | bool | `true` | Require `<think>` tag before `<answer>` (Wordle-style) |
| `ev_samples` | int | `200` | Monte Carlo samples for EV estimation of the first action |
| `rules.num_decks` | int | `6` | Force number of decks when `randomize_rules=false` |
| `randomize_rules` | bool | `true` | Randomize S17/H17, DAS, and num decks per example; if `false`, use `rules.*` values |
| `max_turns` | int | `12` | Safety cap: end rollout after this many assistant turns |
| `max_format_retries` | int | `3` | After N invalid/malformed answers in a turn, auto-apply baseline action and continue |
| `mode` | string | unset | When set to `"single"`, run single-turn mode; otherwise multi-turn |
| `single_turn` | bool | `false` | Convenience flag; equivalent to `mode="single"` when true |

Allowed actions are: `HIT`, `STAND`, `DOUBLE`, `SPLIT`.

### Metrics

| Metric | Meaning |
| ------ | ------- |
| `reward` | Weighted sum of metrics (EV + format) |
| `delta_ev_sum` | Sum over turns of EV(action|state) − EV(baseline|state) |
| `ev_reward` | Monte Carlo expected value of the first action (bets) |
| `realized_return_metric` | Realized total result of the entire hand (bets) |
| `format_reward_func` | Parser’s format reward for well-formed tags |

Single-turn mode:
- `reward` = `marginal_ev_reward + 0.1 × strict_format_reward`
- `marginal_ev_reward`: EV(action|state) − EV(baseline|state) using a common random seed
- `chosen_action_ev`: Absolute EV of the chosen action (logged)
- `strict_format_reward`: Parser format score

Reward computation:
- Main reward: `reward = delta_ev_sum + 0.1 × format_reward_func`.
- `delta_ev_sum`: For each assistant turn t, we compute Q_t = EV(action|state_t) and V_t = EV(baseline|state_t) using Monte Carlo with the same random stream (low-variance). We add (Q_t − V_t) across all turns (including split hands). Baseline is the basic‑strategy policy adjusted to allowed actions for that state.
- Malformed answers: The env accepts lenient forms (e.g., `<answer-STAND</answer>`); if it must salvage formatting, the format bonus is set to 0 for that turn. After `max_format_retries` invalid attempts in a single turn, the env auto-applies the baseline action and moves on.
- `ev_reward`: Still logged (weight 0) — EV of the first action only from the initial state (continuation via basic strategy). Typical ranges: about `−2.0` to `+3.0` in bets for doubles/splits; most spots `−1.0` to `+1.5`.
- `realized_return_metric`: The actual one‑off outcome of the hand from the environment’s deal; a useful “overall score” but not included in the main reward by default (weight 0).

Performance note:
- Per‑turn EV uses `ev_samples` simulations at each assistant turn; runtime scales with turns × `ev_samples` × examples × repeats. Use smaller `ev_samples` for speed or increase for tighter estimates.

### Prompt Format
Each example starts with a state prompt (rules, your hand, dealer upcard). The model responds with an action; the environment updates the state and continues until the hand is resolved. Respond using:

```
<think>Optional brief reasoning.</think>
<answer>HIT|STAND|DOUBLE|SPLIT</answer>
```

### Example Transcript (2–3 turns)

```
System: You are a competitive game player. In each turn, think in <think>…</think> and put the action in <answer>…</answer>.

User:
Blackjack — dealer stands on soft 17; DAS allowed; shoe: 6 deck(s).
Your active hand: 9, 3 (total: 12). Dealer upcard: 2.
Allowed actions: HIT, STAND, DOUBLE. Respond with one of these inside <answer>...</answer>.
Rules details: Double only on two cards; Split only on identical pairs; one split max; Double after split only if DAS; No surrender; Blackjack pays 3:2.

Assistant:
<think>Hard 12 vs 2 is a hit.</think>
<answer>HIT</answer>

User:
Blackjack — dealer stands on soft 17; DAS allowed; shoe: 6 deck(s).
Your active hand: 9, 3, 5 (total: 17). Dealer upcard: 2.
Allowed actions: HIT, STAND. Respond with one of these inside <answer>...</answer>.
Rules details: Double only on two cards; Split only on identical pairs; one split max; Double after split only if DAS; No surrender; Blackjack pays 3:2.

Assistant:
<think>Stand on 17.</think>
<answer>STAND</answer>

User:
Standing. Dealer: 2, 10, 6. Result: +1.0 bets. Hand over.
```

Game details shown each turn:
- Dealer stands/hits on soft 17, DAS setting, and shoe size.
- Allowed actions for the current hand (respecting two-card/double rules and pair/split constraints).
- Rule reminders: double on two cards, split pairs only, one split max, DAS gating, no surrender, blackjack pays 3:2.

### Notes on Rules
- Encodes a standard multi-deck basic strategy. Default assumes S17 and DAS.
- Some rule variations (e.g., double 11 vs Ace) are parameterized via `env-args.rules`.

### Terminology
- Bet (unit): base wager per hand. Typical outcomes: win `+1`, lose `-1`, push `0`; blackjack pays `+1.5`; doubles pay `±2`; split hands sum their results.
- Dealer upcard: the dealer’s face-up card; the face-down card is the “hole” and is revealed when the dealer plays.

### How Evaluation Runs
- Multi-turn:
  - The dataset pre-generates randomized scenarios (initial hands) and provides a `question` per example with the initial state.
  - Chat loop per example:
    - System message instructs formatting; user shows current state and allowed actions.
    - Assistant replies with `<answer>...</answer>`; the environment applies the action, deals cards, and posts the updated state.
    - Continues until the hand is finished (bust/stand/double for all hands including split).
  - Scoring: marginal EV shaping across turns (main), EV of first action logged, plus format reward.
- Single-turn:
  - The dataset provides a single state (initial or mid-hand). The model outputs exactly one action.
  - Scoring: marginal EV of the chosen move relative to baseline (main), absolute EV logged, plus format reward.

### Saving Results
- By default, results are not saved to disk.
- To save locally, pass `-s/--save-dataset`. Outputs are written to:
  - `environments/blackjack_env/outputs/evals/blackjack-env--<model>/<uuid>/` if the env directory is present, otherwise `./outputs/evals/...`
  - Files: `results.jsonl` (prompts, completions, answers, rewards, metrics) and `metadata.json`.
- To push to Hugging Face Hub, pass `-H/--save-to-hf-hub` and optionally `-D/--hf-hub-dataset-name`.
