# warnings lets me hide one harmless SQLite message further down
import warnings

# SQLAlchemy is the ORM: it turns Python classes into database tables and Python code into SQL
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# my settings file; the database address comes from here
import config

# True when the database is the local SQLite file, False for PostgreSQL and others
_is_sqlite = config.DATABASE_URL.startswith("sqlite")

# only relevant to SQLite
if _is_sqlite:
    # SQLite stores NUMERIC as float. Amounts are 2-decimal KES, so this is safe; hide the noise.
    # hide the 'Decimal not supported natively' notice (amounts have 2 decimals so the float storage is fine)
    warnings.filterwarnings("ignore", message=".*support Decimal objects natively.*")

# the engine is the actual connection to the database
engine = create_engine(
    config.DATABASE_URL,
    # SQLite refuses use from several threads by default; FastAPI uses several, so switch that check off (PostgreSQL needs nothing)
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # for PostgreSQL: test a connection before using it so a dropped one never causes an error
    pool_pre_ping=not _is_sqlite,
)

# factory for database sessions (one per request).
# autocommit=False: I call commit() myself. autoflush=False: nothing is written until I say so
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# every model class in models.py inherits from Base, which is how SQLAlchemy finds the tables
Base = declarative_base()
