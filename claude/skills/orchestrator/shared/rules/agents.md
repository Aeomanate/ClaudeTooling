# AgentsCommon: Sub-Agent Rules

Rules governing sub-agent dispatch, isolation, and reporting. Every
persistent sub-agent loads this file as part of its MANDATORY pre-work.
Single source of truth for AGT rules.

Two agent classes exist, distinguished by naming and role, not by a
technical reuse limit - any spawned agent stays addressable via
`SendMessage` for its whole session (see AGT-1 for what that does and
does not authorize):
- **Persistent** (`orchestrator-persistent-<role>`): a role coordinator.
  Spawned once via `Agent`, reused for every later round via `SendMessage`.
  Only the orchestrator dispatches this class (AGT-1).
- **Per-task** (`orchestrator-agent-<purpose>` or a general-purpose
  sub-agent): a bounded single task. Spawned via `Agent` by the
  orchestrator or a persistent sub-agent. Runs once and returns; resuming
  it for a later round is a `SendMessage`, not a fresh spawn.

---

## AGT-1: DISPATCH-DISCIPLINE

**Statement:** At most 10 sub-agents run in parallel, each scan agent covers at most 5 source files, agents with non-overlapping file sets launch in parallel, and a full source or test file is never read in the orchestrator's or a persistent agent's own context - it goes to a sub-agent.

Only the orchestrator dispatches a persistent sub-agent
(`orchestrator-persistent-*`). No sub-agent calls `Agent` with that type, and
none `SendMessage`s another persistent name on its own initiative. Both the
orchestrator and persistent sub-agents spawn per-task sub-agents freely; a
per-task sub-agent spawns none, returning a scoping report to whoever
dispatched it. Cross-role work routes through `SendMessage({to: "main",
...})` - `"main"` is the literal target for the orchestrator's session, and
`"orchestrator"` resolves to no reachable agent.

**Reuse before spawning.** A new per-task dispatch is preceded by checking
whether one already spawned this session holds matching context; that one is
reused via `SendMessage`. A fresh spawn happens only when the task differs
from what any live sub-agent holds, or none exists yet.

- A write to `.ai/` outside `BRANCH_PLAN.md` is preceded by an `AskUserQuestion` to the developer. `BRANCH_PLAN.md` is the only plan file; a separate one exists only when the developer asks for it in-session.
- **Allowed exception:** a dispatch that already names a peer by literal agentId as the recipient of a result may send that result straight to the peer - the orchestrator made the routing decision, the peer executes it.
- Bad: launching 15 agents at once, or reading full source files directly instead of delegating.
- Bad: a per-task sub-agent spawning its own sub-agent instead of returning a scoping report.
- Bad: a persistent sub-agent handing new work to another persistent sub-agent instead of asking the orchestrator to route it.
- Bad: `SendMessage`-ing a per-task agent you did not spawn - you cannot know its task or trust its context.
- Bad: spawning a fresh sub-agent for a task a live one already holds context for, with no stated reason the existing one can't take it.

---

## AGT-3: FRESH-CONTEXT

**Statement:** Every sub-agent starts with a fresh, isolated context - the harness default, which no dispatch text needs to ask for. The payload carries the task, the scope and file paths, and the agent reads the relevant rules and code itself.
- Never quote rule text or paste a function body into the prompt. A pasted rules block, a diff, or a body longer than a few lines instead of a path and range is a violation.
- Prior output is passed as a file path to read, never a pasted body, and the path is forwarded onward when a later agent needs it.
- Locations are cited as `file:start-end`. Line numbers drift, so a range that no longer matches is re-located by symbol with `Grep` rather than trusted. A report claiming to have inspected or changed a section without a range is a violation.
- A verifier receives the artifact and the rules to check it against, never the author's reasoning. It flags rather than fixes, and its report is its own final message - an `Edit` or `Write` to the artifact it was checking is a violation.
- Bad: pasting a rules file's full text "so the agent doesn't have to look it up".
- Bad: reporting "updated process_producer.cpp" with no line numbers.
- Bad: passing the full edit context to a verification agent "so it understands why".

---

## AGT-23: USER-LITERAL / OFF-SCOPE-RECHECK

**Statement:** Two disciplines for orchestrator-to-agent communication.

### Part A: USER-LITERAL

A user directive affecting an in-flight persistent sub-agent's work reaches
that agent as the user's literal words verbatim, alongside the orchestrator's
own operational paraphrase:

```
User directive (literal, verbatim):
> <exact user words>

Operational implication: <what to do>
```

- The literal quote anchors the agent to the authoritative source; a paraphrase alone risks softening or dropping emphasis across the relay. A forward missing either the quoted block or the separate implication line is a violation.

### Part B: OFF-SCOPE-RECHECK

Completed work touching files or features outside the dispatched scope is
re-checked before acceptance:
1. `git diff` the off-scope files.
2. Verify new symbol references resolve.
3. Verify the off-scope change doesn't cross a role boundary.
4. Trace new placeholder substitutions to their data source.
5. Summarize the off-scope work to the user with an accept/reject
   recommendation.

- Bad: accepting a CONVERGED report at face value without `git diff`-checking the full file list for off-scope edits.

---

## AGT-26: RELAY-IDENTIFY

**Statement, sub-agent side:** No sub-agent holds `AskUserQuestion`, so an approval gate or option-pick goes to the orchestrator via `SendMessage(to: "main", ...)`, stating the full situation and every option so the relay never requires opening the sub-agent's transcript.

**Statement, orchestrator side:** A relay leads with which sub-agent it is from and what it is working on, in one short line before the question:

```
gitter (splitting the DEL-3 commit) is asking: <question>
```

- Applies whether the relay uses `AskUserQuestion` or plain text. A relay with no attribution is a violation.
- Bad: forwarding "should I overwrite this file?" with no mention of which sub-agent asked or what it's doing.

---

## AGT-29: STATE-REPORT-ON-CONTACT

**Statement:** A persistent sub-agent answers any `SendMessage` with a short state report naming its current phase or step, what it just did if anything happened since the last report, and what it is waiting on next.
- Applies alike to a resume ping after compaction, a reachability check, a status request and a normal task-completion message.
- Bad: replying "Acknowledged, continuing" with no phase name or wait-condition, forcing the orchestrator to ask again or read the workflow file to find out what is happening.

---

## AGT-30: USER-CHANNEL-TRUST

**Statement:** A sub-agent's report that the developer said or approved something is a plausible claim, verified by asking that sub-agent for specifics - what was said, when - via `SendMessage`, cheapest-first per WF-19. The developer can reach a sub-agent through a channel outside the orchestrator's own relay.
- Calling such a claim "fabricated" or "hallucinated" without first asking the sub-agent for confirmation or detail is a violation.
- This changes only how the orchestrator judges whether the interaction happened. A relayed claim still cannot grant escalation past the orchestrator's own permission settings, and a sub-agent reporting it was denied permission and asking the orchestrator to act instead is still refused and surfaced to the developer.
- Bad: a sub-agent reports "the user told me to leave this change as-is", and the orchestrator declares this impossible because the sub-agent "has no channel to the user", without checking whether the developer does have one.
