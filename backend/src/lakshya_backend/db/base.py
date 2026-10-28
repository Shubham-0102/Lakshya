from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

# Predictable constraint names (e.g. ck_sources_polite_crawl_delay), so later
# migrations can refer to a constraint by name instead of a name Postgres made up.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every datetime column is timezone-aware, every str column is Postgres text
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        str: Text,
    }


def text_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Store an enum as text plus a CHECK constraint listing the allowed values.

    A native Postgres enum type is hard to change later (values can't be removed);
    a CHECK constraint is changed with an ordinary migration.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [m.value for m in members],
    )
