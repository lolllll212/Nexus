---
description: Hand off completed work to another agent or the user with a structured summary.
agent: opencode-application
---

Create a handoff summary for the work just completed.

Use this exact format:

```
HANDOFF
  task: <one line>
  branch: <branch name>
  files: <comma separated>
  verify: <the command you ran + result>
  notes: <anything the next agent must know>
```

Then run `git add -A && git commit` with a message following the convention in `docs/AGENT_COORDINATION.md`.

$ARGUMENTS