# Neon riso — visual style

The look of Hedgefly's main world, **Natural Selection Capital HQ** (`visuals/hq2/`), its poster
cards (`visuals/posters/`) and everything cut from them. It keeps what made the riso rooms work
— isometric cutaway dioramas, halftone grain, hand-wobbled lines, plates that do not quite line
up — and prints them in light instead of ink: neon screen-printed onto black paper.

Original design. It borrows the *technique* of risograph printing, not anyone's artwork; the
riso-rooms reference is a way of drawing, not a picture to copy. The earlier warm-paper HQ
(`visuals/hq/`, branch `session-a/day4`) and the fly terminal (`visuals/terminal/`) stay in the
repo: the first as B-roll, the second as an optional inset panel.

## The idea

A risograph run on black stock with fluorescent drums. Every surface is a halftone of light:
walls are a sparse dot screen in a dim ink, floors a denser one, and anything that matters
glows. Where two plates overlap they ADD, the way light does, instead of darkening the way ink
does — so overprints brighten toward white rather than muddying toward black.

## Paper and inks

| token | value | what it means |
|---|---|---|
| paper | `#07070b` | near-black stock with a faint violet cast; never pure black |
| `cyan` | `#27f2d2` | **the real tribe**, and nothing else |
| `magenta` | `#ff3d9a` | **the scrambled tribe**, and nothing else |
| `gold` | `#ffc93c` | **the hero lineage** alone |
| `amber` | `#ff7a1a` | **the locked test set** alone: the vault, its seals, its warnings |
| `slate` | `#5b6cff` at low tone | architecture: walls, floors, furniture, the building itself |
| `ghost` | `#d8dcff` at low tone | linework and small type on dark surfaces; and the language model in the Model's Office, which is neither tribe, hero nor vault |

**Colour means who, never how good.** Cyan and magenta must be equally bright and equally
saturated — check them in greyscale; they should read as the same value. If one tribe's colour
looks like the winner's, the comparison the whole film makes is rigged before a single fly has
traded. The same goes for the plates: a tribe is never printed at a higher tone than the other.

Anything that is neither a tribe, the hero, nor the vault is `slate` or `ghost`. A new colour
needs a new meaning, written into this table first.

**How good is tone, not hue.** The Barcode Wall paints one cell per fly per generation and has
to show fitness, which is exactly the thing colour is not allowed to carry. It carries it in the
*density of the ink* instead: a real fly's cell is cyan and a scrambled fly's is magenta,
whatever either of them earned, and the halftone gets denser as fitness rises. Both tribes are
scaled against one shared range taken over the whole run, so a dark band means the same thing in
both blocks and the two still read as the same value in greyscale. Any future room that needs to
show a quantity does it the same way: tone within the ink that says *who*, never a hue that says
*how good*.

**A point of view may not change a reading.** The blueprint plan, the dollhouse section and the
night-to-day light move the camera, take the furniture away or wash the whole frame - and the
wash is one flat pass over everything, identical for every ink, so a tribe can never come out of
dawn brighter than the other. None of the three may touch a number, and none of them does.

## The four rules of the look

1. **Every fill is a halftone of light.** Knock out to paper (black), then screen an ink on top
   as a dot pattern at a tone 0–1, composited additively (`screen`/`lighter`). No flat fills.
2. **Plates don't line up.** Each ink sits ~1px off register and at its own screen angle; the
   moiré is part of the print.
3. **Lines are drawn by hand.** Every path is resampled and wobbled with noise; outlines are
   `ghost` or the object's ink, 1.0–1.6 wide.
4. **It boils, and it glows.** The frame redraws at 12 fps with the wobble reseeded every 4
   frames, and anything alive — a fly, a screen, a lamp — carries a soft halo of its own ink.

## Characters are flies

Every character in every room is a **fly with wings**: the scientist in the Lab, the traders on
the floor, the guard at the vault. Never a person, never a human silhouette. A fly character is
an isometric body, a head with two big compound eyes, six short legs and two wings that flicker
every frame at their own phase. Tribe flies are their tribe's ink; staff flies are `slate`
with `ghost` eyes, so they never compete with the tribes for colour.

## Type

Hand-lettered: a stencil alphabet drawn as polylines through the same wobbly pen as everything
else, so signs boil with the walls. On the posters the headline is set huge — it is the
image — and the three stats are set big and plain beneath it. No web fonts in the world itself.

## What this style refuses

- No gradients except a lamp's or a screen's halo. No blur filters. No drop shadows.
- No people. No colour that means nothing. No tribe colour used to mean "good".
- No decorative numbers: every figure on screen or on a poster is read out of `runs.json`
  (`visuals/hq/data-contract.md`), which comes from the logs — PLAN.md rule 8.
