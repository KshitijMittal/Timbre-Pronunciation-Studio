from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class Rule:
    source: str
    replacement: str
    rule_id: str = ""
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule_id: str
    source: str
    replacement: str
    count: int


@dataclass(frozen=True, slots=True)
class TransformResult:
    original_text: str
    transformed_text: str
    matches: tuple[RuleMatch, ...]
    chained_rule_ids: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return self.transformed_text != self.original_text


def apply_rules(text: str, rules: Sequence[Rule]) -> TransformResult:
    ordered = sorted(
        (rule for rule in rules if rule.source),
        key=lambda rule: (-len(rule.source), rule.created_at, rule.rule_id),
    )

    if not ordered or not text:
        return TransformResult(
            original_text=text,
            transformed_text=text,
            matches=tuple(
                RuleMatch(rule.rule_id, rule.source, rule.replacement, 0)
                for rule in ordered
            ),
            chained_rule_ids=_detect_chains(ordered),
        )

    index_by_source = {rule.source.casefold(): i for i, rule in enumerate(ordered)}
    alternation = "|".join(re.escape(rule.source) for rule in ordered)
    pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", re.IGNORECASE)
    counts = [0] * len(ordered)

    def substitute(match: re.Match[str]) -> str:
        index = index_by_source[match.group(0).casefold()]
        counts[index] += 1
        return ordered[index].replacement

    transformed = pattern.sub(substitute, text)

    return TransformResult(
        original_text=text,
        transformed_text=transformed,
        matches=tuple(
            RuleMatch(rule.rule_id, rule.source, rule.replacement, counts[i])
            for i, rule in enumerate(ordered)
        ),
        chained_rule_ids=_detect_chains(ordered),
    )


def _detect_chains(rules: Sequence[Rule]) -> tuple[str, ...]:
    sources = [rule.source.casefold() for rule in rules]
    chained: list[str] = []

    for index, rule in enumerate(rules):
        replacement = rule.replacement.casefold()
        if any(
            other and other_index != index and other in replacement
            for other_index, other in enumerate(sources)
        ):
            chained.append(rule.rule_id)

    return tuple(chained)
