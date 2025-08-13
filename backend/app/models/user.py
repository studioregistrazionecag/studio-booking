from sqlalchemy import Column, Integer, String, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from ..database import Base


class Role(str, enum.Enum):
    ARTIST = "ARTIST"
    PRODUCER = "PRODUCER"
    MANAGER = "MANAGER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)

    role = Column(Enum(Role), nullable=False, default=Role.ARTIST)
    is_active = Column(Boolean, default=True)

    # utili per joinedload / nomi in output
    artist_bookings = relationship("Booking", foreign_keys="Booking.artist_id", back_populates="artist")
    producer_bookings = relationship("Booking", foreign_keys="Booking.producer_id", back_populates="producer")