"""Apollo configuration client stub.

Provides a no-op implementation of Apollo config management.
In production, Apollo overrides are applied during app startup.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def load_apollo_overrides() -> None:
    """Load configuration overrides from Apollo config center.

    No-op stub — replace with real implementation when Apollo is available.
    """
    logger.debug("Apollo config overrides: no-op stub (apollo not configured)")
