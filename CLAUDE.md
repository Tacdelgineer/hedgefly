# Hedgefly

Read PLAN.md before doing anything. Its NON-NEGOTIABLE RULES override every other
goal, including speed and "making it work".

- Work only on the task you were given. When it's done, stop and report.
- Never read `data/btc_locked_test.parquet` anywhere except `finale.py`.
- Never train or modify brain weights.
- Every number shown to viewers must come from `runs/` logs.
- On the DGX Spark (ARM64), confirm the GPU is actually used; never silently fall back to CPU.
- If a rule blocks you, say so and ask. Don't work around it.
- Small commits with clear messages.
