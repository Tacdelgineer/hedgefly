# Neon riso — the look

A risograph run on black stock with fluorescent drums. Isometric cutaway rooms, halftone grain,
hand-wobbled lines, plates that do not quite line up — printed in light instead of ink.

It borrows the *technique* of risograph printing, not anyone's artwork. Draw original rooms.

## The idea

Every surface is a halftone of light. Walls are a sparse dot screen in a dim ink, floors a
denser one, and anything that matters glows. Where two plates overlap they **add**, the way
light does, instead of darkening the way ink does — so overprints brighten toward white rather
than muddying toward black. That one inversion is what makes it read as neon rather than as a
print scan.

## Paper and inks

`lib/neon-riso.js` defines these. Do not add a colour without giving it a meaning first.

| token | value | what it is for |
|---|---|---|
| paper | `#07070b` | near-black stock with a faint violet cast; **never pure black** |
| `cyan` | `#27f2d2` | a subject |
| `magenta` | `#ff3d9a` | the subject it is compared against |
| `gold` | `#ffc93c` | the one thing being followed through the story |
| `amber` | `#ff7a1a` | the held-back thing: what is sealed, locked, or not yet revealed |
| `slate` | `#5b6cff` at low tone | architecture: walls, floors, furniture, the building |
| `ghost` | `#d8dcff` at low tone | linework, small type, and anything outside the comparison |

### Binding colours to a project

Write the table out for the project before drawing, with the project's own nouns in the
right-hand column. A colour with no entry is a bug. For example:

| token | this project |
|---|---|
| `cyan` | the real tribe, and nothing else |
| `magenta` | the scrambled tribe, and nothing else |
| `gold` | the hero lineage alone |
| `amber` | the locked test set: the vault, its seals, its warnings |

**Colour means who, never how good.** The two compared colours must be equally bright and
equally saturated — check them in greyscale, where they should read as the same value. If one
side's colour looks like the winner's, the comparison is rigged before any data is shown. The
same goes for tone: one subject is never printed at a higher tone than the other.

## The four rules of the look

1. **Every fill is a halftone of light.** Knock out to paper, then screen an ink on top as a
   dot pattern at a tone 0–1, composited additively. No flat fills.
2. **Plates don't line up.** Each ink sits about a pixel off register and carries its own screen
   angle. The moiré is the point, not an artefact.
3. **Lines are drawn by hand.** Every path is resampled and wobbled with noise. Outlines are
   `ghost` or the object's own ink, 1.0–1.6 wide.
4. **It boils, and it glows.** The frame redraws at 12fps with the wobble reseeded every 4
   frames, and anything alive — a character, a screen, a lamp — carries a soft halo of its ink.

## Rooms

A room is a **cutaway box**: a floor and two walls, the near walls removed so the camera can
see in. `pen.shell(room)` draws it. Rooms sit on a grid (`col`, `row`) with a gap between, so
the world reads as a building seen from above and to the side.

Furnish before you wire data. A room with only a chart on the wall looks like a slide; a room
with a desk, a lamp, a plant, a rug and somebody working in it looks like a place that happens
to contain a chart. `lib/neon-riso.js` carries `box`, `table`, `chair`, `rug`, `lamp`, `plant`,
`window`, `bookcase`, `books` for exactly this.

## Characters

Every character is a **fly with wings** — `pen.fly(i, j, z, {...})`. Never a person, never a
human silhouette. A fly is an isometric body, a head with two big compound eyes, six short legs
and two wings that flicker each frame at their own phase.

A character belonging to one of the compared subjects wears that subject's ink. Staff and
bystanders are `slate` with `ghost` eyes, so they never compete for colour.

If flies are wrong for the project, swap the character — but keep it non-human and keep it one
shape throughout. The point is that the world has inhabitants and they are all of a kind.

## Type

Hand-lettered: a stencil alphabet drawn as polylines through the same wobbly pen as everything
else, so signs boil with the walls. `text(pen, str, at, size, opts)` and
`textCentred(...)`; `opts.wall` of `'i'` or `'j'` shears the lettering onto a wall plane.

Headlines are set huge — the lettering *is* the image. Supporting figures go big and plain
beneath. No web fonts in the world itself.

## What this style refuses

- No gradients except a lamp's or a screen's halo. No blur filters. No drop shadows.
- No people. No colour that means nothing. No subject's colour used to mean "good".
- No stock images, no AI images, no photographs. Every mark is drawn in code.
- **No decorative numbers.** Every figure on screen is read out of the data file. A number
  typed into the page is the one bug this style cannot survive.
