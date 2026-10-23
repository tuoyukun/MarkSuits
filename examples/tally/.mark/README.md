# .mark

Multi-agent collaboration state for tally, managed by the Mark plugin.
How the workflow runs: `mark rules collaboration`.

| Path | Purpose |
|---|---|
| `config.toml` | Facts about this project (paths, commands, write scopes); workflow defaults ship with Mark |
| `features/<id>/`, `bugs/<id>/` | One directory per ticket: status + artifacts |
| `gates/` | Human approval records (file exists = approved). Never delete |
| `locks/` | Runtime dispatch locks (not committed) |
| `template.toml` | Mark version and the answers given to `mark init` (written by Mark; do not edit) |
| `.base/` | The files as Mark last wrote them, so an upgrade can keep your edits (do not edit) |

Role agents, dispatch prompts and artifact formats ship with the plugin and update with it.
To change one for this project, add a file of the same name, which then wins:
`.claude/agents/<role>.md`, `.mark/prompts/<scenario>.md`, `.mark/formats/<name>.md`
(`mark format <name>` prints the format in effect).
