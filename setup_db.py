import sqlite3

DB_PATH = "rasa.db"
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ticket_booking_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT,
    destination TEXT,
    travel_date TEXT,
    passenger_name TEXT,
    phone_number TEXT,
    seat_preference TEXT,
    class_selection TEXT,
    flight_time TEXT
);
"""


def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(TABLE_SQL)
    conn.commit()
    conn.close()
    print("Database and table created (if not exists).")

