---
name: shared-machine
description: >
  Share one machine politely with the person at it and with other agent
  sessions: check free CPU, memory and GPU before heavy work (builds, renders,
  benchmarks, large model loads), run it at lower priority with a note on a
  shared board, and tell other local sessions what you are about to run. Use
  before starting anything that keeps the CPU or GPU busy for more than a
  minute, or when the machine feels slow.
license: MIT
---

# Shared machine

The person at the machine and several agent sessions often share one computer. A build on every core makes the person's desktop lag; two GPU benchmarks at once spoil each other's numbers; two big jobs can run out of memory. This skill gives sessions a way to look before they start and to tell each other what they are running.

It needs an agent that can run commands on the machine, such as a CLI coding agent. Cloud sessions run on other machines, so they can ignore it.

The script is `scripts/machine.py` next to this file (Python 3, standard library only). Below, `machine.py` means that path.

## Ground rules

The board informs; it does not block. A guard that blocks invites a way around it, so nothing here stops a command.

- When something does not fit (too few free cores, a GPU benchmark already running, memory or VRAM would go over a limit), wait or ask the user. Do not squeeze it through another way.
- Do not stop, pause or reprioritise processes you did not start. Ask the user.
- The person at the machine comes first. If they say the machine is slow, look at `machine.py status` and offer to pause or lower your own work.
- Silence from another session is not a yes. If a conflict matters, ask the user.
- The numbers here are defaults. The user changes them in the config file (below).

## Before heavy work

1. `machine.py status` shows free cores, memory, GPU use, and what other sessions put on the board.
2. `machine.py check --cpu 8` (add `--mem`, `--vram`, `--gpu-bench` as they apply) prints `ok`, or the reasons to wait or ask.
3. Start it through the board:

   ```bash
   machine.py run --what "build" --cpu 9 -- ninja -j9
   ```

   `run` puts a claim on the board, starts the command at lower priority (`nice`, default 10), and removes the claim when the command ends. `machine.py jobs` prints a suggested `-j`: the cores, minus some kept free, minus what others claimed.

For work that `run` cannot wrap (a GUI app, a job started elsewhere), use `machine.py claim --what "render" --hours 3` (or `--pid <pid>`) and `machine.py release <id>` when done.

What counts as heavy is your call: roughly, anything that keeps many cores or the GPU busy for more than a minute, or needs a large share of memory.

## Telling other sessions

**Claude Code (recommended).** Claude Code can list the other Claude Code sessions running on the same machine and send them a message (the `ListAgents` and `SendMessage` tools). Before heavy work, or when the board shows something that clashes with your plan, send the other session a short message: what you will run, roughly how long, what it uses. They read it in their own conversation and can answer. Do not wait on an answer as if it were permission.

**Other agents, and between different agents.** Leave a note on the board, which every session sees in `machine.py status`:

```bash
machine.py --session my-project say "rendering at 20:00 for about an hour, GPU busy"
```

Use both when sessions from different agents share the machine.

## Config

`~/.config/shared-machine/config.json` (all keys optional):

```json
{
  "keep_free_cores": 2,
  "nice": 10,
  "vram_limit_mib": 9000,
  "gpu_bench_max": 1,
  "note_hours": 24
}
```

- `keep_free_cores`: cores left for the person and everything else. Default: a quarter of the cores, at least 2. On a machine with many cores, lowering priority alone may already be enough.
- `vram_limit_mib`: a ceiling for total GPU memory use. Default: none.
- `gpu_bench_max`: GPU benchmarks at once. Default 1, so the numbers stay comparable.

The board lives in `$XDG_RUNTIME_DIR/shared-machine/` (cleared at reboot), or a folder in the temp directory. `SHARED_MACHINE_BOARD` overrides it, and `SHARED_MACHINE_SESSION` sets the name shown for this session (default: the folder name).
