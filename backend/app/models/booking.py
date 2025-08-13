from sqlalchemy import Column, Integer, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum
from ..database import Base


class BookingStatus(str, enum.Enum):
    PENDING_PRODUCER = "PENDING_PRODUCER"
    PENDING_MANAGER = "PENDING_MANAGER"
    CONFIRMED = "CONFIRMED"
    REJECTED_BY_PRODUCER = "REJECTED_BY_PRODUCER"
    REJECTED_BY_MANAGER = "REJECTED_BY_MANAGER"
    # nuovi stati di annullamento
    CANCELED_BY_PRODUCER = "CANCELED_BY_PRODUCER"
    CANCELED_BY_ARTIST = "CANCELED_BY_ARTIST"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)

    slot_id = Column(Integer, ForeignKey("availability_slots.id"), nullable=False)
    artist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    producer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.PENDING_PRODUCER)
    # NB: il campo si chiama "notes" (plurale)
    notes = Column(Text, default="")

    slot = relationship("AvailabilitySlot", back_populates="bookings")
    artist = relationship("User", foreign_keys=[artist_id], back_populates="artist_bookings")
    producer = relationship("User", foreign_keys=[producer_id], back_populates="producer_bookings")