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
from dotenv import load_dotenv
load_dotenv()
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
        # Fallback: Capture words before grocery items, numbers, units or transaction keywords
        GROCERY_KEYWORDS = [
            "ulligadda", "vulligadda", "ulli", "aloo", "aloo gadda", "bangaladumpa", "biyyam", "rice",
            "pappu", "nune", "oil", "sabbu", "soap", "bellam", "panchadara", "sugar", "tamata", "mirchi",
            "mirapakayalu", "atta", "rava", "tea", "milk", "paalu", "curd", "perugu", "salt", "uppu",
            "ఉల్లిగడ్డ", "ఆలూ", "బియ్యం", "పప్పు", "నూనె", "సబ్బు", "బెల్లం", "పంచదార", "టమాటా", "పాలు"
        ]
        words = cleaned.split()
        name_words = []
        for w in words:
            wl = w.lower()
            if any(char.isdigit() for char in wl) or wl in (CREDIT_KEYWORDS + PAYMENT_KEYWORDS + GROCERY_KEYWORDS + UNIT_KEYWORDS + ["hello", "namaste", "hai", "and", "total", "mottam"]):
                break
            name_words.append(w)
            if len(name_words) >= 2:  # Support surname + given name (e.g. Ganta Ramesh)
                break
        if name_words:
            customer_name = " ".join(name_words).title()

    # 4. Extract Items & Quantities
    items: List[ItemDetail] = []
    # Pattern A: [item] [qty] [unit] e.g. "ulligadda 1 kg", "aloo gadda 0.5 kg"
    pattern_a = r'([a-zA-Z\u0C00-\u0C7F]+(?:\s+[a-zA-Z\u0C00-\u0C7F]+)?)\s+([0-9]+(?:\.[0-9]+)?|half|ardha|pavu)\s*([a-zA-Z\u0C00-\u0C7F]+)?'
    for m in re.finditer(pattern_a, lower):
        pot_name = m.group(1).strip()
        pot_qty = m.group(2)
        pot_unit = m.group(3) or ""
        if pot_qty == "half" or pot_qty == "ardha": pot_qty = "0.5"
        elif pot_qty == "pavu": pot_qty = "0.25"
        if pot_unit in UNIT_KEYWORDS and pot_name.lower() not in (CREDIT_KEYWORDS + PAYMENT_KEYWORDS + ["rupees", "rs", "rupayalu", "total", "mottam"]):
            items.append(ItemDetail(name=pot_name.capitalize(), quantity=pot_qty, unit=pot_unit))

    # Pattern B: [qty] [unit] [item] e.g. "1 kg rice", "2 packet sabbu"
    if not items:
        pattern_b = r'([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z\u0C00-\u0C7F]+)?\s+([a-zA-Z\u0C00-\u0C7F]+)'
        for m in re.finditer(pattern_b, lower):
            qty = m.group(1)
            pot_unit = m.group(2) or ""
            pot_name = m.group(3)
            if pot_unit in UNIT_KEYWORDS and pot_name not in (CREDIT_KEYWORDS + PAYMENT_KEYWORDS + ["rupees", "rs", "rupayalu"]):
                items.append(ItemDetail(name=pot_name.capitalize(), quantity=qty, unit=pot_unit))

    # Generate note string from items if present
    note = None
    if items:
        note_parts = [f"{it.name} ({it.quantity or ''} {it.unit or ''})".strip() for it in items]
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
            
            sys_prompt = """You are an expert AI transaction extractor for an Indian Kirana (grocery) shop voice ledger app in Telangana and Andhra Pradesh.
The shopkeeper speaks naturally in Telugu, mixed Telugu-English, or Hindi.

Vocabulary & Context:
1. Customer Names:
   - Telugu names often include surname + given name, e.g. "Ganta Ramesh", "Jakkena Srikar", "Kotha Suresh", or single names "Ramesh", "Suresh", "Anitha".
   - Suffixes like "ki", "ku", "gaaru", "garu", "se", "ne" are grammatical particles, NOT part of the name.
2. Common Telugu Grocery items:
   - ulligadda / vulligadda / ulli = Onion
   - aloo gadda / aloo / bangaladumpa = Potato
   - biyyam = Rice
   - pappu / kandi pappu = Dal / Pulses
   - nune / oil = Cooking Oil
   - sabbu = Soap
   - bellam = Jaggery
   - panchadara / chekkara = Sugar
   - tamata = Tomato
   - atta, rava, tea podi, mirapakayalu / mirchi, paalu, perugu, uppu.
3. Quantities:
   - 1kg, 2kg, half kg (0.5 kg), pavu kg (0.25 kg), muppavu kg (0.75 kg), packet, litre.
4. Transaction Type:
   - "credit" (UDHARA / APPU): udhar, udhara, appu, baaki, credit, rayi, rayee, rayandi, खाता, అప్పు, ఉధార, రాయండి.
   - "payment" (JAMA / VASOOL): payment, paid, jama, kattadu, kattaru, chellimpu, vasool, ichadu, చెల్లింపు, జమ, కట్టాడు.
5. Amount:
   - Extract numerical amount in rupees (e.g. 250 rs -> 250.0).

Return ONLY valid JSON:
{
  "customer_name_spoken": "Ganta Ramesh",
  "transaction_type": "credit" or "payment" or null,
  "amount_rupees": float or null,
  "items": [{"name": "Item Name", "quantity": "1", "unit": "kg"}],
  "note": "Itemized summary of items or note"
}"""
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://api.openai.com/v1/chat/completions"
            model = "qwen/qwen3.8-27b" if provider == "groq" else "gpt-4o-mini"
            req_data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": transcript}
                ],
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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
