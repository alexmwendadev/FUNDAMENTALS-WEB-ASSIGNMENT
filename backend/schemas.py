# Optional means 'can be missing / None'
from typing import Optional
# pydantic checks incoming data against these classes. BaseModel = a data shape, Field = extra rules (like length limits),
# field_validator = custom conversion, ConfigDict = settings
from pydantic import BaseModel, ConfigDict, Field, field_validator

# turns a Decimal (money from the database) into a normal float so it can be sent as JSON; None stays None
def _num(value):
    return float(value) if value is not None else None

# what the signup form must send
class UserCreate(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=128)
    email: str = Field(max_length=254)
    # defaults to customer
    role: str = "customer"
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)

# what the profile page may change (everything is optional)
class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)

# what the API sends back about a user. Notice there is no password or reset token here, so they can never leak
class UserResponse(BaseModel):
    # lets pydantic read straight from a database object, not just a dictionary
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    payment_method: Optional[str] = None
    payment_number: Optional[str] = None
    profile_picture: Optional[str] = None

# a product as the shop page receives it
class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_name: str
    unit_price: float
    unit: str
    stock: int
    image_url: str
    farmer_id: int
    category: str = "vegetables"
    farmer_username: Optional[str] = None

    # runs BEFORE validation: converts the database Decimal into a float
    @field_validator("unit_price", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)

    # the database may hold None; show 0 instead
    @field_validator("stock", mode="before")
    @classmethod
    def stock_to_int(cls, v):
        return int(v or 0)

# what the buyer sends when pressing Pay
class CheckoutRequest(BaseModel):
    product_id: int
    # at least 1, at most 10,000
    quantity: int = Field(ge=1, le=10000)
    # delivery place, 3 to 200 characters
    location: str = Field(min_length=3, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254)

# the new order's id and the Pesapal link to pay on
class CheckoutResponse(BaseModel):
    order_id: int
    redirect_url: str

# an order as shown on the dashboards
class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_name: str
    unit_price: Optional[float] = None
    unit: Optional[str] = None
    qty: Optional[int] = None
    amount: Optional[float] = None
    currency: Optional[str] = "KES"
    product_id: Optional[int] = None
    farmer_id: Optional[int] = None
    buyer_username: str
    
    phone: Optional[str] = None 
    
    location: str
    status: str
    created_at: Optional[str] = None
    paid_at: Optional[str] = None
    # the newest payment's status (computed on the Order model)
    payment_status: Optional[str] = None
    # lets the buyer contact the farmer (computed on the Order model)
    farmer_phone: Optional[str] = None

    # the same Decimal-to-float conversion for the money fields
    @field_validator("unit_price", "amount", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)

# the tracking id Pesapal gives the buyer when they come back to the site
class VerifyRequest(BaseModel):
    order_tracking_id: str = Field(min_length=8, max_length=64)

# the order plus the payment's status
class VerifyResponse(BaseModel):
    order: OrderResponse
    payment_status: Optional[str] = None

# what the contact form sends
class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=2000)

# the same fields plus the id (it inherits from the class above)
class ContactMessageResponse(ContactMessageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

# step 1 of the password reset: just the email
class ForgotPasswordRequest(BaseModel):
    email: str

# step 2: the token from the email link and the new password
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str