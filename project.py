import sys
import os
import datetime as _datetime
import mysql.connector

# --- DB Connection ---
def get_connection():
    conn = mysql.connector.connect(
        user='test',
        password='password',
        database='cs122a'
    )
    conn.autocommit = False
    return conn

# --- DDL ---
DDL = """
DROP TABLE IF EXISTS Approval;
DROP TABLE IF EXISTS Hosting;
DROP TABLE IF EXISTS OffCampus;
DROP TABLE IF EXISTS OnCampus;
DROP TABLE IF EXISTS Venue;
DROP TABLE IF EXISTS Slot;
DROP TABLE IF EXISTS Event;
DROP TABLE IF EXISTS Administrator;
DROP TABLE IF EXISTS Participant;
DROP TABLE IF EXISTS Organizer;
DROP TABLE IF EXISTS User;

CREATE TABLE User (
    uid INT,
    email TEXT NOT NULL,
    username TEXT NOT NULL,
    joined DATE NOT NULL,
    PRIMARY KEY (uid)
);

CREATE TABLE Organizer (
    uid INT,
    department TEXT NOT NULL,
    experience INT NOT NULL,
    PRIMARY KEY (uid),
    FOREIGN KEY (uid) REFERENCES User(uid) ON DELETE CASCADE
);

CREATE TABLE Participant (
    uid INT,
    type TEXT,
    PRIMARY KEY (uid),
    FOREIGN KEY (uid) REFERENCES User(uid) ON DELETE CASCADE
);

CREATE TABLE Administrator (
    uid INT,
    firstname TEXT NOT NULL,
    lastname TEXT NOT NULL,
    PRIMARY KEY (uid),
    FOREIGN KEY (uid) REFERENCES User(uid) ON DELETE CASCADE
);

CREATE TABLE Event (
    eid INT,
    creator_uid INT NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    datetime DATETIME NOT NULL,
    PRIMARY KEY (eid),
    FOREIGN KEY (creator_uid) REFERENCES Organizer(uid) ON DELETE CASCADE
);

CREATE TABLE Slot (
    eid INT,
    snum INT NOT NULL,
    is_reserved BOOLEAN NOT NULL,
    uid INT,
    PRIMARY KEY (eid, snum),
    FOREIGN KEY (eid) REFERENCES Event(eid) ON DELETE CASCADE,
    FOREIGN KEY (uid) REFERENCES Participant(uid) ON DELETE CASCADE
);

CREATE TABLE Venue (
    vid INT,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip TEXT NOT NULL,
    PRIMARY KEY (vid)
);

CREATE TABLE OnCampus (
    vid INT,
    code TEXT NOT NULL,
    PRIMARY KEY (vid),
    FOREIGN KEY (vid) REFERENCES Venue(vid) ON DELETE CASCADE
);

CREATE TABLE OffCampus (
    vid INT,
    distance INT NOT NULL,
    PRIMARY KEY (vid),
    FOREIGN KEY (vid) REFERENCES Venue(vid) ON DELETE CASCADE
);

CREATE TABLE Hosting (
    eid INT NOT NULL,
    vid INT NOT NULL,
    is_primary BOOLEAN NOT NULL,
    PRIMARY KEY (eid, vid),
    FOREIGN KEY (eid) REFERENCES Event(eid) ON DELETE CASCADE,
    FOREIGN KEY (vid) REFERENCES Venue(vid) ON DELETE CASCADE
);

CREATE TABLE Approval (
    uid INT NOT NULL,
    vid INT NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    PRIMARY KEY (uid, vid),
    FOREIGN KEY (uid) REFERENCES Administrator(uid) ON DELETE CASCADE,
    FOREIGN KEY (vid) REFERENCES OffCampus(vid) ON DELETE CASCADE
);
"""

# Table name -> ordered columns matching DDL order
TABLE_COLUMNS = {
    'User':          ['uid', 'email', 'username', 'joined'],
    'Organizer':     ['uid', 'department', 'experience'],
    'Participant':   ['uid', 'type'],
    'Administrator': ['uid', 'firstname', 'lastname'],
    'Event':         ['eid', 'creator_uid', 'title', 'type', 'datetime'],
    'Slot':          ['eid', 'snum', 'is_reserved', 'uid'],
    'Venue':         ['vid', 'street', 'city', 'state', 'zip'],
    'OnCampus':      ['vid', 'code'],
    'OffCampus':     ['vid', 'distance'],
    'Hosting':       ['eid', 'vid', 'is_primary'],
    'Approval':      ['uid', 'vid', 'valid_from', 'valid_until'],
}

# Insertion order respects FK dependencies
TABLE_INSERT_ORDER = [
    'User', 'Organizer', 'Participant', 'Administrator',
    'Event', 'Slot',
    'Venue', 'OnCampus', 'OffCampus',
    'Hosting', 'Approval',
]

def print_row(row):
    # Safely handles None to preserve exact CSV empty field expectations, and forces clean 1/0 for booleans
    formatted = []
    for item in row:
        if item is None:
            formatted.append("")
        elif isinstance(item, bool):
            formatted.append("1" if item else "0")
        elif isinstance(item, _datetime.datetime):
            # Force YYYY-MM-DD hh:mm:ss with no microseconds
            formatted.append(item.strftime("%Y-%m-%d %H:%M:%S"))
        elif isinstance(item, _datetime.date):
            formatted.append(item.strftime("%Y-%m-%d"))
        else:
            formatted.append(str(item))
    print(','.join(formatted))

# import is a reserved word, use import_data instead
def import_data(folder):
    """
    1. Drop and recreate all tables.
    2. Read each CSV from the folder and insert rows.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Execute DDL statements one by one (DDL causes implicit commits in MySQL)
        for statement in DDL.strip().split(';'):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)

        # Build a case-insensitive lookup of files actually present in the folder,
        # since the dataset may name files like User.csv or user.csv
        present = {}
        for fname in os.listdir(folder):
            present[fname.lower()] = fname

        # Insert data from CSVs in dependency order
        for table in TABLE_INSERT_ORDER:
            # Resolve the real filename regardless of capitalization
            key = f'{table.lower()}.csv'
            if key not in present:
                continue
            csv_path = os.path.join(folder, present[key])

            cols = TABLE_COLUMNS[table]
            placeholders = ', '.join(['%s'] * len(cols))
            col_names = ', '.join(cols)
            insert_sql = (
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            )

            with open(csv_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    values = line.split(',')
                    # Convert 'NULL' strings to None
                    values = [None if v == 'NULL' or v == '' else v for v in values]
                    cursor.execute(insert_sql, values)

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")


def insertAdmin(uid, email, username, joined, firstname, lastname):
    """
    2. Insert a new user and administrator into User and Administrator tables.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_uid = int(uid) if uid is not None else None

        # Explicitly check for duplicate uid before inserting to catch cases
        # where autocommit behavior or connector version might swallow the PK error
        cursor.execute("SELECT COUNT(*) FROM User WHERE uid = %s", (val_uid,))
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            print("Fail")
            return

        cursor.execute(
            "INSERT INTO User (uid, email, username, joined) VALUES (%s, %s, %s, %s)",
            (val_uid, email, username, joined)
        )
        cursor.execute(
            "INSERT INTO Administrator (uid, firstname, lastname) VALUES (%s, %s, %s)",
            (val_uid, firstname, lastname)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")


def addVenue(eid, vid, is_primary):
    """
    3. Add a venue to an existing event in the Hosting table.
       If is_primary=true, ensure no other primary venue exists for this event.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_eid = int(eid) if eid is not None else None
        val_vid = int(vid) if vid is not None else None
        is_primary_bool = str(is_primary).lower() == 'true' if is_primary is not None else False

        if is_primary_bool and val_eid is not None:
            # Check if a primary venue already exists for this event
            cursor.execute(
                "SELECT COUNT(*) FROM Hosting WHERE eid = %s AND is_primary = TRUE",
                (val_eid,)
            )
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.close()
                conn.close()
                print("Fail")
                return

        cursor.execute(
            "INSERT INTO Hosting (eid, vid, is_primary) VALUES (%s, %s, %s)",
            (val_eid, val_vid, is_primary_bool)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")


# reserve slot
def reserveSlot(eid, snum, uid):
    """
    Reserve a specific slot for a participant.
    The slot must currently be unreserved.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_eid = int(eid) if eid is not None else None
        val_snum = int(snum) if snum is not None else None
        val_uid = int(uid) if uid is not None else None

        # check slot exists and is currently unreserved
        cursor.execute(
            "SELECT is_reserved FROM Slot WHERE eid = %s AND snum = %s",
            (val_eid, val_snum)
        )
        result = cursor.fetchone()

        # if slot doesn't exist or is already taken, it's a fail
        if result is None or result[0]:
            cursor.close()
            conn.close()
            print("Fail")
            return

        # update the slot with the participant's uid and flip the reservation flag
        cursor.execute(
            "UPDATE Slot SET is_reserved = TRUE, uid = %s WHERE eid = %s AND snum = %s",
            (val_uid, val_eid, val_snum)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")


# cancel reservation
def cancelReservation(eid, snum, uid):
    """
    Cancel a participant's reservation for a specific event slot.
    Only cancel if the slot is currently reserved by the given participant.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_eid = int(eid) if eid is not None else None
        val_snum = int(snum) if snum is not None else None
        val_uid = int(uid) if uid is not None else None

        # ensure the slot is actually reserved by the user
        cursor.execute(
            "SELECT COUNT(*) FROM Slot WHERE eid = %s AND snum = %s AND uid = %s AND is_reserved = TRUE",
            (val_eid, val_snum, val_uid)
        )

        if cursor.fetchone()[0] == 0:
            cursor.close()
            conn.close()
            print("Fail")
            return

        # unreserve slot and strip the user ID
        cursor.execute(
            "UPDATE Slot SET is_reserved = FALSE, uid = NULL WHERE eid = %s AND snum = %s",
            (val_eid, val_snum)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")


# update event
def updateEvent(eid, title, datetime_str):
    """
    Update the title and the datetime of an event.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_eid = int(eid) if eid is not None else None

        # update event matching the given eid
        cursor.execute(
            "UPDATE Event SET title = %s, datetime = %s WHERE eid = %s",
            (title, datetime_str, val_eid)
        )

        # no rows affected means the eid didn't exist
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            print("Fail")
            return

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")

def deleteOrganizer(uid):
    """
    Delete an organizer from the database.
    ON DELETE CASCADE deletes the events, slots, and hosting records.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_uid = int(uid) if uid is not None else None

        cursor.execute("DELETE FROM Organizer WHERE uid = %s", (val_uid,))

        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            print("Fail")
            return

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        if conn:
            conn.rollback()
            conn.close()
        print("Fail")

def availableEvents(date):
    """
    List all future events that still have at least one
    unreserved slot. Sort by datetime ascending, then eid asc.
    """

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.eid, e.title, e.type, e.datetime,
                       COUNT(*) AS availableSlots
            FROM Event e
            JOIN Slot s ON e.eid = s.eid
            WHERE e.datetime > %s 
                       AND s.is_reserved = FALSE
            GROUP BY e.eid, e.title, e.type, e.datetime
            ORDER BY e.datetime ASC, e.eid ASC
        """, (date,))

        for row in cursor.fetchall():
            print_row(row)

        cursor.close()
        conn.close()

    except Exception:
        pass

def popularEventTypes(N):
    """
    For each event type, compute total reserved slots across all events.
    Return only types with at least N reserved slots. Sort by
    reservedCount descending, then type ascending.
    """

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_N = int(N) if N is not None else None

        cursor.execute("""
            SELECT e.type, COUNT(*) AS reservedCount
            FROM Event e
            JOIN Slot s ON e.eid = s.eid
            WHERE s.is_reserved = TRUE
            GROUP BY e.type
            HAVING COUNT(*) >= %s
            ORDER BY reservedCount DESC, e.type ASC
        """, (val_N,))

        for row in cursor.fetchall():
            print_row(row)

        cursor.close()
        conn.close()

    except Exception:
        pass

# 10. Participant schedule
def participantSchedule(uid):
    """
    Given a participant ID, list all events for which the
    participant has reserved a slot.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_uid = int(uid) if uid is not None else None

        cursor.execute("""
            SELECT e.eid, e.title, e.type, e.datetime, MIN(s.snum) AS snum,
                v.vid, v.street, v.city, v.state, v.zip
            FROM Slot s
            JOIN Event e ON s.eid = e.eid
            LEFT JOIN Hosting h ON e.eid = h.eid AND h.is_primary = TRUE
            LEFT JOIN Venue v ON h.vid = v.vid
            WHERE s.uid = %s AND s.is_reserved = TRUE
            GROUP BY e.eid, e.title, e.type, e.datetime,
                     v.vid, v.street, v.city, v.state, v.zip
            ORDER BY e.datetime ASC, e.eid ASC
        """, (val_uid,))

        for row in cursor.fetchall():
            print_row(row)

        cursor.close()
        conn.close()
    except Exception:
        pass

# 11. Organizer event count
def organizerStats(N):
    """
    List organizers who have created at least N events.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_N = int(N) if N is not None else None

        cursor.execute("""
            SELECT u.uid, u.username, o.department, COUNT(e.eid) AS eventCount
            FROM User u
            JOIN Organizer o ON u.uid = o.uid
            JOIN Event e ON o.uid = e.creator_uid
            GROUP BY u.uid, u.username, o.department
            HAVING COUNT(e.eid) >= %s
            ORDER BY eventCount DESC, u.uid ASC
        """, (val_N,))

        for row in cursor.fetchall():
            print_row(row)

        cursor.close()
        conn.close()

    except Exception:
        pass

# 12. Venue event list
def venueEvents(vid):
    """
    Given a venue ID, list all events hosted at that venue.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        val_vid = int(vid) if vid is not None else None

        cursor.execute("""
            SELECT e.eid, e.title, e.type, e.datetime, h.is_primary
            FROM Event e
            JOIN Hosting h ON e.eid = h.eid
            WHERE h.vid = %s
            ORDER BY e.datetime ASC, e.eid ASC
        """, (val_vid,))

        for row in cursor.fetchall():
            print_row(row)

        cursor.close()
        conn.close()
    except Exception:
        pass

# --- Dispatcher ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 project.py <function> [args...]")
        return

    func = sys.argv[1]
    args = sys.argv[2:]

    # Handle the "NULL" string conversion requirement safely
    args = [None if a == 'NULL' else a for a in args]

    if func == 'import':
        import_data(args[0])

    elif func == 'insertAdmin':
        # uid email username joined firstname lastname
        insertAdmin(args[0], args[1], args[2], args[3], args[4], args[5])

    elif func == 'addVenue':
        # eid vid is_primary
        addVenue(args[0], args[1], args[2])

    elif func == 'reserveSlot':
        reserveSlot(args[0], args[1], args[2])

    elif func == 'cancelReservation' or func == 'cancel':
        # Accommodates distinct terminal parsing flags safely
        if func == 'cancel' and len(args) > 0 and args[0] == 'Reservation':
            cancelReservation(args[1], args[2], args[3])
        else:
            cancelReservation(args[0], args[1], args[2])

    elif func == 'updateEvent' or func == 'update':
        if func == 'update' and len(args) > 0 and args[0] == 'Event':
            updateEvent(args[1], args[2], args[3])
        else:
            updateEvent(args[0], args[1], args[2])

    elif func == 'deleteOrganizer' or func == 'delete':
        if func == 'delete' and len(args) > 0 and args[0] == 'Organizer':
            deleteOrganizer(args[1])
        else:
            deleteOrganizer(args[0])

    elif func == 'availableEvents' or func == 'available':
        if func == 'available' and len(args) > 0 and args[0] == 'Events':
            availableEvents(args[1])
        else:
            availableEvents(args[0])

    elif func == 'popularEventTypes':
        popularEventTypes(args[0])

    elif func == 'participantSchedule':
        participantSchedule(args[0])

    elif func == 'organizerStats':
        organizerStats(args[0])

    elif func == 'venueEvents':
        venueEvents(args[0])

    else:
        print(f"Unknown function: {func}")


if __name__ == '__main__':
    main()