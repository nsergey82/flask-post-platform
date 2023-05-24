from flask import Flask, request, session, redirect, Response, render_template_string
from datetime import datetime
from threading import Thread
from socket import gethostname
from worker import worker, get_worker_state, add_user, get_user_data
import time
import requests

from oidcutils import (
    handle_callback,
    init_oidc,
    dpop_from_atoken_for_url,
    prepare_auth_data,
    webid_from_access_token,
    webid_to_resource,
    set_session_storage,
    get_from_session_storage,
    OID_CALLBACK_PATH,
)

_IS_TEST = gethostname() == "DESKTOP-9PMKQUR"
_WORKER_IDLE_SECONDS = 10 if _IS_TEST else 60 * 20
_STARTER_SECONDS = 1 if _IS_TEST else 10

# URL when deployed to render, change to server
_THIS = (
    "http://127.0.0.1:8000" if _IS_TEST else "https://rss-post-platform.onrender.com"
)
# ID provider. Can support many
_ISSUER = "https://solidcommunity.net/"

# the route in this app used for handling idp redirects back
_CALLBACK_URL = f"{_THIS}{OID_CALLBACK_PATH}"

_TEMPLATE = """
<h2>RSS feeds for {{ web_id }}</h2>
{%for title in data%}
    <li>{{ data[title][1] }} &nbsp; <a href="{{ data[title][0] }}">{{ title }}</a></li>
{%endfor%}
"""


def start_worker_thread(cache, arguments=(_WORKER_IDLE_SECONDS,)):
    worker_thread = cache["worker"]
    if worker_thread is None:
        worker_thread = Thread(target=worker, args=arguments)
        worker_thread.start()
        cache["worker"] = worker_thread

    msg = "starting..."
    worker_state = get_worker_state()
    if "worker" in worker_state:
        msg = f"{datetime.now()}: Worker cycles: {worker_state['worker']} latest: {worker_state['latest']} worker alive: {worker_thread.is_alive()}"
    print(msg)
    return msg


def get_cookies_to_worker(key, atoken):
    web_id = webid_from_access_token(atoken)
    url = webid_to_resource(web_id)
    hget = dpop_from_atoken_for_url(key, atoken, url, method="GET")
    hpost = dpop_from_atoken_for_url(key, atoken, url, method="PUT")
    hpost["Content-Type"] = "application/json; charset=utf-8"
    add_user(web_id, (hget, hpost))


def create_app():
    app = Flask(__name__)
    app.secret_key = "2612ea_678df63cda52e_fdff4e424e45_3"

    app.cache = {}
    app.cache["oidc"] = init_oidc(_ISSUER, _CALLBACK_URL)
    app.cache["worker"] = None

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
            return redirect("/")

        provider_info = app.cache["oidc"][0]
        client_id = app.cache["oidc"][1]
        key, value, query = prepare_auth_data(request.url, client_id, _CALLBACK_URL)
        set_session_storage(
            key, value
        )  # we need this partial session for when they come back

        # send them to go to their id provider (e.g. solidcommunity)
        url = provider_info["authorization_endpoint"] + "?" + query
        print("Ask browser to authorize via", url)
        return redirect(url)

    @app.route(OID_CALLBACK_PATH)
    def oid_callback():
        provider_info = app.cache["oidc"][0]
        client_id = app.cache["oidc"][1]

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

    @app.route("/admin/start")
    def start():
        return start_worker_thread(app.cache)

    @app.route("/")
    def index():
        web_id = webid_from_access_token(session.get("access_token", None))
        if web_id is not None:
            data = get_user_data(web_id)
            if data is not None:
                data.pop("RSS_FEEDS_SUBSCRIBED_TO")
                return Response(
                    render_template_string(_TEMPLATE, web_id=web_id, data=data),
                    mimetype="text/html",
                )
        return redirect("login")

    def starter():
        time.sleep(_STARTER_SECONDS)
        url = _THIS + "/admin/start"
        print("Calling", url)
        requests.get(url)

    Thread(target=starter).start()

    return app
