from collections.abc import Sequence
from datetime import datetime, timezone

from custom_types import TicketDict, TicketDictID, UserDTO, status_type
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column, relationship, sessionmaker


class Base(MappedAsDataclass, DeclarativeBase, repr=False, unsafe_hash=True, kw_only=True):
    """
    Base for SQLAlchemy dataclass
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)


class User(Base, sessionmaker):
    __tablename__ = "users"
    user_uid: Mapped[int] = mapped_column(Integer)
    first_name: Mapped[str] = mapped_column(String(30))
    last_name: Mapped[str] = mapped_column(String(30))
    department: Mapped[str] = mapped_column(String(50))
    is_priority: Mapped[int] = mapped_column(Integer)

    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="user", init=False)

    def __repr__(self) -> str:
        return (
            f"User=(id={self.id!s}, first_name={self.first_name!s}, last_name={self.last_name!s},"
            f"department={self.department!s}, is_priority={self.is_priority!s})"
        )


def get_user_by_uid(user_uid: int) -> User | None:
    with Session() as session:
        return session.query(User).filter_by(user_uid=user_uid).one_or_none()


def add_user(user_dict: UserDTO) -> User:
    with Session() as session:
        new_user = User(
            user_uid=user_dict.user_uid,
            first_name=user_dict.first_name,
            last_name=user_dict.last_name,
            department=user_dict.department,
            is_priority=user_dict.is_priority,
        )
        session.add(new_user)
        session.commit()
        return new_user


class BlockedUser(Base, sessionmaker):
    __tablename__ = "blocked_users"
    user_uid: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String)


def add_blocked_user(uid: int, user_name: str):
    with Session() as session:
        blocked_user = BlockedUser(user_uid=uid, username=user_name)
        session.add(blocked_user)
        session.commit()


def unblock_user(user_uid: int):
    with Session() as session:
        blocked_user = session.query(BlockedUser).filter_by(user_uid=user_uid).one_or_none()
        if blocked_user:
            session.delete(blocked_user)
            session.commit()


def check_blocked(user_uid: int) -> bool:
    with Session() as session:
        return bool(session.query(BlockedUser).filter_by(user_uid=user_uid).one_or_none())


def all_blocked_users():
    with Session() as session:
        return [[user.user_uid, user.username] for user in session.query(BlockedUser).all()]


class Ticket(Base, sessionmaker):
    __tablename__ = "tickets"
    user_uid: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_uid"))
    user: Mapped["User"] = relationship("User", back_populates="tickets", init=False)
    title: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[status_type] = mapped_column(String)
    update_reason: Mapped[str | None] = mapped_column(String, nullable=True, init=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.now(tz=timezone.utc))
    dates_created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(tz=timezone.utc))

    def __repr__(self) -> str:
        return (
            f"User(user_id={self.user_uid} title={self.title!r}, description={self.description!r},"
            f"status = {self.status})"
        )

    def as_ticket_dict(self) -> TicketDict:
        return TicketDict(user_uid=self.user_uid, title=self.title, description=self.description, status=self.status)


def list_tickets(uid=0, status: str | None = None) -> Sequence[TicketDict]:
    """Возвращает список словарей тикетов"""
    with Session() as session:
        if uid != 0:
            select_tickets = select(Ticket).where(Ticket.user_uid.__eq__(uid))
        elif status is None:
            select_tickets = select(Ticket)
        else:
            select_tickets = select(Ticket).where(Ticket.status.__eq__(status))

        return [
            TicketDict.model_validate(ticket, from_attributes=True)
            for ticket in session.query(select_tickets.subquery()).all()
        ]


def list_ticket_ids(uid: int) -> Sequence[TicketDictID]:
    """Получает список словарей с ID тикетов"""
    with Session() as session:
        select_tickets = select(Ticket).where(Ticket.user_uid.__eq__(uid))
        return [
            TicketDictID.model_validate(ticket, from_attributes=True)
            for ticket in session.query(select_tickets.subquery()).all()
        ]


def get_ticket_by_id(ticket_id: int) -> Ticket | None:
    """Получает тикет из базы данных по его id."""
    with Session() as session:
        ticket: Ticket | None = session.query(Ticket).filter_by(id=ticket_id).one_or_none()
        if not ticket:
            print(f"Тикет с id {ticket_id} не найден!")
            return
        return ticket


def edit_ticket_status(
    ticket_id: int,
    new_status: status_type,
    reason: str = "Тикет завершен администратором.",
) -> None:
    """Редактирует статус тикета в БД по его ID"""
    with Session() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).one_or_none()
        if ticket:
            if new_status in ("rejected", "completed"):
                ticket.update_reason = reason
            ticket.status = new_status
            ticket.last_updated = datetime.now(tz=timezone.utc)
            session.commit()


def add_ticket(ticket_dict: TicketDict) -> int:
    """Запись тикетов в БД"""
    with Session() as session:
        new_ticket = Ticket(
            user_uid=ticket_dict.user_uid,
            title=ticket_dict.title,
            description=ticket_dict.description,
            dates_created=datetime.now(tz=timezone.utc),
            last_updated=datetime.now(tz=timezone.utc),
            status=ticket_dict.status,
        )
        print(new_ticket)
        session.add(new_ticket)
        session.commit()
        return new_ticket.id


engine = create_engine("sqlite:///bot.db", echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(autoflush=False, bind=engine)
