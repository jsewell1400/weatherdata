"""
Entry point for the weather fetcher application.

Usage:
    python -m weatherfetcher
"""

import asyncio
import signal
import sys
import structlog

from .config import settings
from .fetcher import run_fetcher


def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if sys.stdout.isatty() else structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    """Main entry point."""
    configure_logging()
    
    logger = structlog.get_logger(__name__)
    
    logger.info(
        "Weather Fetcher starting",
        mongo_host=settings.mongo_host,
        mongo_database=settings.mongo_database,
        observation_interval=settings.observation_interval_seconds,
        station_refresh_interval=settings.station_refresh_interval_seconds,
    )
    
    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Set up signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop, logger)))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        loop.run_until_complete(run_fetcher())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.close()
        logger.info("Weather Fetcher stopped")


async def shutdown(loop: asyncio.AbstractEventLoop, logger) -> None:
    """Graceful shutdown handler."""
    logger.info("Shutdown signal received, stopping...")
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


if __name__ == "__main__":
    main()
