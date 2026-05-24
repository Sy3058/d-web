# Commit Guide

## Core Principle

> One commit = one logical change.
> Every commit must be independently revertable.

## Commit Message Format

    [PREFIX] type: subject (50 chars max)

    body (optional, wrap at 72 chars)
    - What changed and why
    - How is implied by the code itself

## PREFIX

| PREFIX   | Target                                |
|----------|---------------------------------------|
| [BE]     | Backend (FastAPI)                     |
| [FE]     | Frontend (Astro)                      |
| [ADMIN]  | Admin page (React)                    |
| [INFRA]  | Docker, CI/CD, Caddy                  |
| [COMMON] | Cross-cutting: docs, root configs, .githooks, .claude |

## Types

| Type       | Description                        |
|------------|------------------------------------|
| feat       | New feature                        |
| fix        | Bug fix                            |
| refactor   | Code change, no behavior change    |
| test       | Add or update tests                |
| docs       | Documentation only                 |
| style      | Formatting, linting                |
| chore      | Build, dependencies, config        |
| perf       | Performance improvement            |

## Examples

Good:

    [BE] feat: add episode purchase endpoint
    [FE] fix: viewer image not loading on mobile
    [BE] refactor: extract signed URL generation to service layer
    [INFRA] chore: add GitHub Actions deploy workflow

Bad:

    fix bug                     ← no PREFIX, no type, vague
    [BE] feat: Add stuff        ← too vague
    [FE] update viewer          ← no type

## Commit Checklist

- [ ] One purpose per commit
- [ ] Message readable without opening the diff
- [ ] Reverting this commit won't break anything else
- [ ] Changed files under 5 (exceptions: formatting, restructuring)
- [ ] Test code committed separately from feature code

## When Large Commits Are OK

- Full directory restructuring
- Dependency version upgrades
- Bulk lint/format apply (style commit)

> Even then: keep it separate from feature commits.