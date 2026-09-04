"""Schema versioning for Reader3 book storage."""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1


def migrate_book_data(data: dict) -> dict:
    """Upgrade book data from any older schema version to the current one.
    
    Each migration step transforms the data dict in place from version N to N+1.
    New migration steps should be added as elif clauses.
    """
    version = data.get("_schema_version", 0)
    
    if version >= CURRENT_SCHEMA_VERSION:
        return data
    
    # Migration from version 0 (pickle-era, no version field) to version 1
    if version < 1:
        data["_schema_version"] = 1
        # No structural changes needed for v0 -> v1;
        # this just marks the data as having been through the JSON pipeline
    
    return data
