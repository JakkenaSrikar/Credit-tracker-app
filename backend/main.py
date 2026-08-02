import os
import time
import jwt
import hashlib
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from database import engine, Base, Store, User, Customer, Transaction, get_db

# Initialize database tables
Base.metadata.create_all(bind=engine)

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

# 16. CREATE TRANSACTION (SCOPED)
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
    
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required.")
        
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
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
            
    new_tx = Transaction(
        customer_id=customer_id,
        created_by_user_id=current_user.id,
        type=tx_type,
        amount=amount,
        note=note.strip() if note else None,
        date=tx_date
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    
    return {
        "id": new_tx.id,
        "customer_id": new_tx.customer_id,
        "type": new_tx.type,
        "amount": new_tx.amount,
        "note": new_tx.note,
        "date": new_tx.date
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
    message = f"Namaste {cust_data.name}, your udhara balance at {store.name} is ₹{balance_formatted}. Please settle when convenient. Thank you!"
    
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
