import sqlite3

DB_PATH = "rasa.db"

def show_bookings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ticket_booking_details;")
    rows = cursor.fetchall()
    if not rows:
        print("No bookings found.")
    else:
        print("Saved bookings:")
        for row in rows:
            print(row)
    conn.close()

if __name__ == "__main__":
    show_bookings()
