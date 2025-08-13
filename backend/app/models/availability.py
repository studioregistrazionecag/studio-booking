from sqlalchemy import Column, Integer, Date, Time, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    day = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_blocked = Column(Boolean, default=False)  # per emergenze

    manager = relationship("User")
    __table_args__ = (UniqueConstraint("day","start_time","end_time", name="uniq_slot"),)