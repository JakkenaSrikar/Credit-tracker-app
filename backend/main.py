import os
from dotenv import load_dotenv
load_dotenv()

import time
import jwt
import hashlib
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from database import engine, Base, Store, User, Customer, Transaction, get_db, ensure_schema
from speech_service import transcribe_audio, SpeechServiceError
from ai_extraction_service import extract_transaction_draft
from customer_matcher import match_customer

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Unicode Fonts download for Devanagari (Hindi) and Telugu PDF support
FONT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(FONT_DIR, "FreeSans.ttf")
TELUGU_FONT_PATH = os.path.join(FONT_DIR, "NotoSansTelugu-Regular.ttf")

FONT_NAME = 'Helvetica'
TELUGU_FONT_NAME = 'Helvetica'

def download_unicode_fonts():
    global FONT_NAME, TELUGU_FONT_NAME
    
    # 1. Download FreeSans (Hindi/English)
    if not os.path.exists(FONT_PATH):
        print("Downloading FreeSans Unicode font...")
        url = "https://raw.githubusercontent.com/evanw/tfdump/master/FreeSans.ttf"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, FONT_PATH)
            print("FreeSans font downloaded successfully.")
        except Exception as e:
            print(f"Failed to download FreeSans font: {e}")
            
    # 2. Download Noto Sans Telugu
    if not os.path.exists(TELUGU_FONT_PATH):
        print("Downloading NotoSansTelugu font...")
        url = "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Regular.ttf"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, TELUGU_FONT_PATH)
            print("NotoSansTelugu font downloaded successfully.")
        except Exception as e:
            print(f"Failed to download Telugu font: {e}")

    # Register FreeSans
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont('FreeSans', FONT_PATH))
        FONT_NAME = 'FreeSans'
        print("FreeSans font registered successfully.")
    except Exception as e:
        print(f"Could not register FreeSans font: {e}")

    # Register NotoSansTelugu
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont('NotoSansTelugu', TELUGU_FONT_PATH))
        TELUGU_FONT_NAME = 'NotoSansTelugu'
        print("NotoSansTelugu font registered successfully.")
    except Exception as e:
        print(f"Could not register NotoSansTelugu font: {e}")

download_unicode_fonts()

# Initialize database tables
Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Kirana Shop Udhara Tracker Multi-Store API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Security Configurations
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_kirana_tracker_key_2026")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

# In-Memory Rate Limiting for Login (IP-based)
login_rate_limit = {}

def check_login_rate_limit(client_ip: str):
    now = time.time()
    if client_ip in login_rate_limit:
        record = login_rate_limit[client_ip]
        if record["blocked_until"] > 0:
            if now > record["blocked_until"]:
                login_rate_limit[client_ip] = {"count": 0, "blocked_until": 0, "last_attempt": now}
            else:
                remaining = int(record["blocked_until"] - now)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many login attempts. Please try again after {remaining} seconds."
                )
        if now - record["last_attempt"] > 60:
            record["count"] = 0
            record["last_attempt"] = now
    else:
        login_rate_limit[client_ip] = {"count": 0, "blocked_until": 0, "last_attempt": now}

def record_failed_login(client_ip: str):
    now = time.time()
    if client_ip not in login_rate_limit:
        login_rate_limit[client_ip] = {"count": 1, "blocked_until": 0, "last_attempt": now}
        return
    record = login_rate_limit[client_ip]
    record["count"] += 1
    record["last_attempt"] = now
    if record["count"] >= 5:
        record["blocked_until"] = now + 60  # Block for 60 seconds
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Login locked for 60 seconds."
        )

def record_successful_login(client_ip: str):
    if client_ip in login_rate_limit:
        del login_rate_limit[client_ip]

# In-Memory Rate Limiting for Voice Operations (User-based)
voice_rate_limit = {}

def check_voice_rate_limit(user_id: int):
    now = time.time()
    record = voice_rate_limit.get(user_id)
    if not record or now - record["window_start"] > 60:
        voice_rate_limit[user_id] = {"count": 1, "window_start": now}
        return
    if record["count"] >= 30:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many voice requests. Please wait a moment."
        )
    record["count"] += 1


# Hashing Utilities
def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_pin(pin: str, hashed: str) -> bool:
    try:
        salt_hex, key_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, 100000)
        return new_key == key
    except Exception:
        return False

def hash_recovery_answer(answer: str) -> str:
    cleaned = answer.strip().lower()
    return hashlib.sha256(cleaned.encode('utf-8')).hexdigest()


# Token Helpers
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        store_id = payload.get("store_id")
        user_id = payload.get("user_id")
        if not store_id or not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == user_id, User.store_id == store_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User session not found")
    return user


def format_rupees(paise: int) -> str:
    amount_rs = paise / 100.0
    if amount_rs.is_integer():
        return f"{int(amount_rs)}"
    return f"{amount_rs:.2f}"


# --- AUTH & TENANT ENDPOINTS ---

# 1. SETUP STATUS (Checks if there are any stores in system)
@app.get("/api/setup/status")
def get_setup_status(db: Session = Depends(get_db)):
    stores_count = db.query(Store).count()
    if stores_count == 0:
        return {"setup_required": True}
    return {"setup_required": False}

# 2. STORE SIGNUP
@app.post("/api/stores", status_code=status.HTTP_201_CREATED)
def signup_store(payload: dict, db: Session = Depends(get_db)):
    store_name = payload.get("store_name")
    owner_name = payload.get("owner_name")
    pin = payload.get("pin")
    recovery_question = payload.get("recovery_question")
    recovery_answer = payload.get("recovery_answer")
    language = payload.get("language", "en")
    
    if not store_name or not owner_name or not pin:
        raise HTTPException(status_code=400, detail="Store name, Owner name, and PIN are required.")
    
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits.")
        
    if language not in ["en", "te"]:
        language = "en"

    # Check duplicate store name (case-insensitive)
    existing_store = db.query(Store).filter(func.lower(Store.name) == store_name.strip().lower()).first()
    if existing_store:
        raise HTTPException(status_code=400, detail="A store with this name already exists.")

    new_store = Store(name=store_name.strip(), language=language)
    db.add(new_store)
    db.commit()
    db.refresh(new_store)

    hashed_pin = hash_pin(pin)
    recovery_hash = hash_recovery_answer(recovery_answer) if recovery_answer else None

    new_user = User(
        store_id=new_store.id,
        name=owner_name.strip(),
        pin_hash=hashed_pin,
        role="owner",
        recovery_question=recovery_question.strip() if recovery_question else None,
        recovery_answer_hash=recovery_hash
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"store_id": new_store.id, "user_id": new_user.id, "role": new_user.role})
    return {
        "token": token,
        "store_id": new_store.id,
        "user_id": new_user.id,
        "role": new_user.role,
        "store_name": new_store.name,
        "user_name": new_user.name,
        "language": new_store.language
    }

# 3. LOGIN
@app.post("/api/login")
def login(payload: dict, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)
    
    store_id = payload.get("store_id")
    store_name = payload.get("store_name")
    pin = payload.get("pin")
    
    if not pin:
        raise HTTPException(status_code=400, detail="PIN is required.")
        
    store = None
    if store_id:
        try:
            store = db.query(Store).filter(Store.id == int(store_id)).first()
        except ValueError:
            pass
    elif store_name:
        store = db.query(Store).filter(func.lower(Store.name) == store_name.strip().lower()).first()
        
    if not store:
        record_failed_login(client_ip)
        raise HTTPException(status_code=404, detail="Store not found.")
        
    # Search user within this store whose PIN matches
    users = db.query(User).filter(User.store_id == store.id).all()
    matched_user = None
    for u in users:
        if verify_pin(pin, u.pin_hash):
            matched_user = u
            break
            
    if not matched_user:
        record_failed_login(client_ip)
        raise HTTPException(status_code=401, detail="Invalid PIN.")
        
    record_successful_login(client_ip)
    token = create_access_token(data={"store_id": store.id, "user_id": matched_user.id, "role": matched_user.role})
    return {
        "token": token,
        "store_id": store.id,
        "user_id": matched_user.id,
        "role": matched_user.role,
        "store_name": store.name,
        "user_name": matched_user.name,
        "language": store.language
    }

# 4. STORE LIST (For login autocomplete/selection dropdown)
@app.get("/api/stores/list")
def get_stores_list(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.name.asc()).all()
    return [{"id": s.id, "name": s.name} for s in stores]


# --- USER STAFF MANAGEMENT ---

# 5. CREATE USER (Owner-only)
@app.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owners can add users.")
        
    name = payload.get("name")
    pin = payload.get("pin")
    role = payload.get("role", "staff")
    recovery_question = payload.get("recovery_question")
    recovery_answer = payload.get("recovery_answer")
    
    if not name or not pin:
        raise HTTPException(status_code=400, detail="Name and PIN are required.")
        
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits.")
        
    if role not in ["owner", "staff"]:
        role = "staff"
        
    # Check PIN uniqueness within this store
    all_users = db.query(User).filter(User.store_id == current_user.store_id).all()
    for u in all_users:
        if verify_pin(pin, u.pin_hash):
            raise HTTPException(status_code=409, detail="PIN already in use within this store.")
            
    new_user = User(
        store_id=current_user.store_id,
        name=name.strip(),
        pin_hash=hash_pin(pin),
        role=role,
        recovery_question=recovery_question.strip() if recovery_question else None,
        recovery_answer_hash=hash_recovery_answer(recovery_answer) if recovery_answer else None
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "name": new_user.name, "role": new_user.role}

# 6. LIST STORE USERS
@app.get("/api/users")
def get_store_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.store_id == current_user.store_id).order_by(User.role.asc(), User.name.asc()).all()
    return [{"id": u.id, "name": u.name, "role": u.role} for u in users]

# 7. DELETE USER (Owner-only, Last Owner protection)
@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owners can delete users.")
        
    target_user = db.query(User).filter(User.id == user_id, User.store_id == current_user.store_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    if target_user.role == "owner":
        owners_count = db.query(User).filter(User.store_id == current_user.store_id, User.role == "owner").count()
        if owners_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining owner of this store.")
            
    db.delete(target_user)
    db.commit()
    return {"message": "User deleted successfully."}


# --- PIN RESET FLOW ---

# 8. REQUEST PIN RESET (Retrieves recovery question)
@app.post("/api/pin-reset/request")
def request_pin_reset(payload: dict, db: Session = Depends(get_db)):
    store_id = payload.get("store_id")
    user_name = payload.get("user_name")
    
    if not store_id or not user_name:
        raise HTTPException(status_code=400, detail="Store ID and User name are required.")
        
    user = db.query(User).filter(User.store_id == int(store_id), func.lower(User.name) == user_name.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")
        
    if not user.recovery_question:
        raise HTTPException(status_code=400, detail="No recovery question configured for this account.")
        
    return {
        "user_id": user.id,
        "recovery_question": user.recovery_question
    }

# 9. CONFIRM PIN RESET
@app.post("/api/pin-reset/confirm")
def confirm_pin_reset(payload: dict, db: Session = Depends(get_db)):
    store_id = payload.get("store_id")
    user_id = payload.get("user_id")
    recovery_answer = payload.get("recovery_answer")
    new_pin = payload.get("new_pin")
    
    if not store_id or not user_id or not recovery_answer or not new_pin:
        raise HTTPException(status_code=400, detail="All fields are required.")
        
    if not new_pin.isdigit() or len(new_pin) != 4:
        raise HTTPException(status_code=400, detail="New PIN must be exactly 4 digits.")
        
    user = db.query(User).filter(User.id == int(user_id), User.store_id == int(store_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")
        
    if not user.recovery_answer_hash or hash_recovery_answer(recovery_answer) != user.recovery_answer_hash:
        raise HTTPException(status_code=401, detail="Incorrect recovery answer.")
        
    # Check PIN uniqueness in store
    all_users = db.query(User).filter(User.store_id == user.store_id).all()
    for u in all_users:
        if u.id != user.id and verify_pin(new_pin, u.pin_hash):
            raise HTTPException(status_code=409, detail="New PIN already in use within this store.")

    user.pin_hash = hash_pin(new_pin)
    db.commit()
    return {"message": "PIN updated successfully. Please login with your new PIN."}


# --- STORE SETTINGS LANGUAGE ---

# 10. UPDATE STORE LANGUAGE
@app.put("/api/stores/settings")
def update_store_settings(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    language = payload.get("language")
    if language not in ["en", "te"]:
        raise HTTPException(status_code=400, detail="Language must be 'en' or 'te'.")
        
    store = db.query(Store).filter(Store.id == current_user.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store settings not found.")
        
    store.language = language
    db.commit()
    return {"message": "Store settings updated.", "language": store.language}


# --- CUSTOMER ENDPOINTS (SCOPED TO STORE) ---

def get_balance_expr():
    credit_sum = func.coalesce(func.sum(case((Transaction.type == 'credit', Transaction.amount), else_=0)), 0)
    payment_sum = func.coalesce(func.sum(case((Transaction.type == 'payment', Transaction.amount), else_=0)), 0)
    return credit_sum - payment_sum

def get_customer_balance(db: Session, customer_id: int) -> int:
    balance_expr = get_balance_expr()
    bal = db.query(balance_expr).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(Customer.id == customer_id).group_by(Customer.id).scalar()
    return bal if bal is not None else 0

# 11. CREATE CUSTOMER (STORE-SCOPED)
@app.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.get("name")
    phone = payload.get("phone")
    
    if not name or name.strip() == "":
        raise HTTPException(status_code=400, detail="Customer name is required.")
        
    new_customer = Customer(
        store_id=current_user.store_id,
        name=name.strip(),
        phone=phone.strip() if phone else None
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return {"id": new_customer.id, "name": new_customer.name, "phone": new_customer.phone, "balance": 0}

# 12. GET CUSTOMERS (SEARCH & SORT, SCOPED)
@app.get("/api/customers")
def get_customers(
    search: Optional[str] = Query(None),
    sort: str = Query("balance_desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    balance_expr = get_balance_expr()
    
    query = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.created_at,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id)
    
    if search:
        query = query.filter(Customer.name.like(f"%{search}%"))
        
    if sort == "balance_desc":
        query = query.order_by(balance_expr.desc())
    elif sort == "balance_asc":
        query = query.order_by(balance_expr.asc())
    elif sort == "name_asc":
        query = query.order_by(Customer.name.asc())
    elif sort == "created_desc":
        query = query.order_by(Customer.created_at.desc())
        
    results = query.all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "phone": r.phone,
            "balance": r.balance,
            "created_at": r.created_at
        } for r in results
    ]

# 22. CUSTOMER QUICK LIST (SCOPED, last transaction ordered)
@app.get("/api/customers/quick-list")
def get_customers_quick_list(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    results = db.query(
        Customer.id,
        Customer.name,
        Customer.phone
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).order_by(
        func.max(Transaction.date).desc(), Customer.created_at.desc()
    ).all()
    
    return [{"id": r.id, "name": r.name, "phone": r.phone} for r in results]

# 13. GET CUSTOMER BY ID (PAGINATED, SCOPED)
@app.get("/api/customers/{customer_id}")
def get_customer(
    customer_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    balance_expr = get_balance_expr()
    cust_data = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.created_at,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.id == customer_id,
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).first()
    
    if not cust_data:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    total_txs = db.query(Transaction).filter(Transaction.customer_id == customer_id).count()
    txs = db.query(Transaction).filter(
        Transaction.customer_id == customer_id
    ).order_by(Transaction.date.desc(), Transaction.id.desc()).offset((page - 1) * size).limit(size).all()
    
    return {
        "id": cust_data.id,
        "name": cust_data.name,
        "phone": cust_data.phone,
        "balance": cust_data.balance,
        "created_at": cust_data.created_at,
        "total_transactions": total_txs,
        "page": page,
        "pages": (total_txs + size - 1) // size if total_txs > 0 else 1,
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "note": t.note,
                "date": t.date,
                "created_at": t.created_at,
                "edited_at": t.edited_at
            } for t in txs
        ]
    }

# 14. UPDATE CUSTOMER (SCOPED)
@app.put("/api/customers/{customer_id}")
def update_customer(
    customer_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    name = payload.get("name")
    phone = payload.get("phone")
    
    if not name or name.strip() == "":
        raise HTTPException(status_code=400, detail="Customer name is required.")
        
    customer.name = name.strip()
    customer.phone = phone.strip() if phone else None
    db.commit()
    return {"id": customer.id, "name": customer.name, "phone": customer.phone}

# 15. DELETE CUSTOMER (SCOPED)
@app.delete("/api/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    force: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    balance_expr = get_balance_expr()
    balance = db.query(balance_expr).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(Customer.id == customer_id).group_by(Customer.id).scalar() or 0
    
    if balance != 0 and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "outstanding_balance",
                "balance": balance,
                "message": f"This customer has an outstanding balance of ₹{format_rupees(balance)}. Delete anyway?"
            }
        )
        
    db.delete(customer)
    db.commit()
    return {"message": "Customer and all transactions deleted successfully."}


# --- TRANSACTION ENDPOINTS (SCOPED) ---

# 16. CREATE TRANSACTION (SCOPED & IDEMPOTENT)
@app.post("/api/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    customer_id = payload.get("customer_id")
    tx_type = payload.get("type")
    amount = payload.get("amount")
    note = payload.get("note")
    date_str = payload.get("date")
    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        idempotency_key = str(idempotency_key).strip()
        if len(idempotency_key) > 128:
            idempotency_key = idempotency_key[:128]
    
    customer_name = payload.get("customer_name")
    customer = None
    if customer_id and customer_id != "new":
        customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
    elif customer_name and str(customer_name).strip():
        clean_name = str(customer_name).strip()
        customer = db.query(Customer).filter(
            Customer.store_id == current_user.store_id,
            func.lower(Customer.name) == clean_name.lower()
        ).first()
        if not customer:
            customer = Customer(
                store_id=current_user.store_id,
                name=clean_name.title(),
                phone=payload.get("phone")
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
        customer_id = customer.id

    if not customer:
        raise HTTPException(status_code=400, detail="Valid customer_id or customer_name is required.")
        
    if tx_type not in ["credit", "payment"]:
        raise HTTPException(status_code=400, detail="Transaction type must be 'credit' or 'payment'.")
        
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
        
    tx_date = datetime.utcnow()
    if date_str:
        try:
            tx_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format.")
            
    # Check Idempotency Key (Store Scoped)
    if idempotency_key:
        existing_tx = db.query(Transaction).join(Customer).filter(
            Transaction.idempotency_key == idempotency_key,
            Customer.store_id == current_user.store_id
        ).first()
        if existing_tx:
            # Check if payload parameters match
            if existing_tx.customer_id == customer_id and existing_tx.type == tx_type and existing_tx.amount == amount:
                current_bal = get_customer_balance(db, customer_id)
                return {
                    "id": existing_tx.id,
                    "customer_id": existing_tx.customer_id,
                    "customer_name": customer.name,
                    "type": existing_tx.type,
                    "amount": existing_tx.amount,
                    "note": existing_tx.note,
                    "date": existing_tx.date,
                    "idempotency_key": existing_tx.idempotency_key,
                    "current_balance": current_bal,
                    "idempotent_replay": True
                }
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key reused with different transaction parameters."
                )

    new_tx = Transaction(
        customer_id=customer_id,
        created_by_user_id=current_user.id,
        type=tx_type,
        amount=amount,
        note=note.strip() if note else None,
        date=tx_date,
        idempotency_key=idempotency_key
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    
    current_bal = get_customer_balance(db, customer_id)
    
    return {
        "id": new_tx.id,
        "customer_id": new_tx.customer_id,
        "customer_name": customer.name,
        "type": new_tx.type,
        "amount": new_tx.amount,
        "note": new_tx.note,
        "date": new_tx.date,
        "idempotency_key": new_tx.idempotency_key,
        "current_balance": current_bal,
        "idempotent_replay": False
    }

# 17. GET TRANSACTIONS FOR CUSTOMER (SCOPED)
@app.get("/api/transactions/{customer_id}")
def get_customer_transactions(
    customer_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    total_txs = db.query(Transaction).filter(Transaction.customer_id == customer_id).count()
    txs = db.query(Transaction).filter(
        Transaction.customer_id == customer_id
    ).order_by(Transaction.date.desc(), Transaction.id.desc()).offset((page - 1) * size).limit(size).all()
    
    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "note": t.note,
                "date": t.date,
                "created_at": t.created_at,
                "edited_at": t.edited_at
            } for t in txs
        ],
        "total_transactions": total_txs,
        "page": page,
        "pages": (total_txs + size - 1) // size if total_txs > 0 else 1
    }

# 18. UPDATE TRANSACTION (SCOPED)
@app.put("/api/transactions/{tx_id}")
def update_transaction(
    tx_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Enforce data isolation by joining Customer
    tx = db.query(Transaction).select_from(Transaction).join(Customer).filter(
        Transaction.id == tx_id,
        Customer.store_id == current_user.store_id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    amount = payload.get("amount")
    note = payload.get("note")
    
    if amount is not None:
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
        tx.amount = amount
        
    tx.note = note.strip() if note else None
    tx.edited_at = datetime.utcnow()
    
    db.commit()
    db.refresh(tx)
    
    return {
        "id": tx.id,
        "customer_id": tx.customer_id,
        "type": tx.type,
        "amount": tx.amount,
        "note": tx.note,
        "date": tx.date,
        "edited_at": tx.edited_at
    }

# 19. DELETE TRANSACTION (SCOPED - Returns full object for UNDO)
@app.delete("/api/transactions/{tx_id}")
def delete_transaction(
    tx_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tx = db.query(Transaction).select_from(Transaction).join(Customer).filter(
        Transaction.id == tx_id,
        Customer.store_id == current_user.store_id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    # Read values before deleting
    tx_data = {
        "customer_id": tx.customer_id,
        "type": tx.type,
        "amount": tx.amount,
        "note": tx.note,
        "date": tx.date.isoformat() if tx.date else None
    }
    
    db.delete(tx)
    db.commit()
    return {"message": "Transaction deleted successfully.", "deleted_transaction": tx_data}


# --- VOICE KHATA ENDPOINTS (AUTHENTICATED & STORE-SCOPED) ---

@app.post("/api/voice/transcribe")
async def voice_transcribe(
    request: Request,
    language: str = Query("te"),
    x_mock_transcript: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user)
):
    check_voice_rate_limit(current_user.id)
    
    if x_mock_transcript:
        return {
            "transcript": x_mock_transcript.strip(),
            "language": language,
            "provider": "mock"
        }
        
    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio payload provided.")
        
    content_type = request.headers.get("content-type", "audio/webm")
    if ";" in content_type:
        content_type = content_type.split(";")[0].strip()
        
    try:
        result = transcribe_audio(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language_hint=language,
            mock_transcript=None
        )
        return result
    except SpeechServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Audio transcription failed.")


@app.post("/api/voice/parse")
def voice_parse(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_voice_rate_limit(current_user.id)
    transcript = payload.get("transcript")
    if not transcript or not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is required.")
        
    language = payload.get("language", "te")
    
    # 1. AI extraction to draft
    draft = extract_transaction_draft(transcript=transcript.strip(), language=language)
    
    # 2. Store-scoped customer matching
    cust_match = match_customer(
        db=db,
        store_id=current_user.store_id,
        spoken_name=draft.customer_name_spoken
    )
    
    return {
        "draft": draft.model_dump(),
        "customer_match": cust_match
    }


# --- DASHBOARD & UTILITY ENDPOINTS ---

# 20. DASHBOARD SUMMARY (SCOPED)
@app.get("/api/dashboard/summary")
def get_dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    balance_expr = get_balance_expr()
    
    subquery = db.query(
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).subquery()
    
    total_outstanding = db.query(func.sum(subquery.c.balance)).filter(subquery.c.balance > 0).scalar() or 0
    total_customers = db.query(Customer).filter(Customer.store_id == current_user.store_id).count()
    
    top_debtors_query = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).having(balance_expr > 0).order_by(balance_expr.desc()).limit(5).all()
    
    recent_txs = db.query(
        Transaction.id,
        Transaction.type,
        Transaction.amount,
        Transaction.note,
        Transaction.date,
        Customer.name.label("customer_name"),
        Customer.id.label("customer_id")
    ).select_from(Transaction).join(Customer).filter(
        Customer.store_id == current_user.store_id
    ).order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(10).all()
    
    store = db.query(Store).filter(Store.id == current_user.store_id).first()
    
    return {
        "shop_name": store.name if store else "My Store",
        "language": store.language if store else "en",
        "total_outstanding": total_outstanding,
        "total_customers": total_customers,
        "top_debtors": [
            {
                "id": d.id,
                "name": d.name,
                "phone": d.phone,
                "balance": d.balance
            } for d in top_debtors_query
        ],
        "recent_transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "note": t.note,
                "date": t.date,
                "customer_name": t.customer_name,
                "customer_id": t.customer_id
            } for t in recent_txs
        ]
    }

# 21. DAILY CLOSING SUMMARY (SCOPED)
@app.get("/api/dashboard/today")
def get_daily_closing(
    tz_offset: int = Query(330), # Default to IST (+330 minutes)
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Calculate start and end of current local day in UTC
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(minutes=tz_offset)
    
    local_start_of_day = datetime(local_now.year, local_now.month, local_now.day, 0, 0, 0) - timedelta(minutes=tz_offset)
    local_end_of_day = datetime(local_now.year, local_now.month, local_now.day, 23, 59, 59) - timedelta(minutes=tz_offset)
    
    txs = db.query(
        Transaction.id,
        Transaction.type,
        Transaction.amount,
        Transaction.note,
        Transaction.date,
        Customer.name.label("customer_name")
    ).select_from(Transaction).join(Customer).filter(
        Customer.store_id == current_user.store_id,
        Transaction.date >= local_start_of_day,
        Transaction.date <= local_end_of_day
    ).order_by(Transaction.date.desc()).all()
    
    total_credit = sum(t.amount for t in txs if t.type == "credit")
    total_payment = sum(t.amount for t in txs if t.type == "payment")
    
    return {
        "date": local_now.strftime("%Y-%m-%d"),
        "total_credit_given": total_credit,
        "total_payments_received": total_payment,
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "note": t.note,
                "date": t.date,
                "customer_name": t.customer_name
            } for t in txs
        ]
    }




# --- REMINDERS (SCOPED) ---

# 23. GET REMINDER LINK
@app.get("/api/customers/{customer_id}/reminder-link")
def get_reminder_link(
    customer_id: int,
    tz_offset: int = Query(330),
    lang: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    balance_expr = get_balance_expr()
    cust_data = db.query(
        Customer.name,
        Customer.phone,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.id == customer_id,
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).first()
    
    if not cust_data:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    if not cust_data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add a valid phone number to send a reminder"
        )
        
    # Clean phone: keep only digits
    clean_phone = "".join(filter(str.isdigit, cust_data.phone))
    
    # Normalize to 10 digits
    if len(clean_phone) == 11 and clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]
    elif len(clean_phone) == 12 and clean_phone.startswith("91"):
        clean_phone = clean_phone[2:]
        
    if len(clean_phone) != 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add a valid phone number to send a reminder"
        )
        
    final_phone = "91" + clean_phone
    balance_formatted = format_rupees(cust_data.balance)
    
    store = db.query(Store).filter(Store.id == current_user.store_id).first()
    
    # Resolve target language for reminder text (falls back to store language settings)
    target_lang = lang if lang in ["en", "te", "hi"] else store.language
    
    # Fetch today's credit transactions for items list
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(minutes=tz_offset)
    local_start_of_day = datetime(local_now.year, local_now.month, local_now.day, 0, 0, 0) - timedelta(minutes=tz_offset)
    local_end_of_day = datetime(local_now.year, local_now.month, local_now.day, 23, 59, 59) - timedelta(minutes=tz_offset)

    today_credits = db.query(Transaction).filter(
        Transaction.customer_id == customer_id,
        Transaction.type == "credit",
        Transaction.date >= local_start_of_day,
        Transaction.date <= local_end_of_day
    ).all()

    today_items_text = ""
    if today_credits:
        notes = []
        for t in today_credits:
            amt_rs = format_rupees(t.amount)
            note_desc = t.note.strip() if t.note and t.note.strip() else ("Credit" if target_lang == "en" else "उधार" if target_lang == "hi" else "అప్పు")
            notes.append(f"{note_desc} (₹{amt_rs})")
            
        items_list = ", ".join(notes)
        if target_lang == "te":
            today_items_text = f"ఈరోజు కొనుగోలు చేసినవి: {items_list}. "
        elif target_lang == "hi":
            today_items_text = f"आज की खरीदारी: {items_list}. "
        else:
            today_items_text = f"Today's purchase: {items_list}. "

    # Build translated message
    if target_lang == "te":
        message = f"నమస్తే {cust_data.name}, {store.name} లో మీ మొత్తం బకాయి రుసుము ₹{balance_formatted}. {today_items_text}దయచేసి వీలైనప్పుడు చెల్లించగలరు. ధన్యవాదాలు!"
    elif target_lang == "hi":
        message = f"नमस्ते {cust_data.name}, {store.name} में आपका कुल बकाया ₹{balance_formatted} है। {today_items_text}कृपया सुविधानुसार भुगतान करें। धन्यवाद!"
    else:
        message = f"Namaste {cust_data.name}, your udhara balance at {store.name} is ₹{balance_formatted}. {today_items_text}Please settle when convenient. Thank you!"
    
    url_encoded_msg = quote(message)
    wa_link = f"https://wa.me/{final_phone}?text={url_encoded_msg}"
    
    return {
        "wa_link": wa_link,
        "sms_text": message
    }


# --- CSV EXPORT ---

# 24. EXPORT TRANSACTIONS
@app.get("/api/export/transactions")
def export_transactions(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    tz_offset: int = Query(330),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Parse dates or fallback to current month
    if from_date and to_date:
        try:
            start_date = datetime.fromisoformat(from_date) - timedelta(minutes=tz_offset)
            # End of to_date day
            to_dt = datetime.fromisoformat(to_date)
            end_date = datetime(to_dt.year, to_dt.month, to_dt.day, 23, 59, 59) - timedelta(minutes=tz_offset)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date parameters. Use YYYY-MM-DD.")
    else:
        # Default to current month in local time
        local_now = datetime.utcnow() + timedelta(minutes=tz_offset)
        import calendar
        _, last_day = calendar.monthrange(local_now.year, local_now.month)
        
        start_date = datetime(local_now.year, local_now.month, 1, 0, 0, 0) - timedelta(minutes=tz_offset)
        end_date = datetime(local_now.year, local_now.month, last_day, 23, 59, 59) - timedelta(minutes=tz_offset)
        
    txs = db.query(
        Transaction.date,
        Transaction.type,
        Transaction.amount,
        Transaction.note,
        Customer.name.label("customer_name"),
        Customer.phone.label("customer_phone")
    ).select_from(Transaction).join(Customer).filter(
        Customer.store_id == current_user.store_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).order_by(Transaction.date.desc()).all()
    
    # Generate CSV stream
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Customer Name", "Phone", "Type", "Amount (Rs)", "Note", "Date"])
    
    for t in txs:
        amount_rs = t.amount / 100.0
        # Convert date back to local time for export
        local_date = t.date + timedelta(minutes=tz_offset)
        formatted_date = local_date.strftime("%d-%m-%Y %H:%M")
        writer.writerow([
            t.customer_name,
            t.customer_phone or "N/A",
            t.type.capitalize(),
            f"{amount_rs:.2f}",
            t.note or "",
            formatted_date
        ])
        
    output.seek(0)
    
    response = StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=ledger_transactions.csv"
    return response


# --- PDF EXPORT (ENTIRE LEDGER + TODAY LEDGER) ---

@app.get("/api/export/pdf")
def export_pdf(
    tz_offset: int = Query(330),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Fetch entire ledger balances
    balance_expr = get_balance_expr()
    customers = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(
        Customer.store_id == current_user.store_id
    ).group_by(Customer.id).order_by(Customer.name.asc()).all()
    
    # 2. Fetch today's transactions for this store
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(minutes=tz_offset)
    local_start_of_day = datetime(local_now.year, local_now.month, local_now.day, 0, 0, 0) - timedelta(minutes=tz_offset)
    local_end_of_day = datetime(local_now.year, local_now.month, local_now.day, 23, 59, 59) - timedelta(minutes=tz_offset)
    
    today_txs = db.query(
        Transaction.id,
        Transaction.type,
        Transaction.amount,
        Transaction.note,
        Transaction.date,
        Customer.name.label("customer_name")
    ).select_from(Transaction).join(Customer).filter(
        Customer.store_id == current_user.store_id,
        Transaction.date >= local_start_of_day,
        Transaction.date <= local_end_of_day
    ).order_by(Transaction.date.desc()).all()

    store = db.query(Store).filter(Store.id == current_user.store_id).first()
    
    # Shop reports translations
    shop_trans = {
        "en": {
            "title_suffix": "Udhara Ledger Report",
            "date": "Date",
            "time": "Generated Local Time",
            "summary_title": "Today's Summary Metrics",
            "today_credit": "Today's Credit Given:",
            "today_payment": "Today's Payments Received:",
            "total_ledger": "Total Ledger Due:",
            "active_accounts": "Active Customer Accounts:",
            "today_entries": "Today's Transaction Entries",
            "no_entries": "No transaction logs recorded today.",
            "cust_name": "Customer Name",
            "type": "Type",
            "amount": "Amount",
            "note": "Note / Description",
            "logged_time": "Logged Time",
            "entire_balances": "Entire Outstanding Ledger Dues",
            "no_customers": "No customers registered.",
            "phone": "Phone Number",
            "status": "Status",
            "due": "Due Amount",
            "owes": "Owes Shop",
            "overpaid": "Overpaid",
            "settled": "Settled"
        },
        "te": {
            "title_suffix": "ఉధార లెడ్జర్ నివేదిక",
            "date": "తేదీ",
            "time": "జనరేట్ చేసిన సమయం",
            "summary_title": "ఈరోజు సారాంశం",
            "today_credit": "ఈరోజు ఇచ్చిన అప్పు:",
            "today_payment": "ఈరోజు వసూలైన మొత్తం:",
            "total_ledger": "మొత్తం బకాయి నిల్వ:",
            "active_accounts": "యాక్టివ్ ఖాతాల సంఖ్య:",
            "today_entries": "ఈరోజు లావాదేవీలు",
            "no_entries": "ఈరోజు ఎటువంటి లావాదేవీలు నమోదు కాలేదు.",
            "cust_name": "కస్టమర్ పేరు",
            "type": "రకం",
            "amount": "మొత్తం",
            "note": "వివరణ / వస్తువు వివరాలు",
            "logged_time": "సమయం",
            "entire_balances": "కస్టమర్ల మొత్తం బకాయిల పట్టిక",
            "no_customers": "కస్టమర్లు ఎవరూ లేరు.",
            "phone": "ఫోన్ నెంబర్",
            "status": "స్థితి",
            "due": "మొత్తం బకాయి",
            "owes": "బకాయి ఉన్నారు",
            "overpaid": "అడ్వాన్స్ చెల్లించారు",
            "settled": "సరిపోయింది"
        },
        "hi": {
            "title_suffix": "उधार खाता रिपोर्ट",
            "date": "तारीख",
            "time": "रिपोर्ट का समय",
            "summary_title": "आज का सारांश",
            "today_credit": "आज दिया गया उधार:",
            "today_payment": "आज मिला भुगतान:",
            "total_ledger": "कुल खाता बकाया:",
            "active_accounts": "सक्रिय ग्राहकों की संख्या:",
            "today_entries": "आज के लेन-देन",
            "no_entries": "आज कोई लेन-देन दर्ज नहीं किया गया।",
            "cust_name": "ग्राहक का नाम",
            "type": "प्रकार",
            "amount": "राशि",
            "note": "विवरण / सामान",
            "logged_time": "समय",
            "entire_balances": "सभी बकाया खातों की सूची",
            "no_customers": "कोई ग्राहक पंजीकृत नहीं है।",
            "phone": "फ़ोन नंबर",
            "status": "स्थिति",
            "due": "कुल बकाया",
            "owes": "बकाया है",
            "overpaid": "अग्रिम भुगतान",
            "settled": "समान है"
        }
    }
    
    st_lang = store.language if store.language in ["en", "te", "hi"] else "en"
    t = shop_trans[st_lang]
    
    # Resolve active font for whole ledger document
    active_font = FONT_NAME
    if st_lang == "te":
        active_font = TELUGU_FONT_NAME
    elif st_lang == "en":
        active_font = "Helvetica"

    # Create PDF Report
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=active_font,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#4F46E5"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontName=active_font,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceBefore=14,
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#374151")
    )
    bold_cell = ParagraphStyle(
        'BoldCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#111827")
    )
    header_cell = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=8,
        leading=10,
        textColor=colors.white
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#374151")
    )

    elements = []
    
    # Title Header
    elements.append(Paragraph(f"{store.name} - {t['title_suffix']}", title_style))
    elements.append(Paragraph(f"{t['date']}: {local_now.strftime('%d-%m-%Y')}  |  {t['time']}: {local_now.strftime('%I:%M %p')}", subtitle_style))
    
    # Section 1: Today's Summary Metrics
    elements.append(Paragraph(t["summary_title"], section_style))
    total_today_credit = sum(tx.amount for tx in today_txs if tx.type == "credit")
    total_today_payment = sum(tx.amount for tx in today_txs if tx.type == "payment")
    total_outstanding_ledger = sum(c.balance for c in customers if c.balance > 0)

    summary_data = [
        [
            Paragraph(t["today_credit"], bold_cell),
            Paragraph(f"₹{format_rupees(total_today_credit)}", body_style),
            Paragraph(t["total_ledger"], bold_cell),
            Paragraph(f"₹{format_rupees(total_outstanding_ledger)}", body_style)
        ],
        [
            Paragraph(t["today_payment"], bold_cell),
            Paragraph(f"₹{format_rupees(total_today_payment)}", body_style),
            Paragraph(t["active_accounts"], bold_cell),
            Paragraph(str(len(customers)), body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[140, 130, 140, 130])
    summary_table.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F9FAFB"))
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10))

    # Section 2: Today's Transactions
    elements.append(Paragraph(t["today_entries"], section_style))
    if not today_txs:
        elements.append(Paragraph(f"<i>{t['no_entries']}</i>", body_style))
    else:
        tx_table_data = [[
            Paragraph(t["cust_name"], header_cell),
            Paragraph(t["type"], header_cell),
            Paragraph(t["amount"], header_cell),
            Paragraph(t["note"], header_cell),
            Paragraph(t["logged_time"], header_cell)
        ]]
        for tx in today_txs:
            local_time = tx.date + timedelta(minutes=tz_offset)
            type_lbl = "Credit" if tx.type == "credit" else "Payment"
            type_color = "#EF4444" if tx.type == "credit" else "#10B981"
            type_markup = f"<font color='{type_color}'><b>{type_lbl}</b></font>"
            tx_table_data.append([
                Paragraph(tx.customer_name, table_cell),
                Paragraph(type_markup, table_cell),
                Paragraph(f"₹{format_rupees(tx.amount)}", table_cell),
                Paragraph(tx.note or "-", table_cell),
                Paragraph(local_time.strftime("%I:%M %p"), table_cell)
            ])
        tx_table = Table(tx_table_data, colWidths=[120, 80, 80, 160, 100])
        tx_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#4F46E5")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(tx_table)

    elements.append(Spacer(1, 10))

    # Section 3: Entire Udhara Balances
    elements.append(Paragraph(t["entire_balances"], section_style))
    if not customers:
        elements.append(Paragraph(f"<i>{t['no_customers']}</i>", body_style))
    else:
        cust_table_data = [[
            Paragraph(t["cust_name"], header_cell),
            Paragraph(t["phone"], header_cell),
            Paragraph(t["status"], header_cell),
            Paragraph(t["due"], header_cell)
        ]]
        for c in customers:
            status_text = t["owes"] if c.balance > 0 else t["overpaid"] if c.balance < 0 else t["settled"]
            bal_color = "#EF4444" if c.balance > 0 else "#10B981" if c.balance < 0 else "#6B7280"
            bal_text = f"<font color='{bal_color}'><b>₹{format_rupees(abs(c.balance))}</b></font>"
            cust_table_data.append([
                Paragraph(c.name, table_cell),
                Paragraph(c.phone or "-", table_cell),
                Paragraph(status_text, table_cell),
                Paragraph(bal_text, table_cell)
            ])
        cust_table = Table(cust_table_data, colWidths=[180, 120, 110, 130])
        cust_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#4F46E5")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(cust_table)

    doc.build(elements)
    buffer.seek(0)
    
    response = StreamingResponse(
        io.BytesIO(buffer.getvalue()),
        media_type="application/pdf"
    )
    response.headers["Content-Disposition"] = "attachment; filename=udhara_ledger_report.pdf"
    return response


# --- CUSTOMER TRANSACTION REPORT PDF (TODAY vs ALL TIME) ---

@app.get("/api/customers/{customer_id}/export/pdf")
def export_customer_pdf(
    customer_id: int,
    range: str = Query("all"), # "today" | "all"
    lang: str = Query("en"), # "en" | "te" | "hi"
    tz_offset: int = Query(330),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify customer and store scoping
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.store_id == current_user.store_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    balance_expr = get_balance_expr()
    cust_balance = db.query(balance_expr).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(Customer.id == customer_id).group_by(Customer.id).scalar() or 0

    # Fetch transactions
    tx_query = db.query(Transaction).filter(Transaction.customer_id == customer_id)
    
    if range == "today":
        utc_now = datetime.utcnow()
        local_now = utc_now + timedelta(minutes=tz_offset)
        local_start_of_day = datetime(local_now.year, local_now.month, local_now.day, 0, 0, 0) - timedelta(minutes=tz_offset)
        local_end_of_day = datetime(local_now.year, local_now.month, local_now.day, 23, 59, 59) - timedelta(minutes=tz_offset)
        tx_query = tx_query.filter(Transaction.date >= local_start_of_day, Transaction.date <= local_end_of_day)
        
    txs = tx_query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    
    # Translations dictionary for PDF structure
    translations_dict = {
        "en": {
            "title": "Customer Ledger Report",
            "customer": "Customer Name",
            "phone": "Phone",
            "store": "Store",
            "balance": "Due Amount",
            "range": "Report Range",
            "today": "Today's Transactions Only",
            "all": "All-time Transaction History",
            "date": "Date / Time",
            "type": "Type",
            "amount": "Amount",
            "note": "Note / Description",
            "credit": "Credit Given",
            "payment": "Payment Received",
            "total_credit": "Total Credit",
            "total_payment": "Total Payment",
            "net_due": "Net Due Amount",
            "owes": "Owes Shop",
            "overpaid": "Overpaid",
            "settled": "Settled",
            "empty": "No transaction entries found for this range."
        },
        "te": {
            "title": "కస్టమర్ లెడ్జర్ నివేదిక",
            "customer": "కస్టమర్ పేరు",
            "phone": "ఫోన్ నెంబర్",
            "store": "షాప్ పేరు",
            "balance": "మొత్తం బకాయి",
            "range": "రిపోర్ట్ వ్యవధి",
            "today": "ఈరోజు లావాదేవీలు మాత్రమే",
            "all": "మొత్తం లావాదేవీల చరిత్ర",
            "date": "తేదీ / సమయం",
            "type": "రకం",
            "amount": "మొత్తం",
            "note": "వివరణ / వస్తువు వివరాలు",
            "credit": "అప్పు ఇచ్చాము",
            "payment": "వసూలు అయింది",
            "total_credit": "మొత్తం అప్పు",
            "total_payment": "మొత్తం చెల్లింపు",
            "net_due": "నికర బకాయి",
            "owes": "బకాయి ఉన్నారు",
            "overpaid": "అడ్వాన్స్ చెల్లించారు",
            "settled": "సరిపోయింది",
            "empty": "ఈ వ్యవధిలో ఎటువంటి లావాదేవీలు లేవు."
        },
        "hi": {
            "title": "ग्राहक खाता रिपोर्ट",
            "customer": "ग्राहक का नाम",
            "phone": "फ़ोन नंबर",
            "store": "दुकान का नाम",
            "balance": "कुल बकाया",
            "range": "रिपोर्ट अवधि",
            "today": "केवल आज के लेन-देन",
            "all": "कुल खाता इतिहास",
            "date": "तारीख / समय",
            "type": "प्रकार",
            "amount": "राशि",
            "note": "विवरण / सामान",
            "credit": "उधार दिया",
            "payment": "भुगतान मिला",
            "total_credit": "कुल उधार",
            "total_payment": "कुल भुगतान",
            "net_due": "कुल शुद्ध बकाया",
            "owes": "बकाया है",
            "overpaid": "अग्रिम भुगतान",
            "settled": "समान है",
            "empty": "इस अवधि के लिए कोई लेन-देन नहीं मिला।"
        }
    }
    
    t = translations_dict.get(lang if lang in ["en", "te", "hi"] else "en")
    store = db.query(Store).filter(Store.id == current_user.store_id).first()
    
    # Resolve active font for customer PDF document
    active_font = FONT_NAME
    if lang == "te":
        active_font = TELUGU_FONT_NAME
    elif lang == "en":
        active_font = "Helvetica"

    # Create PDF Report
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles - using registered TTFont (FreeSans / NotoSansTelugu)
    title_style = ParagraphStyle(
        'CustTitle',
        parent=styles['Heading1'],
        fontName=active_font,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#4F46E5"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'CustSub',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'CustSection',
        parent=styles['Heading2'],
        fontName=active_font,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceBefore=14,
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        'CustBody',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#374151")
    )
    bold_cell = ParagraphStyle(
        'CustBoldCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#111827")
    )
    header_cell = ParagraphStyle(
        'CustHeaderCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=8,
        leading=10,
        textColor=colors.white
    )
    table_cell = ParagraphStyle(
        'CustTableCell',
        parent=styles['Normal'],
        fontName=active_font,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#374151")
    )

    elements = []
    
    elements.append(Paragraph(t["title"], title_style))
    elements.append(Paragraph(f"{t['store']}: {store.name}  |  {t['customer']}: {customer.name}", subtitle_style))
    
    # Customer summary metrics
    bal_formatted = format_rupees(abs(cust_balance))
    status_label = t["owes"] if cust_balance > 0 else t["overpaid"] if cust_balance < 0 else t["settled"]
    range_label = t["today"] if range == "today" else t["all"]
    
    summary_data = [
        [
            Paragraph(f"<b>{t['customer']}:</b>", body_style), Paragraph(customer.name, body_style),
            Paragraph(f"<b>{t['balance']}:</b>", body_style), Paragraph(f"₹{bal_formatted} ({status_label})", bold_cell)
        ],
        [
            Paragraph(f"<b>{t['phone']}:</b>", body_style), Paragraph(customer.phone or "-", body_style),
            Paragraph(f"<b>{t['range']}:</b>", body_style), Paragraph(range_label, body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[110, 160, 110, 160])
    summary_table.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F9FAFB"))
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10))
    
    # Transactions table
    elements.append(Paragraph(range_label, section_style))
    if not txs:
        elements.append(Paragraph(f"<i>{t['empty']}</i>", body_style))
    else:
        tx_table_data = [[
            Paragraph(t["date"], header_cell),
            Paragraph(t["type"], header_cell),
            Paragraph(t["amount"], header_cell),
            Paragraph(t["note"], header_cell)
        ]]
        
        total_credit = sum(tx.amount for tx in txs if tx.type == "credit")
        total_payment = sum(tx.amount for tx in txs if tx.type == "payment")
        
        for tx in txs:
            local_time = tx.date + timedelta(minutes=tz_offset)
            type_text = t["credit"] if tx.type == "credit" else t["payment"]
            type_color = "#EF4444" if tx.type == "credit" else "#10B981"
            type_markup = f"<font color='{type_color}'><b>{type_text}</b></font>"
            
            tx_table_data.append([
                Paragraph(local_time.strftime("%d-%m-%Y %I:%M %p"), table_cell),
                Paragraph(type_markup, table_cell),
                Paragraph(f"₹{format_rupees(tx.amount)}", table_cell),
                Paragraph(tx.note or "-", table_cell)
            ])
            
        tx_table = Table(tx_table_data, colWidths=[130, 110, 100, 200])
        tx_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#4F46E5")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(tx_table)
        elements.append(Spacer(1, 10))
        
        # Totals Summary with calculations
        net_due = total_credit - total_payment
        totals_data = [
            [Paragraph(f"<b>{t['total_credit']}:</b>", body_style), Paragraph(f"₹{format_rupees(total_credit)}", body_style)],
            [Paragraph(f"<b>{t['total_payment']}:</b>", body_style), Paragraph(f"₹{format_rupees(total_payment)}", body_style)],
            [Paragraph(f"<b>{t['net_due']} ({t['total_credit']} - {t['total_payment']}):</b>", bold_cell), Paragraph(f"₹{format_rupees(net_due)}", bold_cell)]
        ]
        totals_table = Table(totals_data, colWidths=[200, 340])
        totals_table.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0,0), (-1,-1), 4)
        ]))
        elements.append(totals_table)
        
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"{customer.name}_report_{range}.pdf".replace(" ", "_")
    response = StreamingResponse(
        io.BytesIO(buffer.getvalue()),
        media_type="application/pdf"
    )
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response
