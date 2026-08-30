from __future__ import annotations

import re
from typing import Any

from app.domain.writing_agent_schemas import (
    ClaimEvidenceMatrix,
    ClaimMatrixRow,
    FinalClaimsOutput,
)
from app.services.retrieval import term_similarity


class ClaimChecker:
    checker_version = "claim-checker-v1"

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).lower()

    @classmethod
    def _evidence_chunks(cls, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}

        def visit(value: object) -> None:
            if isinstance(value, dict):
                evidence_ref = str(value.get("evidence_ref") or "")
                text = str(value.get("text") or "")
                if evidence_ref and text:
                    output.setdefault(evidence_ref, value)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        return output

    @classmethod
    def _quote_verified(
        cls,
        quote: str,
        matched_chunks: list[dict[str, Any]],
    ) -> bool:
        normalized = cls._normalized(quote)
        if len(normalized) < 8:
            return False
        return any(
            normalized in cls._normalized(str(chunk.get("text") or "")) for chunk in matched_chunks
        )

    @staticmethod
    def _initial_claims(initial_claims: object) -> dict[str, str]:
        if not isinstance(initial_claims, list):
            return {}
        return {
            str(item.get("claim_id") or ""): str(item.get("statement") or "")
            for item in initial_claims
            if isinstance(item, dict)
            and str(item.get("claim_id") or "")
            and str(item.get("statement") or "")
        }

    def evaluate(
        self,
        *,
        final_artifact_id: str,
        final_claims_artifact_id: str,
        final_body: str,
        extraction: FinalClaimsOutput,
        evidence_retrieval: dict[str, Any],
        initial_claims: object,
        approved_issue_ids: set[str],
    ) -> ClaimEvidenceMatrix:
        evidence = self._evidence_chunks(evidence_retrieval)
        initial = self._initial_claims(initial_claims)
        normalized_final_body = self._normalized(final_body)
        rows: list[ClaimMatrixRow] = []

        for claim in extraction.claims:
            matched_refs = [value for value in claim.evidence_refs if value in evidence]
            missing_refs = [value for value in claim.evidence_refs if value not in evidence]
            matched_chunks = [evidence[value] for value in matched_refs]
            quote_verified = self._quote_verified(claim.evidence_quote, matched_chunks)
            semantic_support = max(
                (
                    term_similarity(
                        claim.statement,
                        str(chunk.get("text") or ""),
                    )
                    for chunk in matched_chunks
                ),
                default=0.0,
            )
            final_quote_verified = (
                self._normalized(claim.exact_quote) in normalized_final_body
            )
            if not matched_refs:
                support_status = "unsupported"
            elif missing_refs:
                support_status = "partial"
            elif claim.evidence_quote and quote_verified and semantic_support >= 0.28:
                support_status = "supported"
            elif claim.evidence_quote:
                support_status = "partial"
            elif semantic_support >= 0.28:
                support_status = "supported"
            else:
                support_status = "partial"

            origin_similarity = term_similarity(
                claim.statement,
                initial.get(claim.origin_claim_id, ""),
            )
            origin_statement = initial.get(claim.origin_claim_id, "")
            origin_length = len(self._normalized(origin_statement))
            claim_length = len(self._normalized(claim.statement))
            scope_length_preserved = claim_length <= max(
                int(origin_length * 1.8),
                origin_length + 30,
            )
            if (
                claim.origin_claim_id
                and claim.origin_claim_id in initial
                and origin_similarity >= 0.22
                and scope_length_preserved
            ):
                scope_status = "preserved"
            elif claim.approved_issue_ids and set(claim.approved_issue_ids) <= approved_issue_ids:
                scope_status = "approved_revision"
            else:
                scope_status = "new_claim"

            reasons: list[str] = []
            if not final_quote_verified:
                reasons.append("FINAL_CLAIM_QUOTE_NOT_FOUND")
            if claim.importance == "critical" and support_status != "supported":
                reasons.append("CRITICAL_CLAIM_UNSUPPORTED")
            if claim.importance == "major" and support_status != "supported":
                reasons.append("MAJOR_CLAIM_UNSUPPORTED")
            if claim.importance in {"critical", "major"} and scope_status == "new_claim":
                reasons.append("UNAUTHORIZED_FINAL_CLAIM_EXPANSION")
            rows.append(
                ClaimMatrixRow(
                    claim_id=claim.claim_id,
                    statement=claim.statement,
                    location=claim.location,
                    claim_type=claim.claim_type,
                    importance=claim.importance,
                    evidence_refs=list(claim.evidence_refs),
                    matched_evidence_refs=matched_refs,
                    missing_evidence_refs=missing_refs,
                    evidence_quote_verified=quote_verified,
                    semantic_support=round(semantic_support, 6),
                    final_quote_verified=final_quote_verified,
                    support_status=support_status,
                    scope_status=scope_status,
                    blocking_reasons=reasons,
                )
            )

        blocking = [row for row in rows if row.blocking_reasons]
        return ClaimEvidenceMatrix(
            final_artifact_id=final_artifact_id,
            final_claims_artifact_id=final_claims_artifact_id,
            total_claims=len(rows),
            supported_claims=sum(row.support_status == "supported" for row in rows),
            critical_unsupported_claims=sum(
                "CRITICAL_CLAIM_UNSUPPORTED" in row.blocking_reasons for row in rows
            ),
            major_unsupported_claims=sum(
                "MAJOR_CLAIM_UNSUPPORTED" in row.blocking_reasons for row in rows
            ),
            unauthorized_major_expansions=sum(
                "UNAUTHORIZED_FINAL_CLAIM_EXPANSION" in row.blocking_reasons for row in rows
            ),
            completion_allowed=not blocking,
            rows=rows,
        )
