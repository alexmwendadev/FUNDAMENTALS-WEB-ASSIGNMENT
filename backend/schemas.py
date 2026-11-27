from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

def _num(value):
    return float(value) if value is not None else None

class UserCreate(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=128)
    email: str = Field(max_length=254)
    role: str = "customer"
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)

class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=30)
    payment_number: Optional[str] = Field(default=None, max_length=40)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    payment_method: Optional[str] = None
    payment_number: Optional[str] = None
    profile_picture: Optional[str] = None

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

    @field_validator("unit_price", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)

    @field_validator("stock", mode="before")
    @classmethod
    def stock_to_int(cls, v):
        return int(v or 0)

class CheckoutRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=10000)
    location: str = Field(min_length=3, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254)

class CheckoutResponse(BaseModel):
    order_id: int
    redirect_url: str

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
    payment_status: Optional[str] = None
    farmer_phone: Optional[str] = None

    @field_validator("unit_price", "amount", mode="before")
    @classmethod
    def money_to_number(cls, v):
        return _num(v)

class VerifyRequest(BaseModel):
    order_tracking_id: str = Field(min_length=8, max_length=64)

class VerifyResponse(BaseModel):
    order: OrderResponse
    payment_status: Optional[str] = None

class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=2000)

class ContactMessageResponse(ContactMessageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str