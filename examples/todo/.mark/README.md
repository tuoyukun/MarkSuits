# .mark

Multi-agent collaboration state for todo, managed by the Mark plugin.
How the workflow runs: [collaboration.md](collaboration.md).

| Path | Purpose |
|---|---|
| `config.toml` | Engine configuration (roles, gates, write scopes) |
| `collaboration.md` | How humans and agents work together here |
| `prompts/` | Dispatch prompt templates, one per scenario |
| `formats/` | Artifact formats (requirement, design, plan, handoff, verdict …) |
| `features/<id>/`, `bugs/<id>/` | One directory per ticket: status + artifacts |
| `gates/` | Human approval records (file exists = approved). Never delete |
| `locks/` | Runtime dispatch locks (not committed) |
| `.copier-answers.yml` | Template version record for `copier update -a .mark/.copier-answers.yml` |

