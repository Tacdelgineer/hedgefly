---
name: neon-riso-fly
description: Build an explorable isometric "world" of cutaway rooms drawn entirely in code on one HTML canvas, in a neon-risograph look - halftone dots on near-black paper, misregistered plates, hand-wobbled lines, 12fps boil - where each room is driven by a JSON data contract and the whole thing can be filmed headless to PNG frames and mp4, wide and vertical. Use when someone wants to turn a dataset, a pipeline, a simulation or an experiment into a explorable diorama, a "room by room" explainer, a data-driven animated world, riso/halftone/screen-print isometric art, or B-roll for a video about their own numbers. Not for UI work, ordinary charts, or slide decks.
---

# Neon riso rooms

A world made of isometric cutaway rooms, drawn with one pen on one canvas, where **every number
on a wall is read out of a data file** rather than typed into the page. Rooms are the chapters:
the camera moves from one to the next, and the same page can be explored by hand, embedded, or
filmed shot by shot into mp4.

The look: a risograph run on black stock with fluorescent drums. Halftone dots everywhere,
plates a pixel out of register, lines wobbled by noise, the whole frame boiling at 12fps.

## When to use this

Reach for it when someone has **their own numbers** and wants them to become a place: a
simulation to replay, an experiment with generations or stages, a pipeline with distinct
phases, a system with parts worth walking through. It suits anything that has *chapters*.

Do not reach for it for dashboards, product UI, ordinary charts, or slides. It is slow to draw
and deliberately textured; that is the wrong tool for a table of numbers.

## What is in here

| file | what it is |
|---|---|
| `lib/neon-riso.js` | the whole drawing core: pen, inks, halftone screens, isometric shells, fly characters, stencil type. Copy it in unchanged. |
| `style.md` | the look, and the one rule that keeps it honest: colour means *who*, never *how good*. Read before choosing any colour. |
| `data-contract.md` | the pattern that keeps numbers out of the page source. Write one of these first. |
| `example/index.html` | a complete one-room world, working, reading `example/data.json`. Start by copying this. |
| `example/data.json` | a tiny contract instance, so the example runs with no project attached. |
| `scripts/record_hq.mjs` | films any such page headless: PNG frames plus mp4, wide and vertical. |
| `scripts/pagekit.mjs` | shared plumbing `record_hq.mjs` needs (Chrome, ffmpeg, page inlining). |

## How to start

1. **Write the data contract first.** Before drawing anything, decide what one JSON file has
   to contain for every room to be drawable, and write `data-contract.md` for it. A room that
   needs a number the contract does not carry is a room that will end up with a number typed
   into it, and that is the failure this whole pattern exists to prevent. See
   `data-contract.md` for the shape and the reasoning.

2. **Copy the skeleton.** Into the project:

   ```
   visuals/lib/neon-riso.js      <- from lib/, unchanged
   visuals/world/index.html      <- from example/, then edited
   visuals/world/data.json       <- written by the project's own exporter
   scripts/pagekit.mjs           <- from scripts/
   scripts/record_hq.mjs         <- from scripts/
   ```

   `example/index.html` loads `../lib/neon-riso.js` through an HTML comment marker:

   ```html
   <!--NEON-RISO--><script src="../lib/neon-riso.js"></script><!--/NEON-RISO-->
   ```

   Keep that marker exactly as it is. The recorder and any standalone build replace it with an
   inlined copy of the core plus the data, which is how the page runs from a `file://` URL with
   no server.

3. **Write the exporter.** A script in the project's own language that reads its real outputs
   and writes the contract file. It is the only bridge; nothing in the page reads the project's
   raw data directly.

4. **Add rooms one at a time.** Each is a `room({...})` call with a `draw(pen, t, R)`. Give it
   a shape and its furniture first, then wire its numbers. `example/index.html` has one fully
   worked room with the parts labelled.

5. **Serve it** (`python -m http.server` from the project root, then open
   `visuals/world/index.html`), because a page that fetches its data needs http. The recorder
   does not: it inlines everything.

6. **Film it** once the rooms hold real numbers:

   ```
   node scripts/record_hq.mjs --page visuals/world/index.html --data visuals/world/data.json
   node scripts/record_hq.mjs --page visuals/world/index.html --shapes wide --only vault --seconds 10
   ```

   Output: `results/film/<shape>/<shot>/frame_00001.png ...` plus `<shot>.mp4` per shot, when
   an ffmpeg that can write H.264 is on PATH (`apt install ffmpeg`, or `winget install ffmpeg`
   on Windows). Without one it writes VP8 `.webm` previews and prints the command to encode the
   frames elsewhere. `$HEDGEFLY_FFMPEG` overrides the choice.

## The control surface a page must expose

`record_hq.mjs` drives a page through one global. A page that defines it can be filmed; a page
that does not, cannot. The minimum:

```js
window.__hedgefly = {
  ready: false,                  // flip true once the data has loaded and the first frame drew
  step(ms){ ... },               // advance the virtual clock by ms and draw exactly one frame
  shot(kind, arg, ms){ ... },    // 'room' + a room id, 'building', 'hero'; ms = tween length
  rooms: () => ['lab','vault'],  // the room ids, in the order the film should visit them
};
```

Useful additions, each unlocking shots in the recorder:

```js
  play(on){ ... }                // let the world advance its own state (generations, stages)
  stage(n){ ... }                // jump to a given step of the data, for a scrubbed shot
  cam(x, y, zoom){ ... }         // set the camera directly, for a push or a track
  frame(id) => {x, y, zoom}      // the default framing of a room, so a shot can be built from it
  spot(id, i, j, z) => {x, y}    // a point inside a room, in world pixels, to aim at
```

**The virtual clock is the whole trick.** The page reads time from
`window.__HEDGEFLY_VCLOCK__` when it is set, rather than from `performance.now()`:

```js
const NOW = () => window.__HEDGEFLY_VCLOCK__ != null ? window.__HEDGEFLY_VCLOCK__ : performance.now();
```

The recorder sets it, steps it by exactly `1000/fps` per frame, and screenshots after each
step. A recording is then identical every time and cannot drop a frame however slowly the
capture runs. Take the `?record` handling in `example/index.html` verbatim.

## Rules that keep it honest

- **Every number on screen comes from the data file.** Not from a constant in the page, not
  from the author's memory. If a wall shows a count, the contract carries that count. Grep the
  page for digits inside quoted strings before shipping; anything that turns up is either a
  label or a bug.
- **Colour means who, never how good.** Two things being compared must be equally bright and
  equally saturated. Check in greyscale. See `style.md`.
- **The page replays, it never computes.** No simulation, no re-derivation, no arithmetic
  beyond what it takes to draw a value the contract already holds.
- **Every mark is drawn in code.** No stock images, no AI images, no web fonts in the world
  itself. The type is a stencil alphabet in `lib/neon-riso.js`.

## Credit

The isometric-diorama idea and the risograph treatment follow Kevin Ngo's "a small light, room
by room" as *technique*, not as artwork to reproduce. Draw original rooms.
