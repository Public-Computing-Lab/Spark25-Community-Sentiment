# Lessons Learned and Future Scope

This document captures the reality of the project after implementation and testing. It is intended as a handoff artifact for future student teams who may maintain, expand, or redesign the system.

## What Didn't Work

### Response speed remained inconsistent

One of the biggest issues was latency. The chatbot could answer many questions correctly, but it still took too long to reply in some cases. This was especially noticeable when the system had to decide between SQL, RAG, and hybrid retrieval before generating the final answer. The experience felt less conversational than intended, even when the answer quality was acceptable.

### General-question answers were often too long

For broad or open-ended questions, the chatbot tended to produce responses that were more verbose than necessary. This reduced usability because users often wanted a short, direct answer first, with the option to ask follow-up questions if needed. In practice, overly long responses made the system feel less efficient and harder to scan.

### Some improvements were uneven across data sources

When the answer was retrieved from Boston.gov content, the system generally pointed to the correct source successfully. That was a meaningful improvement. However, this also highlighted an inconsistency: source grounding worked better in some retrieval paths than others, so the overall user experience was not uniformly reliable across all content sources.

### Hybrid execution strategy created unnecessary delay

The hybrid pipeline was initially not as efficient as it could have been because RAG and SQL logic were not fully optimized to run in parallel. Running one stage after the other increased response time and made the system slower on questions that required both structured and unstructured information.

## Lessons Learned

### Measure retrieval performance continuously

If this project were started again, retrieval time would be documented immediately after each major pipeline addition or architecture change. Waiting until later to measure performance made it harder to identify which components introduced the largest delays. A better approach is to benchmark representative queries throughout development and keep a running log of response times.

### Design for parallelism from the beginning

The system should have been structured so that hybrid retrieval paths ran in parallel from the start rather than sequentially. This would likely have reduced latency and produced a better user experience earlier in development. Future teams should treat parallel execution as a core architecture decision, not an optimization added later.

### Tune answer length as a product requirement

Answer brevity should be treated as an explicit design goal rather than only a prompt-level adjustment. The team learned that even a technically correct response can feel low quality if it is too long for the user’s intent. Future iterations should test concise-answer settings, response templates, and UI patterns that prioritize a short summary first.

### Validate each pipeline with task-specific queries

A general system-level test was not enough to expose the weaknesses of each retrieval path. Future development should use a fixed set of representative queries for SQL, RAG, and hybrid modes so that changes can be evaluated more systematically. This makes regressions easier to catch and helps teams compare architectural choices with evidence.

## Future Recommendations

### Expand ingestion coverage

The next phase of the project should expand document and data ingestion to include:

- Codman Square Health Center
- Age Strong Commission
- Dorchester Food Coop

These sources would broaden the assistant's community value by covering health, aging, and local food access, all of which are important topics for Dorchester residents.

### Add human-in-the-loop moderation

The team recommends testing a moderation workflow that includes trusted community reviewers. This would help verify sensitive, ambiguous, or high-impact outputs before they are treated as reliable community guidance. A human review layer may also improve trust and reduce the risks of hallucinated or incomplete answers.

### Open Community Notes to public submission with vetting

The current Community Notes model should be extended from an admin-only workflow to a public submission flow with review and vetting. This would allow residents or partner organizations to contribute corrections, context, and local knowledge while preserving quality control. A future implementation should include clear review states, moderation rules, and provenance tracking.

### Prioritize performance instrumentation

The next cohort should build lightweight latency monitoring into the development workflow. At minimum, the system should record routing time, retrieval time, and final generation time for representative queries. This will make optimization work much easier and will give future teams a clear baseline for improvement.

### Improve source consistency across retrieval modes

Since Boston.gov retrieval showed stronger source attribution behavior, future work should examine what made that path more reliable and apply the same principles elsewhere. A good next step would be standardizing citation formatting and metadata handling so that source quality is consistent no matter which retrieval mode is used.
