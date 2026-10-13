"""Кольцевой буфер: два семафора + Lock или одна Condition + Lock."""
import argparse
from collections import Counter
import logging
from pathlib import Path
import random
import threading
import time

CAPACITY = 5
TOTAL = 1000
PRODUCERS = 3
CONSUMERS = 2
STOP = object()
EMPTY = object()
TIMEOUT = 10


def require(condition, message):
    # Не assert: проверки работают и при python3 -O.
    if not condition:
        logging.error("INVARIANT FAILED: %s", message)
        raise RuntimeError(message)


class RingBuffer:
    """Внешний код обязан удерживать общий мьютекс при доступе к буферу."""
    def __init__(self):
        self.data = [EMPTY] * CAPACITY
        self.head = 0
        self.tail = 0
        self.count = 0
        self.max_count = 0

    def check(self):
        require(0 <= self.count <= CAPACITY, "Размер буфера вне 0..5")
        require(0 <= self.head < CAPACITY, "Некорректный head")
        require(0 <= self.tail < CAPACITY, "Некорректный tail")
        require(self.tail == (self.head + self.count) % CAPACITY,
                "Нарушена связь head, tail и count")
        occupied = {(self.head + i) % CAPACITY for i in range(self.count)}
        for index, value in enumerate(self.data):
            require((value is not EMPTY) == (index in occupied),
                    f"Неверное содержимое ячейки {index}")

    def put(self, item):
        self.check()
        require(self.count < CAPACITY, "Переполнение буфера")
        self.data[self.tail] = item
        self.tail = (self.tail + 1) % CAPACITY
        self.count += 1
        self.max_count = max(self.max_count, self.count)
        self.check()

    def get(self):
        self.check()
        require(self.count > 0, "Чтение из пустого буфера")
        item = self.data[self.head]
        self.data[self.head] = EMPTY
        self.head = (self.head + 1) % CAPACITY
        self.count -= 1
        self.check()
        return item


class SemaphoreBuffer:
    def __init__(self):
        self.ring = RingBuffer()
        self.mutex = threading.Lock()
        self.empty = threading.Semaphore(CAPACITY)
        self.full = threading.Semaphore(0)

    def put(self, item):
        require(self.empty.acquire(timeout=TIMEOUT), "Тайм-аут empty.acquire")
        try:
            with self.mutex:
                self.ring.put(item)
        except BaseException:
            self.empty.release()  # Вернуть резерв при ошибке до публикации.
            raise
        self.full.release()

    def get(self):
        require(self.full.acquire(timeout=TIMEOUT), "Тайм-аут full.acquire")
        try:
            with self.mutex:
                item = self.ring.get()
        except BaseException:
            self.full.release()
            raise
        self.empty.release()
        return item


class ConditionBuffer:
    def __init__(self):
        self.ring = RingBuffer()
        self.condition = threading.Condition(threading.Lock())

    def put(self, item):
        deadline = time.monotonic() + TIMEOUT
        with self.condition:
            while self.ring.count == CAPACITY:
                remaining = deadline - time.monotonic()
                require(remaining > 0, "Тайм-аут: буфер полон")
                self.condition.wait(timeout=remaining)
            self.ring.put(item)
            # Одна Condition обслуживает две группы. Будим всех,
            # чтобы не выбрать только поток, чьё условие всё ещё ложно.
            self.condition.notify_all()

    def get(self):
        deadline = time.monotonic() + TIMEOUT
        with self.condition:
            while self.ring.count == 0:
                remaining = deadline - time.monotonic()
                require(remaining > 0, "Тайм-аут: буфер пуст")
                self.condition.wait(timeout=remaining)
            item = self.ring.get()
            self.condition.notify_all()
            return item


def run_once(mode, run_number):
    buffer = SemaphoreBuffer() if mode == "sem" else ConditionBuffer()
    audit = threading.Lock()
    produced = Counter()
    consumed = Counter()
    errors = []
    started = threading.Event()

    def guarded(function, *args):
        try:
            require(started.wait(TIMEOUT), "Тайм-аут старта")
            function(*args)
        except Exception as error:
            logging.exception("WORKER FAILED: %s", threading.current_thread().name)
            with audit:
                errors.append(str(error))

    def producer(number):
        rng = random.Random(100 * run_number + number)
        # Вместе производители создают ровно ID 0..999, без пересечений.
        for item in range(number, TOTAL, PRODUCERS):
            buffer.put(item)
            with audit:
                produced[item] += 1
                require(produced[item] == 1, f"Повторно произведён {item}")
            if item % 11 == 0:
                time.sleep(rng.uniform(0, 0.0005))

    def consumer(number):
        rng = random.Random(1000 + 100 * run_number + number)
        while True:
            item = buffer.get()
            if item is STOP:
                return
            with audit:
                require(type(item) is int and 0 <= item < TOTAL, "Неверный ID")
                consumed[item] += 1
                require(consumed[item] == 1, f"Повторно потреблён {item}")
            # Имитация обработки идёт вне блокировки буфера.
            if item % 7 == 0:
                time.sleep(rng.uniform(0, 0.0005))

    def join_all(threads):
        deadline = time.monotonic() + 30
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        require(not any(t.is_alive() for t in threads), "Потоки зависли")
        with audit:
            require(not errors, f"Ошибки потоков: {errors}")

    producers = [threading.Thread(target=guarded, args=(producer, i),
                 name=f"producer-{i}", daemon=True) for i in range(PRODUCERS)]
    consumers = [threading.Thread(target=guarded, args=(consumer, i),
                 name=f"consumer-{i}", daemon=True) for i in range(CONSUMERS)]
    for thread in consumers + producers:
        thread.start()
    started.set()
    join_all(producers)
    # Служебные маркеры после ВСЕХ данных: один на каждого потребителя.
    for _ in range(CONSUMERS):
        buffer.put(STOP)
    join_all(consumers)

    # Все рабочие потоки завершены: безопасно проверить итоговое состояние.
    expected = Counter(range(TOTAL))
    require(produced == expected, "Потеря/дублирование произведённых ID")
    require(consumed == expected, "Потеря/дублирование потреблённых ID")
    buffer.ring.check()
    require(buffer.ring.count == 0, "Буфер не пуст после завершения")
    require(buffer.ring.max_count <= CAPACITY, "Превышена ёмкость")
    line = (f"PASS mode={mode} run={run_number} produced={sum(produced.values())} "
            f"consumed={sum(consumed.values())} unique={len(consumed)} "
            f"max_buffer={buffer.ring.max_count}/5 final_buffer=0 violations=0")
    print(line)
    logging.info(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sem", "cond"], required=True)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs должен быть положительным")
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=f"logs/pc_{args.mode}.log", filemode="w",
                        level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(threadName)s %(message)s")
    try:
        for number in range(1, args.runs + 1):
            run_once(args.mode, number)
    except Exception:
        logging.exception("RUN FAILED")
        raise


if __name__ == "__main__":
    main()
