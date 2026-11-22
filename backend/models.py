# column types: Integer, String, Numeric (exact decimals for money); ForeignKey links tables together
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
# relationship lets one object reach related rows, e.g. order.payments
from sqlalchemy.orm import relationship

# the shared base class every table below inherits from
from database import Base


# USERS table: customers and farmers share it, 'role' tells them apart
class User(Base):
    # name of the table in the database
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)  # unique number for each user
    username = Column(String, unique=True, index=True)  # login name (stored lowercase). unique=True stops duplicates
    email = Column(String, nullable=True)  # used for payment receipts. Optional because older accounts have none
    hashed_password = Column(String)  # the argon2 hash, never the real password
    role = Column(String, default="customer")  # 'customer' or 'farmer'
    profile_picture = Column(String, nullable=True)  # path or link of the profile image
    phone = Column(String, nullable=True)  # contact number in 2547XXXXXXXX form
    payment_method = Column(String, nullable=True)  # farmers only: mpesa, airtel money or till
    payment_number = Column(String, nullable=True)  # farmers only: the number or till that payouts go to

    # all products this user (a farmer) has listed
    products = relationship("Product", back_populates="owner")


# PRODUCTS table: things farmers sell
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)  # unique number for each product
    item_name = Column(String, index=True)  # display name, e.g. Maize
    unit_price = Column(Numeric(10, 2))          # KES per unit, e.g. 90.00
    unit = Column(String)                        # kg, bag, bunch...
    stock = Column(Integer, default=0)           # whole units available
    image_url = Column(String)  # where the photo lives (/uploads/... or a Cloudinary link)
    farmer_id = Column(Integer, ForeignKey("users.id"))  # which user owns this product

    # the farmer (User) who owns the product
    owner = relationship("User", back_populates="products")
    # all orders placed for this product
    orders = relationship("Order", back_populates="product")

    # not a column: a read-only value worked out when asked
    @property
    # gives the farmer's username so the product card can show 'By <name>'
    def farmer_username(self):
        return self.owner.username if self.owner else None


# ORDERS table: one row per purchase
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)  # unique order number
    # Snapshot of what was bought, so later edits or deletes of the product don't change history.
    product_name = Column(String)  # name at the time of purchase
    unit_price = Column(Numeric(10, 2))
    unit = Column(String)
    qty = Column(Integer)  # how many units were bought
    amount = Column(Numeric(10, 2))              # total, calculated on the server
    currency = Column(String, default="KES")  # always KES for now
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # link to the product; becomes empty if the product is later deleted
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # the farmer who must deliver it
    buyer_username = Column(String)  # who bought it (the customer's username)
    phone = Column(String)  # customer's phone for this delivery
    location = Column(String)  # delivery location typed at checkout
    # pending (awaiting payment) -> paid -> delivered, or refunded
    status = Column(String, default="pending", nullable=False)
    created_at = Column(String)  # when the order was placed (ISO text)
    paid_at = Column(String, nullable=True)  # when payment was confirmed; empty until then

    # the Product row this order refers to
    product = relationship("Product", back_populates="orders")
    # every payment attempt for this order, oldest first
    payments = relationship("Payment", back_populates="order", order_by="Payment.id")

    # read-only value, not a column
    @property
    # status of the newest payment attempt (None if there is none yet)
    def payment_status(self):
        # newest attempt = last in the list, because the list is ordered by id
        """Status of the most recent payment attempt, if any."""
        return self.payments[-1].status if self.payments else None


# PAYMENTS table: each try at paying for an order. A customer can try more than once
class Payment(Base):
    """One attempt to pay for an order. An order can have several (retries)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)  # unique payment number
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)  # which order this payment is for
    merchant_reference = Column(String, unique=True, index=True)  # my own reference sent to Pesapal (SHAMBA-<order>-<random>); unique
    tracking_id = Column(String, unique=True, index=True, nullable=True)  # Pesapal's id for the payment; filled in after Pesapal accepts the order
    amount = Column(Numeric(10, 2))  # amount this attempt should pay
    currency = Column(String, default="KES")  # currency of the attempt
    # pending | completed | failed | reversed | review
    status = Column(String, default="pending", nullable=False)  # see the comment above for the possible values
    payment_method = Column(String, nullable=True)  # how they paid (M-Pesa, card...), copied from Pesapal's answer
    confirmation_code = Column(String, nullable=True)  # Pesapal's confirmation code, useful if a payment is ever disputed
    created_at = Column(String)  # when the attempt started
    updated_at = Column(String)  # when it last changed

    # the Order this payment belongs to
    order = relationship("Order", back_populates="payments")


# CONTACT_MESSAGES table: messages sent from the contact form
class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)  # unique message number
    name = Column(String)  # sender's name
    email = Column(String)  # sender's email, so I can reply
    message = Column(String)  # the message text
