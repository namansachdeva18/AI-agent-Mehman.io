"""SQLite database schema definitions for Mehman.io.

Creates all normalized tables:
- properties
- rooms
- amenities
- property_amenities (junction)
- room_amenities (junction)
- policies
- add_ons
- availability
- booking_holds
- conversations (Phase 3: persistent conversation state & versioning)
- conversation_messages (Phase 3: ordered message history)
"""

CREATE_TABLES_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'India',
    description TEXT NOT NULL,
    star_rating REAL NOT NULL CHECK(star_rating >= 1.0 AND star_rating <= 5.0),
    check_in_time TEXT NOT NULL DEFAULT '14:00',
    check_out_time TEXT NOT NULL DEFAULT '11:00',
    address TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    max_guests INTEGER NOT NULL CHECK(max_guests >= 1),
    max_adults INTEGER NOT NULL CHECK(max_adults >= 1),
    max_children INTEGER NOT NULL DEFAULT 0,
    base_price_per_night REAL NOT NULL CHECK(base_price_per_night > 0),
    room_size_sqft INTEGER NOT NULL,
    bed_type TEXT NOT NULL,
    total_units INTEGER NOT NULL CHECK(total_units >= 1),
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE,
    UNIQUE (property_id, name)
);

CREATE TABLE IF NOT EXISTS amenities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'general'
);

CREATE TABLE IF NOT EXISTS property_amenities (
    property_id INTEGER NOT NULL,
    amenity_id INTEGER NOT NULL,
    PRIMARY KEY (property_id, amenity_id),
    FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE,
    FOREIGN KEY (amenity_id) REFERENCES amenities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS room_amenities (
    room_id INTEGER NOT NULL,
    amenity_id INTEGER NOT NULL,
    PRIMARY KEY (room_id, amenity_id),
    FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
    FOREIGN KEY (amenity_id) REFERENCES amenities (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    policy_type TEXT NOT NULL,
    description TEXT NOT NULL,
    FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS add_ons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    pricing_type TEXT NOT NULL CHECK(pricing_type IN ('PER_NIGHT', 'PER_BOOKING', 'PER_PERSON', 'PER_PERSON_PER_NIGHT')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    available_units INTEGER NOT NULL CHECK(available_units >= 0),
    price_override REAL DEFAULT NULL,
    FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
    UNIQUE (room_id, date)
);

CREATE TABLE IF NOT EXISTS booking_holds (
    id TEXT PRIMARY KEY,
    room_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    guest_name TEXT DEFAULT NULL,
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL,
    guests INTEGER NOT NULL CHECK(guests >= 1),
    total_price REAL NOT NULL CHECK(total_price >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'HELD' CHECK(status IN ('HELD', 'CONFIRMED', 'EXPIRED', 'CANCELLED')),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'COMPLETED', 'ABANDONED')),
    booking_state_json TEXT NOT NULL DEFAULT '{}',
    current_hold_id TEXT DEFAULT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (current_hold_id) REFERENCES booking_holds (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL', 'guest', 'agent')),
    content TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK(sequence_number >= 1),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    UNIQUE (conversation_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
CREATE INDEX IF NOT EXISTS idx_rooms_property ON rooms(property_id);
CREATE INDEX IF NOT EXISTS idx_availability_room_date ON availability(room_id, date);
CREATE INDEX IF NOT EXISTS idx_booking_holds_session ON booking_holds(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conv_messages_seq ON conversation_messages(conversation_id, sequence_number);
"""
