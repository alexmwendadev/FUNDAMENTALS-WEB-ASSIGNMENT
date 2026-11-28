# column types and helpers: Column = a table column, ForeignKey = link to another table, Numeric = exact decimal (for money)
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
# relationship lets Python objects reach related rows (user.products, order.payments)
from sqlalchemy.orm import relationship
# the parent class that turns an ordinary class into a database table
from database import Base

# one row per account (farmers and customers share this table; 'role' tells them apart)
class User(Base):
    # the real table name in the database
    __tablename__ = "users"
    # a unique number for each user, made automatically
    id = Column(Integer, primary_key=True, index=True)
    # the login name: unique, indexed for fast lookups, stored in lowercase
    username = Column(String, unique=True, index=True)
    # used for password reset emails. It is NOT unique, so two accounts can share one email
    email = Column(String, nullable=True)
    # the argon2 hash of the password, never the password itself
    hashed_password = Column(String)
    # 'farmer' or 'customer'
    role = Column(String, default="customer")
    # link to the avatar image
    profile_picture = Column(String, nullable=True)
    # contact number, stored as 2547...
    phone = Column(String, nullable=True)
    # where a farmer wants to be paid: mpesa, airtel money or till
    payment_method = Column(String, nullable=True)
    # the phone number or till number for that method
    payment_number = Column(String, nullable=True)
    # random string emailed in the reset link; cleared once it is used
    reset_token = Column(String, nullable=True)
    # when that token stops working (date saved as text)
    reset_token_expires = Column(String, nullable=True)

    # all the products this user sells (empty for customers)
    products = relationship("Product", back_populates="owner")

# something a farmer is selling
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    # the name shown in the shop
    item_name = Column(String, index=True)
    # price per unit; Numeric(10, 2) = up to 10 digits with 2 decimals, so money isn't rounded wrongly
    unit_price = Column(Numeric(10, 2))
    # what the price is per: kg, bag, crate...
    unit = Column(String)
    # how many units are left; goes down when an order is paid
    stock = Column(Integer, default=0)
    # link to the product photo
    image_url = Column(String)
    # which user owns this product (links to users.id)
    farmer_id = Column(Integer, ForeignKey("users.id"))
    # defaults to vegetables
    category = Column(String, default="vegetables")

    # product.owner gives the farmer's User row; back_populates keeps both sides in sync
    owner = relationship("User", back_populates="products")
    # every order made for this product
    orders = relationship("Order", back_populates="product")

    # not a column: a computed value so the API can show the farmer's username
    @property
    def farmer_username(self):
        return self.owner.username if self.owner else None

# one purchase by a buyer
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    # a copy of the name at purchase time, so the history stays right even if the product is edited or deleted
    product_name = Column(String)
    unit_price = Column(Numeric(10, 2))
    unit = Column(String)
    # how many units were bought
    qty = Column(Integer)
    # the total: unit_price x qty
    amount = Column(Numeric(10, 2))
    # always KES for now
    currency = Column(String, default="KES")
    # set to NULL if the farmer later deletes the product
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    # the farmer who must deliver this order
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # who bought it
    buyer_username = Column(String)
    
    # Optional so Pesapal can fill it later
    phone = Column(String, nullable=True) 
    
    # the delivery place typed by the buyer
    location = Column(String)
    # pending -> paid -> delivered (or refunded)
    status = Column(String, default="pending", nullable=False)
    # when the order was made (date saved as text)
    created_at = Column(String)
    # when payment was confirmed
    paid_at = Column(String, nullable=True)

    # order.product is the Product row
    product = relationship("Product", back_populates="orders")
    # every payment attempt for this order, oldest first
    payments = relationship("Payment", back_populates="order", order_by="Payment.id")

    # the farmer's phone, so the buyer can contact them
    @property
    def farmer_phone(self):
        if self.product and self.product.owner:
            return self.product.owner.phone
        return None

    # the status of the newest payment attempt (or None if there is none yet)
    @property
    def payment_status(self):
        return self.payments[-1].status if self.payments else None

# one attempt to pay for an order (an order can have several if the first one fails)
class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    # my unique code for this attempt, sent to Pesapal
    merchant_reference = Column(String, unique=True, index=True)
    # Pesapal's id for this payment (filled in after the checkout starts)
    tracking_id = Column(String, unique=True, index=True, nullable=True)
    # how much this attempt is for
    amount = Column(Numeric(10, 2))
    currency = Column(String, default="KES")
    # pending, completed, failed, reversed or review
    status = Column(String, default="pending", nullable=False)
    # how they paid, as reported by Pesapal
    payment_method = Column(String, nullable=True)
    # the receipt code from M-Pesa or the bank
    confirmation_code = Column(String, nullable=True)
    created_at = Column(String)
    # last time the status changed
    updated_at = Column(String)

    # payment.order is the Order row
    order = relationship("Order", back_populates="payments")

# messages sent through the contact form
class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    message = Column(String)