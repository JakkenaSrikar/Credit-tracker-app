import os
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from database import DATABASE_URL, Base, engine

def run_migration():
    print(f"Connecting to database: {DATABASE_URL}")
    
    # 1. Create new tables (stores, users) if they don't exist
    Base.metadata.create_all(bind=engine)
    print("Created stores and users tables if they did not exist.")
    
    # Check if settings table exists
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    with engine.begin() as conn:
        # 2. Check if old shop_settings table exists
        if "shop_settings" in tables:
            print("Found deprecated 'shop_settings' table. Migrating old configuration...")
            
            # Read old settings
            settings = conn.execute(text("SELECT shop_name, owner_pin FROM shop_settings")).fetchone()
            if settings:
                shop_name, owner_pin = settings
                print(f"Migrating shop settings: '{shop_name}'")
                
                # Check if store 1 already exists
                store_exists = conn.execute(text("SELECT id FROM stores WHERE id = 1")).fetchone()
                if not store_exists:
                    conn.execute(
                        text("INSERT INTO stores (id, name, language, created_at) VALUES (1, :name, 'en', :now)"),
                        {"name": shop_name, "now": datetime.utcnow()}
                    )
                    conn.execute(
                        text("INSERT INTO users (id, store_id, name, pin_hash, role, recovery_question, recovery_answer_hash, created_at) VALUES (1, 1, 'Owner', :pin, 'owner', 'My Shop PIN Recovery', NULL, :now)"),
                        {"pin": owner_pin, "now": datetime.utcnow()}
                    )
                    print("Migrated shop and owner profile.")
            
            # 3. Migrate Customers Table
            columns_cust = [c["name"] for c in inspector.get_columns("customers")]
            if "store_id" not in columns_cust:
                print("Migrating 'customers' table to add 'store_id'...")
                if "sqlite" in DATABASE_URL:
                    # SQLite copy pattern (foreign keys + not null constraints cannot be added via ALTER in SQLite)
                    conn.execute(text("ALTER TABLE customers RENAME TO customers_old"))
                    conn.execute(text("""
                        CREATE TABLE customers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            store_id INTEGER NOT NULL,
                            name VARCHAR NOT NULL,
                            phone VARCHAR,
                            created_at DATETIME,
                            FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE CASCADE
                        )
                    """))
                    conn.execute(text("INSERT INTO customers (id, store_id, name, phone, created_at) SELECT id, 1, name, phone, created_at FROM customers_old"))
                    conn.execute(text("DROP TABLE customers_old"))
                else:
                    # PostgreSQL ALTER pattern
                    conn.execute(text("ALTER TABLE customers ADD COLUMN store_id INTEGER REFERENCES stores(id) ON DELETE CASCADE"))
                    conn.execute(text("UPDATE customers SET store_id = 1"))
                    conn.execute(text("ALTER TABLE customers ALTER COLUMN store_id SET NOT NULL"))
                print("customers table migrated.")
                
            # 4. Migrate Transactions Table
            columns_tx = [c["name"] for c in inspector.get_columns("transactions")]
            if "created_by_user_id" not in columns_tx:
                print("Migrating 'transactions' table to add 'created_by_user_id'...")
                if "sqlite" in DATABASE_URL:
                    # SQLite copy pattern
                    conn.execute(text("ALTER TABLE transactions RENAME TO transactions_old"))
                    conn.execute(text("""
                        CREATE TABLE transactions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            customer_id INTEGER NOT NULL,
                            created_by_user_id INTEGER NOT NULL,
                            type VARCHAR NOT NULL,
                            amount INTEGER NOT NULL,
                            note VARCHAR,
                            date DATETIME,
                            created_at DATETIME,
                            edited_at DATETIME,
                            FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
                            FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE CASCADE
                        )
                    """))
                    conn.execute(text("INSERT INTO transactions (id, customer_id, created_by_user_id, type, amount, note, date, created_at, edited_at) SELECT id, customer_id, 1, type, amount, note, date, created_at, edited_at FROM transactions_old"))
                    conn.execute(text("DROP TABLE transactions_old"))
                else:
                    # PostgreSQL ALTER pattern
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"))
                    conn.execute(text("UPDATE transactions SET created_by_user_id = 1"))
                    conn.execute(text("ALTER TABLE transactions ALTER COLUMN created_by_user_id SET NOT NULL"))
                print("transactions table migrated.")
                
            # 5. Drop deprecated shop_settings table
            conn.execute(text("DROP TABLE shop_settings"))
            print("Dropped deprecated 'shop_settings' table.")
            print("Migration completed successfully!")
        else:
            print("No legacy 'shop_settings' table found. Schema is already v2 or fresh. Skipping data migration.")

if __name__ == "__main__":
    run_migration()
