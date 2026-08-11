from __future__ import annotations

import asyncio
import logging

from app.core.virtual_try_on import build_virtual_try_on_service


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def main() -> None:
    service = build_virtual_try_on_service()
    if not service.configured:
        raise RuntimeError("VTO provider and result signing secret must be configured")
    await service.worker_loop()


if __name__ == "__main__":
    asyncio.run(main())
