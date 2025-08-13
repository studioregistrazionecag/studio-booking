from sqlalchemy import Column, Integer, Date, Time, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
import enum
from ..database import Base


class SlotStatus(str, enum.Enum):
    LIBERO = "LIBERO"          # prenotabile
    IN_SOSPESO = "IN_SOSPESO"  # richiesta in corso (bloccato)
    OCCUPATO = "OCCUPATO"      # confermato
    CHIUSO = "CHIUSO"          # chiuso/eliminato


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(Enum(SlotStatus), default=SlotStatus.LIBERO, nullable=False)
    is_deleted = Column(Boolean, default=False)

    # booking collegati a questo slot
    bookings = relationship("Booking", back_populates="slot")