# global-skills

A collection of reusable **agent skills** — packaged instructions, references and
runnable scripts that teach an AI agent how to do a specific job well.

Skills here are **general purpose**. Nothing is tied to one client, project or
dataset. If a skill mentions a concrete example, it is to demonstrate a
technique, not to limit its scope.

## Available skills

| Skill | What it does |
|---|---|
| [`pbix-report-authoring`](skills/pbix-report-authoring/) | Build and edit Power BI `.pbix` files programmatically — multi-page dashboards with KPI cards, charts, tables, shape maps and navigation — by authoring the report layer directly instead of clicking through Power BI Desktop. |

## What is a skill

A skill is a folder containing a `SKILL.md` with YAML frontmatter:

```
my-skill/
├── SKILL.md        # required: frontmatter + instructions
├── references/     # optional: detail loaded on demand
├── scripts/        # optional: runnable helpers
└── examples/       # optional: working samples
```

`name` must match the folder name. `description` is what the agent matches
against to decide whether to load the skill, so it should name both *what* it
does and *when* to use it, front-loading the words a user would actually type.

```markdown
---
name: my-skill
description: Use when doing X — triggers on "x", "y". Covers A, B and C.
---

# My Skill
...
```

## Using these skills

### opencode

Install globally:

```powershell
.\install\install.ps1
```

or manually copy a skill folder to:

- Windows: `%USERPROFILE%\.config\opencode\skills\<name>\`
- macOS / Linux: `~/.config/opencode/skills/<name>/`

For a project-local copy, put it in `.opencode/skills/<name>/` in the repo.

Restart opencode afterwards — skills load at startup.

### Other harnesses

`~/.claude/skills/` and `~/.agents/skills/` are auto-scanned by several agent
tools. The same folder works unchanged.

### From a git URL

opencode can load skills straight from a repository:

```json
{ "skills": { "urls": ["https://example.com/.well-known/skills/"] } }
```

## Contributing

- Keep skills **general**. If it only works for one dataset, it belongs in that
  project's repo, not here.
- **Verify anything you claim.** The scripts ship because they were run, not
  because they look plausible. If you add a script, test it against a real file.
- Distinguish clearly between what you *verified* and what you *inferred*.
  Where a constant or property is unconfirmed, say so in the reference.
- No third-party dependencies unless unavoidable; Python scripts should run on
  a stock interpreter.
- Keep `SKILL.md` focused and push detail into `references/`.

## Licence

MIT — see [LICENSE](LICENSE). Scripts are provided as-is; test against your own
files before relying on them.