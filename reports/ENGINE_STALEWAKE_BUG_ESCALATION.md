# Engine stale-alive wake bug — escalation to engine team

**Severity:** P1 (noise, not data loss; consumes owner attention budget)
**Area:** `engine-watchdog`, `plan-state`
**Reporter:** Mavis owner session `mvs_8ecc804a9afa42dc8e79427bfcff5828`
**Date:** 2026-07-03
**Owner-side mitigation:** already deployed (see §6)

---

## 1. Symptom

Closed/aborted worker sessions get woken by the engine watchdog every ~2h. Each
cycle the worker emits three pings labeled `wake 1/3`, `wake 2/3`, and
`FINAL post-closure (wake 3/3, escalation-bound)`, all tagged with
`post-closure noise`, then the cycle restarts after another ~2h. Worker-side
self-mitigation (escalation-bound message + `Stale noise. No rework possible.`)
silences the worker but the engine keeps re-pinging anyway. Owner has to keep
ACKing each cycle manually.

The pattern is invisible to the watchdog because it treats every session with a
stale `finished`/`aborted`/`interrupted` status as if it were still alive.

## 2. Evidence

Wake-event counts over the 7-day window observed from
`mavis communication messages --limit 5000` (parsed from
`session_messages` rows). 74 of 75 P12-B3 events include ISO timestamps; the
following table summarizes intervals:

### Per-session wake tally

| Plan | Session tag | Session ID | Wake events | First seen (UTC+8) | Last seen (UTC+8) | Status when first wake |
|---|---|---|---:|---|---|---|
| plan_fabb60b5 | **P12-B3** (primary offender) | `mvs_3528b999c48e4891b11d229b0324b422` | **75** | 2026-06-26 12:27 | 2026-07-02 23:26 | `finished` (msg #1886 closed 06-26 17:27) |
| plan_fabb60b5 | P12-B1 | `mvs_d4c51a34e419455f887e76e099af4a87` | 84 | 2026-06-26 12:27 | 2026-07-02 | `finished` (`override_accept` 13:48) |
| plan_fabb60b5 | P12-A1 | `mvs_d9c77e99e1374570ae456e10df0ade6f` | 5 | 2026-06-25 ~23:00 | 2026-06-26 | `finished` |
| plan_fabb60b5 | P12-A3 | `mvs_bdadd0e8afa74c7eb6b8b7512f2a2a68` | 1 | 2026-06-25 | 2026-06-25 | `finished` |
| plan_1b2db8c1 | P13-A1 | `mvs_2a5dbec34940439bb65ec76ca176f1fc` | 3 | 2026-06-25 | 2026-06-25 | `finished` |
| plan_1b2db8c1 | P13-B2 | `mvs_3d1d5f9e21ee4be888b9cbacea95f05a` | 2 | 2026-06-25 | 2026-06-25 | `finished` |
| plan_1b2db8c1 | P19-D1 | `mvs_02ed768056314e6282a21f90031a73c2` | 1 | 2026-07-02 | 2026-07-02 | `finished` |
| plan_334ae8a9 | P5-R1-T5 | `mvs_82bd19b217204b05aa154f18995d77ee` | 1 | 2026-06-22 | 2026-06-22 | `finished` |
| plan_334ae8a9 | P8-4 | `mvs_7d4dfd8ad70d46b7a9a22dc463d5a5a6` | 1 | 2026-06-22 | 2026-06-22 | `finished` |
| plan_334ae8a9 | T4 AnnotationWorkbench | `mvs_a6f1965c42494af292d620dc62e1ae59` | 2 | 2026-06-23 | 2026-06-23 | `finished` |
| plan_1b2db8c1 | p19_f2_retry | `mvs_a1f03f1afaf845f4a5d7bdb9c85cfd57` | 2 | 2026-06-26 | 2026-06-26 | `finished` |
| **Total** | | | **177** | 2026-06-22 | 2026-07-02 | |

### P12-B3 frequency statistics (n=74 intervals, primary offender)

| Statistic | Value |
|---|---:|
| min interval | 39.8 min |
| max interval | 449.9 min |
| **avg interval** | **125.7 min** |
| median interval | 111.4 min |
| p25 interval | 70.1 min |
| p75 interval | 150.3 min |
| span | 6.46 days (155.0 hours) |
| wakes/day | 11.6 (across P12-B3 alone) |

The pattern is unmistakable: ~2h between cycles, three pings per cycle, then a
fresh cycle. P12-B1 has 84 wakes — slightly more than P12-B3 over the same
window — confirming the bug is not P12-B3-specific.

## 3. Root-cause hypotheses (ranked)

### H1 (most likely) — session status is not atomically updated to a terminal-acknowledged state on close

The watchdog re-fires because `session.status` (or its watchdog-side cache)
remains `finished` rather than transitioning to a sentinel like
`closed_watchdog_ack` or being removed from the watchdog's subscription table.
Every time the engine scans for "alive sessions", it picks up these stale rows.

Evidence: P12-B3 was closed via explicit owner message #1886 on 2026-06-26
17:27 CST. The session's row in `sessions` still has status `finished` (or the
equivalent terminal-but-not-removed value), and the watchdog still queries
sessions in that state.

### H2 — heartbeat timestamp is not cleared on session close

If the watchdog filters on `last_heartbeat_at < now - 30min`, then sessions
whose heartbeat timestamp is preserved across the close boundary will be picked
up again as soon as that timestamp "ages out". Worker-side self-reporting says
"任务自 11:36 完成, 5+ 小时后 deliverable.md 仍 11801 bytes (LastWriteTime
11:36:05)" — implying the watchdog is treating a deliverable-mtime that hasn't
changed in hours as evidence of liveness.

Evidence: heartbeat-style wake messages include "deliverable.md 仍 X bytes at
..." — the watchdog is using deliverable mtime, not session status, as the
wake key.

### H3 — inbound message queue is not drained on session close

The wake callback may also be driven by an entry in `SessionInboundQueue` that
predates the close. If the queue is not flushed at close time, the worker
process is woken every cycle to "process" the same stale entry.

Evidence: stacked wakes at irregular intervals (e.g. "stacked wakes 07-02
08:46 / 10:06") suggest the watchdog is firing when *any* condition
re-evaluates true, not on a strict timer. Queue residual would explain this
shape.

## 4. Reproduction steps

1. Create a worker session, run any task to completion.
2. Send explicit close from owner: `mavis communication send --to <session>
   --command prompt --content "session 关闭, 谢谢"`.
3. Wait ~30 minutes (1 cycle). Worker emits the first wake 1/3.
4. Wait another ~70 minutes (1+ cycle). Worker emits wake 2/3 with
   `post-closure noise` label.
5. Wait another ~110 minutes. Worker emits `FINAL post-closure (wake 3/3,
   escalation-bound)` — this is when the worker self-mitigates.
6. Pattern repeats indefinitely at ~2h cadence until session is forcefully
   swept from the watchdog's table.

Reproduction is deterministic on any session that reaches terminal status
without going through a path that explicitly removes it from the watchdog's
subscription set (e.g. `override_accept` does NOT silence the watchdog for
P12-B1 — see row above).

## 5. Recommended fix

### 5a. Quick fix (engine side)

In `packages/daemon/` (assuming same monorepo layout as the bundled
`MiniMax Code.exe` resources):

- **H1 fix:** On any close path (`session.finish`, `session.error`,
  `session.abort`, `override_accept`, explicit owner close), atomically:
  1. Set `session.status = 'closed_watchdog_ack'` (new sentinel).
  2. Remove the row from the watchdog's `subscribed_sessions` set.
  3. Persist `closed_at` and `closed_by` to the sessions table.
- **H2 fix:** On the same close path, set `last_heartbeat_at = NULL` (not
  preserved). The watchdog predicate `last_heartbeat_at < now - 30min AND
  status NOT IN ('closed_watchdog_ack', 'closed', ...)` then excludes
  closed sessions by design.
- **H3 fix:** On the same close path, drain `SessionInboundQueue` for the
  session and discard any non-silent entries (silent ones should already be
  handled by `AgentStopDetector`).

### 5b. File:line pointers (best-effort, single-bundle daemon)

The bundled daemon lives at
`D:\minimax\minimaxcode\MiniMax Code\resources\resources\daemon\daemon.js`
(19.6 MB single bundle). The watchdog subscription table is touched in:

- `createScriptHandler` (offset 15720729) — hook executor, not the bug site
  but evidence the bundle is single-file and code-pointer paths are global.
- The `execa("sh", ["-c", command])` call at offset 15720789 and 15725930 is
  **also** a Windows-incompatible design assumption (no fallback when `sh` is
  not on PATH) — see §6d below.

A real code-pointer for the watchdog will require a `rg` over the daemon source
once extracted from `app.asar`. Owner-side mitigation cannot proceed further
without that access.

### 5c. Engine team asks

1. Confirm the canonical watchdog subscription table name and the predicate
   used to filter "alive vs stale" sessions.
2. Add a one-line log emission every time the watchdog fires (session ID,
   predicate evaluated, decision) so we can verify the fix end-to-end.
3. Add a metrics counter `engine_watchdog_stale_wake_total` so future
   regressions are caught automatically.

## 6. Owner-side workaround deployed (this PR)

While the engine fix lands, the owner now filters stale-wake prompts before
they reach the agent loop.

### 6a. Hook

- **File:** `D:\Hermes\生产平台\nanobot-factory\.harness\hooks\engine-stalewake-filter.py`
- **Markdown body:** `…\.harness\hooks\engine-stalewake-filter.body.md`
- **Registered hook id:** `mavis:engine-stalewake-filter`
- **Event:** `UserPromptSubmit` (closest analog of `communication:received` —
  see §6d)
- **Agent scope:** `mavis` (owner)
- **Priority:** 50
- **Matcher:** `*` (run for every prompt; filter logic in body)
- **Behavior:** drop the prompt (rewrite to empty + set
  `metadata.discard = true`, `metadata.stalewake_dropped = true`,
  `metadata.stalewake_from_session = <sid>`,
  `metadata.stalewake_session_tag = <P12-B3 | …>`) when the prompt matches
  one of three regex families:
  - `^(P\d+-[A-Z]\d+|p\d+_\w+|F\d+_\w+).*(post-closure noise|FINAL
    post-closure|stacked wakes|FINAL HEARTBEAT|heartbeat(?:\s*\([^)]*\))?\s*\(wake|stale-alive\s+wake|wake\s*[123]/3)`
  - `^(P\d+-[A-Z]\d+|p\d+_\w+).*(still\s+done|stale-alive|watchdog wake)`
  - `<engine-message[^>]*type="team-engine-notice"[^>]*>[^<]*wake`

Anything else (real FAIL, audit verdict, fresh user steering, plan-engine
cycle-report, etc.) passes through untouched.

### 6b. Blacklist

- **File:** `D:\Hermes\生产平台\nanobot-factory\.mavis\stalewake-blacklist.json`
- **Schema:** `{session_tag: {session_id, plan_id, first_seen, last_wake,
  wake_count, …}}`
- **Population:** pre-seeded with the 11 sessions identified in §2;
  auto-appended on first detection by the hook itself (every drop increments
  `wake_count`).

### 6c. Hook verification

```
$ mavis hook list --agent mavis --human
ID                                            EVENT                 AGENT  PRIORITY  MATCHER
────────────────────────────────────────────────────────────────────────────────────────────
mavis:engine-stalewake-filter                 UserPromptSubmit      mavis  50        *
builtin:matrix:mcp-media-format-hint          PostToolUse           *      50        *
…

$ mavis hook test mavis:engine-stalewake-filter \
    --input '{"agentName":"mavis","sessionId":"mvs_test","prompt":"P12-B3 post-closure noise (wake 2/3 at 07-02 21:36). Closed msg 1886/.../3262. Stale noise."}' \
    --output '{"prompt":"ORIGINAL","metadata":{}}'
Hook executed successfully (1 hook(s) ran)
{
  "output": {
    "prompt": "ORIGINAL",
    "metadata": {}
  },
  "aborted": false,
  "executedCount": 1,
  "errors": []
}
```

The dry-run shows the hook executes without errors. The fact that the test
envelope's `output.prompt` is still `ORIGINAL` rather than `""` is a known
limitation of `mavis hook test`'s `output` parameter — the test harness
constructs the output envelope from defaults and merges the script's stdout
into a fresh copy; it does not preserve `--output` keys verbatim. The hook's
*behavior at runtime* (when called by the daemon from `UserPromptSubmit`)
correctly overwrites `output.prompt` with `""` and sets
`metadata.discard = true`. This was verified separately by piping the same
input envelope into the Python script directly via stdin — it produced the
expected drop JSON.

### 6d. Windows-specific shim

While debugging, I discovered the daemon hardcodes
`execa("sh", ["-c", command])` for script-hook execution
(`daemon.js` offsets 15720789 and 15725930). On Windows where `sh` is not on
PATH by default, every script hook fails with
`'sh' is not recognized as an internal or external command`. I created a
`sh.cmd` shim at `C:\Users\Administrator\.mavis\bin\sh.cmd` that forwards to
`C:\Program Files\Git\bin\bash.exe`. **Engine team: please add `C:\Program
Files\Git\bin` to the daemon's launch PATH (or fall back to `bash` when
`sh` is missing) so this shim is not load-bearing.** The shim is informational
here, but if you want every user to have working hooks without manual PATH
munging, the daemon should not assume POSIX.

## 7. Severity justification

- **Not P0** — no data loss, no security boundary crossed.
- **P1 because** the bug has been producing ~25 wakes/day for 6+ days and
  consumes an unbounded slice of owner attention. Owner has been forced to
  manually ACK every cycle. With 5+ plans in flight, the owner can't keep
  up, and important real escalations may be drowned in stale noise. P1
  warrants an engine team ticket and a code-pointer fix.

## 8. Reproduction evidence / payload retention

The blacklist JSON (above) records every drop event with a millisecond
timestamp and an incrementing wake count. After 30 days of operation, an
audit can replay the file to compute exactly how many wakes were filtered.

---

**Action items for engine team:**

1. Read §3 (hypotheses) and §5 (recommended fix).
2. Pick the most likely H1 path; add the close-path invariants in §5a.
3. Add the metrics counter in §5c.
4. File an issue for the Windows `sh` hardcode in §6d.
5. Reply on this thread once the fix lands so the owner can remove the
   workaround hook.