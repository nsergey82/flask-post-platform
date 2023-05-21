from datetime import datetime
from threading import get_ident
import time
import json
from collections import namedtuple

from oidcutils import webid_to_resource
from rsslogic import rss_iteration

import requests

worker_state = {"users": {}}
_DB = "https://solidtokens.nsergey82.repl.co/"

User = namedtuple("User", ["web_id", "headers", "fetcher", "putter"])


def fetch_from_db():
    data = requests.get(_DB).json()
    print(data)
    for k, v in data.items():
        add_user(k, json.loads(v), False)


def update_db(webid: str, headers: str):
    requests.post(_DB + "update", data={"webid": webid, "token": json.dumps(headers)})
    print("db updated")


def add_user(web_id, headers, shall_update_db=True):
    if web_id in worker_state["users"]:
        print(web_id, "already in users. Ignoring")
        return

    def fetcher():
        url = webid_to_resource(web_id)
        resp = requests.get(url=url, headers=headers[0])
        if resp.status_code == requests.codes.ok:
            return resp.json()
        print(f"{resp.status_code} while fetching {url}")
        return {}

    def putter(newdata):
        url = webid_to_resource(web_id)
        resp = requests.put(
            url=url,
            data=json.dumps(newdata),
            headers=headers[1],
        )
        if resp.status_code != requests.codes.created:
            print(f"{resp.status_code} while putting {url}")

    worker_state["users"][web_id] = User(web_id, headers, fetcher, putter)
    if shall_update_db:
        update_db(web_id, headers)


def _operate_users(users):
    print(f"Backend worker active [{get_ident()}] {datetime.now()}")
    print(len(users), "user tokens present")
    for user in users.values():
        print("Updating for User", user.web_id)
        rss_iteration(user.fetcher, user.putter)


def get_user_data(web_id):
    if web_id in worker_state["users"]:
        return worker_state["users"][web_id].fetcher()
    return None


def get_worker_state():
    return worker_state


def worker(idle_seconds):
    print("Starting worker with sleep of", idle_seconds)
    i = 0

    fetch_from_db()
    while True:
        i += 1

        worker_state["worker"] = i
        worker_state["latest"] = datetime.now()

        _operate_users(worker_state["users"])
        time.sleep(idle_seconds)
