from flask import Flask, request, session, redirect
import requests
from datetime import datetime
from threading import Thread, get_ident
import time
import json

from oidcutils import (
    handle_callback,
    init_oidc,
    dpop_from_atoken_for_url,
    prepare_auth_data,
    webid_from_access_token,
)

# URL when deployed to render, change to server
_THIS = "https://rss-post-platform.onrender.com"
# ID provider. Can support many
_ISSUER = "https://solidcommunity.net/"
# the route in this app used for handling idp redirects back
_OID_CALLBACK_PATH = "/oauth/callback"
_CALLBACK_URL = f"{_THIS}{_OID_CALLBACK_PATH}"
_TEST_URL = "https://sergeynepomnyachiy.solidcommunity.net/private/test2.md"
_RSS = "https://devblogs.microsoft.com/oldnewthing/feed"

WORKER_IDLE_SECONDS = 30
worker_state = {"users": {}}
provider_info, client_id = init_oidc(_ISSUER, _CALLBACK_URL)

# keyed by state, contains {'key': {...}, 'code_verifier': ...}
# will hold sessions partially established
# (e.g., one way sent, redirect didn't return)
state_storage = {}


def get_from_session_storage(key):
    global state_storage
    assert key in state_storage, f"key '{key}' not in STATE_STORAGE?"
    return state_storage[key]


def set_session_storage(key, value):
    global state_storage
    state_storage[key] = value


def update_pod_with_rss(podjsn, rss):
    lines = rss.split("\n")
    now = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
    for line in lines:
        if "<title>" in line:
            if line not in podjsn:
                podjsn[line] = now
    return podjsn


def operate_users(users):
    print(f"Backend worker active [{get_ident()}] {datetime.now()}")
    for user, headers in users.items():
        print("User", user)
        resp = requests.get(url=_TEST_URL, headers=headers[0])
        if resp.status_code == 200:
            # read json from POD
            podjsn = resp.json()
            sz = len(podjsn)
            print("Before:", sz)
            # fetch RSS content
            resp = requests.get(url=_RSS)
            if resp.status_code == 200:
                newdata = update_pod_with_rss(podjsn, resp.text)
                if len(newdata) != sz:
                    print("After:", len(newdata))
                    resp = requests.put(
                        url=_TEST_URL, data=json.dumps(newdata), headers=headers[1]
                    )
                    print(resp.status_code)
            else:
                print("Could not read RSS")
        else:
            print("failed read:", resp.status_code)


def worker():
    global worker_state
    i = 0
    while True:
        i += 1

        worker_state["worker"] = i
        worker_state["latest"] = datetime.now()

        operate_users(worker_state["users"])
        time.sleep(WORKER_IDLE_SECONDS)


worker_thread = None

app = Flask(__name__)
app.secret_key = "2612ea_678df63cda52e_fdff4e424e45_3"


@app.route("/health")
def health():
    return "OK"


@app.route("/login")
def login():
    # we are fully logged in and have an access token
    if "access_token" in session:
        msg = f"Logged in successfully as {webid_from_access_token(session['access_token'])}"
        print(msg)
        get_cookies_to_worker(session["key"], session["access_token"])
        return msg

    global client_id
    key, value, query = prepare_auth_data(request.url, client_id, _CALLBACK_URL)
    set_session_storage(
        key, value
    )  # we need this partial session for when they come back

    # send them to go to their id provider (e.g. solidcommunity)
    url = provider_info["authorization_endpoint"] + "?" + query
    print("Ask browser to authorize via", url)
    return redirect(url)


def get_cookies_to_worker(key, atoken):
    global worker_state
    hget, web_id = dpop_from_atoken_for_url(key, atoken, _TEST_URL, method="GET")
    hpost, _ = dpop_from_atoken_for_url(key, atoken, _TEST_URL, method="PUT")
    hpost["Content-Type"] = "application/json; charset=utf-8"
    worker_state["users"][web_id] = (hget, hpost)


@app.route(_OID_CALLBACK_PATH)
def oid_callback():
    global provider_info
    global client_id

    # fetch stored state for this session needed to complete the handshake
    auth_code = request.args["code"]
    state = request.args["state"]
    value = get_from_session_storage(state)

    result, keypair = handle_callback(
        value, provider_info, client_id, auth_code, _CALLBACK_URL
    )

    # if all went well, we have obtained a DPoP token
    # set those as cookies
    key, atoken = keypair.export(), result["access_token"]
    session["key"] = key
    session["access_token"] = atoken
    get_cookies_to_worker(key, atoken)
    return redirect(value.pop("redirect_url"))


@app.route("/")
def index():
    global worker_thread
    if worker_thread is None:
        worker_thread = Thread(target=worker)
        worker_thread.start()

    msg = ""
    if "worker" in worker_state:
        msg = f"{datetime.now()}: Worker cycles: {worker_state['worker']} latest: {worker_state['latest']} worker alive: {worker_thread.is_alive()}"
    print(msg)
    return msg
