# date and time tools for working out when a login token expires
from datetime import datetime, timedelta, timezone

# PyJWT: creates and checks the signed login tokens
import jwt
# passlib hashes passwords so the real password is never stored
from passlib.context import CryptContext

# my settings file
import config

# the key that signs tokens (anyone without it cannot forge a login)
SECRET_KEY = config.SECRET_KEY
# signing method used for the tokens
ALGORITHM = "HS256"
# how long a token stays valid
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

# argon2 is the hashing method; 'deprecated=auto' lets old hashes be upgraded later
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# checks a typed password against the stored hash (True/False)
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


# turns a plain password into a hash to store in the database
def get_password_hash(password):
    return pwd_context.hash(password)


# builds the login token the browser keeps after login
def create_access_token(data: dict):
    # copy so the caller's dictionary isn't changed
    to_encode = data.copy()
    # add the expiry time (UTC now + the allowed minutes)
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # sign everything with the secret key and return the token string
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
