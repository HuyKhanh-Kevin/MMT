
import json
import re
import inspect

from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints, Union
from types import UnionType

from common import ProtocolConstants


def to_snake_case(name: str) -> str:
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def reject_duplicates(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value

    return result


def reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def to_json_value(value):
    """Convert Python objects to JSON-compatible values."""

    if is_dataclass(value) and not isinstance(value, type):
        attributes = {
            f.name: getattr(value, f.name)
            for f in fields(value)
        }

    elif isinstance(value, dict):
        # Dictionary keys are preserved.
        return {
            k: to_json_value(v)
            for k, v in value.items()
        }

    elif isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]

    elif hasattr(value, "__dict__"):
        attributes = vars(value)

    else:
        return value

    result = {}

    for name, item in attributes.items():
        key = to_snake_case(name)

        if key in result:
            raise ValueError(f"Duplicate field: {key}")

        result[key] = to_json_value(item)

    return result


def validate_type(value, expected, allow_null=False):
    """Validate types without implicit scalar conversion."""

    if value is None:
        if allow_null:
            return None
        raise ValueError("Null creator property is not allowed")

    if expected in (Any, inspect.Parameter.empty):
        return value

    origin = get_origin(expected)
    args = get_args(expected)

    if origin in (Union, UnionType):
        for option in args:
            if option is type(None):
                continue
            try:
                return validate_type(value, option, allow_null)
            except (TypeError, ValueError):
                continue
        raise TypeError(f"Invalid value for {expected}")

    if origin is list:
        if not isinstance(value, list):
            raise TypeError("Expected list")
        return [
            validate_type(item, args[0])
            for item in value
        ] if args else value

    if origin is dict:
        if not isinstance(value, dict):
            raise TypeError("Expected dict")
        if len(args) == 2:
            return {
                validate_type(k, args[0]):
                validate_type(v, args[1])
                for k, v in value.items()
            }
        return value

    if expected in (str, int, float, bool):
        if type(value) is not expected:
            raise TypeError(
                f"Expected {expected.__name__}, "
                f"got {type(value).__name__}"
            )
        return value

    if expected is dict:
        if not isinstance(value, dict):
            raise TypeError("Expected dict")
        return value

    if expected is list:
        if not isinstance(value, list):
            raise TypeError("Expected list")
        return value

    if isinstance(expected, type):
        if not isinstance(value, dict):
            raise TypeError(
                f"Expected JSON object for {expected.__name__}"
            )
        return construct_object(value, expected)

    return value


def construct_object(data, target_type, allow_null=False):
    """Construct DTO and reject missing/unknown fields."""

    if target_type is dict:
        return data

    if is_dataclass(target_type):
        hints = get_type_hints(target_type)
        schema = {
            f.name: hints.get(f.name, Any)
            for f in fields(target_type)
            if f.init
        }
    else:
        signature = inspect.signature(target_type)
        hints = get_type_hints(target_type.__init__)

        schema = {
            name: hints.get(name, Any)
            for name, param in signature.parameters.items()
            if param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY
            )
        }

    mapped = {
        to_snake_case(name): (name, expected)
        for name, expected in schema.items()
    }

    if len(mapped) != len(schema):
        raise ValueError("Duplicate mapped property names")

    unknown = set(data) - set(mapped)
    missing = set(mapped) - set(data)

    if unknown:
        raise ValueError(f"Unknown properties: {sorted(unknown)}")

    if missing:
        raise ValueError(f"Missing properties: {sorted(missing)}")

    kwargs = {}

    for json_name, (python_name, expected) in mapped.items():
        kwargs[python_name] = validate_type(
            data[json_name],
            expected,
            allow_null=allow_null
        )

    return target_type(**kwargs)


class JsonPayloadCodec:

    @staticmethod
    def checkSize(payload: bytes) -> None:
        if (
            len(payload) == 0
            or len(payload) >
            ProtocolConstants.MAX_JSON_PAYLOAD_SIZE
        ):
            raise ValueError("Invalid JSON payload size")

    @staticmethod
    def encode(value: object) -> bytes:
        if value is None:
            raise ValueError("Payload must not be null")

        data = to_json_value(value)

        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")

        payload = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False
        ).encode("utf-8")

        JsonPayloadCodec.checkSize(payload)
        return payload

    @staticmethod
    def decode(payload: bytes, target_type: type):
        if payload is None or target_type is None:
            raise ValueError(
                "Payload and target type must not be null"
            )

        if not isinstance(payload, bytes):
            raise TypeError("Payload must be bytes")

        JsonPayloadCodec.checkSize(payload)

        # Reject malformed UTF-8
        text = payload.decode("utf-8", errors="strict")

        # Reject duplicates, trailing tokens and NaN/Infinity
        data = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant
        )

        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")

        # Preserve the Java LoginResponse special case.
        # For stricter identity matching, compare with the
        # actual imported LoginResponse class.
        allow_null = target_type.__name__ == "LoginResponse"

        return construct_object(
            data, target_type, allow_null=allow_null
        )
