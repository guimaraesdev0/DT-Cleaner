# Adding a detector

A detector answers one narrow question: *"does this directory name, at this
location, look like a disposable artifact of my ecosystem?"*

It proposes. It never decides. The `SafetyEngine` runs afterwards and can only
lower the verdict, so a bug in a new detector can cause missed artifacts — never
an unsafe deletion.

## 1. Write the rules

```python
# dtcleaner/core/detectors/elixir.py
from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class ElixirDetector(RuleDetector):
    name = "elixir"
    ecosystem = Ecosystem.ELIXIR          # add it to the Ecosystem enum first

    rules = (
        Rule(
            name="_build",                # unambiguous, tool-owned name
            category=Category.OTHER,
            item_type="mix_build",
            risk=RiskLevel.LOW,
            base_confidence=0.85,
            regenerate_hint="mix compile",
        ),
        Rule(
            name="deps",                  # ambiguous: flag it, lower confidence
            category=Category.OTHER,
            item_type="mix_deps",
            risk=RiskLevel.MEDIUM,
            base_confidence=0.5,
            regenerate_hint="mix deps.get",
        ),
    )


register(ElixirDetector())
```

Then add the module to `_load_builtin()` in `detectors/base.py`.

## 2. Declare the project markers

In `constants.py`:

```python
PROJECT_MARKERS[Ecosystem.ELIXIR] = frozenset({"mix.exs", "mix.lock"})
```

Without this the validator can never prove context, and every candidate from
your detector will end up UNKNOWN.

## 3. Rule fields

| Field | Meaning |
|---|---|
| `name` | the directory name, matched case-insensitively |
| `category` | which group it appears under in the dashboard |
| `item_type` | stable identifier used for risk lookup and logs |
| `risk` | LOW / MEDIUM / HIGH — how costly it is to regenerate |
| `base_confidence` | starting score before context is considered |
| `regenerate_hint` | the command that brings it back, shown in Details |
| `parent_name` | require the parent folder to have this name |

`ambiguous` is derived automatically from `AMBIGUOUS_DIR_NAMES` — you do not set
it. If your name belongs to that list, context becomes mandatory.

## 4. Choosing `base_confidence`

| Situation | Range |
|---|---|
| name owned exclusively by one tool (`__pycache__`, `.next`) | 0.80 – 0.90 |
| name owned by a tool but reused elsewhere (`.gradle`) | 0.70 – 0.80 |
| ambiguous name, strong parent signal (`app/build`) | 0.65 – 0.75 |
| ambiguous name, no extra signal (`dist`, `build`) | 0.45 – 0.55 |

The scorer adds `+0.30` for a proven project and subtracts `0.06` per level of
distance, so an ambiguous rule at 0.50 lands at 0.80 when a marker sits right
above it — comfortably deletable — and at 0.30 when there is none, which is
below the threshold and therefore UNKNOWN.

## 5. Choosing `risk`

Risk is not "how sure are we" — that is confidence. Risk is **how much it costs
if we were right but the user wanted it anyway**.

- **LOW** — one command, mostly local (`npm install`, `mix compile`)
- **MEDIUM** — re-downloads from the network, or takes minutes (`cargo build`,
  a Gradle cache, a tox environment)
- **HIGH** — hard to reproduce; never auto-selected

When unsure, pick the higher one.

## 6. Write the false-positive test

Every new detector needs a test proving its ambiguous names are refused without
context. Add it to `tests/test_false_positives.py`:

```python
def test_deps_without_mix_exs_is_not_deletable(classifier, make_tree):
    base = make_tree({"somewhere/deps/notes.txt": "x"})
    item = classify_dir(classifier, base / "somewhere" / "deps")
    assert item is not None
    assert item.is_selectable is False
```

A detector without this test does not ship.

## 7. Translate the category

If you introduced a new `Category`, add `category.<value>` to **both**
`dtcleaner/i18n/locales/en.json` and `pt_br.json`. The test
`test_every_key_exists_in_every_locale` will fail otherwise.
