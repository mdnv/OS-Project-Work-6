"""Настоящее потерянное уведомление: разрыв между проверкой и wait."""
import argparse
import logging
from pathlib import Path
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed", action="store_true")
    args = parser.parse_args()
    Path("logs").mkdir(exist_ok=True)
    suffix = "fixed" if args.fixed else "bug"
    logging.basicConfig(filename=f"logs/lost_wakeup_{suffix}.log", filemode="w",
                        level=logging.INFO, encoding="utf-8")
    cv = threading.Condition(threading.Lock())
    checked = threading.Event()
    notified = threading.Event()
    state = {"ready": False}
    results = []

    def consumer():
        with cv:
            if state["ready"]:
                return
        # ОШИБКА: отпустили cv между проверкой и постановкой на ожидание.
        checked.set()
        if not notified.wait(5):
            return
        with cv:
            if args.fixed:
                # Проверка и ожидание вновь объединены одним мьютексом.
                while not state["ready"]:
                    if not cv.wait(timeout=1):
                        return
                results.append("PASS: predicate true, no wait needed")
            else:
                awakened = cv.wait(timeout=0.3)
                if not awakened and state["ready"]:
                    logging.error("LOST WAKEUP: notify happened before wait")
                    results.append("EXPECTED BUG: ready=True, wait timed out")

    thread = threading.Thread(target=consumer, daemon=True)
    thread.start()
    if not checked.wait(5):
        raise RuntimeError("Потребитель не проверил условие")
    with cv:
        state["ready"] = True
        cv.notify()  # Потребитель ещё НЕ ждёт: уведомление не запоминается.
    notified.set()
    thread.join(5)
    if thread.is_alive() or len(results) != 1:
        raise RuntimeError("Демонстрация не завершилась ожидаемым результатом")
    print(results[0])
    logging.info(results[0])


if __name__ == "__main__":
    main()
