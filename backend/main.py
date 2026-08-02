import os
import time
import jwt
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from database import engine, Base, Customer, Transaction, ShopSettings, get_db

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kirana Shop Udhara Tracker API")

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

# Simple In-Memory Rate Limiting for Login
# Map IP -> {"count": int, "blocked_until": float, "last_attempt": float}
login_rate_limit = {}

def check_login_rate_limit(client_ip: str):
    now = time.time()
    if client_ip in login_rate_limit:
        record = login_rate_limit[client_ip]
        # Clean up block if time passed
        if record["blocked_until"] > 0:
            if now > record["blocked_until"]:
                login_rate_limit[client_ip] = {"count": 0, "blocked_until": 0, "last_attempt": now}
            else:
                remaining = int(record["blocked_until"] - now)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many login attempts. Please try again after {remaining} seconds."
                )
        
        # Reset count if last attempt was > 60 seconds ago
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


# Password Hashing using PBKDF2 (Zero external compiler dependencies)
import hashlib

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


# Token Generation & Verification
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=30)  # 30 days long-lived
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_current_shop(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        shop_id = payload.get("shop_id")
        if shop_id is None:
            raise HTTPException(
                status_code=status.HTTP_418_IM_A_TEAPOT,  # Custom representation for invalid token
                detail="Could not validate credentials"
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    settings = db.query(ShopSettings).filter(ShopSettings.id == shop_id).first()
    if settings is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Shop settings not found")
    return settings


# Format balance in Rupees from Paise
def format_rupees(paise: int) -> str:
    amount_rs = paise / 100.0
    if amount_rs.is_integer():
        return f"{int(amount_rs)}"
    return f"{amount_rs:.2f}"


# --- ENDPOINTS ---

# 1. SETUP STATUS
@app.get("/api/setup/status")
def get_setup_status(db: Session = Depends(get_db)):
    settings = db.query(ShopSettings).first()
    if not settings:
        return {"setup_required": True}
    return {"setup_required": False, "shop_name": settings.shop_name}

# 2. FIRST-TIME SETUP
@app.post("/api/setup", status_code=status.HTTP_201_CREATED)
def setup_shop(payload: dict, db: Session = Depends(get_db)):
    # Check if already setup
    settings = db.query(ShopSettings).first()
    if settings:
        raise HTTPException(status_code=400, detail="Shop is already configured.")
    
    shop_name = payload.get("shop_name")
    pin = payload.get("pin")
    
    if not shop_name or not pin:
        raise HTTPException(status_code=400, detail="Shop name and 4-digit PIN are required.")
    
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits.")
    
    hashed_pin = hash_pin(pin)
    new_settings = ShopSettings(shop_name=shop_name, owner_pin=hashed_pin)
    db.add(new_settings)
    db.commit()
    db.refresh(new_settings)
    
    # Auto-login after setup
    token = create_access_token(data={"shop_id": new_settings.id})
    return {"token": token, "shop_name": new_settings.shop_name}

# 3. LOGIN
@app.post("/api/login")
def login(payload: dict, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)
    
    pin = payload.get("pin")
    if not pin:
        raise HTTPException(status_code=400, detail="PIN is required.")
        
    settings = db.query(ShopSettings).first()
    if not settings:
        raise HTTPException(status_code=400, detail="Shop settings not configured. Please complete setup first.")
        
    if verify_pin(pin, settings.owner_pin):
        record_successful_login(client_ip)
        token = create_access_token(data={"shop_id": settings.id})
        return {"token": token, "shop_name": settings.shop_name}
    else:
        record_failed_login(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN.")


# --- CUSTOMER ENDPOINTS ---

# Helper expression for dynamic balance calculation
def get_balance_expr():
    credit_sum = func.coalesce(func.sum(case((Transaction.type == 'credit', Transaction.amount), else_=0)), 0)
    payment_sum = func.coalesce(func.sum(case((Transaction.type == 'payment', Transaction.amount), else_=0)), 0)
    return credit_sum - payment_sum

# 4. CREATE CUSTOMER
@app.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: dict, current_shop: ShopSettings = Depends(get_current_shop), db: Session = Depends(get_db)):
    name = payload.get("name")
    phone = payload.get("phone")
    
    if not name or name.strip() == "":
        raise HTTPException(status_code=400, detail="Customer name is required.")
    
    # Strip spaces
    name = name.strip()
    phone = phone.strip() if phone else None
    
    new_customer = Customer(name=name, phone=phone)
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    
    return {"id": new_customer.id, "name": new_customer.name, "phone": new_customer.phone, "balance": 0}

# 5. GET CUSTOMERS (SEARCH & SORT)
@app.get("/api/customers")
def get_customers(
    search: Optional[str] = Query(None),
    sort: str = Query("balance_desc"),
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    balance_expr = get_balance_expr()
    
    query = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.created_at,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(Transaction, Customer.id == Transaction.customer_id).group_by(Customer.id)
    
    if search:
        # Case insensitive fuzzy match
        query = query.filter(Customer.name.like(f"%{search}%"))
        
    # Sort mapping
    if sort == "balance_desc":
        query = query.order_by(balance_expr.desc())
    elif sort == "balance_asc":
        query = query.order_by(balance_expr.asc())
    elif sort == "name_asc":
        query = query.order_by(Customer.name.asc())
    elif sort == "created_desc":
        query = query.order_by(Customer.created_at.desc())
    else:
        query = query.order_by(balance_expr.desc())
        
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

# 6. GET CUSTOMER BY ID (PAGINATED TRANSACTIONS)
@app.get("/api/customers/{customer_id}")
def get_customer(
    customer_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    # Calculate balance dynamically
    balance_expr = get_balance_expr()
    cust_data = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.created_at,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(Transaction, Customer.id == Transaction.customer_id).filter(Customer.id == customer_id).group_by(Customer.id).first()
    
    if not cust_data:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    # Fetch paginated transactions (most recent first)
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

# 7. UPDATE CUSTOMER
@app.put("/api/customers/{customer_id}")
def update_customer(
    customer_id: int,
    payload: dict,
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    name = payload.get("name")
    phone = payload.get("phone")
    
    if not name or name.strip() == "":
        raise HTTPException(status_code=400, detail="Customer name is required.")
        
    customer.name = name.strip()
    customer.phone = phone.strip() if phone else None
    
    db.commit()
    db.refresh(customer)
    
    return {"id": customer.id, "name": customer.name, "phone": customer.phone}

# 8. DELETE CUSTOMER (BLOCK IF BALANCE != 0 UNLESS FORCE=TRUE)
@app.delete("/api/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    force: bool = Query(False),
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    # Calculate balance
    balance_expr = get_balance_expr()
    balance_data = db.query(balance_expr).select_from(Customer).outerjoin(
        Transaction, Customer.id == Transaction.customer_id
    ).filter(Customer.id == customer_id).group_by(Customer.id).scalar()
    
    balance = balance_data if balance_data is not None else 0
    
    if balance != 0 and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "outstanding_balance",
                "balance": balance,
                "message": f"This customer has an outstanding balance of ₹{format_rupees(balance)}. Delete anyway?"
            }
        )
        
    # Proceed to delete customer (Cascade will delete transactions)
    db.delete(customer)
    db.commit()
    return {"message": "Customer and all transactions deleted successfully."}


# --- TRANSACTION ENDPOINTS ---

# 9. CREATE TRANSACTION
@app.post("/api/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: dict,
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    customer_id = payload.get("customer_id")
    tx_type = payload.get("type")  # "credit" | "payment"
    amount = payload.get("amount")  # in paise
    note = payload.get("note")
    date_str = payload.get("date")  # ISO datetime string (optional)
    
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required.")
        
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
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
        type=tx_type,
        amount=amount,
        note=note,
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

# 10. GET PAGINATED TRANSACTIONS FOR CUSTOMER
@app.get("/api/transactions/{customer_id}")
def get_customer_transactions(
    customer_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
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

# 11. UPDATE TRANSACTION
@app.put("/api/transactions/{tx_id}")
def update_transaction(
    tx_id: int,
    payload: dict,
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    amount = payload.get("amount")
    note = payload.get("note")
    
    if amount is not None:
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
        tx.amount = amount
        
    tx.note = note
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

# 12. DELETE TRANSACTION
@app.delete("/api/transactions/{tx_id}")
def delete_transaction(
    tx_id: int,
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
        
    db.delete(tx)
    db.commit()
    return {"message": "Transaction deleted successfully."}


# --- DASHBOARD ENDPOINTS ---

# 13. DASHBOARD SUMMARY
@app.get("/api/dashboard/summary")
def get_dashboard_summary(current_shop: ShopSettings = Depends(get_current_shop), db: Session = Depends(get_db)):
    # Calculate total outstanding credit (sum of all POSITIVE customer balances)
    # Using SQL Subquery
    balance_expr = get_balance_expr()
    subquery = db.query(
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(Transaction, Customer.id == Transaction.customer_id).group_by(Customer.id).subquery()
    
    total_outstanding = db.query(func.sum(subquery.c.balance)).filter(subquery.c.balance > 0).scalar() or 0
    total_customers = db.query(Customer).count()
    
    # Top Debtors (customers with positive balance, ordered desc)
    top_debtors_query = db.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(Transaction, Customer.id == Transaction.customer_id).group_by(Customer.id).having(balance_expr > 0).order_by(balance_expr.desc()).limit(5).all()
    
    # Recent Transactions (last 10 transactions with customer info)
    recent_txs = db.query(
        Transaction.id,
        Transaction.type,
        Transaction.amount,
        Transaction.note,
        Transaction.date,
        Customer.name.label("customer_name"),
        Customer.id.label("customer_id")
    ).select_from(Transaction).join(Customer, Transaction.customer_id == Customer.id).order_by(
        Transaction.created_at.desc(), Transaction.id.desc()
    ).limit(10).all()
    
    return {
        "shop_name": current_shop.shop_name,
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


# --- REMINDERS ENDPOINT ---

# 14. REMINDER LINK (WHATSAPP & SMS)
@app.get("/api/customers/{customer_id}/reminder-link")
def get_reminder_link(
    customer_id: int,
    current_shop: ShopSettings = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    # Fetch customer and current balance
    balance_expr = get_balance_expr()
    cust_data = db.query(
        Customer.name,
        Customer.phone,
        balance_expr.label("balance")
    ).select_from(Customer).outerjoin(Transaction, Customer.id == Transaction.customer_id).filter(Customer.id == customer_id).group_by(Customer.id).first()
    
    if not cust_data:
        raise HTTPException(status_code=404, detail="Customer not found.")
        
    if not cust_data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reminders require a phone number. Please edit this customer to add a phone number."
        )
        
    balance_formatted = format_rupees(cust_data.balance)
    
    # Message template
    # "Namaste [Name], your udhara balance at [Shop Name] is ₹[balance]. Please settle when convenient. Thank you!"
    message = f"Namaste {cust_data.name}, your udhara balance at {current_shop.shop_name} is ₹{balance_formatted}. Please settle when convenient. Thank you!"
    
    # Ensure phone is formatted. Clean it of symbols (+, spaces, hyphens) but keep digits
    clean_phone = "".join(filter(str.isdigit, cust_data.phone))
    
    # Generate WhatsApp Link
    # wa.me format requires country code without leading + or 00. Let's check.
    # Default to India (+91) if it doesn't start with code or is 10 digits
    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone
        
    url_encoded_msg = quote(message)
    wa_link = f"https://wa.me/{clean_phone}?text={url_encoded_msg}"
    
    return {
        "wa_link": wa_link,
        "sms_text": message
    }
