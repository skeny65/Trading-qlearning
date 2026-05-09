"""
strategy_registry.py - Registro central de todos los StrategyWorkers.

Uso:
    from core.strategy_registry import StrategyRegistry
    StrategyRegistry.initialize_all()
    worker = StrategyRegistry.get("apuesta")
    decision = worker.decide(body)
"""
import logging
from typing import Optional
from core.strategy_worker import StrategyWorker

logger = logging.getLogger("bot3.registry")


class StrategyRegistry:
    """Singleton registry of StrategyWorker instances."""

    _workers: dict = {}

    @classmethod
    def register(cls, worker: StrategyWorker):
        cls._workers[worker.strategy_id] = worker
        logger.info(f"Strategy registered: {worker.strategy_id}")

    @classmethod
    def get(cls, strategy_id: str) -> Optional[StrategyWorker]:
        return cls._workers.get(strategy_id)

    @classmethod
    def list_all(cls) -> list:
        return list(cls._workers.keys())

    @classmethod
    def initialize_all(cls):
        """Instantiate and register all available strategies."""
        from strategies.apuesta.worker  import ApuestaWorker
        from strategies.qlearning.worker import QLearningWorker
        from strategies.tanque.worker   import TanqueWorker

        for WorkerClass in [ApuestaWorker, QLearningWorker, TanqueWorker]:
            try:
                worker = WorkerClass()
                cls.register(worker)
            except Exception as e:
                logger.error(f"Failed to initialize {WorkerClass}: {e}")
