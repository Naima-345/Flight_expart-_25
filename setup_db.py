import sqlite3

DB_PATH = "rasa.db"

BOOKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ticket_booking_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT,
    destination TEXT,
    travel_date TEXT,
    passenger_name TEXT,   -- primary contact
    phone_number TEXT,     -- primary contact
    seat_preference TEXT,
    class_selection TEXT,
    flight_time TEXT,
    travel_count INTEGER,
    created_at TEXT
);
"""

PASSENGERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS passengers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER,
    name TEXT,
    phone TEXT,
    email TEXT,
    FOREIGN KEY (booking_id) REFERENCES ticket_booking_details(id)
);
"""

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(BOOKING_TABLE_SQL)
    cursor.execute(PASSENGERS_TABLE_SQL)
    conn.commit()
    conn.close()
    print("✅ Database and tables created (if not exists).")
