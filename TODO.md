# DeployGuard-Recovery — TODO

Living task list. Two sections: **Pending Work** (not done) and **Improvements**
(works, but could be better). Priority: 🔴 high / 🟡 medium / 🟢 low.

---

## A. Pending Work

### Needs Daytona credits (the sponsor story)
- [ ] 🔴 **Write `DaytonaRunner` (Seam 2)** — wrap kind inside a Daytona DinD sandbox;
      add fork + snapshot. *Most important pending item — makes Daytona essential,
      not decorative.* (~1 hr)
- [ ] 🔴 **Fork-per-lap** — every candidate fix starts from byte-identical cluster
      state. (~30 min after runner exists)

### Needs Gemini (key available ✅)
- [ ] 🔴 **Run full `train --llm gemini` → `freeze` → `eval --llm gemini`** to generate
      a real results table with LLM reasoning. (~20 min)
- [ ] 🟡 **Capture the eval output** as the demo artifact (`eval/results_*.json`).

### No keys needed
- [ ] 🔴 **Demo slides + rehearsal** — 2 slides (problem + method) + live script. (~45 min)
- [ ] 🟡 **Add `--llm gemini` coverage to `verify.py`** so the pre-demo gate tests the
      real path. (~15 min)
- [ ] 🟡 **Update docs** (README / GEMINI_SETUP) with the final demo commands.

---

## B. Improvements

### 🔴 High impact — these decide the demo
- [ ] **Fix the "all systems score 3/3" tie.** Currently rules, Gemini, and memory all
      succeed on the held-out fault → no visible winner. Add a fault where **rules fail
      but Gemini succeeds**, and ideally one where **Gemini is slow but memory is
      instant**. Without this, the learning story is invisible. *#1 priority.*
- [ ] **Capture latency + token/cost per system.** The System C pitch is "faster and
      cheaper than reasoning every time" — but we only measure success/safety. Add
      per-lap wall-clock time and Gemini token count so the table shows
      *"Memory: 0.2s, $0 vs Gemini: 3.1s, ~1200 tokens."* (~30 min)

### 🟡 Medium impact — polish and credibility
- [ ] **Smarter memory matching** — richer similarity scoring so memory generalizes to
      variations of a known fault (strengthens "learned a pattern, not a lookup").
- [ ] **Gemini determinism + robustness** — set `temperature=0`, retry on
      rate-limit/timeout, silence the AFC warning.
- [ ] **Clearer "before" state** — switch deployment to `Recreate` strategy so the
      failure is visibly dramatic on stage (avoids the `ready=True`-on-broken quirk).
      (~5 min)
- [ ] **Multiple held-out faults** — eval on 2–3 unseen faults, not one repeated.

### 🟢 Low impact — nice-to-have / stretch
- [ ] **Train a classifier** on `runs/*.json` instead of pure memory lookup (real
      weights, not just retrieval).
- [ ] **Parallelize laps** across Daytona forks (faster + shows off Daytona scale).
- [ ] **Improve the prompt** with few-shot examples of good fixes.
- [ ] **Cost/Pareto plot** for slides (success vs cost vs latency).

---

## Recommended order (if time is short)

1. **Daytona integration** — sponsor's product + rigor story.
2. **Differentiating fault + latency/cost metrics** (Improvements #1 & #2) — without
   these all three systems look identical and "learning" is invisible.
3. **Run the real Gemini eval + rehearse** — demo measured numbers, not the mock.

Everything else is polish. #1 and #2 under Improvements are the difference between
"nice harness" and "clearly better than the baseline."

---

## Done ✅
- [x] Failure Gym (kind on podman) + 4 fault injectors
- [x] Evidence collector + objective scorer (verified fails on unfixed faults)
- [x] Rule-based brain (baseline)
- [x] Memory store + memory-augmented brain + freeze
- [x] Training loop + held-out eval infrastructure
- [x] `verify.py` self-check
- [x] Gemini LLM integration (Seam 1) — tested end-to-end
- [x] Docs: README, TEAM_GUIDE, TEAMMATE_BRIEFING, FILE_GUIDE, GEMINI_SETUP
