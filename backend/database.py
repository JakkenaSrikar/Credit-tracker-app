from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./udhara.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL, connect_args=connect_args
)

# Enable foreign key support in SQLite
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class ShopSettings(Base):
    __tablename__ = "shop_settings"
    id = Column(Integer, primary_key=True, index=True)
    shop_name = Column(String, nullable=False)
    owner_pin = Column(String, nullable=False)  # Hashed PIN

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)  # Optional/nullable
    created_at = Column(DateTime, default=datetime.utcnow)

    # Cascade delete transactions when customer is deleted
    transactions = relationship("Transaction", back_populates="customer", cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # "credit" | "payment"
    amount = Column(Integer, nullable=False)  # in paise
    note = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="transactions")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
