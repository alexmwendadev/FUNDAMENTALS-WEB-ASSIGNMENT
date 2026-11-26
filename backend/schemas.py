# Optional marks a field that may be left out (None)
from typing import Optional

# pydantic checks incoming JSON and shapes outgoing JSON.
# Field adds limits, field_validator converts a value before it is checked
from pydantic import BaseModel, ConfigDict, Field, field_validator


# helper: money comes out of the database as Decimal, the browser wants a plain number
def _num(value):
    """Money comes out of the database as Decimal; send plain numbers to the browser."""
    return float(value) if value is not None else None


# --- Users ---
# what the signup form sends in. The farmer-only fields are optional
class UserCreate(BaseModel):
    username: str = Field(max_length=60)  # max_length stops absurdly long input
    password: str = Field(max_length=128)
    email: str = Field(max_length=254)
    role: str = "customer"
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)


# what the profile page may change. Every field is optional, so only the fields sent get updated
class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)


# what the API sends back about a user. The password hash is deliberately not included
class UserResponse(BaseModel):
    # lets pydantic read values straight off a database object
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    payment_method: Optional[str] = None
    payment_number: Optional[str] = None
    profile_picture: Optional[str] = None


# --- Products ---
# what the API sends back for a product
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

    # convert the Decimal price to a plain number before it is checked
    @field_validator("unit_price", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)

    # old rows can have no stock value; treat that as 0
    @field_validator("stock", mode="before")
    @classmethod
    def stock_to_int(cls, v):
        return int(v or 0)


# --- Orders & payments ---
# what the checkout page sends. Note there is NO price or total here: the server works that out
# Also NO phone number here, because Pesapal collects it on their page.
class CheckoutRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=10000)  # whole number from 1 to 10000
    location: str = Field(min_length=3, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254)


# after checkout: the new order number and the Pesapal page to send the customer to
class CheckoutResponse(BaseModel):
    order_id: int
    redirect_url: str


# what the API sends back for an order
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
    phone: str
    location: str
    status: str
    created_at: Optional[str] = None
    paid_at: Optional[str] = None
    payment_status: Optional[str] = None
    farmer_phone: Optional[str] = None

    # convert both Decimal money values to plain numbers
    @field_validator("unit_price", "amount", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)


# sent by the payment-return page: Pesapal's tracking id from the address bar
class VerifyRequest(BaseModel):
    order_tracking_id: str = Field(min_length=8, max_length=64)  # length limits keep out junk


# answer to a verify request: the order plus the latest payment status
class VerifyResponse(BaseModel):
    order: OrderResponse
    payment_status: Optional[str] = None


# --- Contact ---
# what the contact form sends in, with length limits
class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=2000)


# same fields plus the id the database assigned
class ContactMessageResponse(ContactMessageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

# --- Password Reset ---
class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str