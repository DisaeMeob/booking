from src.database import Base
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Integer

class HotelsOrm(Base):
    __tablename__ = 'hotels'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String)