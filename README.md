# Blackjack Basic Strategy Env

**Source Code Repository:** [https://github.com/peterN908/Blackjack-RL-Env](https://github.com/peterN908/Blackjack-RL-Env)

### Overview
- **Environment ID**: `blackjack-env`
- **Short description**: Multi-turn heads-up Blackjack with EV-based scoring of the first action.
- **Tags**: blackjack, games, multi-turn, eval

### Datasets
- **Primary dataset**: Programmatically generated randomized Blackjack states (shoe size, S17/H17, DAS, initial deal).
- **Source**: On-load generator with basic-strategy continuation policy for EV estimation (see `strategy.py`).
- **Size**: Controlled by `max_examples` (defaults to 200 if unspecified). Each evaluation uses fresh random scenarios (optionally fixed by `seed`).

### Task
- **Type**: multi-turn (chat)
- **Parser**: XMLParser expecting `<think>` and `<answer>` tags
- **Rubric overview**:
  - EV of the first action (Monte Carlo expected value in units of bets)
  - Format reward from parser for well-formed XML tags

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

Allowed actions are: `HIT`, `STAND`, `DOUBLE`, `SPLIT`.

### Metrics

| Metric | Meaning |
| ------ | ------- |
| `reward` | Weighted sum of metrics (EV + format) |
| `ev_reward` | Monte Carlo expected value of the first action (bets) |
| `realized_return_metric` | Realized total result of the entire hand (bets) |
| `format_reward_func` | Parser’s format reward for well-formed tags |

Reward computation:
- Rubric combines `ev_reward` (weight `1.0`) and `format_reward_func` (weight `0.1`).
- `ev_reward` is computed via Monte Carlo from the initial state using the chosen first action and a fixed continuation policy (basic strategy). Values typically range from about `-2.0` to `+3.0` for split/double cases (measured in bets), but most scenarios lie in `[-1.0, +1.5]`.
- `realized_return_metric` reports the actual outcome of the played hand using the environment’s exact dealing sequence; treat this as the “overall score” for that rollout.

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
- The dataset pre-generates randomized scenarios (shoe size, S17/H17, DAS, initial hands) and provides a `question` per example with the initial state.
- Chat loop per example:
  - System message instructs formatting; user shows current state and allowed actions.
  - Assistant replies with `<answer>...</answer>`; the environment applies the action, deals cards, and posts the updated state.
  - Continues until the hand is finished (bust/stand/double for all hands including split).
- Scoring:
  - `ev_reward`: Monte Carlo EV of the first action only (continuation policy = basic strategy). This gives a principled, model-agnostic value of the initial decision.
  - `format_reward_func`: structural correctness bonus.

### Saving Results
- By default, results are not saved to disk.
- To save locally, pass `-s/--save-dataset`. Outputs are written to:
  - `environments/blackjack_env/outputs/evals/blackjack-env--<model>/<uuid>/` if the env directory is present, otherwise `./outputs/evals/...`
  - Files: `results.jsonl` (prompts, completions, answers, rewards, metrics) and `metadata.json`.
- To push to Hugging Face Hub, pass `-H/--save-to-hf-hub` and optionally `-D/--hf-hub-dataset-name`.
