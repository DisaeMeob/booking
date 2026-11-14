# Hotel Booking Backend API (`booking`)

An asynchronous REST API backend for a hotel booking system built with **Python 3.13**, **FastAPI**, **SQLAlchemy 2.0 (`asyncpg`)**, **PostgreSQL**, **Pydantic v2**, **Redis**, and **Celery**.

Developed as a backend engineering project focused on clean layered architecture, transactional integrity, and concurrency control in PostgreSQL. The API exposes **27 endpoints**, and the automated test suite includes **137 passing tests** as of the latest verification.

---

## Engineering Highlights

- **PostgreSQL Row-Level Locking (`SELECT ... FOR UPDATE`)**
  - Serializes concurrent booking attempts on the same room to prevent overbooking when the last available unit is requested simultaneously.
  - Protects parent-child integrity during deletion (`DELETE /hotels/{hotel_id}`, `DELETE /hotels/{hotel_id}/rooms/{room_id}`, `DELETE /facilities/{facility_id}`) against concurrent creation or attachment of dependent records.
  - Uses deterministic lock acquisition ordering (`hotels` -> `rooms` -> `facilities` sorted via `ORDER BY facilities.id FOR UPDATE`) when validating and attaching room facilities.
- **Sweep-Line Peak Occupancy Algorithm**
  - When decreasing a room's `quantity` via `PUT` or `PATCH`, [`BookingsRepository.get_peak_occupancy`](src/repositories/bookings.py) runs an event-based sweep-line algorithm over active bookings (sorting check-outs before check-ins on identical dates) to compute the maximum simultaneous occupancy and reject reductions below that peak (`409 Conflict`).
- **Repository, Data Mapper, and Unit of Work (`DBManager`)**
  - [`DBManager`](src/utils/db_manager.py) manages a single `AsyncSession` per request across all repositories (`hotels`, `rooms`, `facilities`, `room_facility`, `bookings`, `users`) and guarantees `rollback()` and session cleanup on exit.
  - Dedicated `DataMapper` classes convert SQLAlchemy ORM entities to Pydantic v2 domain schemas so ORM models do not leak into the API layer.
- **Redis Caching with Custom Key Builder**
  - `GET /hotels` responses are cached in Redis via `fastapi-cache2` (`@cache(expire=10)`) using a custom MD5 key builder ([`custom_key_builder`](src/init.py)) that normalizes query parameters and excludes non-serializable request dependencies.
- **Background Processing with Celery & Celery Beat**
  - Image uploads (`POST /images`) trigger an asynchronous Celery task ([`resize_image`](src/tasks/tasks.py)) that generates `1000px`, `500px`, and `200px` wide images using Pillow (`LANCZOS`).
  - A scheduled Celery Beat job (`booking_today_checkin`, configured via `crontab(hour=8)`) runs daily to query bookings with today's check-in date using an isolated `NullPool` database session.
- **137 Automated Tests (Unit & Integration)**
  - Covers key CRUD workflows, boundary validation, date-overlap edge cases, and multi-transaction concurrency scenarios verified directly against PostgreSQL's `pg_stat_activity` and `pg_blocking_pids()`.

---

## Implemented Features

- **Authentication & Users (`/auth`)**
  - User registration with `bcrypt` password hashing (`passlib`), UTF-8 72-byte password validation, and duplicate email handling (`409 Conflict`).
  - Login endpoint (`POST /auth/login`) issuing a signed JWT (`PyJWT`) delivered **exclusively** via the `HttpOnly` cookie `access_token` (`SameSite=Lax`, `Path=/`, `Max-Age` synced with token expiration; `Secure` enabled in `PROD`). The JSON response returns `{"ok": true}` and never exposes the JWT in the response body.
  - Current user profile lookup (`GET /auth/me`) and cookie logout (`DELETE /auth/logout`).
- **Hotels (`/hotels`)**
  - Search hotels that have available rooms for a requested date range (`date_from`, `date_to`), with optional case-insensitive substring filters (`title`, `location`) and pagination (`page`, `per_page`).
  - Full CRUD (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`) with a deletion guard returning `409 Conflict` if the hotel has existing rooms.
- **Rooms (`/hotels/{hotel_id}/rooms`)**
  - List available rooms for a hotel and date range with eager-loaded facilities (`joinedload`).
  - Create, replace (`PUT`), partially update (`PATCH`), and delete rooms along with their `facilities_ids`.
  - Validates that all provided `facilities_ids` exist (`400 Bad Request` on missing IDs), deduplicates facility links, enforces the peak occupancy invariant on `quantity` reductions (`409 Conflict`), and forbids deleting rooms that have bookings (`409 Conflict`).
- **Facilities (`/facilities`)**
  - Full CRUD (`GET`, `GET /{facility_id}`, `POST`, `PUT /{facility_id}`, `PATCH /{facility_id}`, `DELETE /{facility_id}`).
  - Pydantic v2 validation: whitespace stripping (`str_strip_whitespace=True`), length constraints (`1..100` characters), explicit `null` rejection on `PATCH`, and duplicate title handling (`409 Conflict` backed by the `uq_facilities_title` unique constraint).
  - Deletion guard returning `409 Conflict` when a facility is linked to any room in `rooms_facilities`.
- **Bookings (`/bookings`)**
  - Create bookings (`POST /bookings`) with date validation (`date_from >= today` and `date_from < date_to`), availability verification via SQL CTEs, and computed `total_cost` (`price * nights`).
  - List personal bookings (`GET /bookings/me`) and cancel personal bookings (`DELETE /bookings/{booking_id}`).
- **Images (`/images`)**
  - Upload hotel images for resizing either via a Celery worker (`POST /images`) or FastAPI's `BackgroundTasks` (`POST /images/background`).
- **Request Timing & Logging Middleware**
  - Logs client host, HTTP method, path, status code, and processing duration while attaching an `X-Process-Time` response header.

---

## Technology Stack

- **Python:** 3.13
- **API Framework:** FastAPI, Starlette, Uvicorn
- **Database & Migrations:** PostgreSQL, SQLAlchemy 2.0 (Async), `asyncpg`, Alembic
- **Validation & Configuration:** Pydantic v2, `pydantic-settings`, `email-validator`
- **Caching & Broker:** Redis (`redis.asyncio`), `fastapi-cache2`
- **Task Queue:** Celery, Celery Beat
- **Image Processing:** Pillow (PIL)
- **Authentication:** `PyJWT`, `passlib` (`bcrypt`)
- **Testing:** `pytest`, `pytest-asyncio`, `pytest-dotenv`, `httpx`

---

## Project Architecture

```text
src/
├── api/             # FastAPI routers (auth, hotels, rooms, facilities, bookings, images) & dependencies
├── schemas/         # Pydantic v2 request/response and domain schemas
├── services/        # Authentication & token service (AuthService)
├── repositories/    # Data access layer (BaseRepository, specialized repositories, SQL CTE helpers)
│   └── mappers/     # DataMapper classes (ORM model <-> Pydantic schema conversion)
├── models/          # SQLAlchemy 2.0 declarative models
├── utils/           # DBManager (async session and transaction context manager)
├── connectors/      # Redis async client wrapper (RedisManager)
├── tasks/           # Celery instance, Beat schedule, and background tasks
├── migrations/      # Alembic migration environment and revision scripts
├── core/            # Logger configuration
├── middleware.py    # HTTP request timing and logging middleware
├── config.py        # Settings loaded from .env via pydantic-settings
├── database.py      # SQLAlchemy async engines (default pool and NullPool) & sessionmakers
├── init.py          # Redis manager instance and custom FastAPICache key builder
└── main.py          # FastAPI application setup, lifespan hooks, and router registration
```

---

## Database Schema

The PostgreSQL schema is managed with Alembic migrations (`src/migrations/versions/`) and consists of 6 tables:

- **`users`**: `id` (PK), `email` (`VARCHAR(200)`, `UNIQUE`), `hashed_password` (`VARCHAR(200)`)
- **`hotels`**: `id` (PK), `title` (`VARCHAR(100)`), `location` (`VARCHAR`)
- **`rooms`**: `id` (PK), `hotel_id` (`FK -> hotels.id`), `title` (`VARCHAR`), `description` (`VARCHAR`, nullable), `price` (`INTEGER`), `quantity` (`INTEGER`)
- **`facilities`**: `id` (PK), `title` (`VARCHAR(100)`, unique constraint `uq_facilities_title`)
- **`rooms_facilities`**: `id` (PK), `room_id` (`FK -> rooms.id ON DELETE CASCADE`), `facility_id` (`FK -> facilities.id ON DELETE CASCADE`), composite unique constraint `uq_rooms_facilities_room_id_facility_id` on `(room_id, facility_id)`
- **`booking`**: `id` (PK), `user_id` (`FK -> users.id`), `room_id` (`FK -> rooms.id`), `date_from` (`DATE`), `date_to` (`DATE`), `price` (`INTEGER`), and `@hybrid_property total_cost`

---

## API Overview (27 Endpoints)

### Auth (`/auth` — 4 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | No | Register a new user (`200 OK`, `409 Conflict` if email exists, `422` on invalid password) |
| `POST` | `/auth/login` | No | Authenticate user, set `HttpOnly` cookie `access_token`, and return `{"ok": true}` (`200 OK`, `401 Unauthorized`) |
| `GET` | `/auth/me` | Cookie | Get current authenticated user profile (`200 OK`, `401 Unauthorized`) |
| `DELETE` | `/auth/logout` | No | Delete `access_token` cookie and return `{"ok": true}` (`200 OK`) |

### Hotels (`/hotels` — 6 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/hotels` | No | List hotels with available rooms for `date_from`..`date_to` (`200 OK`, cached for 10s) |
| `GET` | `/hotels/{hotel_id}` | No | Get hotel by ID (`200 OK`, `404 Not Found`) |
| `POST` | `/hotels` | No | Create a new hotel (`200 OK`) |
| `PUT` | `/hotels/{hotel_id}` | No | Full update of a hotel (`200 OK`) |
| `PATCH` | `/hotels/{hotel_id}` | No | Partial update of a hotel (`200 OK`) |
| `DELETE` | `/hotels/{hotel_id}` | No | Delete a hotel (`200 OK`, `404 Not Found`, `409 Conflict` if rooms exist) |

### Rooms (`/hotels/{hotel_id}/rooms` — 6 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/hotels/{hotel_id}/rooms` | No | List available rooms for `date_from`..`date_to` with facilities (`200 OK`) |
| `GET` | `/hotels/{hotel_id}/rooms/{room_id}` | No | Get room by ID with facilities (`200 OK`, `404 Not Found`) |
| `POST` | `/hotels/{hotel_id}/rooms` | No | Create a room with `facilities_ids` (`200 OK`, `400 Bad Request`, `404 Not Found`) |
| `PUT` | `/hotels/{hotel_id}/rooms/{room_id}` | No | Full update of a room and its facilities (`200 OK`, `400`, `404`, `409 Conflict`) |
| `PATCH` | `/hotels/{hotel_id}/rooms/{room_id}` | No | Partial update of a room and/or its facilities (`200 OK`, `400`, `404`, `409`, `422`) |
| `DELETE` | `/hotels/{hotel_id}/rooms/{room_id}` | No | Delete a room (`200 OK`, `404 Not Found`, `409 Conflict` if bookings exist) |

### Facilities (`/facilities` — 6 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/facilities` | No | List all facilities (`200 OK`) |
| `GET` | `/facilities/{facility_id}` | No | Get facility by ID (`200 OK`, `404 Not Found`) |
| `POST` | `/facilities` | No | Create a facility (`200 OK`, `409 Conflict` on duplicate title, `422`) |
| `PUT` | `/facilities/{facility_id}` | No | Full update of a facility (`200 OK`, `404`, `409`, `422`) |
| `PATCH` | `/facilities/{facility_id}` | No | Partial update of a facility (`200 OK`, `404`, `409`, `422`) |
| `DELETE` | `/facilities/{facility_id}` | No | Delete an unused facility (`200 OK`, `404`, `409 Conflict` if linked to rooms) |

### Bookings (`/bookings` — 3 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/bookings/me` | Cookie | List bookings of the current authenticated user (`200 OK`, `401 Unauthorized`) |
| `POST` | `/bookings` | Cookie | Create a booking (`200 OK`, `401`, `404`, `409 Conflict` if no rooms left, `422`) |
| `DELETE` | `/bookings/{booking_id}` | Cookie | Cancel a personal booking (`200 OK`, `401`, `404 Not Found`) |

### Images (`/images` — 2 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/images` | No | Upload an image and enqueue Celery `resize_image` task (`200 OK`) |
| `POST` | `/images/background` | No | Upload an image and run `resize_image` via FastAPI `BackgroundTasks` (`200 OK`) |

Interactive OpenAPI documentation is served at `/docs` (Swagger UI) and `/redoc` (ReDoc).

---

## Booking & Availability Logic

1. **Date Overlap Filtering via SQL CTEs ([`rooms_ids_for_booking`](src/repositories/utils.py)):**
   - Two booking intervals overlap when `BookingsOrm.date_from < requested_date_to AND BookingsOrm.date_to > requested_date_from`. Adjacent stays (`existing.date_to == requested_date_from`) do not overlap and are permitted.
   - The `rooms_count` CTE counts overlapping bookings per `room_id`, and `rooms_left_table` computes `rooms_left = quantity - COALESCE(rooms_booked, 0)`, filtering for `rooms_left > 0`.
2. **Row-Locked Booking Creation ([`BookingsRepository.add_booking`](src/repositories/bookings.py)):**
   - Locks the target `RoomsOrm` row with `SELECT ... FOR UPDATE`, re-evaluates availability within the same transaction, and inserts the booking with the room's current price.

---

## Local Setup & Running

### 1. Prerequisites
- **Python 3.13**
- **PostgreSQL**
- **Redis**

### 2. Install Dependencies

```bash
git clone https://github.com/DisaeMeob/booking.git
cd booking

python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables

Configure `.env` in the project root (see [`src/config.py`](src/config.py) for all required fields):

```env
MODE=LOCAL

DB_NAME=booking_db
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=your_local_password

REDIS_HOST=localhost
REDIS_PORT=6379

JWT_SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

> **Security Note:** `JWT_SECRET_KEY` must be a unique, randomly generated secret key (for example, generated via `openssl rand -hex 32`), and must never use a published, default, or shared value.

For running the test suite, create `.env-test` (referenced by [`pytest.ini`](pytest.ini)) with `MODE=TEST` and a dedicated test database.

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the API Server and Celery Processes

Run the FastAPI application:
```bash
uvicorn src.main:app --reload
```

Run the Celery worker and Celery Beat scheduler (in separate terminals):
```bash
celery --app=src.tasks.celery_app:celery_instance worker -l INFO
celery --app=src.tasks.celery_app:celery_instance beat -l INFO
```

---

## Testing

The test suite (`tests/`) runs against a dedicated PostgreSQL test database (`MODE=TEST` in `.env-test`), uses `NullPool` sessions to avoid event-loop cross-talk, and initializes an in-memory cache backend in [`tests/conftest.py`](tests/conftest.py).

```bash
# Run all 137 tests
.venv/bin/pytest -v

# Run individual test suites
.venv/bin/pytest tests/integration_tests/bookings/test_api.py -v
.venv/bin/pytest tests/integration_tests/facilities/test_api.py -v
.venv/bin/pytest tests/integration_tests/rooms/test_api.py -v
.venv/bin/pytest tests/integration_tests/hotels/test_api.py -v
.venv/bin/pytest tests/integration_tests/test_auth.py -v
.venv/bin/pytest tests/unit_tests/test_auth.py -v
```
