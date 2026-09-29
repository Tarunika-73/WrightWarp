"""The one consistent ObjectId <-> string conversion point.

Rule used everywhere in this codebase: MongoDB's ``_id`` is a real
``ObjectId`` inside the database and inside repository internals: every
other layer (API responses, Pydantic schemas/documents, cross-document
references such as ``flight_quotes.search_run_id``) uses the plain
string form. Repositories are the only code that calls
``to_object_id``/``to_str_id``.
"""
from bson import ObjectId
from bson.errors import InvalidId


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"Not a valid ObjectId: {value!r}") from exc


def to_str_id(value: ObjectId | str) -> str:
    return str(value)
