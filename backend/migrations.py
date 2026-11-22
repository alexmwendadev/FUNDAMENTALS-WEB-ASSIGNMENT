"""Brings an existing database up to date on startup.

SQLAlchemy's create_all() makes missing tables but never changes existing ones,
so new columns are added here and old text prices/quantities are converted to
real numbers. Safe to run on every start: it only touches what is missing."""
# logging to report what the migration did
import logging

# inspect reads the existing tables and columns; text runs raw SQL
from sqlalchemy import inspect, text

# reuses the old-price and quantity readers
import services

# shared logger
log = logging.getLogger("shamba")

# columns added after the first version of the database, per table: (column name, SQL type).
# If one is missing it gets added; if it exists nothing happens
NEW_COLUMNS = {
    "users": [("email", "VARCHAR"), ("profile_picture", "VARCHAR")],
    "products": [("unit_price", "NUMERIC(10, 2)"), ("unit", "VARCHAR"), ("stock", "INTEGER")],
    "orders": [("qty", "INTEGER"), ("unit_price", "NUMERIC(10, 2)"), ("unit", "VARCHAR"),
               ("amount", "NUMERIC(10, 2)"), ("currency", "VARCHAR"), ("paid_at", "VARCHAR")],
}


# names of the columns a table currently has
def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


# adds every column from NEW_COLUMNS that the database doesn't have yet
def _add_missing_columns(engine):
    # tables that exist right now
    tables = set(inspect(engine).get_table_names())
    # go through each table
    for table, columns in NEW_COLUMNS.items():
        # a brand new database: create_all already made it with every column
        if table not in tables:
            continue
        # columns it already has
        have = _columns(engine, table)
        # check each wanted column
        for name, ddl in columns:
            # missing: add it
            if name not in have:
                # one transaction per ALTER TABLE
                with engine.begin() as conn:
                    # the SQL that adds the column (existing rows get an empty value)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                # report it in the console
                log.info("Migration: added %s.%s", table, name)


# converts old text prices/quantities (price='90(per kg)', quantity='59') into unit_price, unit and stock
def _convert_products(engine):
    # which columns exist
    have = _columns(engine, "products")
    # no old columns means a fresh database: nothing to convert
    if not {"price", "quantity"} <= have:
        return  # fresh database: nothing old to convert
    # one transaction for the whole conversion
    with engine.begin() as conn:
        # only products that haven't been converted yet (unit_price still empty), so it's safe to run every start
        rows = conn.execute(text("SELECT id, price, quantity FROM products WHERE unit_price IS NULL")).fetchall()
        # one product at a time
        for pid, price, quantity in rows:
            # read the old text price
            unit_price, unit = services.parse_legacy_price(price)
            # write the new values back
            conn.execute(
                # price falls back to 0 if unreadable (a 0 price can't be bought); stock falls back to 0
                text("UPDATE products SET unit_price = :p, unit = :u, stock = :s WHERE id = :id"),
                {"p": float(unit_price or 0), "u": unit, "s": services.parse_legacy_quantity(quantity) or 0, "id": pid},
            )
        # only say something when there was work
        if rows:
            # report how many
            log.info("Migration: converted %d products to numeric price and stock", len(rows))


# same idea for orders: fills qty, unit_price, unit, amount and currency from the old text values
def _convert_orders(engine):
    # which columns exist
    have = _columns(engine, "orders")
    # fresh database: nothing to convert
    if not {"price", "quantity"} <= have:
        return
    # one transaction
    with engine.begin() as conn:
        # only orders that haven't been converted yet (qty still empty)
        rows = conn.execute(text("SELECT id, price, quantity FROM orders WHERE qty IS NULL")).fetchall()
        # one order at a time
        for oid, price, quantity in rows:
            # read the old text price
            unit_price, unit = services.parse_legacy_price(price)
            # old quantity, or 1 if unreadable
            qty = services.parse_legacy_quantity(quantity) or 1
            # total = price x quantity, or empty if the price was unreadable
            amount = services.compute_amount(unit_price, qty) if unit_price else None
            # write the numbers back
            conn.execute(
                # currency is set to KES for old orders
                text("UPDATE orders SET qty = :q, unit_price = :p, unit = :u, amount = :a, currency = 'KES' WHERE id = :id"),
                {"q": qty, "p": float(unit_price) if unit_price else None, "u": unit,
                 "a": float(amount) if amount is not None else None, "id": oid},
            )
        # only say something when there was work
        if rows:
            # report how many
            log.info("Migration: converted %d orders to numeric amounts", len(rows))


# called once from main.py at startup
def run_migrations(engine):
    # step 1: add any missing columns
    _add_missing_columns(engine)
    # step 2: convert old product text into numbers
    _convert_products(engine)
    # step 3: convert old order text into numbers
    _convert_orders(engine)
