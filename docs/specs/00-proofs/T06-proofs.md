# T06 Proof Summary — Restructure agent prompts for prompt cache optimization

## Requirements Verified

| Requirement | Status | Evidence |
|---|---|---|
| R06.1 — Static content first, dynamic content last | PASS | T06-01-file.txt |
| R06.2 — Focus, exclusions, calibration, schema precede diff | PASS | T06-01-file.txt |
| R06.3 — Trust boundaries correctly placed in dynamic section | PASS | T06-01-file.txt |
| R06.4 — Prompt caching note with cost rationale | PASS | T06-01-file.txt |

## Files Modified

- `skills/deep-review/SKILL.md` — Agent prompt template reordered, caching note added
