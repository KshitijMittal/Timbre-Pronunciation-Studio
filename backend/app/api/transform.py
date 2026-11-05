from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.core.dictionary_store import DictionaryStore
from app.core.pronunciation_rules import Rule as EngineRule
from app.core.pronunciation_rules import apply_rules
from app.deps import get_settings, get_store
from app.errors import LimitExceeded, ValidationError
from app.models.schemas import (
    InlineRule,
    LimitOut,
    RuleMatchOut,
    TransformRequest,
    TransformResponse,
    WarningOut,
)

router = APIRouter(tags=["transform"])


@router.post("/transform", response_model=TransformResponse)
def transform(
    payload: TransformRequest,
    settings: Settings = Depends(get_settings),
    store: DictionaryStore = Depends(get_store),
) -> TransformResponse:
    rules = _resolve_rules(payload, store)
    char_count = len(payload.text)
    script_length = len(payload.text.strip())

    # The same rule synthesize applies: whitespace does not count toward the block.
    if script_length > settings.script_block_chars:
        raise LimitExceeded(
            f"Script is {script_length:,} characters. "
            f"The limit is {settings.script_block_chars:,}."
        )

    limit_status = (
        "warn" if char_count > settings.script_warn_chars else "ok"
    )

    result = apply_rules(payload.text, rules)

    warnings: list[WarningOut] = []
    for match in result.matches:
        if match.count == 0:
            warnings.append(
                WarningOut(
                    code="RULE_NOT_FOUND_IN_TEXT",
                    rule_id=match.rule_id or None,
                    message="Term not found in this script.",
                )
            )
        if "<" in match.replacement or ">" in match.replacement:
            warnings.append(
                WarningOut(
                    code="REPLACEMENT_CONTAINS_MARKUP",
                    rule_id=match.rule_id or None,
                    message=(
                        "Timbre strips inline markup, so this replacement will "
                        "probably not be spoken as written."
                    ),
                )
            )

    for rule_id in result.chained_rule_ids:
        warnings.append(
            WarningOut(
                code="RULE_CHAIN_DETECTED",
                rule_id=rule_id or None,
                message=(
                    "This replacement contains another rule's term; applying the "
                    "dictionary twice would change the text again."
                ),
            )
        )

    return TransformResponse(
        original_text=result.original_text,
        transformed_text=result.transformed_text,
        changed=result.changed,
        char_count=char_count,
        limit=LimitOut(
            warn_at=settings.script_warn_chars,
            block_at=settings.script_block_chars,
            status=limit_status,
        ),
        matches=[
            RuleMatchOut(
                rule_id=match.rule_id,
                source=match.source,
                replacement=match.replacement,
                count=match.count,
            )
            for match in result.matches
        ],
        warnings=warnings,
    )


def _resolve_rules(
    payload: TransformRequest, store: DictionaryStore
) -> list[EngineRule]:
    if payload.rules is not None:
        return _inline_rules(payload.rules)

    if payload.dictionary_id is None:
        return []

    dictionary = store.get(payload.dictionary_id)
    return [
        EngineRule(
            source=rule.source,
            replacement=rule.replacement,
            rule_id=rule.id,
            created_at=rule.created_at,
        )
        for rule in dictionary.rules
    ]


def _inline_rules(inline: list[InlineRule]) -> list[EngineRule]:
    """Inline rules bypass the store, so the duplicate-source gate is repeated here."""
    seen: set[str] = set()
    rules: list[EngineRule] = []

    for item in inline:
        source = item.source.strip()
        if not source:
            raise ValidationError("Source term cannot be empty.")
        replacement = item.replacement.strip()
        if not replacement:
            raise ValidationError("Replacement cannot be empty.")

        key = source.casefold()
        if key in seen:
            raise ValidationError(
                f'This dictionary already has a rule for "{source}".'
            )
        seen.add(key)
        rules.append(
            EngineRule(
                source=source,
                replacement=replacement,
                rule_id=item.id or "",
                created_at=item.created_at or "",
            )
        )

    return rules
