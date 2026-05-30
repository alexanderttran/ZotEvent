import sys
import os
import mysql.connector

# --- DB Connection ---
def get_connection():
    return mysql.connector.connect(
        user='test',
        password='password',
        database='cs122a'
    )

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
    'user':          ['uid', 'email', 'username', 'joined'],
    'organizer':     ['uid', 'department', 'experience'],
    'participant':   ['uid', 'type'],
    'administrator': ['uid', 'firstname', 'lastname'],
    'event':         ['eid', 'creator_uid', 'title', 'type', 'datetime'],
    'slot':          ['eid', 'snum', 'is_reserved', 'uid'],
    'venue':         ['vid', 'street', 'city', 'state', 'zip'],
    'oncampus':      ['vid', 'code'],
    'offcampus':     ['vid', 'distance'],
    'hosting':       ['eid', 'vid', 'is_primary'],
    'approval':      ['uid', 'vid', 'valid_from', 'valid_until'],
}

# Insertion order respects FK dependencies
TABLE_INSERT_ORDER = [
    'user', 'organizer', 'participant', 'administrator',
    'event', 'slot',
    'venue', 'oncampus', 'offcampus',
    'hosting', 'approval',
]

# import is a reserved word, use import_data instead
def import_data(folder):
    """
    1. Drop and recreate all tables.
    2. Read each CSV from the folder and insert rows.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Execute DDL statements one by one
        for statement in DDL.strip().split(';'):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)
        conn.commit()

        # Insert data from CSVs in dependency order
        for table in TABLE_INSERT_ORDER:
            csv_path = os.path.join(folder, f'{table}.csv')
            if not os.path.exists(csv_path):
                continue

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
                    values = [None if v == 'NULL' else v for v in values]
                    cursor.execute(insert_sql, values)

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception as e:
        print("Fail")


def insertAdmin(uid, email, username, joined, firstname, lastname):
    """
    2. Insert a new user and administrator into User and Administrator tables.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO User (uid, email, username, joined) VALUES (%s, %s, %s, %s)",
            (uid, email, username, joined)
        )
        cursor.execute(
            "INSERT INTO Administrator (uid, firstname, lastname) VALUES (%s, %s, %s)",
            (uid, firstname, lastname)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        print("Fail")


def addVenue(eid, vid, is_primary):
    """
    3. Add a venue to an existing event in the Hosting table.
       If is_primary=true, ensure no other primary venue exists for this event.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        is_primary_bool = is_primary.lower() == 'true'

        if is_primary_bool:
            # Check if a primary venue already exists for this event
            cursor.execute(
                "SELECT COUNT(*) FROM Hosting WHERE eid = %s AND is_primary = TRUE",
                (eid,)
            )
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.close()
                conn.close()
                print("Fail")
                return

        cursor.execute(
            "INSERT INTO Hosting (eid, vid, is_primary) VALUES (%s, %s, %s)",
            (eid, vid, is_primary_bool)
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Success")
    except Exception:
        print("Fail")


# --- Dispatcher ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 project.py <function> [args...]")
        return

    func = sys.argv[1]
    args = sys.argv[2:]

    if func == 'import':
        import_data(args[0])

    elif func == 'insertAdmin':
        # uid email username joined firstname lastname
        insertAdmin(args[0], args[1], args[2], args[3], args[4], args[5])

    elif func == 'addVenue':
        # eid vid is_primary
        addVenue(args[0], args[1], args[2])

    else:
        print(f"Unknown function: {func}")


if __name__ == '__main__':
    main()