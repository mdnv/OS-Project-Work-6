"""Контролируемое чередование: 2 потребителя, 1 элемент, notify_all."""
import argparse
import logging
from pathlib import Path
import threading

from pc_fixed import RingBuffer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["if", "while"], required=True)
    args = parser.parse_args()
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=f"logs/condition_{args.mode}.log", filemode="w",
                        level=logging.INFO, encoding="utf-8")
    ring = RingBuffer()
    cv = threading.Condition(threading.Lock())
    ready = [threading.Event(), threading.Event()]
    consumed_one = threading.Event()
    closed = False
    consumed = []
    violations = []
    unexpected = []

    def consumer(number):
        try:
            with cv:
                ready[number].set()
                if args.mode == "if":
                    if ring.count == 0:
                        if not cv.wait(timeout=5):
                            raise TimeoutError("Нет уведомления")
                else:
                    while ring.count == 0 and not closed:
                        if not cv.wait(timeout=5):
                            raise TimeoutError("Нет уведомления")
                    if ring.count == 0 and closed:
                        return
                # В if-режиме второй потребитель приходит сюда при count=0.
                if ring.count == 0:
                    message = "Чтение из пустого буфера после wait"
                    violations.append(message)
                    logging.error("INVARIANT FAILED: %s", message)
                    return
                consumed.append(ring.get())
                consumed_one.set()
        except Exception as error:
            with cv:
                unexpected.append(str(error))
                logging.exception("UNEXPECTED FAILURE")

    threads = [threading.Thread(target=consumer, args=(i,), daemon=True)
               for i in range(2)]
    for thread in threads:
        thread.start()
    for event in ready:
        if not event.wait(5):
            raise RuntimeError("Потребитель не запустился")
    # Событие ready выставлено под cv. Захватить cv главный поток сможет
    # только после того, как последний потребитель перейдёт в wait.
    with cv:
        ring.put(42)
        cv.notify_all()
    if not consumed_one.wait(5):
        raise RuntimeError("Элемент не потреблён")
    if args.mode == "while":
        # Завершение второго потребителя после повторной проверки условия.
        with cv:
            closed = True
            cv.notify_all()
    for thread in threads:
        thread.join(5)
    if any(t.is_alive() for t in threads) or unexpected:
        raise RuntimeError(f"Неожиданный сбой: {unexpected}")
    expected_errors = 1 if args.mode == "if" else 0
    if consumed != [42] or len(violations) != expected_errors:
        raise RuntimeError("Демонстрация не воспроизвела ожидаемый результат")
    print(f"mode={args.mode} consumed=1 violations={len(violations)}")
    print("EXPECTED BUG: empty buffer after wait" if args.mode == "if"
          else "PASS: condition checked again")
    logging.info("mode=%s consumed=1 violations=%s", args.mode, len(violations))


if __name__ == "__main__":
    main()
