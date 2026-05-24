from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI

from synaptic.api.routes import router
from synaptic.config import settings
from synaptic.consensus.engine import ConsensusEngine
from synaptic.mempool.decoder import CalldataDecoder
from synaptic.mempool.listener import MempoolListener
from synaptic.mempool.parser import parse_transaction
from synaptic.signals.base import Signal, SignalResult
from synaptic.signals.heuristics import HeuristicSignal
from synaptic.signals.simulation import SimulationSignal
from synaptic.simulation.fork_pool import ForkPool
from synaptic.simulation.pis import PISComputer
from synaptic.state.redis_cache import RedisStateCache
from synaptic.state.abi_loader import ABILoader

# --- Structured logging ---
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# --- Global app state ---
_app_state: dict[str, Any] = {}


def get_app_state() -> dict[str, Any]:
    """Return the global app state dict for use in route handlers."""
    return _app_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI app."""
    global _app_state

    logger.info("Starting Synaptic Core Engine v0.1.0")

    # --- Redis state cache ---
    cache = RedisStateCache()
    await cache.connect()
    _app_state["cache"] = cache

    # --- ABI decoder + loader ---
    decoder = CalldataDecoder(cache.redis)
    abi_loader = ABILoader(cache.redis, decoder)
    abi_count = await abi_loader.load_local()
    logger.info("Loaded %d local ABIs", abi_count)
    _app_state["decoder"] = decoder
    _app_state["abi_loader"] = abi_loader

    # --- Fork pool ---
    fork_pool = ForkPool(
        pool_size=settings.fork_pool_size,
        fork_url=settings.alchemy_http_url,
        fork_block_lag=settings.fork_block_lag,
    )
    await fork_pool.initialize()
    _app_state["fork_pool"] = fork_pool

    # --- Protocol configs ---
    protocol_configs = {}
    try:
        protocol_configs = json.loads(settings.monitored_protocols)
    except json.JSONDecodeError:
        logger.warning("Could not parse MONITORED_PROTOCOLS, using empty config")

    # --- Signals ---
    pis_computer = PISComputer(fork_pool)
    signals: list[Signal] = [
        HeuristicSignal(state_cache=cache),
        SimulationSignal(pis_computer=pis_computer, protocol_configs=protocol_configs),
    ]
    _app_state["signals"] = signals

    # --- Consensus engine ---
    consensus = ConsensusEngine(total_signals=len(signals))
    _app_state["consensus"] = consensus

    # --- Mempool listener (background task) ---
    listener = MempoolListener()
    _app_state["listener_running"] = True

    async def run_listener():
        try:
            async for tx_raw in listener.stream():
                tx = parse_transaction(tx_raw)
                # Fire all signals
                results = []
                for signal in signals:
                    try:
                        result = await signal.evaluate(tx)
                        results.append(result)
                    except Exception as e:
                        logger.error("Signal %s failed for tx %s: %s", signal.signal_id, tx.hash[:10], e)
                # Consensus
                if results:
                    await consensus.decide(tx.hash, results)
        except Exception as e:
            logger.error("Listener task crashed: %s", e)
            _app_state["listener_running"] = False

    listener_task = asyncio.create_task(run_listener())
    _app_state["listener_task"] = listener_task

    logger.info(
        "Synaptic ready — %d signals, %d fork instances, listener active",
        len(signals),
        settings.fork_pool_size,
    )

    yield

    # --- Shutdown ---
    logger.info("Shutting down Synaptic...")
    _app_state["listener_running"] = False
    await listener.stop()
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    await fork_pool.shutdown()
    await cache.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Synaptic",
    description="Simulation-first DeFi security layer",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
