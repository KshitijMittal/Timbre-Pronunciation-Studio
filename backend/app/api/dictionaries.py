from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.dictionary_store import DictionaryStore
from app.deps import get_store
from app.models.schemas import (
    Dictionary,
    DictionaryCreate,
    DictionaryListResponse,
    DictionarySummary,
    DictionaryUpdate,
    StoreWarningOut,
)

router = APIRouter(tags=["dictionaries"])


@router.get("/dictionaries", response_model=DictionaryListResponse)
def list_dictionaries(
    store: DictionaryStore = Depends(get_store),
) -> DictionaryListResponse:
    dictionaries, warnings = store.list_all()
    return DictionaryListResponse(
        dictionaries=[
            DictionarySummary(
                id=dictionary.id,
                name=dictionary.name,
                rule_count=len(dictionary.rules),
                created_at=dictionary.created_at,
                updated_at=dictionary.updated_at,
            )
            for dictionary in dictionaries
        ],
        warnings=[StoreWarningOut(file=item.file, reason=item.reason) for item in warnings],
    )


@router.post(
    "/dictionaries", response_model=Dictionary, status_code=status.HTTP_201_CREATED
)
def create_dictionary(
    payload: DictionaryCreate, store: DictionaryStore = Depends(get_store)
) -> Dictionary:
    return store.create(payload.name)


@router.patch("/dictionaries/{dictionary_id}", response_model=Dictionary)
def rename_dictionary(
    dictionary_id: str,
    payload: DictionaryUpdate,
    store: DictionaryStore = Depends(get_store),
) -> Dictionary:
    return store.rename(dictionary_id, payload.name)


@router.delete("/dictionaries/{dictionary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dictionary(
    dictionary_id: str, store: DictionaryStore = Depends(get_store)
) -> Response:
    store.delete(dictionary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
