# Skills

Claude Code skills extracted from this project, kept here so they are version controlled.
Install one by copying it into `~/.claude/skills/`:

    cp -r skills/neon-riso-fly ~/.claude/skills/

## neon-riso-fly

The look and the machinery of `visuals/` packaged for reuse on any project: the drawing core,
the style rules, the data-contract pattern, a worked two-room example, and the headless
recorder. It is standalone by design and carries its own copy of the core, so it works on a
fresh project with no relation to this one.

`skills/neon-riso-fly/lib/neon-riso.js` is a copy of `visuals/lib/neon-riso.js`. When the core
changes here, refresh it:

    cp visuals/lib/neon-riso.js skills/neon-riso-fly/lib/neon-riso.js

The skill's `scripts/record_hq.mjs` and `scripts/pagekit.mjs` are the generalised siblings of
this repo's own: `--page` and `--data` are arguments rather than constants, the shot list is
built from whatever rooms a page declares, and nothing in them knows about flies or tribes.
