import sqlite3

DB_PATH = "rasa.db"

# Connect to the database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check table columns
cursor.execute("PRAGMA table_info(ticket_booking_details);")
columns = cursor.fetchall()

print("Table columns:")
for col in columns:
    print(col)

conn.close()
