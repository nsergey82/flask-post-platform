from flask import Flask

from datetime import datetime
from threading import Thread
from threading import Lock

import time

WORKER_IDLE_SECONDS = 600

def worker():
    i = 0
    while True:
        i += 1
        print(f"worker active [{i}] {datetime.now()}")
        time.sleep(WORKER_IDLE_SECONDS)


w = Thread(target=worker, daemon=True)
w.start()

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "Hello, World!"
