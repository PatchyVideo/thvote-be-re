from sqlalchemy import Column, String, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import INET

from base import Base


class User(Base):
    # CREATE TABLE user
    __tablename__ = 'user'

    # id TEXT PRIMARY KEY UNIQUE
    id = Column(String, primary_key=True, unique=True)

    # phone_number TEXT NULL
    phone_number = Column(String, nullable=True)

    # email TEXT NULL
    email = Column(String, nullable=True)

    # register_date DATETIME NOT NULL
    register_date = Column(DateTime, nullable=False)

    # register_ip_addr INET NOT NULL
    register_ip_address = Column(INET, nullable=False)

    __table_args__ = (
        CheckConstraint(
            'phone_number IS NOT NULL OR email IS NOT NULL',
            name='at_least_one_identifier'
        ),
    )
