# Research Engine — Canary Questions Specification

This document defines the canonical acceptance canary questions used to audit the Research Engine for domain isolation, entity fidelity, and negative-evidence honesty.

---

## Canary Q1: Amazon Kiro & Spec-Driven Development

- **ID**: `q-kiro-empirical`
- **Question Text**:
  > *"What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"*
- **Scope**: `kiro`
- **Domain**: Software engineering, AI developer tooling, autonomous coding agents, specification-driven contracts.
- **Architectural Purpose**:
  - Validates retrieval and synthesis over authentic empirical software engineering literature.
  - Tests **Entity Fidelity (Gate G3)**: Requires exact entity matching for Amazon Kiro claims; rejects broad, generic 2023 AI assistant papers as substitutes for Kiro-specific claims.
  - Rejects vendor marketing assertions as empirical facts (Gate G4).
  - Must never contain clinical, healthcare, or food science claims.
- **Expected Results**:
  - **Findings**: Real relevant findings or an honest gap; no off-topic papers admitted.
  - **Enterprise Sources**: Enterprise sources shown with status per source.
  - **Status Vocabulary**: Valid status names restricted to `PUBLISH_READY` / `REVISE` / `BLOCKED` / `NOT_PUBLISHABLE`.

---

## Canary Q2: Hospital Clinical AI Triage

- **ID**: `q-how-are-hospitals-governin`
- **Question Text**:
  > *"How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?"*
- **Scope**: `security`
- **Domain**: Clinical acute care, hospital triage, patient safety governance, regulatory compliance.
- **Architectural Purpose**:
  - Validates **Cross-Domain Isolation**: The synthesis for Q2 must share **ZERO** assertive findings sentences with Q1.
  - Cites **ZERO** software engineering papers, microservices observations, or developer velocity statistics.
  - Contains **ZERO** practitioner observations from Lane C unless explicitly tagged and abstracted for hospital clinical triage.
- **Expected Results**:
  - **Domain Isolation**: 0 shared assertive findings sentences with Q1.
  - **Citation Scope**: 0 software engineering citations or developer velocity metrics.
  - **Evidence Alignment**: "Aligned" is never claimed without enterprise evidence.
  - **Field Note Abstract**: Restricted exclusively to clinical acute care triage governance and patient safety.

---

## Canary Q3: Adversarial "No Evidence" Control (Quantum-Secure Sourdough Fermentation Controllers)

- **ID**: `q-quantum-secure-sourdough-ferme-a924f6cd`
- **Question Text**:
  > *"What empirical evidence exists on quantum-secure sourdough fermentation controllers?"*
- **Scope**: `enterprise`
- **Domain**: Nonsensical / unmeasured intersection (quantum cryptography + artisan baking).
- **Architectural Purpose**:
  - Serves as the negative control canary where **no legitimate empirical evidence exists**.
  - **Zero Findings Guarantee**: The engine must return exactly **zero findings** (`key_findings: []`).
  - **Gap Matrix Outcome**: Evaluates honestly to **Outcome 4** (`unmeasured` / no evidence found).
  - **Zero Fabrication**: The engine must NEVER hallucinate papers, borrow off-topic cryptography or sourdough papers, or emit synthetic text to fill report sections.
- **Expected Results**:
  - **Findings Count**: Exactly 0 findings (`key_findings: []`).
  - **Gap Matrix**: Evaluates to Outcome 4 (`unmeasured` / no evidence found).
  - **Publication Status**: `NOT_PUBLISHABLE` only (never `BLOCKED`).
  - **Citations**: 0 citations, 0 fabricated claims.
