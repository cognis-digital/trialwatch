# Demo 01 - Basic clinical-trial diff

This demo shows TRIALWATCH detecting real-world clinical-trial changes between
two snapshots taken at different times (e.g. last week's export vs today's).

## Files

- `snapshot_old.json` - baseline (a list of trials)
- `snapshot_new.json` - fresh export with several changes

## What changed between the two snapshots

| NCT          | Change                                                        |
|--------------|---------------------------------------------------------------|
| NCT01000001  | Status `Recruiting` -> `Terminated`  (**critical**)           |
| NCT01000002  | Enrollment `100` -> `300`  (+200%, **warning**)               |
| NCT01000003  | Phase `Phase 1` -> `Phase 2`, completion date moved (**info**) |
| NCT01000004  | Removed from feed entirely (**warning**)                      |
| NCT01000005  | Brand-new trial added (**info**)                              |

## Run it

```bash
# Human-readable table
python -m trialwatch diff demos/01-basic/snapshot_old.json demos/01-basic/snapshot_new.json

# JSON for CI / jq piping
python -m trialwatch diff demos/01-basic/snapshot_old.json demos/01-basic/snapshot_new.json --format json
```

## Expected result

- The table lists 6+ changes, with the `Terminated` status flagged `[CRIT]`.
- Because there is a critical change, the process exits with code **1**
  (a CI gate would alert).
- With `--fail-on critical` it still exits 1; with `--fail-on info` it also
  exits 1. Only if there were no qualifying findings would it exit 0.
