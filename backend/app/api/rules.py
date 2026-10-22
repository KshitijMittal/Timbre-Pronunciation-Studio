from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.dictionary_store import DictionaryStore
from app.deps import get_store
from app.models.schemas import Dictionary, Rule, RuleCreate, RuleListResponse, RuleUpdate

router = APIRouter(tags=["rules"])


@router.get("/dictionaries/{dictionary_id}/rules", response_model=RuleListResponse)
def list_rules(
    dictionary_id: str, store: DictionaryStore = Depends(get_store)
) -> RuleListResponse:
    return RuleListResponse(rules=store.get(dictionary_id).rules)


@router.post(
    "/dictionaries/{dictionary_id}/rules",
    response_model=Rule,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    dictionary_id: str,
    payload: RuleCreate,
    store: DictionaryStore = Depends(get_store),
) -> Rule:
    _, rule = store.add_rule(
        dictionary_id,
        source=payload.source,
        replacement=payload.replacement,
        rule_type=payload.type,
    )
    return rule


@router.patch("/rules/{rule_id}", response_model=Rule)
def update_rule(
    rule_id: str, payload: RuleUpdate, store: DictionaryStore = Depends(get_store)
) -> Rule:
    _, rule = store.update_rule(
        rule_id,
        source=payload.source,
        replacement=payload.replacement,
        rule_type=payload.type,
    )
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, store: DictionaryStore = Depends(get_store)) -> Response:
    store.delete_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
