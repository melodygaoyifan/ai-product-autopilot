# The demo reel

The two scripts that compose the demo video from screenshots of a **real
run**. They lived in `/tmp` until now, with one machine's home directory
baked into them, which meant the next person to want a demo — including
future me after a reboot — would have started from nothing.

Nothing here captures screens. Frames come from actually driving the
Studio; these scripts caption, time and assemble what a run produced. That
ordering is the point: the reel can only show what the product did.

## Inputs

| variable | meaning | default |
|---|---|---|
| `AVS_DEMO_SRC` | directory of raw screenshots from a real run | `~/Downloads/autoproduct-demo-frames` |
| `AVS_DEMO_WORK` | scratch directory for composed frames, audio and ffmpeg lists | `/tmp/avs-demo` |
| `AVS_DEMO_OUT` | the finished mp4 | `~/Downloads/avs-yc-demo-vo.mp4` |

Frame file names are listed in `SEQUENCE` (in `build_demo.py`) and
`SEGMENTS` (in `build_voiceover.py`); a missing frame is a hard error
rather than a silently shorter video.

## Running them

```bash
uv run --with pillow python scripts/demo/build_demo.py       # captioned frames + concat list
uv run python scripts/demo/build_voiceover.py                # timing, scratch VO, mp4
```

`build_voiceover.py` needs `ffmpeg`/`ffprobe` on PATH and macOS `say` for
the scratch narration track. **The scratch track is a placeholder** — the
shipped reel is meant to carry a human voice; `narration.txt` is the script
to record against, with the timecodes that actually shipped.

## The rules these encode

- **Captions describe only what is visible in the frame.** Frames 04 and 05
  both show zero modules built, so neither is captioned as mid-build
  progress, and no frame is captioned as a retry because none shows one.
- **Timing is derived, not guessed.** Each segment is held at least as long
  as its line takes to speak, plus lead-in and tail, and never shorter than
  the silent cut. Over the 180s cap is a hard error, not a trim.
- **The report frame shows a run that partly failed.** A demo you can only
  pass is marketing; that frame is the one that makes the rest credible.
