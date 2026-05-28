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
        from strategies.apuesta.worker   import ApuestaWorker
        from strategies.qlearning.worker import QLearningWorker
        from strategies.tanque.worker    import TanqueWorker
        from strategies.e4.worker        import Strategy4Worker
        from strategies.e5.worker        import Strategy5Worker
        from strategies.e6.worker        import Strategy6Worker
        from strategies.e7.worker        import Strategy7Worker
        from strategies.e8.worker        import Strategy8Worker
        from strategies.e9.worker        import Strategy9Worker
        from strategies.e10.worker       import Strategy10Worker

        for WorkerClass in [
            ApuestaWorker, QLearningWorker, TanqueWorker,
            Strategy4Worker, Strategy5Worker, Strategy6Worker,
            Strategy7Worker, Strategy8Worker, Strategy9Worker, Strategy10Worker,
        ]:
            try:
                worker = WorkerClass()
                cls.register(worker)
            except Exception as e:
                logger.error(f"Failed to initialize {WorkerClass}: {e}")
