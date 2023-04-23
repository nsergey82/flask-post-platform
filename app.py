from flask import Flask

from datetime import datetime
from threading import Thread

import time

WORKER_IDLE_SECONDS = 30
state = {}


def worker():
    i = 0
    while True:
        i += 1
        now = datetime.now()
        state["worker"] = i
        state["latest"] = now
        print(f"Backend worker active [{i}] {now}")
        time.sleep(WORKER_IDLE_SECONDS)


w = Thread(target=worker, daemon=True)
w.start()

app = Flask(__name__)


@app.route("/")
def hello_world():
    msg = f"{datetime.now()}: Worker cycles: {state['worker']} latest: {state['latest']}"
    print(msg)
    return msg
