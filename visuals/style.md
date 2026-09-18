# Fly Terminal — visual style

The second look for Hedgefly, and the one the video leads with. The risograph HQ
(`visuals/hq/`) stays as B-roll; nothing here borrows from it. That world was warm paper and
printed ink. This one is a screen in a dark room at 3am: the trading terminal the flies are
plugged into.

Original design. Do not copy the riso reference, and do not imitate any existing terminal
product's branding.

## The idea

A monitor showing a live experiment. The chart is the world; the flies fly over it. Everything
is emitted light on near-black, slightly out of focus, with the faint horizontal banding of a
screen that has been on too long. The reader should feel like they are watching an instrument,
not a dashboard: no cards, no rounded panels, no drop shadows, no product chrome.

## Palette

Colour carries one meaning only: **who is this**. Nothing is coloured for decoration.

| token | value | what it means |
|---|---|---|
| `--void` | `#06080c` | the background, near-black with a blue cast |
| `--panel` | `#0b0f16` | a pane's fill, barely lighter than the void |
| `--grid` | `#16202e` | rules, axes, borders |
| `--real` | `#2ff5c8` | **the real tribe.** Cyan-green, the brightest thing on screen |
| `--scrambled` | `#ff3d7f` | **the scrambled tribe.** Magenta-red, equally saturated |
| `--hero` | `#ffd23f` | the hero lineage alone: its trail, its tag, its line |
| `--up` / `--down` | `#1f9e6e` / `#b3335c` | candle bodies, deliberately duller than the tribes |
| `--ink` | `#c9d6e6` | body text |
| `--dim` | `#5a6b80` | labels, axis numbers, anything secondary |
| `--locked` | `#ff6a1f` | the sealed pane, and nothing else |

The two tribe colours must stay equally bright and equally saturated. If one reads as the
"good" colour the whole comparison is rigged, and that is the one claim the piece is making.
Check them in greyscale: they should be indistinguishable in value.

## Type

Monospace throughout: `ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`.
Uppercase for labels with `letter-spacing: .12em`; sentence case for nothing. Numbers are
tabular (`font-variant-numeric: tabular-nums`) so a changing figure does not jitter. Sizes:
11px labels, 13px body, 18px scoreboard figures, 34px the generation counter.

## The four rules of the look

1. **Light comes from the mark itself.** Every bright element carries a glow of its own colour,
   drawn as a soft pass under a sharp pass — canvas `shadowBlur` with `shadowColor` set to the
   element's colour, then the same path drawn again crisp. Never a CSS `box-shadow`, never a
   glow in a colour the element is not.
2. **Scanlines and bloom sit over everything.** One 2px horizontal banding pattern at about 6%
   opacity across the whole canvas, plus a slow vertical sweep every ~9s. Applied once, last,
   over the finished frame, never per element.
3. **Nothing is pure white and nothing is pure black.** Highlights top out at `--ink`;
   the darkest value is `--void`. A pure `#fff` or `#000` anywhere is a bug.
4. **Motion is small, continuous and never eased.** Flies beat their wings every frame, the
   chart does not animate at all, and panels update on the generation tick. No transitions, no
   bounce, no easing curves — this is an instrument reading out, not an interface animating.

## Layout

A fixed three-column grid, no scrolling, 100vh:

```
┌──────────────────────────────────────────────┬────────────────┐
│  GEN 23/39        [play] [=========|-------] │  SCOREBOARD    │
├──────────────────────────────────────────────┤  real / scram  │
│                                              │  momentum      │
│   CANDLES + 200 FLIES + hero trail           │  random        │
│   (the world)                                │  buy & hold    │
│                                              ├────────────────┤
│                                              │  BRAIN MESH    │
├──────────────────────────────────────────────┤────────────────┤
│  THE PILE — dead flies, accumulating         │  LOCKED  ▓▓▓▓  │
└──────────────────────────────────────────────┴────────────────┘
```

`?vertical` switches to 9:16 for Shorts: the world keeps the top ~62% of the height, the
scoreboard becomes a single row under it, and the mesh and locked pane sit side by side at the
bottom. Same code, same data, different arrangement — never a second implementation.

## The flies

A fly is drawn, not a dot: a 3px body, a head, and two wings redrawn every frame at a
per-fly phase so the swarm shimmers rather than pulsing in unison. Alive flies are their
tribe's colour at an alpha set by how well they are doing. A fly that goes broke stops flying,
falls, and lands in **the pile** along the bottom, where it stays for the rest of the run —
the pile only ever grows, and it is the piece's memory of everything selection has cost.

The hero fly is `--hero`, larger, with a trail of its last ~40 positions fading to nothing, a
name tag, and its own equity line drawn across the world pane.

## What this style refuses

- No gradients except the glow itself. No blur filters on text.
- No colour that means nothing. A new colour needs a new meaning, in this table, first.
- No easing, no spring physics, no transitions on any property.
- No decorative "data" — every mark on screen is a number from `runs.json`
  (`visuals/hq/data-contract.md`), which is PLAN.md rule 8.
