"""
Neo4j schema migrations: constraints and indexes for synaptic graph memory.

Ensures:
- Uniqueness constraint on Concept(id, tenant) to prevent duplicate nodes
  under concurrent MERGE operations.
- Indexes on Concept(tenant) and Concept(label) to avoid full scans as graph memory grows.
All statements are idempotent via IF NOT EXISTS.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NEO4J_MIGRATIONS: list[str] = [
    # Composite uniqueness constraint: Concept(id, tenant)
    "CREATE CONSTRAINT concept_id_tenant_unique IF NOT EXISTS FOR (c:Concept) REQUIRE (c.id, c.tenant) IS UNIQUE",
    # Tenant index for multi-tenant query isolation and fast lookups
    "CREATE INDEX concept_tenant_idx IF NOT EXISTS FOR (c:Concept) ON (c.tenant)",
    # Label index for label-based concept discovery
    "CREATE INDEX concept_label_idx IF NOT EXISTS FOR (c:Concept) ON (c.label)",
]


def get_neo4j_migrations() -> list[str]:
    """Return the ordered list of Cypher schema migration statements."""
    return list(NEO4J_MIGRATIONS)


async def apply_neo4j_migrations(driver: Any, database: str = "nexus") -> list[str]:
    """Execute idempotent schema migrations on the Neo4j database.

    Args:
        driver: An async Neo4j driver (or test driver mock).
        database: Target database name (default: "nexus").

    Returns:
        List of Cypher statements executed.
    """
    applied: list[str] = []
    statements = get_neo4j_migrations()

    async with driver.session(database=database) as session:
        for stmt in statements:
            logger.info("Applying Neo4j migration: %s", stmt)
            await session.run(stmt)
            applied.append(stmt)

    logger.info("Successfully applied %d Neo4j schema migrations", len(applied))
    return applied
