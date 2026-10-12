"""
AI Transaction Extraction Service.
Translates spoken transcript into a structured, validated draft transaction.
Supports rule-based NLP parser (Telugu, Telugu+English, Telugu+Hindi) and optional LLM providers (Groq/OpenAI/Gemini).
Never commits transactions directly.
"""
import os
import re
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ItemDetail(BaseModel):
    name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None

class VoiceDraft(BaseModel):
    customer_name_spoken: Optional[str] = None
    transaction_type: Optional[str] = None  # "credit" | "payment" | None
    amount_rupees: Optional[float] = None
    amount_paise: Optional[int] = None
    items: List[ItemDetail] = []
    transcript: str
    missing_fields: List[str] = []
    clarification_required: bool = False
    note: Optional[str] = None

CREDIT_KEYWORDS = [
    "udhar", "udharu", "appu", "baaki", "credit", "raayi", "rayi", "ivvu", "ichamu",
    "ఉధార", "అప్పు", "బాకీ", "రాయి", "ఇవ్వు", "ఇచ్చాము", "ఖాతా", "ఉధార్"
]

PAYMENT_KEYWORDS = [
    "pay", "paid", "payment", "kattadu", "kattaru", "chellimpu", "jama", "ichadu",
    "చెల్లింపు", "కట్టాడు", "కట్టారు", "పేమెంట్", "జమా", "వసూలు", "ఇచ్చాడు"
]

UNIT_KEYWORDS = [
    "kilo", "kg", "packet", "pkt", "liter", "ltr", "gm", "gram", "grams", "sack", "bag", "dawa", "box",
    "కేజీ", "కిలో", "లీటర్", "ప్యాకెట్", "సంచీ", "డజన్", "గ్రామ్"
]

def parse_with_rules(transcript: str) -> VoiceDraft:
    """
    Deterministic rule-based Kirana parser for mixed Telugu/Hindi/English speech.
    """
    cleaned = transcript.strip()
    lower = cleaned.lower()

    # 1. Detect transaction type
    has_credit = any(re.search(r'\b' + re.escape(k) + r'\b', lower) or k in lower for k in CREDIT_KEYWORDS)
    has_payment = any(re.search(r'\b' + re.escape(k) + r'\b', lower) or k in lower for k in PAYMENT_KEYWORDS)

    tx_type = None
    if has_credit and not has_payment:
        tx_type = "credit"
    elif has_payment and not has_credit:
        tx_type = "payment"

    # 2. Extract Amount
    amount_rupees = None
    
    # Priority A: Number directly associated with currency words (rupees, rs, rupayalu, etc.)
    # Example: "150 rupees", "200 rs", "రూపాయలు 150", "150 రూపాయలు", "500/-"
    currency_patterns = [
        r'(?:rs\.?|inr|₹|రూ\.?|రూపాయలు)\s*([0-9]+(?:\.[0-9]{1,2})?)',
        r'([0-9]+(?:\.[0-9]{1,2})?)\s*(?:rs\.?|inr|rupees?|rupayalu|rupai|రూపాయలు|రూ\.?|/-)',
    ]
    
    for pat in currency_patterns:
        match = re.search(pat, lower)
        if match:
            try:
                val = float(match.group(1))
                if 0 < val <= 1000000:
                    amount_rupees = val
                    break
            except ValueError:
                pass

    # Priority B: If not found via currency words, look for standalone numbers that are NOT unit quantities
    # Example: "Ramesh ki 150 udhar" or "Suresh 500 payment"
    if amount_rupees is None:
        # Find all numbers
        all_numbers = re.findall(r'\b([0-9]+(?:\.[0-9]{1,2})?)\b', lower)
        # Exclude numbers followed immediately by units (e.g. 2 kg, 1 packet)
        unit_excluded_numbers = []
        for num in all_numbers:
            # Check if num is followed by a unit
            unit_match = False
            for unit in UNIT_KEYWORDS:
                if re.search(r'\b' + re.escape(num) + r'\s+' + re.escape(unit) + r'\b', lower):
                    unit_match = True
                    break
            if not unit_match:
                unit_excluded_numbers.append(num)
        
        # Take the most plausible amount (often the last or largest non-quantity number)
        if unit_excluded_numbers:
            try:
                candidate = float(unit_excluded_numbers[-1])
                if 0 < candidate <= 1000000:
                    amount_rupees = candidate
            except ValueError:
                pass

    # 3. Extract Customer Name
    customer_name = None
    # Patterns like: "Ramesh ki ...", "Ramesh ne ...", "రమేష్ కి ...", or first 1-2 words
    cust_match = re.search(r'^([a-zA-Z\u0C00-\u0C7F]+(?:\s+[a-zA-Z\u0C00-\u0C7F]+)?)\s*(?:ki|ku|ne|ko|gaaru|garu|se|కి|కు|గారు)\b', cleaned, re.IGNORECASE)
    if cust_match:
        customer_name = cust_match.group(1).strip()
    else:
        # Fallback: First word if not a keyword or number
        words = cleaned.split()
        if words:
            first_word = words[0].strip()
            if not first_word.isdigit() and first_word.lower() not in (CREDIT_KEYWORDS + PAYMENT_KEYWORDS + ["hello", "namaste", "hai"]):
                customer_name = first_word

    # 4. Extract Items & Quantities
    items: List[ItemDetail] = []
    # Pattern: [number] [unit] [item name] or [item name] [number] [unit]
    item_pattern = r'([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z\u0C00-\u0C7F]+)?\s+([a-zA-Z\u0C00-\u0C7F]+)'
    for m in re.finditer(item_pattern, lower):
        qty = m.group(1)
        pot_unit = m.group(2) or ""
        pot_name = m.group(3)
        if pot_unit in UNIT_KEYWORDS and pot_name not in (CREDIT_KEYWORDS + PAYMENT_KEYWORDS + ["rupees", "rs", "rupayalu"]):
            items.append(ItemDetail(name=pot_name, quantity=qty, unit=pot_unit))

    # Generate note string from items if present
    note = None
    if items:
        note_parts = [f"{it.name.capitalize()} ({it.quantity or ''} {it.unit or ''})".strip() for it in items]
        note = ", ".join(note_parts)

    missing_fields = []
    if not customer_name:
        missing_fields.append("customer")
    if not tx_type:
        missing_fields.append("transaction_type")
    if amount_rupees is None:
        missing_fields.append("amount")

    amount_paise = int(round(amount_rupees * 100)) if amount_rupees is not None else None

    return VoiceDraft(
        customer_name_spoken=customer_name,
        transaction_type=tx_type,
        amount_rupees=amount_rupees,
        amount_paise=amount_paise,
        items=items,
        transcript=transcript,
        missing_fields=missing_fields,
        clarification_required=len(missing_fields) > 0,
        note=note
    )

def extract_transaction_draft(transcript: str, language: str = "te") -> VoiceDraft:
    """
    Main extraction entrypoint.
    Checks AI_PROVIDER (e.g. groq, openai). If configured, invokes LLM with fallback to rule parser.
    """
    provider = os.getenv("AI_PROVIDER", "rule_based").lower()
    api_key = os.getenv("AI_API_KEY")

    if provider in ["groq", "openai"] and api_key:
        try:
            # Optional LLM completion path
            import urllib.request
            
            prompt = f"""
You are an AI assistant for an Indian Kirana shop voice ledger. Extract the transaction draft from this spoken text:
"{transcript}"

Output valid JSON matching this exact schema:
{{
  "customer_name_spoken": "name or null",
  "transaction_type": "credit" or "payment" or null,
  "amount_rupees": float or null,
  "items": [{{"name": "...", "quantity": "...", "unit": "..."}}],
  "note": "optional summary of items or null"
}}

Rules:
- If unclear whether credit or payment, transaction_type must be null.
- Preserve explicit amounts spoken. Never invent prices or amounts.
- Never guess a customer if not spoken.
"""
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://api.openai.com/v1/chat/completions"
            model = "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini"
            req_data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "KiranaKhataApp/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                content = resp_json["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                
                cust = parsed.get("customer_name_spoken")
                t_type = parsed.get("transaction_type")
                if t_type not in ["credit", "payment"]:
                    t_type = None
                amt = parsed.get("amount_rupees")
                amt_paise = int(round(amt * 100)) if amt is not None else None
                
                raw_items = parsed.get("items", [])
                items_list = [ItemDetail(**it) for it in raw_items if isinstance(it, dict) and "name" in it]
                note = parsed.get("note")
                
                missing = []
                if not cust: missing.append("customer")
                if not t_type: missing.append("transaction_type")
                if amt is None or amt <= 0: missing.append("amount")
                
                return VoiceDraft(
                    customer_name_spoken=cust,
                    transaction_type=t_type,
                    amount_rupees=amt,
                    amount_paise=amt_paise,
                    items=items_list,
                    transcript=transcript,
                    missing_fields=missing,
                    clarification_required=len(missing) > 0,
                    note=note
                )
        except Exception:
            # On any LLM timeout or error, safely fallback to rule parser
            pass

    return parse_with_rules(transcript)
