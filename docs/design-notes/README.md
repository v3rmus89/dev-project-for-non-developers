# Design notes

Architecture decisions recorded BEFORE their implementation, so the
implementation (and any plan-review loop) debates trade-offs rather than
inventing architecture mid-loop — the failure mode that ran PR #10 to 7 iters
without plateauing.

Each note carries: **options considered + options rejected + acceptance
criteria**, and gets ONE focused cross-direction review (Codex reviews a
Claude-authored note, and vice versa) before the implementation lands — not
the full iterative plan-review loop.

- [`2026-05-29-pr0-fact-check-resolutions.md`](2026-05-29-pr0-fact-check-resolutions.md)
  — post-merge hardening record for PR-0 (shipped in PR #30): the four gaps a
  post-merge review found, which were fixed (containment, under-scan tests) and
  which were deferred to BACKLOG (CLI-flag verification, AI fallback).
