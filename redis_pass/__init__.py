"""
Simple package used to easily reuse complication connection definitions
"""
from __future__ import annotations

from redis import *

__all__ = [
    "Credential",
    "get_connection",
    "get_connection_by_host",
    "register"
]

import types
import typing
import os
import sqlite3
import pathlib
import dataclasses
import re

T = typing.TypeVar('T')
"""A generic type hint"""

CREDENTIAL_TABLE: typing.Final[str] = "redis_pass"
"""The table that the parameters will be stored in"""

_TYPE_PATTERN: re.Pattern[str] = re.compile(r"(?<=\[)[a-z]+(?=])|^[a-zA-Z]+$")
"""
Basic regular expression that matches on the type in an annotation, 
whether it's 'str' or 'typing.Optional[str]' (both become 'str')
"""


@dataclasses.dataclass
class Credential:
    """
    Redis credentials - most, if not all, of the parameters needed to form a redis connection
    """
    host: str = dataclasses.field(default='localhost')
    port: int = dataclasses.field(default=6379)
    username: typing.Optional[str] = dataclasses.field(default=None)
    password: typing.Optional[str] = dataclasses.field(default=None)
    db: int = dataclasses.field(default=0)
    retry_on_timeout: bool = dataclasses.field(default=False)
    socket_timeout: typing.Optional[float] = dataclasses.field(default=None)
    socket_connect_timeout: typing.Optional[float] = dataclasses.field(default=None)
    socket_keepalive: typing.Optional[bool] = dataclasses.field(default=None)
    decode_responses: bool = dataclasses.field(default=False)
    encoding: str = dataclasses.field(default="utf-8")
    encoding_errors: str = dataclasses.field(default="strict")
    health_check_interval: int = dataclasses.field(default=0)
    client_name: typing.Optional[str] = dataclasses.field(default=None)
    ssl: bool = dataclasses.field(default=False)
    ssl_keyfile: typing.Optional[str] = dataclasses.field(default=None)
    ssl_certfile: typing.Optional[str] = dataclasses.field(default=None)
    ssl_cert_reqs: str = dataclasses.field(default="required")
    ssl_ca_certs: typing.Optional[str] = dataclasses.field(default=None)
    ssl_check_hostname: bool = dataclasses.field(default=False)

    @property
    def specificity(self) -> float:
        """
        A measure of how broad or specific the creditial is. The higher the number, the more specific
        """
        total: int = 0
        amount_changed: int = 0

        for field in dataclasses.fields(self.__class__):
            total += 1
            if getattr(self, field.name) != field.default:
                amount_changed += 1

        if total == 0:
            return 0.0

        return amount_changed / total

    def connect(self, **kwargs) -> Redis:
        """
        Connect to redis with these credentials

        :param kwargs: Overriding parameters used to form the connection.
            See the documentation for forming a redis connection
        :return: Redis connection
        """
        parameters = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self.__class__)
        }

        parameters.update(kwargs)

        return Redis(**parameters)

    @classmethod
    def load(cls) -> typing.Sequence[Credential]:
        """
        Load credentials from the store
        :return:
        """
        database_connection: sqlite3.Connection = get_redis_pass_store()
        cursor: sqlite3.Cursor = database_connection.cursor()
        cursor.execute(f'SELECT * FROM {CREDENTIAL_TABLE}')

        headers: typing.Sequence[str] = list(map(lambda column: column[0], cursor.description))
        raw_credentials: typing.Sequence[typing.Dict[str, typing.Any]] = [
            dict(zip(headers, row))
            for row in cursor.fetchall()
        ]

        database_connection.close()

        fields: typing.Dict[str, typing.Type] = {
            field.name: get_field_type(field=field)
            for field in dataclasses.fields(cls)
        }
        credentials: typing.List[Credential] = []

        for raw_credential in raw_credentials:
            parameters: typing.Dict[str, typing.Any] = {}
            for header, value in raw_credential.items():
                field_type = fields.get(header)
                if not field_type:
                    raise KeyError(f"Cannot load data from the store - '{header}' is not a valid field name")

                parameters[header] = None if value is None else field_type(value)
            credential: Credential = cls(**parameters)
            credentials.append(credential)

        return credentials

    def save(self) -> None:
        """
        Save credentials to disk.
        :return:
        """
        database_connection: sqlite3.Connection = get_redis_pass_store()
        field_names: typing.Sequence[str] = list(map(lambda field: field.name, dataclasses.fields(self.__class__)))
        name_value_pairs: typing.List[typing.Tuple[str, typing.Any]] = [
            (name, getattr(self, name))
            for name in field_names
        ]
        script = f"""INSERT OR REPLACE INTO {CREDENTIAL_TABLE} (
    {(', ' + os.linesep).join(map(lambda pair: pair[0], name_value_pairs))}
) VALUES (
    {(', ' + os.linesep).join('?' * len(field_names))}
);"""
        cursor: sqlite3.Cursor = database_connection.cursor()
        cursor.execute(script, list(map(lambda pair: pair[1], name_value_pairs)))
        database_connection.commit()
        database_connection.close()

    @classmethod
    def from_connection(cls, connection: Redis) -> Credential:
        """
        Forms a credential object from an active redis connection

        :param connection: The connection to get constructor parameters from
        :return: The credential object that matches the given connection
        """
        credential: Credential = Credential(
            **connection.connection_pool.connection_kwargs
        )
        return credential


def get_field_type(field: dataclasses.Field) -> type:
    """
    Gets the actual type of a given field. The 'type' on the field object itself is just its name, not the class

    Only works on basic builtin types, though support for annotated types is supplied.

    Can extract a type from a field whose type is 'typing.Optional[int]' or 'bool'

    :param field: A field from a dataclass
    :return: The type object corresponding to the desired type of value
    """
    field_type_match: re.Match = _TYPE_PATTERN.search(field.type)

    if field_type_match:
        typename: str = field_type_match.group()

        type_container: typing.Union[types.ModuleType, typing.Dict[str, typing.Any]] = globals()["__builtins__"]

        if isinstance(type_container, typing.Mapping) and typename in type_container:
            return type_container[typename]
        elif hasattr(type_container, typename):
            return getattr(globals()["__builtins__"], field_type_match.group())

    raise KeyError(f"Could not find an accompanying type for field '{field}'")


def register(connection: Redis):
    """
    Register a connection for later use

    :param connection: The connection whose information to store
    """
    credential: Credential = Credential.from_connection(connection)
    credential.save()


def get_connection_by_host(host: str, **connection_kwargs) -> Redis:
    """
    Create a connection to a redis instance based on stored credentials

    :param host: The address of the redis instance to connect to
    :param connection_kwargs: Keyword arguments used to form the connection
    :return: A connection to the redis instance
    """
    credentials: typing.Sequence[Credential] = list(
        filter(lambda credential: credential.host == host, Credential.load())
    )

    if not credentials:
        raise KeyError(f"There are no saved connections to '{host}'")

    sorted_credentials: typing.List[Credential] = sorted(credentials, key=lambda credential: credential.specificity)

    connection: Redis = sorted_credentials[0].connect(**connection_kwargs)
    connection.ping()

    return connection


def get_storage_path() -> pathlib.Path:
    """
    Get the path to a user's store
    """
    return pathlib.Path(os.getenv("HOME", f"C:\\Users\\{os.getlogin()}")) / ".redis_pass.db"


def get_redis_pass_store() -> sqlite3.Connection:
    """
    Get a connection to the database containing the stored credentials
    :return:
    """
    database_path: pathlib.Path = get_storage_path()

    connection: sqlite3.Connection = sqlite3.connect(str(database_path))

    # If we're in windows, we need to do a little extra work to keep the file secure
    #   It's a little debatable whether or not to put in the extra effort as this will only remove inherited
    #   security identifiers associated with the system itself and the admin

    creation_script: str = f"""CREATE TABLE IF NOT EXISTS {CREDENTIAL_TABLE} (
    host VARCHAR(255) NOT NULL,
    username VARCHAR(50),
    password VARCHAR(50),
    port INTEGER DEFAULT 6379,
    db INTEGER DEFAULT 0,
    retry_on_timeout INTEGER DEFAULT 0,
    socket_timeout REAL,
    socket_connect_timeout REAL,
    socket_keepalive INTEGER,
    decode_responses INTEGER DEFAULT 0,
    encoding VARCHAR(25) DEFAULT 'utf-8',
    encoding_errors VARCHAR(25) DEFAULT 'strict',
    health_check_interval INTEGER DEFAULT 0,
    client_name VARCHAR(255),
    ssl INTEGER DEFAULT 0,
    ssl_keyfile VARCHAR(255),
    ssl_certfile VARCHAR(255),
    ssl_cert_reqs VARCHAR(255) DEFAULT 'required',
    ssl_ca_certs VARCHAR(255),
    ssl_check_hostname INTEGER DEFAULT 0,
    UNIQUE(host, username, password, port, db, ssl)
);"""

    connection.execute(creation_script)
    connection.commit()

    return connection


def get_connection(**kwargs) -> Redis:
    """
    Get a connection to a redis instance by retrieving credentials from the store

    :param kwargs:
    :return:
    """
    credentials: typing.Sequence[Credential] = Credential.load()

    if not credentials or not kwargs:
        return Redis()

    matching_credentials: typing.List[Credential] = []

    for credential in credentials:
        matching_conditions: typing.List[bool] = [
            getattr(credential, field_name) == value
            for field_name, value in kwargs.items()
        ]

        if all(matching_conditions):
            matching_credentials.append(credential)

    if not matching_credentials:
        raise ConnectionError(
            f"No matching credentials were for found the conditions: {kwargs}"
        )

    sorted_credentials: typing.List[Credential] = sorted(
        matching_credentials,
        key=lambda cred: cred.specificity
    )

    connection: Redis = sorted_credentials[0].connect()
    return connection
