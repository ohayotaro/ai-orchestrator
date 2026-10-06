"""Cached schema compilation for public conformance over the existing suite."""
from functools import lru_cache
from jsonschema import Draft202012Validator
from ai_orchestrator.public_contracts import output_schemas, surface

@lru_cache(maxsize=1)
def validators():
    return {name:Draft202012Validator(schema) for name,schema in output_schemas().items()}

@lru_cache(maxsize=1)
def declared():
    return surface()
