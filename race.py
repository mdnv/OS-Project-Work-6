"""Намеренно сломанный счётчик: воспроизводимое потерянное обновление."""
import logging
from pathlib import Path
from threading import Barrier, Thread

THREADS = 4
ITERATIONS = 1000
counter = 0
step = Barrier(THREADS, timeout=5)


def worker():
    global counter
    for _ in range(ITERATIONS):
        old = counter
        # Все читают одно старое значение прежде, чем кто-либо запишет новое.
        step.wait()
        counter = old + 1
        # Следующая итерация начнётся только после всех записей текущей.
        step.wait()


def main():
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/race.log", filemode="w",
                        level=logging.INFO, encoding="utf-8")
    threads = [Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    expected = THREADS * ITERATIONS
    print(f"Expected: {expected}")
    print(f"Actual:   {counter}")
    print(f"Lost:     {expected - counter}")
    if counter != expected:
        logging.error("INVARIANT FAILED: actual=%s expected=%s", counter, expected)
        print("RACE DETECTED (expected demonstration)")
    else:
        raise RuntimeError("Гонка не проявилась: проверьте исходный файл")


if __name__ == "__main__":
    main()
