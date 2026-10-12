"""
Customer Matcher for Voice Khata Entry.
Strictly scoped to the authenticated store.
Matches spoken customer names against existing store customers.
Never exposes customers from other stores.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Customer

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Strip common Telugu/Hindi suffixes like "ki", "ku", "gaaru", "ji", "ne", "ko"
    t = text.strip().lower()
    t = t.replace("’", "").replace("'", "")
    tokens = t.split()
    cleaned_tokens = []
    stopwords = {"ki", "ku", "gaaru", "garu", "ji", "ne", "ko", "se", "నుండి", "కి", "కు", "గారు"}
    for token in tokens:
        if token not in stopwords:
            cleaned_tokens.append(token)
    return " ".join(cleaned_tokens).strip() or t

def match_customer(db: Session, store_id: int, spoken_name: Optional[str]) -> Dict[str, Any]:
    """
    Finds customer match within store_id.
    Returns:
    {
        "matched_customer": Optional[Dict],
        "candidates": List[Dict],
        "clarification_required": bool
    }
    """
    if not spoken_name or not spoken_name.strip():
        return {
            "matched_customer": None,
            "candidates": [],
            "clarification_required": True
        }

    raw_spoken = spoken_name.strip()
    norm_spoken = normalize_text(raw_spoken)

    # Fetch all customers for the store
    customers = db.query(Customer).filter(Customer.store_id == store_id).all()
    if not customers:
        return {
            "matched_customer": None,
            "candidates": [],
            "clarification_required": True,
            "suggested_new_customer": raw_spoken.title()
        }

    exact_matches = []
    partial_matches = []

    for c in customers:
        c_name = c.name.strip()
        c_norm = normalize_text(c_name)

        # 1. Exact match
        if c_norm == norm_spoken or c_name.lower() == raw_spoken.lower():
            exact_matches.append(c)
            continue

        # 2. Substring / Token overlap
        spoken_tokens = set(norm_spoken.split())
        c_tokens = set(c_norm.split())
        if spoken_tokens and c_tokens:
            if spoken_tokens.issubset(c_tokens) or c_tokens.issubset(spoken_tokens):
                partial_matches.append(c)
                continue
            if norm_spoken in c_norm or c_norm in norm_spoken:
                partial_matches.append(c)
                continue

        # 3. Simple phonetic / suffix variation (e.g. Ramesh vs Rameshu)
        if len(norm_spoken) >= 3 and len(c_norm) >= 3:
            if (norm_spoken.startswith(c_norm[:4]) and abs(len(norm_spoken) - len(c_norm)) <= 2) or \
               (c_norm.startswith(norm_spoken[:4]) and abs(len(norm_spoken) - len(c_norm)) <= 2):
                partial_matches.append(c)

    if len(exact_matches) == 1:
        c = exact_matches[0]
        return {
            "matched_customer": {"id": c.id, "name": c.name, "phone": c.phone},
            "candidates": [],
            "clarification_required": False,
            "suggested_new_customer": None
        }
    elif len(exact_matches) > 1:
        # Multiple identical names (e.g. two "Ramesh" with different phones)
        return {
            "matched_customer": None,
            "candidates": [{"id": c.id, "name": c.name, "phone": c.phone} for c in exact_matches],
            "clarification_required": True,
            "suggested_new_customer": None
        }

    if len(partial_matches) == 1:
        c = partial_matches[0]
        return {
            "matched_customer": {"id": c.id, "name": c.name, "phone": c.phone},
            "candidates": [],
            "clarification_required": False,
            "suggested_new_customer": None
        }
    elif len(partial_matches) > 1:
        return {
            "matched_customer": None,
            "candidates": [{"id": c.id, "name": c.name, "phone": c.phone} for c in partial_matches[:5]],
            "clarification_required": True,
            "suggested_new_customer": raw_spoken.title()
        }

    # No match found - suggest creating new profile with spoken name
    return {
        "matched_customer": None,
        "candidates": [],
        "clarification_required": True,
        "suggested_new_customer": raw_spoken.title()
    }
