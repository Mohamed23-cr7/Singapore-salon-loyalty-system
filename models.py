from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# -----------------------------
# ADMIN / STAFF
# -----------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(100),
        nullable=False
    )

    username = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="staff"
    )

    is_active_user = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


# -----------------------------
# CUSTOMERS
# -----------------------------

class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)

    loyalty_number = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )

    full_name = db.Column(
        db.String(100),
        nullable=False
    )

    phone = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120)
    )

    gender = db.Column(
        db.String(20)
    )

    current_punches = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    qr_token = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


# -----------------------------
# VISITS / PUNCHES
# -----------------------------

class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id"),
        nullable=False
    )

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    service_name = db.Column(
        db.String(100),
        nullable=False
    )

    original_price = db.Column(
        db.Numeric(10, 2),
        nullable=False
    )

    discount_percent = db.Column(
        db.Integer,
        default=0
    )

    final_price = db.Column(
        db.Numeric(10, 2),
        nullable=False
    )

    punch_number = db.Column(
        db.Integer,
        nullable=False
    )

    visit_date = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    customer = db.relationship(
        "Customer",
        backref="visits"
    )

    staff = db.relationship(
        "User",
        backref="recorded_visits"
    )


# -----------------------------
# REWARDS
# -----------------------------

class Reward(db.Model):
    __tablename__ = "rewards"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id"),
        nullable=False
    )

    reward_type = db.Column(
        db.String(50),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="available",
        nullable=False
    )

    earned_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    redeemed_at = db.Column(
        db.DateTime
    )

    customer = db.relationship(
        "Customer",
        backref="rewards"
    )


# -----------------------------
# AUDIT LOG
# -----------------------------

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    details = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user = db.relationship(
        "User",
        backref="audit_logs"
    )