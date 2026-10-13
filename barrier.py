"""Повторно используемый барьер для 4 потоков на Lock + Condition."""
import logging
from pathlib import Path
import threading
import time

PARTIES = 4
PHASES = 3


class ReusableBarrier:
    def __init__(self, parties):
        if parties < 1:
            raise ValueError("parties должен быть положительным")
        self.parties = parties
        self.arrived = 0
        self.generation = 0
        self.broken = False
        self.condition = threading.Condition(threading.Lock())

    def wait(self, timeout=10):
        with self.condition:
            if self.broken:
                raise RuntimeError("Барьер сломан")
            generation = self.generation
            self.arrived += 1
            if self.arrived == self.parties:
                self.arrived = 0
                self.generation += 1
                self.condition.notify_all()
                return
            deadline = time.monotonic() + timeout
            while self.generation == generation and not self.broken:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.broken = True
                    self.condition.notify_all()
                    raise RuntimeError("Тайм-аут барьера")
                self.condition.wait(remaining)
            if self.broken:
                raise RuntimeError("Барьер сломан")


def main():
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/barrier.log", filemode="w",
                        level=logging.INFO, encoding="utf-8")
    barrier = ReusableBarrier(PARTIES)
    audit = threading.Lock()
    completed = [set() for _ in range(PHASES)]
    errors = []

    def worker(number):
        try:
            for phase in range(PHASES):
                # До работы новой фазы все должны закончить предыдущую.
                with audit:
                    if phase and len(completed[phase - 1]) != PARTIES:
                        raise RuntimeError("Следующая фаза началась слишком рано")
                time.sleep(0.005 * (PARTIES - number))
                with audit:
                    completed[phase].add(number)
                    print(f"T{number + 1}: phase {phase + 1} done", flush=True)
                barrier.wait()
                with audit:
                    if len(completed[phase]) != PARTIES:
                        raise RuntimeError("Барьер пропустил поток слишком рано")
        except Exception as error:
            logging.exception("THREAD FAILED")
            with audit:
                errors.append(str(error))

    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(PARTIES)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 30
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    if any(t.is_alive() for t in threads) or errors:
        logging.error("INVARIANT FAILED: threads/errors=%s", errors)
        raise RuntimeError("Барьер не прошёл проверку")
    if any(group != set(range(PARTIES)) for group in completed):
        logging.error("INVARIANT FAILED: incomplete phases")
        raise RuntimeError("Фазы завершены не всеми потоками")
    if barrier.generation != PHASES or barrier.arrived != 0:
        logging.error("INVARIANT FAILED: barrier state")
        raise RuntimeError("Неверное итоговое состояние барьера")
    print("PASS: 4 threads, 3 phases, violations=0")
    logging.info("PASS: 4 threads, 3 phases, violations=0")


if __name__ == "__main__":
    main()
