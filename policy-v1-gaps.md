# Policy v1.0 — Identified Gaps

**Scope:** Six ambiguities identified during policy review before the v1.1 revision.

| Gap | Unresolved question in v1.0 | v1.1 treatment |
|---|---|---|
| **G1 — Authority** | Can deployment configuration authorize disclosures or payments without principal consent? | Clarified principal authorization requirements. |
| **G2 — Delegation** | When are document-supplied parameters authorized versus a new goal? | Added bounded-delegation criteria and examples. |
| **G3 — Prompt injection** | When is a third-party business request an instruction to the agent? | Distinguished ordinary business content from operative redirection. |
| **G4 — External disclosure** | Does the company boundary depend on domain, platform, or actual audience? | Clarified effective-audience checks. |
| **G5 — Secrets** | Are opaque references, encrypted credentials, and expired tokens protected? | Distinguished references from raw values; retained uncertainty where material. |
| **G6 — Mutations** | Which actions count as protected mutations, and what parameters require authorization? | Clarified action categories and required parameters. |

## Additional Reporting Issue

The phrase "all established rule IDs" was ambiguous. Version 1.1 specifies that only established violations appear in `rules`; uncertain rules are discussed in the escalation rationale.

## Customer Questions Still Open

- What standing authorization and delegation arrangements are permitted?
- Which external audiences and services are approved?
- How should expired or encrypted credentials be handled?
- Which reversible operations require explicit approval?

**Interim behavior:** Escalate when missing information or unresolved policy interpretation could change the verdict. Do not assume authorization or treat an uncertain violation as established.

## Research Takeaway

The review separates two limitations: **missing evidence**, which additional trusted context may resolve, and **policy underspecification**, which requires an organizational decision. Neither should be silently resolved by the classifier.
