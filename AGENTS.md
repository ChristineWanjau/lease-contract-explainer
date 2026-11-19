# Lease & Contract Explainer

Local-first app that explains leases and contracts in plain language, flags risky clauses, and answers questions with clause citations. Stack: LangChain + Ollama (runs locally, no data leaves the machine), FastAPI backend, Next.js frontend.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for ChristineWanjau/lease-contract-explainer (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
