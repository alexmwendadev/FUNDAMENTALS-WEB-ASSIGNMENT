from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, nullable=True)
    hashed_password = Column(String)
    role = Column(String, default="customer")
    profile_picture = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    payment_number = Column(String, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(String, nullable=True)

    products = relationship("Product", back_populates="owner")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, index=True)
    unit_price = Column(Numeric(10, 2))
    unit = Column(String)
    stock = Column(Integer, default=0)
    image_url = Column(String)
    farmer_id = Column(Integer, ForeignKey("users.id"))
    category = Column(String, default="vegetables")

    owner = relationship("User", back_populates="products")
    orders = relationship("Order", back_populates="product")

    @property
    def farmer_username(self):
        return self.owner.username if self.owner else None

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String)
    unit_price = Column(Numeric(10, 2))
    unit = Column(String)
    qty = Column(Integer)
    amount = Column(Numeric(10, 2))
    currency = Column(String, default="KES")
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    buyer_username = Column(String)
    
    # CHANGED: Made phone nullable so it can be filled in later by Pesapal
    phone = Column(String, nullable=True) 
    
    location = Column(String)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(String)
    paid_at = Column(String, nullable=True)

    product = relationship("Product", back_populates="orders")
    payments = relationship("Payment", back_populates="order", order_by="Payment.id")

    @property
    def farmer_phone(self):
        if self.product and self.product.owner:
            return self.product.owner.phone
        return None

    @property
    def payment_status(self):
        return self.payments[-1].status if self.payments else None

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    merchant_reference = Column(String, unique=True, index=True)
    tracking_id = Column(String, unique=True, index=True, nullable=True)
    amount = Column(Numeric(10, 2))
    currency = Column(String, default="KES")
    status = Column(String, default="pending", nullable=False)
    payment_method = Column(String, nullable=True)
    confirmation_code = Column(String, nullable=True)
    created_at = Column(String)
    updated_at = Column(String)

    order = relationship("Order", back_populates="payments")

class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    message = Column(String)