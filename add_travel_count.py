import sqlite3

DB_PATH = "rasa.db"
TABLE_NAME = "ticket_booking_details"
COLUMN_NAME = "travel_count"

def add_column_if_missing():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute(f"PRAGMA table_info({TABLE_NAME});")
    columns = [col[1] for col in cursor.fetchall()]

    # Add column if missing
    if COLUMN_NAME not in columns:
        cursor.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} INTEGER;")
        conn.commit()
        print(f"Column '{COLUMN_NAME}' added successfully!")
    else:
        print(f"Column '{COLUMN_NAME}' already exists.")

    conn.close()

if __name__ == "__main__":
    add_column_if_missing()














