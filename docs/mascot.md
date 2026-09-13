# BYTE — the watchdog

## Concept

BYTE is a small dog that guards your disk.

The name is the joke: a dog named BYTE, who does not *bite* anything without
permission. A guard dog is the right metaphor for this product — friendly, good
at fetching things, and immovable about what it will not let past. That is
exactly the app's stance: helpful about finding junk, uncompromising about what
it refuses to touch.

BYTE is original to this project and renders in plain text on a terminal grid.

## The art

Five lines, nine columns, pure ASCII. The two `__` on top are floppy ears.

```
 __   __
/  \_/  \
| o   o |
|   w   |
 \_____/
```

### Why it is this small

The first draft was a seven-line vault-robot built from box-drawing characters,
with a broom beside it. Two problems, both real:

1. **It drifted out of alignment.** Different moods substituted characters of
   different widths into the figure, and box-drawing glyphs render at different
   widths across terminals. The result looked broken.
2. **It was too big.** Seven lines plus a side element is a lot of screen for
   decoration, on screens where the data is what matters.

The current design fixes both by construction: every line is a fixed width,
every mood swaps exactly **three single characters**, and there is no Unicode in
the figure at all — so there is no separate ASCII fallback to keep in sync, and
it looks identical everywhere.

`tests/test_mascot.py` enforces all of this. A mood whose face character is two
columns wide, or art that grows past six lines, fails the suite.

## Moods

| Mood | Face | Chip | Line (EN) | Used on |
|---|---|---|---|---|
| `IDLE` | `o w o` | `(o w o)` | "Ready when you are." | Home, Help, Settings |
| `SCANNING` | animated | `(O w o)` | "Sweeping your drives..." | Scan progress |
| `THINKING` | `o ~ o` | `(o ~ o)` | "Checking the project context..." | Results |
| `WARNING` | `O o O` | `(O o O)` | "Review this list before we continue." | Preview with risk |
| `BLOCKED` | `x - x` | `(x - x)` | "Not that one. That path is off limits." | Protected Paths |
| `WORKING` | animated | `(o v o)` | "Cleaning it up." | Cleanup progress |
| `HAPPY` | `^ w ^` | `(^ w ^)` | "All clean. Nice." | Summary (no failures) |
| `EMPTY` | `- . -` | `(- . -)` | "Nothing here to sweep." | Empty states |

Dialogue lives in `dtcleaner/i18n/locales/*.json` under `mascot.*`, so BYTE
speaks the user's language.

## Animation

Two moods animate; the rest are static.

- **SCANNING** — the eyes glance side to side, like a dog following a scent
  (`o w o` → `O w o` → `o w o` → `o w O`), 4 frames at ~120ms
- **WORKING** — the snout moves, like the dog is digging
  (`w` → `v` → `w` → `u`), 4 frames at ~140ms

With `settings.animations = off`, frame 0 is used and nothing moves.

## Usage rules

1. **One BYTE per screen.** Never two. The header chip counts as the screen's
   BYTE when there is no large art on that screen.

2. **The 5-line art is rationed.** Splash, Home, Scan Progress, Cleanup
   Progress, Summary, Help and empty states. Everywhere else uses the chip.

3. **BYTE never celebrates on a risk screen.** A Preview containing anything
   above LOW risk, or set to permanent deletion, shows `WARNING`. A Summary with
   failures shows `WARNING`, not `HAPPY`. The mascot must never make a
   destructive moment feel casual.

4. **Animation respects the setting.** Check `config.animations` before starting
   a timer.

5. **Face slots are one character.** Always. This is the alignment contract.

6. **BYTE does not speak outside `mascot.line()`.** Errors, warnings and
   confirmations use plain product copy. The mascot adds warmth, never
   ambiguity — nobody should have to decode a joke to understand what is about
   to be deleted.

## Wordmark

The splash pairs BYTE with the block wordmark, shown from 90 columns up:

```
██████╗ ████████╗      ██████╗██╗     ███████╗ █████╗ ███╗   ██╗███████╗██████╗
██╔══██╗╚══██╔══╝     ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║██╔════╝██╔══██╗
██║  ██║   ██║ █████╗ ██║     ██║     █████╗  ███████║██╔██╗ ██║█████╗  ██████╔╝
██║  ██║   ██║ ╚════╝ ██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║██╔══╝  ██╔══██╗
██████╔╝   ██║        ╚██████╗███████╗███████╗██║  ██║██║ ╚████║███████╗██║  ██║
╚═════╝    ╚═╝         ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
```

It is 80 columns wide, so below the `-normal` breakpoint a narrow variant takes
its place rather than the logo simply vanishing:

```
╔╦╗╔╦╗   ╔═╗╦  ╔═╗╔═╗╔╗╔╔═╗╦═╗
 ║║ ║    ║  ║  ║╣ ╠═╣║║║║╣ ╠╦╝
═╩╝ ╩    ╚═╝╩═╝╚═╝╩ ╩╝╚╝╚═╝╩╚═
```

Both are mounted on the splash at once and swapped by CSS, so resizing the
terminal switches between them instantly instead of re-composing the screen.

The ASCII fallback is deliberately plain letterspaced text inside a rule — a
hand-drawn ASCII logo reads as noise at this size, and the splash already names
the app below it.

All three variants are padded to equal row widths: a ragged last row reads as a
rendering glitch rather than as a logo. `tests/test_mascot.py` checks that, and
that each variant fits the breakpoint that shows it.
