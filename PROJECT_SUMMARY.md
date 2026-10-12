# Kirana Shop Udhara (Credit) Tracker — Comprehensive Project Documentation & AI Handoff Specification

> **Target Audience:** AI Assistants, Software Engineers, and DevOps Engineers  
> **Repository:** `JakkenaSrikar/Credit-tracker-app`  
> **Version:** 2.1 (Multi-Store / Multi-Tenant, Multilingual, Offline PWA, PDF Statements)  
> **Last Updated:** October 2026

---

## 1. Executive Summary

The **Kirana Shop Udhara Tracker** is a mobile-first, Progressive Web App (PWA) built specifically for small Indian grocery/retail stores (Kirana shops). It replaces traditional paper udhara (credit) khata books with a lightweight, multi-tenant digital ledger.

The app originally started as a single-store solution (v1) and was systematically refactored into **v2 Multi-Tenant Architecture** without data loss. It allows multiple independent stores to run on the same platform, provides role-based access for Owners and Staff, supports offline transactions with automated sync, exports statements in CSV and PDF formats across three languages (English, Telugu, Hindi), and generates customized WhatsApp reminder deep links.

---

## 2. Technology Stack & Infrastructure

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Database ORM:** SQLAlchemy 2.0+
- **Database Engine:** 
  - Local Development: SQLite (`khata.db`)
  - Production: Serverless PostgreSQL (Hosted on **Neon.tech**)
- **Security & Auth:** PyJWT (HMAC-SHA256), SHA-256 password/PIN hashing with in-memory IP brute-force rate limiting
- **Document Generation:** ReportLab 5.0+ with dynamically registered Unicode TrueType fonts (`FreeSans.ttf` and `NotoSansTelugu-Regular.ttf`)
- **Web Server:** Uvicorn (ASGI)

### Frontend
- **Framework:** React 18+ (bundled with Vite)
- **Styling:** Tailwind CSS (Tactile, high-contrast, mobile-first UI with accessibility options: dark mode, font scaling)
- **PWA Capabilities:** `vite-plugin-pwa`, Workbox Service Worker, offline cache-first shell, offline background sync queue
- **Icons:** Lucide React
- **Internationalization (i18n):** Client-side English (`en`) & Telugu (`te`) translation engine (`src/i18n.js`)

### Deployment Environments
- **Frontend Hosting:** Vercel (Auto-deploys from GitHub `main` branch, root directory `/frontend`)
- **Backend Hosting:** Render Web Service (Free Tier, auto-deploys from GitHub `main` branch, root directory `/backend`)
- **Production Database:** Neon.tech Serverless PostgreSQL (`ep-blue-frost-azsr6slc...`)
- **Version Control:** GitHub (`JakkenaSrikar/Credit-tracker-app`)

---

## 3. Database Schema & Architecture

All monetary amounts are stored in **Paise** (integer) to eliminate floating-point precision errors (`1 Rupee = 100 Paise`).

```
+---------------------------------------------------------------+
|                             stores                            |
+---------------------------------------------------------------+
| id (PK, Integer, Auto-Inc)                                    |
| name (String, Not Null)                                       |
| language (String: "en" | "te" | "hi", Default: "en")          |
| created_at (DateTime, UTC)                                    |
+---------------------------------------------------------------+
                                | 1
                                |
                                | N
+---------------------------------------------------------------+
|                             users                             |
+---------------------------------------------------------------+
| id (PK, Integer, Auto-Inc)                                    |
| store_id (FK -> stores.id, Indexed)                           |
| name (String, Not Null)                                       |
| pin_hash (String: 64-char hex SHA-256)                        |
| role (String: "owner" | "staff", Default: "staff")            |
| recovery_question (String, Nullable)                          |
| recovery_answer_hash (String, Nullable)                       |
| created_at (DateTime, UTC)                                    |
+---------------------------------------------------------------+
                                | 1
                                |
                                | N (Audit)
+---------------------------------------------------------------+
|                           customers                           |
+---------------------------------------------------------------+
| id (PK, Integer, Auto-Inc)                                    |
| store_id (FK -> stores.id, Indexed)                           |
| name (String, Not Null, Indexed)                              |
| phone (String, Nullable)                                      |
| created_at (DateTime, UTC)                                    |
+---------------------------------------------------------------+
                                | 1
                                |
                                | N
+---------------------------------------------------------------+
|                         transactions                          |
+---------------------------------------------------------------+
| id (PK, Integer, Auto-Inc)                                    |
| customer_id (FK -> customers.id, Indexed)                     |
| type (String: "credit" | "payment", Not Null)                 |
| amount (Integer [Paise], Not Null)                            |
| note (String, Nullable)                                       |
| date (DateTime, UTC, Indexed)                                 |
| created_by_user_id (FK -> users.id, Nullable)                 |
+---------------------------------------------------------------+
```

### Outstanding Balance Calculation Logic
A customer's balance is calculated dynamically via database aggregation:
$$\text{Balance} = \sum(\text{credit transactions}) - \sum(\text{payment transactions})$$
- **Positive Balance ($> 0$):** Customer owes the shop (Udhara Due).
- **Zero Balance ($= 0$):** Account settled.
- **Negative Balance ($< 0$):** Customer overpaid / store holds advance balance.

### Migration from Single-Tenant (v1) to Multi-Tenant (v2)
- Handled by `backend/migrate_v2.py`.
- Detects existing `shop_settings` table (v1 schema).
- Creates `Store 1` from existing `shop_settings.shop_name`, maps the single owner PIN to an `owner` record in `users`, alters `customers` to add `store_id = 1`, alters `transactions` to add `created_by_user_id = 1`, and drops the deprecated `shop_settings` table without dropping transaction history.

---

## 4. Multi-Tenant Security & Access Control

1. **Strict Data Boundary Enforcement:**
   - Every protected API route depends on `get_current_user` (Bearer JWT).
   - JWT claims encode: `store_id`, `user_id`, `role`, and expiration (`exp = 30 days`).
   - Every single DB query filters explicitly by `store_id == current_user.store_id`. Cross-store queries return `404 Not Found` (never leaking whether an entity exists in another store).
2. **Owner vs. Staff Privileges:**
   - **Owner:** Can view all reports, add/remove staff users, modify store settings, delete/edit customer records.
   - **Staff:** Can log transactions, view customer records, use quick-add. Cannot delete users or manage staff accounts.
   - **Last Owner Protection:** The system blocks deletion of the sole owner in a store (`400 Bad Request`).
3. **PIN Reset via Security Questions:**
   - Single-endpoint recovery flow: `POST /api/pin-reset/request` returns the store's recovery question.
   - `POST /api/pin-reset/confirm` verifies the hashed answer and sets a new 4-digit PIN.
4. **Brute Force Rate Limiting:**
   - In-memory tracker blocks an IP address after 5 consecutive failed login attempts for 15 minutes.

---

## 5. Comprehensive API Endpoints Specification

### Authentication & Setup
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/setup/status` | Public | Returns `{"setup_required": boolean}` based on whether any stores exist |
| `POST` | `/api/stores` | Public | Creates a new Store, initial Owner user, and sets recovery Q&A |
| `GET` | `/api/stores/list` | Public | Lists all store names and IDs for the login dropdown selector |
| `POST` | `/api/login` | Public | Validates Store ID + 4-digit PIN; returns JWT token + user info |
| `POST` | `/api/pin-reset/request` | Public | Retrieves the security question for a given store ID |
| `POST` | `/api/pin-reset/confirm` | Public | Verifies the recovery answer and updates the user's PIN |

### User Management (Owner Only)
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/users` | Bearer (Owner) | Lists all staff and owner accounts for the authenticated store |
| `POST` | `/api/users` | Bearer (Owner) | Creates a new staff or owner login (enforces unique PIN per store) |
| `DELETE` | `/api/users/{user_id}` | Bearer (Owner) | Deletes a user (protected against deleting the last owner) |

### Customer Management
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/customers` | Bearer | Lists customers for the store (supports search, sort, pagination) |
| `GET` | `/api/customers/quick-list` | Bearer | Returns lightweight list (id, name, phone, balance) for Quick-Add autocomplete |
| `GET` | `/api/customers/{customer_id}` | Bearer | Customer details, paginated transactions, and total balance |
| `POST` | `/api/customers` | Bearer | Creates a new customer record |
| `PUT` | `/api/customers/{customer_id}` | Bearer | Updates customer name or phone number |
| `DELETE` | `/api/customers/{customer_id}` | Bearer (Owner) | Deletes customer and cascades associated transactions |

### Transactions & Ledger
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/transactions` | Bearer | Logs a credit or payment entry |
| `PUT` | `/api/transactions/{tx_id}` | Bearer | Edits an existing transaction entry (amount, note) |
| `DELETE` | `/api/transactions/{tx_id}` | Bearer | Deletes a transaction; returns deleted data to support Undo |

### Dashboard & Daily Summaries
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/dashboard/summary` | Bearer | Total outstanding amount across all store customers and total active customer count |
| `GET` | `/api/dashboard/today` | Bearer | Daily closing summary: today's credit given, payments received, and transaction list (supports `tz_offset`) |

### PDF & CSV Exports
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/export/transactions` | Bearer | Downloads date-range filtered transactions as CSV |
| `GET` | `/api/export/pdf` | Bearer | Downloads full-store ledger statement as PDF (includes today's closing summary and total customer balances) |
| `GET` | `/api/customers/{customer_id}/export/pdf` | Bearer | Downloads individual customer PDF statement. Query params: `range=today\|all`, `lang=en\|te\|hi`, `tz_offset=330` |

### Voice Khata & AI Transaction Assistant
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/voice/transcribe` | Bearer | Transcribes spoken audio (Groq Whisper / OpenAI Whisper / Mock). Supports `language=te\|hi\|en`. |
| `POST` | `/api/voice/parse` | Bearer | Parses spoken transcript into structured transaction draft and matches customer within store boundaries. |

### Reminders & Messaging
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/customers/{customer_id}/reminder-link` | Bearer | Returns `wa_link` (WhatsApp deep link) and `sms_text`. Query params: `lang=en\|te\|hi`, `tz_offset=330` |

---

## 6. Frontend Architecture & Features

### Component Directory Map (`frontend/src/`)
```
frontend/src/
├── api.js                   # Fetch wrapper with isolated token cache and offline queue
├── App.jsx                  # Main application state, routing, offline sync listener
├── i18n.js                  # English and Telugu localization dictionaries
├── index.css                # Base Tailwind styles, custom ledger colors, font size rules
├── main.jsx                 # Vite application mount and Service Worker registration
├── useVoiceRecorder.js      # Mobile-first audio recording hook with permission and duration handlers
└── components/
    ├── CustomerDetail.jsx   # Customer view, transaction log, settle reminder, PDF exports, undo
    ├── Dashboard.jsx        # Store summary, search, today's metrics, CSV/PDF export, single FAB
    ├── Login.jsx            # Store dropdown selection + 4-digit PIN pad
    ├── ManageUsers.jsx      # Owner interface for managing staff logins
    ├── PinReset.jsx         # PIN reset form using security questions
    ├── QuickAdd.jsx         # Voice Khata first-class state machine + fast manual entry fallback
    ├── Settings.jsx         # Language selection, dark mode, font scaling toggles
    └── Setup.jsx            # New store registration screen
```

### Key Frontend Implementations
1. **Cache Namespace Isolation:**
   - In a multi-tenant PWA, `localStorage` can bleed cached GET responses between different accounts if they share IDs (e.g. Customer ID `1` in Store A vs Customer ID `1` in Store B).
   - `frontend/src/api.js` scopes all cache keys with a SHA-256 hash prefix derived from the active JWT token (`cache_${tokenHash}_${url}`).
   - Client-side validation errors (HTTP `4xx`) explicitly bypass cache fallbacks to avoid displaying stale data on invalid inputs.
2. **Offline Support & Synchronization Queue:**
   - Transactions created while offline are appended to `localStorage` key `offline_tx_queue`.
   - The UI optimistically updates the ledger immediately and displays an amber "Offline Mode" banner.
   - When `window.addEventListener('online')` triggers, the queue sequentially submits pending transactions to `/api/transactions` and refreshes state.
3. **5-Second Undo Toast:**
   - When a transaction is deleted, the backend returns the deleted record.
   - The frontend holds the transaction in memory and displays a 5-second countdown toast with an "Undo" button.
   - Clicking "Undo" re-submits the exact transaction back to the database.
4. **Single Quick-Add Button:**
   - UI was simplified to feature a single clean "Quick Add" button in the middle dashboard action row, removing clutter from floating action buttons (leaving only the "+ Customer" FAB).

---

## 7. Multilingual Document & PDF Engine

### Unicode Font Handling for Indic Scripts
ReportLab's built-in 14 Type 1 fonts (`Helvetica`, `Times-Roman`, etc.) only support Latin-1 encoding. Passing Telugu or Devanagari Unicode characters results in missing glyph errors (`?` question marks or square blocks).

To solve this across both local Windows and cloud Linux (Render) environments:
1. `backend/main.py` incorporates an automated TrueType Font loader:
   - **Hindi (Devanagari) & English:** Loads `FreeSans.ttf` (downloaded from `evanw/tfdump` if missing).
   - **Telugu:** Loads `NotoSansTelugu-Regular.ttf` (downloaded from `googlefonts/noto-fonts` if missing).
2. Fonts are registered via `reportlab.pdfbase.pdfmetrics.registerFont(TTFont(...))`.
3. The PDF generators dynamically select the font based on the requested language:
   - English (`en`): `Helvetica`
   - Telugu (`te`): `NotoSansTelugu`
   - Hindi (`hi`): `FreeSans`

### PDF Report Types
1. **Store Closing Summary Report (`/api/export/pdf`):**
   - Header with Store Name, Date, and Local Generation Time.
   - Metric grid: Total Credit Given Today, Total Payments Received Today, Total Ledger Due, Active Customer Accounts.
   - Itemized list of today's transaction entries (Customer, Type, Amount, Note, Time).
   - Full ledger table of all customer accounts and their active Due Amount.
2. **Customer Statement Report (`/api/customers/{id}/export/pdf`):**
   - Filterable by `range=today` (today's transactions only) or `range=all` (full history).
   - Available in English, Telugu, or Hindi on demand.
   - Labeled clearly as **"Due Amount"** (`Due Amount` / `మొత్తం బకాయి` / `कुल बकाया`).
   - Includes **Net Calculation Summary** at the bottom:
     - `Total Credit Given`
     - `Total Payment Received`
     - `Net Due Amount = (Total Credit - Total Payment)`

---

## 8. WhatsApp & SMS Reminder Deep Link Engine

The reminder generation endpoint (`/api/customers/{id}/reminder-link`) creates customized messages pre-filled with the customer's phone number and detailed breakdown:

### Phone Number Normalization
- Strips all non-digit characters (`+`, spaces, dashes, parentheses).
- Normalizes 10-digit Indian numbers by prepending country code `91`.
- Handles leading zeros (`09876543210` -> `919876543210`) or existing prefixes (`919876543210`).
- Validates strictly for a 10-digit base before generating links; returns `400 Bad Request` with actionable errors if invalid.

### Dynamic Itemized Pricing
The message queries all credit transactions logged for the customer *today* and lists item names with their respective prices:
- **English Template:**
  > *"Namaste {customer_name}, your udhara balance at {store_name} is ₹{total_balance}. Today's purchase: Rice (₹120), Soap (₹30). Please settle when convenient. Thank you!"*
- **Telugu Template:**
  > *"నమస్తే {customer_name}, {store_name} లో మీ మొత్తం బకాయి రుసుము ₹{total_balance}. ఈరోజు కొనుగోలు చేసినవి: Rice (₹120), Soap (₹30). దయచేసి వీలైనప్పుడు చెల్లించగలరు. ధన్యవాదాలు!"*
- **Hindi Template:**
  > *"नमस्ते {customer_name}, {store_name} में आपका कुल बकाया ₹{total_balance} है। आज की खरीदारी: Rice (₹120), Soap (₹30)। कृपया सुविधानुसार भुगतान करें। धन्यवाद!"*

### On-The-Fly Language Selection
- The customer details screen provides **EN**, **తెలుగు**, and **हिंदी** toggle pills directly on the Settle Reminder card.
- Toggling immediately updates the preview and WhatsApp deep link without altering the store's default global language setting.

---

## 9. Test Suite & Verification

The test suite in `backend/test_v2_isolation.py` validates multi-store tenant boundaries and end-to-end functionality against a live test server:
1. **Store Creation:** Registers Store A and Store B independently.
2. **Tenancy Isolation:**
   - Asserts Store A cannot `GET`, `PUT`, or `DELETE` Store B's customers (returns 404).
   - Asserts Store A cannot log transactions against Store B's customers.
3. **Transaction Deletion & Undo:** Validates rollback payload integrity.
4. **Closing Summaries & CSV Export:** Verifies local date math and CSV column headers.
5. **PDF Export Generation:** Confirms binary output starts with `%PDF` header for store-wide reports and customer-specific reports.
6. **Reminders & Translations:** Validates generated reminder strings for English, Telugu, and Hindi, verifying itemized pricing syntax (`Rice sack (₹120)`).
7. **Role Hierarchy & PIN Recovery:** Verifies staff cannot delete accounts, staff duplicate PINs are blocked, and security question PIN recovery works.

To run tests locally:
```powershell
cd backend
.venv\Scripts\python.exe test_v2_isolation.py
```

---

## 10. Deployment & Environment Configuration

### Required Environment Variables

#### Backend (Render)
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:pass@ep-blue-frost...neon.tech/neondb?sslmode=require`)
- `JWT_SECRET`: Random cryptographically secure string (e.g., `super_secret_kirana_tracker_key_2026`)
- `PORT`: Automatically provided by Render

#### Frontend (Vercel)
- `VITE_API_BASE_URL`: Public URL of the deployed FastAPI backend (e.g., `https://udhara-backend.onrender.com`)

### Migration Runbook for Production Databases
To execute schema upgrades or migrations on a remote PostgreSQL database from a developer machine:
```powershell
$env:DATABASE_URL="postgresql://user:pass@ep-...neon.tech/neondb?sslmode=require"
.venv\Scripts\python.exe migrate_v2.py
```

---

## 11. Key Architectural Gotchas & Solved Bugs

1. **FastAPI Route Parameter Precedence:**
   - *Problem:* Static route `/api/customers/quick-list` returned 422 Unprocessable Entity because `/api/customers/{customer_id}` was declared earlier in the file, interpreting `"quick-list"` as an integer ID.
   - *Fix:* Static sub-routes (`/quick-list`, `/export/pdf`) must always precede dynamic parameterized routes (`/{customer_id}`) in FastAPI route declaration order.
2. **Aggressive PWA Service Worker Caching:**
   - *Problem:* When releasing new frontend code, mobile browser service workers serve stale cached HTML and JS bundles, hitting deprecated endpoints.
   - *Fix:* Configured cache-busting headers, updated Vite PWA build configuration, and advised users on force-refresh (`Ctrl+Shift+R` / clearing website data).
3. **Font Glyph Missing in Indic PDFs:**
   - *Problem:* Standard TrueType fonts like `FreeSans` support Devanagari (Hindi) but lack Telugu Unicode glyphs, rendering Telugu text as `?` question marks.
   - *Fix:* Integrated `NotoSansTelugu-Regular.ttf` specifically for Telugu documents, dynamically switching font families in ReportLab styles based on the target language.
4. **Multi-Store localStorage Collision:**
   - *Problem:* Local storage caches for Customer `1` in Store A collided with Customer `1` in Store B when testing on the same device.
   - *Fix:* Scoped client-side cache keys by prepending the active session's hashed authentication token.
