# Canonical SW EVT template - local reference

Snapshot of the canonical Drive template named in `rules.md`
(**`[C&P Eng] Template for SW EVT doc`**, Drive ID
`1leu4U-2CMwV4EFY4NpCXHQbdeTHgLz2VUohK1o5JRSQ`). The Drive file is the
source of truth; re-fetch it if this drifts.

## `Template EVT` tab (blank form to copy)

| Section | Field | Value |
|---|---|---|
| Story/Feature info | Story/Feature | *(blank)* |
| | Story Owner | *(blank)* |
| | JIRA Link | *(blank)* |
| Build & Test environment Info | Build # | *(blank)* |
| | Branch/Pipeline | *(blank)* |
| | System info | *(blank)* |
| | Device(s) being used | *(blank)* |
| Change Impact Assessment | Select Degree of Impact | *(blank)* |
| | Describe impact | *(blank)* |
| Additional Info | *(one free row)* | *(blank)* |
| EVT Coverage | `Expected \| Results \| Note` | *(three columns only)* |

## `Impact Level Explanation` tab (EVT-7 legend)

| Level | Meaning |
|---|---|
| LOW | Minor changes that are localized, specific to a feature |
| MEDIUM | Adds new components to the system. Integration with UI and Backend. Affects 1-2 components |
| HIGH | Structural changes that impact the entire system/platform. Could potentially affect platform stability. Change affects multiple components of the SW |

## `Sample EVT` tab

A worked example (KIROS-888). Reference it, then delete it when copying
the template for a new EVT.

## `Form Responses 1` tab

Header-only, zero rows. Delete on copy.

## reponame_etw's Coverage columns

`Case Id, Expected, Results, Note`. `Case Id` is the only addition to
the template's own three columns - required because `reponame_etw` cases
live in a repo QA doc the sheet only indexes (EVT-16), not in the row
itself. `Tier`, `Error Detail`, and `Bug Ticket` are not columns.

`reponame_etw` uses `Device(s)`, not the template's `Device(s) being used`.

The Additional Info section carries `reponame_etw`'s own extra rows -
`Full test flows`, `Case document`, `Glossary and setup commands`,
`Case set version`, `Read this first` - beyond the template's one
free-form row (EVT-16 through EVT-19).
