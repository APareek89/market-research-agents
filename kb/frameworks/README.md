# Framework Knowledge Base — schema & ingestion contract

Gold-mine interrogation frameworks for the Agent Council review stages. Each file is ONE framework,
stored whole (never chunk a framework — it is a unit of interrogation).

## File schema (YAML frontmatter + markdown body)

```yaml
id: kebab-case-unique          # primary key
name: Human name
cluster: reasoning-qa | sizing-demand | competition-moats | innovation-growth |
         pricing-economics | gtm-adoption | decision-risk | stakeholder
origin: who/where it came from
strength: one line — what it catches that nothing else does
when_to_use: one sentence, written FOR THE ROUTER (matched against the task, not the content)
trigger_signals: [list of phrases/task shapes that should fire this lens]
reviewer: [vera] | [cleo] | [vera, cleo]   # which review stage may use it
pairs_well_with: [ids]
failure_modes_caught: [list]
```

Body sections, in order:
- **Essence** — 2-3 sentences, why this lens exists.
- **Interrogation set** — numbered questions PHRASED AS A REVIEWER CHALLENGING A DRAFT.
  These are the payload; everything else is metadata.
- **How to apply** — what a weak answer looks like; when the lens does NOT apply.
- **Output contract** — what the critique must demand from the revision.

## Ingestion contract (for the coding session)

- Parse frontmatter + body → one row per framework in Supabase (`mra_frameworks`).
- `when_to_use` + `trigger_signals` are the ROUTER surface (embed or prompt-pack these, not the body).
- Retrieval returns whole rows by id. See ../RETRIEVAL_PIPELINE_SPEC.md.
