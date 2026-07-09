---
name: generate-profile
description: Generate the LingoLoop learning_profile.md report from the local SQLite DB — overall stats, top-10 weaknesses, and recently mastered items — for Context Injection into an LLM tutoring chat. Use when the user asks to "generate my profile", "update my learning profile", "check my LingoLoop progress/weaknesses", or before starting a study conversation.
---

# Generate LingoLoop Learning Profile

This skill runs the LingoLoop profile generator, which reads `data/lingoloop.db`
and writes `learning_profile.md` to the project root. That file is meant to be
pasted into the user's next LLM chat so the tutor teaches to their weaknesses.

## Steps

1. From the project root, run the generator:

   ```bash
   uv run python src/scripts/generate_profile.py
   ```

   If the database does not exist yet, seed dummy data first (or tell the user
   to import real data via the dashboard):

   ```bash
   uv run python src/scripts/seed_dummy.py
   ```

2. Read the generated `learning_profile.md` and summarize for the user:
   - Overall mastery rate.
   - The top weaknesses (highest `wrong_count`) — these are what the next
     conversation should drill.
   - Recently mastered items — candidates for more advanced usage.

3. If the user is about to start a study session, offer to hand them the
   ready-to-paste Context-Injection block (the top of `learning_profile.md`).

## Notes

- Mastery threshold is `consecutive_correct >= 3`.
- The report is deterministic; re-run any time the DB changes.
- Do **not** commit `learning_profile.md` (it is gitignored and personal).
