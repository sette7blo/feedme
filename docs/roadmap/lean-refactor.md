# Feedme Lean Refactor Roadmap

## Goal

Make Feedme easier for humans and agents to modify while reducing stale docs, AI token/image spend, duplicated code, and oversized files.

## Tracking model

- This roadmap is the high-level source of truth.
- GitHub issues are executable phase-sized work units.
- Pull requests should close one phase issue at a time when practical.
- `CHANGELOG.md` is only for user/self-hoster-visible changes, not every internal cleanup.

## Principles

- Extract by domain, not by tiny helper.
- Prefer broad predictable modules over many small files.
- Keep the agent entrypoint short and route to deeper docs only when needed.
- Avoid hardcoded model recommendations; model availability changes.
- Preserve Flask + SQLite + vanilla JS, with no frontend build step.
- Keep runtime behavior stable unless a phase explicitly says otherwise.
- No secrets, personal recipe data, `.env`, `VERSION`, `chef.db`, or `CLAUDE.md` in git.

## Phase status

- Phase 1: Done — [#51](https://github.com/sette7blo/feedme/issues/51)
- Phase 2: Done — [#52](https://github.com/sette7blo/feedme/issues/52)
- Phase 3: Planned — [#53](https://github.com/sette7blo/feedme/issues/53)
- Phase 4: Planned — [#54](https://github.com/sette7blo/feedme/issues/54)
- Phase 5: Planned — [#55](https://github.com/sette7blo/feedme/issues/55)
- Phase 6: Planned — [#56](https://github.com/sette7blo/feedme/issues/56)
- Phase 7: Planned — [#57](https://github.com/sette7blo/feedme/issues/57)

## Phases

### Phase 1 — Lean Feedme docs and remove stale model guidance
Status: Done
GitHub issue: [#51](https://github.com/sette7blo/feedme/issues/51)

Goal: Reduce agent context cost and stale guidance by making the project docs easier to scan and less tied to old model IDs.

Acceptance:
- [x] `CLAUDE.md` is short enough to serve as an agent entrypoint, not an encyclopedia.
- [x] Docs describe model capabilities instead of prescribing stale model IDs.
- [x] Settings placeholders use capability-based text and avoid stale model IDs.
- [x] No secrets or personal runtime data are added to git.

### Phase 2 — Centralize AI provider and model config
Status: Done
GitHub issue: [#52](https://github.com/sette7blo/feedme/issues/52)

Goal: Make AI model/base-url lookup come from one backend source so defaults cannot drift across routes/modules.

Acceptance:
- [x] AI model defaults/fallbacks live in one backend place.
- [x] Recipe, image, vision, nutrition, and meal-plan AI paths use the shared helper.
- [x] Existing `.env` keys continue to work.

### Phase 3 — Reduce AI token and image-cost paths
Status: Planned
GitHub issue: [#53](https://github.com/sette7blo/feedme/issues/53)

Goal: Lower AI spend/latency in paths that scale with recipe count, pasted text size, or uploaded images.

Acceptance:
- [ ] Meal planning sends a bounded shortlist instead of the whole large library.
- [ ] Camera import no longer always sends high-detail full-size images by default.
- [ ] Image generation can fail or be disabled without blocking recipe save.

### Phase 4 — Slim server route file with broad domain modules
Status: Planned
GitHub issue: [#54](https://github.com/sette7blo/feedme/issues/54)

Goal: Keep `server.py` mostly as route wiring while avoiding a pile of tiny backend files.

Acceptance:
- [ ] `server.py` is materially shorter and easier to scan.
- [ ] Moved behavior remains covered by the same routes.
- [ ] No micro-file fragmentation.

### Phase 5 — Consolidate import and recipe normalization logic
Status: Planned
GitHub issue: [#55](https://github.com/sette7blo/feedme/issues/55)

Goal: Reduce duplicated RSS/URL/text/camera recipe parsing and image handling while preserving import behavior.

Acceptance:
- [ ] Common recipe normalization lives in one predictable place.
- [ ] RSS and URL import paths produce equivalent normalized schema fields.
- [ ] Saving a recipe does not needlessly re-read the just-written JSON when avoidable.

### Phase 6 — Add batch endpoints for bulk recipe and meal-plan actions
Status: Planned
GitHub issue: [#56](https://github.com/sette7blo/feedme/issues/56)

Goal: Replace frontend request storms with explicit batch APIs that are easier to reason about and recover from.

Acceptance:
- [ ] Bulk frontend actions use one request per bulk operation.
- [ ] API returns enough detail to show success/failure counts.
- [ ] Existing single-item endpoints still work.

### Phase 7 — Lean frontend rendering helpers without adding a build step
Status: Planned
GitHub issue: [#57](https://github.com/sette7blo/feedme/issues/57)

Goal: Reduce duplicated recipe-card markup, inline handlers/styles, and full-grid churn while keeping vanilla JS/no build step.

Acceptance:
- [ ] Recipe cards render through shared helpers instead of repeated large template blocks.
- [ ] Visible behavior remains the same.
- [ ] Frontend files get easier to scan, not fragmented into many tiny scripts.

## Completion rule

When a phase PR merges:

1. Close the linked GitHub issue via the PR body (`Closes #N`).
2. Update this roadmap status from `Planned` to `Done`.
3. Add a `CHANGELOG.md` entry only if the phase affects users/self-hosters.
4. Avoid creating follow-up issues for tiny helper cleanup unless the task is independently valuable.
