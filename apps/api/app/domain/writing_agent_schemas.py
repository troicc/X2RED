from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EVIDENCE_REF_PATTERN = r"^[^:\s]+:[^\s]+$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,119}$"

EvidenceRef = Annotated[str, Field(pattern=EVIDENCE_REF_PATTERN, max_length=260)]
AgentIdentifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN, max_length=120)]
ClaimImportance = Literal["critical", "major", "minor"]
ClaimType = Literal[
    "fact",
    "number",
    "causal",
    "comparison",
    "capability",
    "interpretation",
    "recommendation",
]
ReviewSeverity = Literal["critical", "major", "minor"]


class StrictWritingAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EditorBriefOutput(StrictWritingAgentModel):
    reader: str = Field(min_length=1, max_length=2000)
    article_promise: str = Field(min_length=1, max_length=2000)
    main_thesis: str = Field(min_length=1, max_length=2000)
    reader_hook: str = Field(min_length=1, max_length=2000)
    must_use: list[str] = Field(default_factory=list, max_length=30)
    must_not_claim: list[str] = Field(default_factory=list, max_length=30)
    article_type: str = Field(min_length=1, max_length=80)
    tone: str = Field(min_length=1, max_length=300)
    open_questions: list[str] = Field(default_factory=list, max_length=30)
    success_criteria: list[str] = Field(default_factory=list, max_length=30)


class EvidenceAssertion(StrictWritingAgentModel):
    item_id: AgentIdentifier
    statement: str = Field(min_length=1, max_length=4000)
    source_index: int = Field(ge=1, le=10_000)
    evidence_ref: EvidenceRef
    evidence_quote: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="", max_length=1000)


class TermDefinition(StrictWritingAgentModel):
    term: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=300)


class SourceMapEntry(StrictWritingAgentModel):
    source_index: int = Field(ge=1, le=10_000)
    source_id: str = Field(min_length=1, max_length=160)
    selection_role: Literal["primary", "supporting", "connected", "written_version"]
    summary: str = Field(min_length=1, max_length=2000)


class EvidencePackOutput(StrictWritingAgentModel):
    facts: list[EvidenceAssertion] = Field(default_factory=list, max_length=80)
    author_claims: list[EvidenceAssertion] = Field(default_factory=list, max_length=80)
    unknowns: list[str] = Field(default_factory=list, max_length=80)
    numbers: list[EvidenceAssertion] = Field(default_factory=list, max_length=80)
    terms: list[TermDefinition] = Field(default_factory=list, max_length=80)
    source_map: list[SourceMapEntry] = Field(default_factory=list, max_length=80)
    material_gaps: list[str] = Field(default_factory=list, max_length=80)
    usable_examples: list[EvidenceAssertion] = Field(default_factory=list, max_length=80)
    claims_for_draft: list[EvidenceAssertion] = Field(default_factory=list, max_length=120)


class OutlineEdge(StrictWritingAgentModel):
    purpose: str = Field(default="", max_length=2000)
    key_point: str = Field(default="", max_length=2000)


class OutlineSection(StrictWritingAgentModel):
    section_id: AgentIdentifier
    heading: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    reader_question: str = Field(min_length=1, max_length=2000)
    key_point: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    terms_allowed: list[str] = Field(default_factory=list, max_length=30)
    target_length: int = Field(default=600, ge=100, le=5000)


class OutlineOutput(StrictWritingAgentModel):
    opening: OutlineEdge = Field(default_factory=OutlineEdge)
    sections: list[OutlineSection] = Field(default_factory=list, max_length=12)
    ending: OutlineEdge = Field(default_factory=OutlineEdge)
    cognitive_load_plan: list[str] = Field(default_factory=list, max_length=30)
    terms_first_use: list[TermDefinition] = Field(default_factory=list, max_length=50)
    evidence_allocation: list[str] = Field(default_factory=list, max_length=50)
    transitions: list[str] = Field(default_factory=list, max_length=30)
    forbidden_moves: list[str] = Field(default_factory=list, max_length=30)


class TextLocation(StrictWritingAgentModel):
    section: str = Field(default="", max_length=300)
    paragraph_index: int | None = Field(default=None, ge=1, le=10_000)
    quote: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def require_anchor(self) -> TextLocation:
        if not self.section and not self.quote and self.paragraph_index is None:
            raise ValueError("location requires a section, paragraph_index, or exact quote")
        return self


class DraftClaim(StrictWritingAgentModel):
    claim_id: AgentIdentifier
    statement: str = Field(min_length=1, max_length=4000)
    location: TextLocation
    claim_type: ClaimType
    importance: ClaimImportance
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    evidence_quote: str = Field(default="", max_length=2000)


class DraftOutput(StrictWritingAgentModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=80_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    claims: list[DraftClaim] = Field(default_factory=list, max_length=160)

    @model_validator(mode="after")
    def unique_claim_ids(self) -> DraftOutput:
        values = [item.claim_id for item in self.claims]
        if len(values) != len(set(values)):
            raise ValueError("a draft may report each claim id exactly once")
        return self


class ReviewIssue(StrictWritingAgentModel):
    issue_id: AgentIdentifier
    category: str = Field(min_length=1, max_length=120)
    location: TextLocation
    severity: ReviewSeverity
    message: str = Field(min_length=1, max_length=3000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    evidence_quote: str = Field(default="", max_length=2000)
    minimal_fix: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def require_review_evidence(self) -> ReviewIssue:
        if not self.evidence_refs and not self.evidence_quote and not self.location.quote:
            raise ValueError("review issue requires an evidence ref or an exact draft quote")
        return self


class ReaderReviewOutput(StrictWritingAgentModel):
    verdict: Literal["pass", "needs_revision", "blocked"]
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=80)
    strong_parts: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_issue_ids(self) -> ReaderReviewOutput:
        values = [item.issue_id for item in self.issues]
        if len(values) != len(set(values)):
            raise ValueError("a reviewer may report each issue id exactly once")
        return self


class FactReviewOutput(ReaderReviewOutput):
    pass


class StyleReviewOutput(ReaderReviewOutput):
    pass


class RevisionDecision(StrictWritingAgentModel):
    issue_id: AgentIdentifier
    decision: Literal["approve", "reject", "defer"]
    reason: str = Field(min_length=1, max_length=3000)
    approved_fix: str = Field(default="", max_length=3000)


class RevisionPlanOutput(StrictWritingAgentModel):
    decisions: list[RevisionDecision] = Field(default_factory=list, max_length=240)
    release_readiness: Literal["ready", "needs_revision", "blocked"]
    rationale: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def unique_issue_decisions(self) -> RevisionPlanOutput:
        values = [item.issue_id for item in self.decisions]
        if len(values) != len(set(values)):
            raise ValueError("revision plan may decide each issue exactly once")
        return self


class AppliedChange(StrictWritingAgentModel):
    issue_id: AgentIdentifier
    before: str = Field(default="", max_length=3000)
    after: str = Field(default="", max_length=3000)
    description: str = Field(min_length=1, max_length=3000)


class FinalDraftOutput(DraftOutput):
    applied_changes: list[AppliedChange] = Field(default_factory=list, max_length=240)

    @model_validator(mode="after")
    def unique_applied_issue_ids(self) -> FinalDraftOutput:
        values = [item.issue_id for item in self.applied_changes]
        if len(values) != len(set(values)):
            raise ValueError("final reviser may apply each issue id exactly once")
        return self


class ExtractedFinalClaim(StrictWritingAgentModel):
    claim_id: AgentIdentifier
    statement: str = Field(min_length=1, max_length=4000)
    exact_quote: str = Field(min_length=1, max_length=2000)
    location: TextLocation
    claim_type: ClaimType
    importance: ClaimImportance
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    evidence_quote: str = Field(default="", max_length=2000)
    origin_claim_id: str = Field(default="", max_length=120)
    approved_issue_ids: list[AgentIdentifier] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def promote_high_risk_claim_types(self) -> ExtractedFinalClaim:
        if (
            self.claim_type in {"number", "causal", "comparison", "capability"}
            and self.importance == "minor"
        ):
            raise ValueError(
                "number, causal, comparison, and capability claims cannot be minor"
            )
        return self


class FinalClaimsOutput(StrictWritingAgentModel):
    claims: list[ExtractedFinalClaim] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_claim_ids(self) -> FinalClaimsOutput:
        values = [item.claim_id for item in self.claims]
        if len(values) != len(set(values)):
            raise ValueError("claim extractor may report each claim id exactly once")
        return self


class ClaimMatrixRow(StrictWritingAgentModel):
    claim_id: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=4000)
    location: TextLocation
    claim_type: ClaimType
    importance: ClaimImportance
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    matched_evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    missing_evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    evidence_quote_verified: bool = False
    semantic_support: float = Field(default=0.0, ge=0.0, le=1.0)
    final_quote_verified: bool = False
    support_status: Literal["supported", "partial", "unsupported"]
    scope_status: Literal["preserved", "approved_revision", "new_claim"]
    blocking_reasons: list[str] = Field(default_factory=list, max_length=20)


class ClaimEvidenceMatrix(StrictWritingAgentModel):
    schema_version: Literal[1] = 1
    checker_version: Literal["claim-checker-v1"] = "claim-checker-v1"
    final_artifact_id: str = Field(min_length=1, max_length=160)
    final_claims_artifact_id: str = Field(min_length=1, max_length=160)
    total_claims: int = Field(ge=0)
    supported_claims: int = Field(ge=0)
    critical_unsupported_claims: int = Field(ge=0)
    major_unsupported_claims: int = Field(default=0, ge=0)
    unauthorized_major_expansions: int = Field(ge=0)
    completion_allowed: bool
    rows: list[ClaimMatrixRow] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def counts_match_rows(self) -> ClaimEvidenceMatrix:
        expected = {
            "total_claims": len(self.rows),
            "supported_claims": sum(row.support_status == "supported" for row in self.rows),
            "critical_unsupported_claims": sum(
                "CRITICAL_CLAIM_UNSUPPORTED" in row.blocking_reasons for row in self.rows
            ),
            "major_unsupported_claims": sum(
                "MAJOR_CLAIM_UNSUPPORTED" in row.blocking_reasons for row in self.rows
            ),
            "unauthorized_major_expansions": sum(
                "UNAUTHORIZED_FINAL_CLAIM_EXPANSION" in row.blocking_reasons
                for row in self.rows
            ),
        }
        mismatched = [name for name, value in expected.items() if getattr(self, name) != value]
        if mismatched:
            raise ValueError("claim matrix counters do not match rows: " + ", ".join(mismatched))
        if self.completion_allowed == any(row.blocking_reasons for row in self.rows):
            raise ValueError("claim matrix completion flag does not match blocking rows")
        return self


class StructuredOutputTrace(StrictWritingAgentModel):
    schema_version: Literal[1] = 1
    mode: Literal["production", "legacy"]
    status: Literal["valid", "repaired", "degraded"]
    schema_name: str = Field(min_length=1, max_length=160)
    repair_attempted: bool = False
    validation_errors: list[str] = Field(default_factory=list, max_length=10)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    warning: str = Field(default="", max_length=500)


ARTIFACT_SCHEMAS: dict[str, type[StrictWritingAgentModel]] = {
    "editorial_brief": EditorBriefOutput,
    "evidence_pack": EvidencePackOutput,
    "outline": OutlineOutput,
    "draft": DraftOutput,
    "reader_review": ReaderReviewOutput,
    "fact_review": FactReviewOutput,
    "style_review": StyleReviewOutput,
    "revision_plan": RevisionPlanOutput,
    "final_draft": FinalDraftOutput,
    "final_claims": FinalClaimsOutput,
}


class WritingAgentContractError(ValueError):
    pass


def schema_for_artifact(artifact_type: str) -> type[StrictWritingAgentModel]:
    schema = ARTIFACT_SCHEMAS.get(artifact_type)
    if schema is None:
        raise WritingAgentContractError(
            f"production writing agent has no schema for artifact {artifact_type}"
        )
    return schema


def validate_contract_context(
    artifact_type: str,
    output: StrictWritingAgentModel,
    context: dict[str, Any] | None,
) -> None:
    values = context or {}
    if "allowed_evidence_refs" in values:
        allowed_evidence_refs = {
            str(value) for value in values.get("allowed_evidence_refs") or []
        }
        referenced: set[str] = set()

        def collect_references(value: object) -> None:
            if isinstance(value, dict):
                singular = value.get("evidence_ref")
                if isinstance(singular, str) and singular:
                    referenced.add(singular)
                plural = value.get("evidence_refs")
                if isinstance(plural, list):
                    referenced.update(str(item) for item in plural if item)
                for child in value.values():
                    collect_references(child)
            elif isinstance(value, list):
                for child in value:
                    collect_references(child)

        collect_references(output.model_dump(mode="json"))
        unknown_refs = referenced - allowed_evidence_refs
        if unknown_refs:
            raise WritingAgentContractError(
                "agent invented evidence refs: " + ", ".join(sorted(unknown_refs))
            )
    if artifact_type in {"reader_review", "fact_review", "style_review"}:
        report = ReaderReviewOutput.model_validate(output)
        prefix = str(values.get("issue_id_prefix") or "")
        invalid = [item.issue_id for item in report.issues if not item.issue_id.startswith(prefix)]
        if prefix and invalid:
            raise WritingAgentContractError(
                f"review issue ids must start with {prefix}: {', '.join(sorted(invalid))}"
            )
        if artifact_type == "fact_review":
            ungrounded = [
                item.issue_id
                for item in report.issues
                if not item.evidence_refs and not item.evidence_quote
            ]
            if ungrounded:
                raise WritingAgentContractError(
                    "fact review issues require source evidence: " + ", ".join(sorted(ungrounded))
                )
    if artifact_type == "revision_plan":
        plan = RevisionPlanOutput.model_validate(output)
        allowed = {str(value) for value in values.get("allowed_issue_ids") or []}
        decided = {item.issue_id for item in plan.decisions}
        unknown = decided - allowed
        missing = allowed - decided
        if unknown:
            raise WritingAgentContractError(
                f"chief editor invented issue ids: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise WritingAgentContractError(
                f"chief editor did not adjudicate issue ids: {', '.join(sorted(missing))}"
            )
    if artifact_type == "final_draft":
        final = FinalDraftOutput.model_validate(output)
        approved = {str(value) for value in values.get("approved_issue_ids") or []}
        required = {str(value) for value in values.get("required_issue_ids") or []}
        applied = {item.issue_id for item in final.applied_changes}
        unknown = applied - approved
        missing = required - applied
        if unknown:
            raise WritingAgentContractError(
                f"final reviser changed unapproved issue ids: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise WritingAgentContractError(
                f"final reviser skipped required issue ids: {', '.join(sorted(missing))}"
            )
    if artifact_type == "final_claims":
        extraction = FinalClaimsOutput.model_validate(output)
        initial_ids = {str(value) for value in values.get("initial_claim_ids") or []}
        approved = {str(value) for value in values.get("approved_issue_ids") or []}
        invalid_origins = {
            item.origin_claim_id
            for item in extraction.claims
            if item.origin_claim_id and item.origin_claim_id not in initial_ids
        }
        invalid_issues = {
            issue_id
            for item in extraction.claims
            for issue_id in item.approved_issue_ids
            if issue_id not in approved
        }
        if invalid_origins:
            raise WritingAgentContractError(
                "claim extractor invented origin claim ids: " + ", ".join(sorted(invalid_origins))
            )
        if invalid_issues:
            raise WritingAgentContractError(
                "claim extractor invented approved issue ids: " + ", ".join(sorted(invalid_issues))
            )


def validate_agent_payload(
    artifact_type: str,
    payload: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> StrictWritingAgentModel:
    schema = schema_for_artifact(artifact_type)
    output = schema.model_validate(payload)
    validate_contract_context(artifact_type, output, context)
    return output
