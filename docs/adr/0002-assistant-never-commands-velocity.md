# The voice assistant never commands velocity

The voice assistant has no velocity input (no `twist_mux` input of its own). It moves the robot only by calling allowlisted high-level actions and services, such as going to a named place, starting or stopping Follow-me, stopping, or a bounded short move like Nav2's `DriveOnHeading`/`BackUp`. Nav2 or Follow-me then does the driving. We chose this because the LLM is the least trustworthy part of the system: a misheard word, a model mistake or an injected instruction would otherwise become motor motion with no collision check, and an LLM is far too slow to stream velocities itself.

## Considered Options

- **Own `twist_mux` input:** rejected; it bypasses obstacle checks and would need its own motion loop and safety logic.
- **Lowest-priority `twist_mux` input with a speed cap:** rejected; still no obstacle checks and the same timing problem.

## Consequences

- A movement the assistant should be able to trigger needs its own allowlisted action, implemented by a deterministic node.
