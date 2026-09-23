# The data contract

One JSON file is everything the world knows. The page replays it and never reads the project's
raw output, never re-runs anything, and never computes a figure it could have been handed.

Write this document **before** the first room. It is short, and writing it first is what keeps
numbers out of the page source.

## Why one file

Three things fall out of it, and they are the reason the pattern is worth the discipline:

- **Numbers stay honest.** A room can only show what the contract carries. When a room needs a
  figure the contract lacks, the fix is to export it — never to type it into the page. Once one
  number is typed in, nobody can tell by looking which of the others are real.
- **The world runs anywhere.** One file inlines into a single self-contained HTML page that
  opens by double-click, with no server and no network.
- **The drawing and the pipeline come apart.** The exporter can be rewritten, and the rooms do
  not care. Rooms can be redrawn, and the pipeline does not care.

## Shape

Top level: what is true of the whole run, then an array of **frames**, one per step of whatever
the project advances through — a generation, an epoch, a day, a stage, a release.

```json
{
  "contract_version": 1,
  "run_id": "2026-09-20-a",
  "generated": "2026-09-20T09:00:00+00:00",
  "stages": 12,
  "subjects": ["treated", "control"],
  "start_value": 1000,

  "frames": [
    {
      "stage": 0,
      "subjects": {
        "treated": {"best": 1021.14, "median": 989.35, "alive": 20, "gone": 80},
        "control": {"best": 1019.96, "median": 985.31, "alive": 20, "gone": 80}
      }
    }
  ]
}
```

Rules that make the rest easy:

- **`contract_version` is an integer, and the page checks it.** Refuse to draw against a version
  the page does not understand, with a message saying so, rather than drawing something wrong.
- **Frames are dense and ascending.** `frames[k]` is stage `k`. A room that draws a curve walks
  `frames.slice(0, current + 1)`; that one line is what makes a curve draw itself on camera.
- **Optional blocks stay optional.** A second measurement, a comparison, a final test: add them
  as blocks that may be absent, and have the room that needs one check for it and say
  "not yet" rather than throw. A world should render against a half-finished run.
- **Round on the way out.** Money to cents, ratios to four places. The page is not the place to
  decide how precise a number was.
- **Pre-thin anything long.** A 50,000-point curve is drawn on a wall a few hundred pixels
  wide. Thin it in the exporter to a few hundred points; ship the summary figures at full
  precision alongside.

## The exporter

One script, in the project's own language, that reads the real output and writes the file. It
is the only bridge. Give it the checks the page would otherwise have to make:

- counts agree with the arrays they describe;
- anything drawn as a range actually contains its own endpoints;
- identifiers referenced across blocks exist;
- and fail loudly, in the exporter, rather than shipping a file that draws wrong.

A world built against a broken file is debugged in a browser. A world built against a file the
exporter refused to write is debugged in one stack trace.

## A fake file for building against

Write a second script that emits a contract instance with invented numbers and the real shape.
Rooms can then be built and filmed before the real pipeline finishes. Mark it — a top-level
`"fake": true` that the page prints on screen — so a fake frame can never be mistaken for a
real one in a cut.

## Versioning

Bump `contract_version` whenever a room would break without a re-export, and say in this
document what changed and which pages read which version. Old worlds kept as B-roll stay
pinned to the version they were built for; do not migrate them.
