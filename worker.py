import time
from app.database import SessionLocal
from app.models import Signal
from app.market import calculate_signal
from app.config import SYMBOLS, UPDATE_INTERVAL


def update_loop():
    while True:
        db = SessionLocal()

        for symbol in SYMBOLS:
            result = calculate_signal(symbol)
            if result:
                db.add(Signal(**result))
                db.commit()

        db.close()
        time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    update_loop()