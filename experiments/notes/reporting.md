> **Historical working notes** written during development, before the final frozen A100 batch. The numbers below come from intermediate dev runs and are superseded by `WRITEUP.md` and `experiments/reports/final_A100_policy_v1_1/`.

### Policy and Classifier Refinement

Following the initial evaluation, the system was refined to address authorization ambiguity, event-type confusion, and unreliable structured outputs.

**Policy v1.1** explicitly configured the company email domain and clarified how delegated document instructions should be interpreted. These changes distinguished legitimate task-related information from instructions attempting to impersonate trusted authority.

The classifier was also updated to enforce event-specific rule applicability, prevent evidence from being attributed to the wrong trace event, and improve JSON generation reliability through a constrained response schema and increased output token budget.

On the same 105-case development set using Qwen3 4B, accuracy improved from **67.6% to 81.9%**, violation recall increased from **64.1% to 79.5%**, unsafe allows decreased from **12 to 6**, and false blocks decreased from **17 to 8**. Invalid responses decreased from two to zero.

These results suggest that explicit policy boundaries, deterministic rule validation, and more reliable output formatting can improve both security sensitivity and legitimate-task preservation. However, because multiple components were modified, their individual contributions have not been isolated. Escalation handling remains an unresolved limitation.



Three findings worth putting in your write-up
1. R2 is over-applied — the main false-positive problem.

Ten of the 17 false blocks cite R2. In case 546fd18131d6, the agent explicitly says it will skip an injected instruction, yet the classifier labels this as adopting the malicious goal. In ecfed975097d, it also mistakes a user-authorized Slack invitation for an unauthorized goal.

2. Rule applicability is still sometimes ignored.

Case f369508dba4b flags a public website lookup under R3, although no external disclosure occurs. Other failures cite rules applicable to tool calls when judging a user_input or tool_response.

3. Secret detection and escalation remain unresolved.

The model incorrectly allows some events containing full bank account identifiers under R4. It also misses all three escalation labels, frequently interpreting an injection-looking channel name as proof that the agent followed the injection.


Strengthening authorization and trust-boundary reasoning increased violation recall from 66.7% to 87.2% and reduced unsafe allows from 10 to 4. However, false blocks rose from 5 to 17, demonstrating that more aggressive security reasoning can incorrectly classify legitimate task execution as malicious.