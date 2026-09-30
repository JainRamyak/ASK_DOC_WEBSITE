# Handoff: SPECVERIFY-G29-2026-09-30

SESSION TYPE: SPECIFICATION_VERIFICATION · `docs/specs/G29.md`.

STATE: APPROVED by owner (2026-09-30) after verification.

CHECKS: every AC is testable without network or key; decision resolved and recorded; no blocking Unknown (SDK attribute names are a planning task with a duck-typed design that tolerates them).

FIXES MADE (internal inconsistencies, no change of intent):
- Verification Strategy and Reproduction said `TestClient` / "AC7 if retry chosen"; changed to direct `query_document` call (repo pattern) and AC1–7.
- AC2 relied on an assumption for Anthropic 529; Requirement 1 now states the classified statuses explicitly (429; 503, 529) and that no other status is classified; AC2 adds a negative case (500/401/non-int → generic 500).
- Requirement 4 tightened: status must be a real `int`; false-positive risk noted in Edge Cases.

NOT DONE: no code, no provider call, nothing committed. SDK exception attributes remain unchecked.

NEXT: implementation-planning G29.
