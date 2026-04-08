from sqlalchemy import Column, DateTime, String, CheckConstraint

from .base import Base


class User(Base):
    """User database model.

    Stores user account information including authentication credentials
    and registration metadata.
    """

    __tablename__ = "user"

    id = Column(String, primary_key=True, unique=True)

    phone_number = Column(String, nullable=True)

    email = Column(String, nullable=True)

    password_hash = Column(String, nullable=True)

    legacy_salt = Column(String, nullable=True)

    register_date = Column(DateTime, nullable=False)

    register_ip_address = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "phone_number IS NOT NULL OR email IS NOT NULL",
            name="at_least_one_identifier",
        ),
    )
