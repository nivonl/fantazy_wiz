"""
SQLAlchemy schema.

Every user-scoped table carries a `user_id` (default local user = 1) even though this is a
single-user tool today. That's the one deliberate "multi-user in mind" decision: adding real
accounts later means an auth layer + real rows, not a migration that reshapes these tables.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

DEFAULT_USER_ID = 1


class Base(DeclarativeBase):
    pass


class Competition(Base):
    """One row per league we support: 'fpl' (Premier League) or 'laliga' (9cat.co.il)."""

    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)  # "fpl" | "laliga"
    name = Column(String, nullable=False)

    teams = relationship("Team", back_populates="competition")
    fixtures = relationship("Fixture", back_populates="competition")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("competition_id", "external_id", name="uq_team_ext"),)

    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    external_id = Column(String, nullable=False)  # provider's own team id, kept as string
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=True)

    competition = relationship("Competition", back_populates="teams")
    players = relationship("Player", back_populates="team")


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("competition_id", "external_id", name="uq_player_ext"),)

    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    external_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)  # GK | DEF | MID | FWD
    price = Column(Float, nullable=True)  # in the platform's own currency units (e.g. 10.5m)

    # per-90 rates used by player_points.py; refreshed each pull, not hand-maintained
    minutes_total = Column(Integer, default=0)
    goals_total = Column(Integer, default=0)
    assists_total = Column(Integer, default=0)
    starts_total = Column(Integer, default=0)
    appearances_total = Column(Integer, default=0)

    team = relationship("Team", back_populates="players")


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (UniqueConstraint("competition_id", "external_id", name="uq_fixture_ext"),)

    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    external_id = Column(String, nullable=False)
    gameweek = Column(Integer, nullable=True)
    kickoff = Column(DateTime, nullable=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    home_score = Column(Integer, nullable=True)  # null until played
    away_score = Column(Integer, nullable=True)

    competition = relationship("Competition", back_populates="fixtures")


class TeamRating(Base):
    """A fitted attack/defense snapshot for one team as of a given gameweek."""

    __tablename__ = "team_ratings"
    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", "as_of_gameweek", name="uq_rating_snapshot"),
    )

    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    as_of_gameweek = Column(Integer, nullable=False)
    attack = Column(Float, nullable=False)
    defense = Column(Float, nullable=False)
    home_advantage = Column(Float, nullable=False)  # global term, duplicated per row for convenience
    fitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserSquad(Base):
    """A user's current 15 for one competition (one live row per user+competition)."""

    __tablename__ = "user_squads"
    __table_args__ = (UniqueConstraint("user_id", "competition_id", name="uq_user_squad"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, default=DEFAULT_USER_ID)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    bank = Column(Float, default=0.0)
    free_transfers = Column(Integer, default=1)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    players = relationship("UserSquadPlayer", back_populates="squad", cascade="all, delete-orphan")


class UserSquadPlayer(Base):
    __tablename__ = "user_squad_players"

    id = Column(Integer, primary_key=True)
    squad_id = Column(Integer, ForeignKey("user_squads.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    is_starter = Column(Integer, default=1)  # 0/1, sqlite has no bool
    is_captain = Column(Integer, default=0)

    squad = relationship("UserSquad", back_populates="players")
