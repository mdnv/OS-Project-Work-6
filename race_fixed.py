"""Тот же счётчик, но read-modify-write защищён одним мьютексом."""
import logging
import time
from pathlib import Path
from threading import Lock, Thread

THREADS = 4
ITERATIONS = 1000
counter = 0
mutex = Lock()


def worker():
    global counter
    for _ in range(ITERATIONS):
        with mutex:
            old = counter
            counter = old + 1
        # Переключение потока вне критической секции.
        time.sleep(0)


def main():
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/race_fixed.log", filemode="w",
                        level=logging.INFO, encoding="utf-8")
    threads = [Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    expected = THREADS * ITERATIONS
    print(f"Expected: {expected}")
    print(f"Actual:   {counter}")
    if counter != expected:
        logging.error("INVARIANT FAILED: actual=%s expected=%s", counter, expected)
        raise RuntimeError("Нарушен инвариант счётчика")
    logging.info("PASS: counter=%s", counter)
    print("PASS: counter invariant")


if __name__ == "__main__":
    main()
