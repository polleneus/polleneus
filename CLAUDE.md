# polleneus — project guide for Claude / agents

**polleneus** is an **offline-first BLE-flooding mesh messenger** for blackout/protest conditions —
"a messenger that works when the infrastructure is down." This repo is the **simulator + design specs**;
the hardware **client** is being built and validated now. Mission test: two phones with no internet still
exchange a message, and the network keeps working as things degrade.

## Read these FIRST (orientation)
1. **`spike/PROJECT-RUNBOOK.md`** — the operational master: current state, the spike→app roadmap, the
   dev/release process, GitHub workflow, consolidated caveats, and the full document index. **Start here.**
   (It and everything under `spike/` is local/git-ignored — read it from disk; it is not in the repo.)
2. **`docs/superpowers/release-blockers.md`** — the authoritative gate list (B1–B5). **B1 (independent
   security audit) gates ALL shipping.**
3. **`docs/superpowers/campaign-p0-p6-closeout.md`** — campaign ratification, the spike→app roadmap, and open
   items.
4. **`docs/superpowers/specs/2026-06-25-polleneus-design.md`** — the parent design (§16 roadmap, 7 invariants,
   threat model). Per-phase specs live alongside it in `docs/superpowers/specs/`.
5. **`spike/LAB.md`** (local) — the hardware lab + BLE spike: devices, build toolchain, adb, test gotchas,
   measured results.

## Current state (as of 2026-06-29)
- The **P0–P6 simulator/spec campaign is DONE** — merged to `main`, CI live (`.github/workflows/`).
- Now in **Phase T (hardware transport):** the BLE spike validated discovery + point-to-point throughput on
  real phones; building the **flooding mesh node**. Transport architecture was decided via an evidence-backed
  research stop; crypto is de-risked to engineering + audit (not research-blocked).
- **No installable app ships before B1 (independent security audit).**

## How to work in this project
- **The loop:** spec → build → **in-loop adversarial review** → PR → merge. Operate with CTO/CEO autonomy;
  the human's gates are new features, spec sign-off, and merging anything that bends an invariant.
- **No guessing:** a genuine unknown triggers a **research stop** (parallel, source-cited) or a **hardware
  test** *before* building. Don't build on assumptions.
- **Honesty first:** the deadliest failure mode is **false confidence** — every claim is measured/cited or
  explicitly marked DEFERRED, and an adversarial review runs on every PR to retract overclaims before merge.
- **GitHub:** all repo work is done as the project's GitHub identity **`polleneus-dev`** (the wrapper + token
  are described in the local runbook — never in this repo). **Always open PRs with `--base main`** (default
  branch is `main`); direct pushes to `main` are blocked — use PRs. **Keep contributors' real-world identities
  out of the repo** (the identity boundary — see the local runbook).
- **Local vs public:** anything under `spike/` is **local and git-ignored** (device serials, LAN IPs, machine
  paths, operational/GitHub mechanics) and must never be committed. The public repo carries only the sanitized
  roadmap, specs, and honest caveats.
- **Session memory** (`polleneus-*` memory files) auto-loads and points back to this guide and the runbook.

## The 7 invariants & the honest posture
The protocol must preserve the 7 invariants in the parent design (byte-uniform sealed blobs, no
routing/servers, etc.). Honest limits to never overstate: a **persistent device-fingerprinted author is not
protected**; **deletion is device-local**; **running the app is a detectable membership signal**; all sim
numbers are **upper bounds**. Details: `release-blockers.md` (B3) and `docs/originator-anonymity-limit.md`.
