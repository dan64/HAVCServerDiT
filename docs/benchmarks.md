# Benchmarks

Every config the project ships, timed on **one clip**, with the same procedure.
This page exists so a speed figure can be traced back to a measurement and
reproduced.

> **One clip is not the stack.** These numbers rank the configs against each
> other on a 15-frame piece of footage at 0.62 Mpx. They are not a promise about
> your material: a config that looks quick here can lose on a different scene,
> and the per-backend notes in [Backends](backends.md) quote a larger workload.
> **The step count differs between rows and is not logged** — see below.

## The dataset

| | |
| --- | --- |
| Clip | `gui\samples\sample_bw.mp4`, 15 reference frames |
| Frame size | **920 × 672 (0.62 Mpx)** |
| Source | the GUI's own *Colorize* runs, one session per config |
| Seed | fixed (42), set by the client |
| Steps | **the GUI panel's value — not recorded per run** (see the caveat below) |
| Era | **2026-10-15 → 2026-10-21**, i.e. every session on the same stack (DynamicVRAM included) |
| GPU | RTX 5070 Ti, 16 GB, driver 617.42 |
| Timing | **end to end**: phase A + phase B, wall clock, first frame included |

"End to end" is deliberate. The GUI prints `Done! … (x s/image, infer only)`,
and that figure is **phase B only** when a split ran: it leaves out the text
encoder, which is exactly the expensive part of the split. The wall clock from
the phase-A marker to the `Done!` line is what a user actually waits for, and
that is what this table reports.

**The step count is recorded only when it was typed into the task name.** The
GUI logs the config and the times, not the *Colorization Steps* value — that is
one panel setting applied to every run, not a per-config default. The two `flux3`
rows carry it because the run was labelled `flux3_klein_6b_int8 (6 steps)` and
`(8 steps)`, and the data agrees (phase B 25 s vs 32 s with phase A identical at
48 s both times). Every other row ran at whatever the panel held that day, and
the log cannot tell us which. It was very likely the shipped default of **2** —
the figures line up with independent 2-step measurements (`qwen21_viggle-soft_int8`
3.07 here against 2.88 measured directly, `flux2_klein_4b_int8` 1.67 against the
author's 2-step field runs) — but that is inference, not evidence. Treat a row's
step count as "probably 2, unverified" unless the name says otherwise.

## Results

| # | Config | s/image | Flow |
| -: | ------ | ------: | ---- |
| 1 | `
klein_4b_int8` | **1.67** | paired split |
| 2 | `qwen-2509-nunchaku-fast_fp4` | 2.07 | paired split |
| 3 | `qwen-2511-nunchaku-fast_fp4` | 2.33 | paired split |
| 4 | `qwen21_turbo-fast_int8` | 2.67 | paired split |
| 5 | `flux2_klein_9b_int8` | 2.80 | paired split |
| 6 | `qwen21_viggle-soft-fast_q4` | 2.80 | paired split |
| 7 | `qwen21_viggle-soft_int8` | 3.07 | single split — **the shipped default** |
| 8 | `qwen21_viggle-sharp_int8` | 3.40 | single split |
| 9 | `qwen-2509-nunchaku_fp4` | 3.67 | single split |
| 10 | `qwen_nunchaku_fp4` | 3.74 | live path |
| 11 | `longcat_gguf-fast_q3` | 4.13 | paired split |
| 12 | `qwen-2511-nunchaku_fp4` | 4.60 | single split |
| 13 | `qwen21_turbo_int8` | 4.67 | single split |
| 14 | `flux2_dev_int4` | 4.80 | paired split |
| 15 | `flux3_klein_6b_int8` (6 steps) | 4.87 | paired split |
| 16 | `qwen21_viggle-soft_q4` | 4.93 | single split |
| 17 | `flux3_klein_6b_int8` (8 steps) | 5.33 | paired split |
| 18 | `qwen-2511_int8` | 5.93 | single split |
| 19 | `qwen-2511-fast_q3` | 5.93 | paired split |
| 20 | `flux2_dev_fp8` | 6.67 | paired split |
| 21 | `longcat_gguf_q3` | 7.33 | single split |
| 22 | `flux2_dev_q2` | 10.40 | paired split — **retired** (D17) |
| 23 | `qwen-2511_q3` | 10.47 | single split |

## What the table says

- **The paired `-fast` configs own the top.** Merging two frames into one canvas
  buys more than any model choice: the same family moves from 3.67
  (`qwen-2509-nunchaku_fp4`) to 2.07 (`-fast`), a 1.8× jump.
- **`flux2_klein_4b_int8` is the fastest config in the stack** at 1.67 s/image.
  It needs 8 GB of VRAM, which is why it is the installer's pick for small
  machines but not the universal default.
- **`qwen21-viggle` is the fastest option that fits 12 GB** (3.07 single split,
  2.80 with `fast_split_TE`), not the fastest overall.
- **`flux3` lands mid-field** (4.87-5.33). Its value is the prompt upsampler
  recognizing conventionally-coloured subjects, not raw speed (see the flux3
  section of [Backends](backends.md)).
- **The retired Q2/Q3 extremes are last**, by a wide margin: that is what D17
  was about.

## An anomaly, recorded on purpose

`longcat_gguf_q3` was also run on **2026-10-16** in the live path (no split) and
took **5.07 s/image** against **7.33** for the split on 2026-10-18. That is the
opposite of what the split is for, and the likely cause is the size: at 0.62 Mpx
the model does not come under VRAM pressure, so separating the phases stops
paying and only adds a second pass over the cache. The 1 Mpx measurements in
[Backends](backends.md) remain the reference for that family. It is recorded
here rather than smoothed away, because a dataset where the inconvenient runs
disappear is not a dataset.

## Reproducing it

The GUI writes one session per *Colorize* run into
`gui\samples\sample_bw_cmnet2_dt-color_log.txt`: a `SESSION STARTED` header
with the date, the task, the phase markers and the `Done!` summary. That log is
the source of every number above.

Reading it by hand means deciding, per session, whether the `Done!` figure is a
whole run or phase B only, and adding phase A back in. The maintenance
checkout's `dist/scripts/parse_gui_log.py` does it (that folder is not part of
the distributed repository, so the script is not shipped):

```
parse_gui_log.py --log <install>\gui\samples\sample_bw_cmnet2_dt-color_log.txt
                 --csv sessions.csv
```

It handles both `Done!` formats, splits the phases, marks sessions from before
2026-10-14 (the DynamicVRAM change) and can write the rows as CSV. To add a
config to this page: run it once from the GUI, append the session to the log,
re-run the script — the row appears with no changes to the code.

> Timings are wall clock on one machine. Expect the absolute values to move with
> the GPU, the driver and whatever else is running; the **ordering has been
> stable** across the sessions in this log.
