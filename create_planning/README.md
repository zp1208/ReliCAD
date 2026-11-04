# Planning Module Layout

This directory separates two independent nodes by responsibility.

## Active node domains

- `requirements_clarification/`
  - Stage 1 intent parsing, ambiguity handling, and `<SUMMARY>` generation
  - Own `node.py`, `skills/`, `schemas/`, `prompts/`
- `checklist_generation/`
  - Stage 1 checklist candidate generation, normalization, and `<CHECKLIST_JSON>` assembly
  - Own `service.py`, `skills/`, `schemas/`, `prompts/`
- `model_planning/`
  - Stage 2 modeling-plan generation
  - Own `node.py`, `skills/`, `schemas/`, `prompts/`

## Entry points

- Stage 1 entry: `planning.requirements_clarification.node.ingest_input`
- Stage 2 entry: `planning.model_planning.node.planning_node`

## Message protocol

- Stage 1 emits one message containing both:
  - `<SUMMARY>...</SUMMARY>`
  - `<CHECKLIST_JSON>...</CHECKLIST_JSON>`
- Stage 1 builds `<CHECKLIST_JSON>` from structured intent plus checklist-generation normalization.
- Stage 2 consumes only the `<SUMMARY>` block.
- Validation consumes both tags from state history.

## Docs

- `docs/update_log/` stores planning refactor logs
