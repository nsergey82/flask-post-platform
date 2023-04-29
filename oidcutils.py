import requests

import jwcrypto
import jwcrypto.jwk
import jwcrypto.jws
import jwcrypto.jwt

from oic.oic import Client as OicClient
from oic.utils.authn.client import CLIENT_AUTHN_METHOD

import base64
import datetime
import json
import hashlib
import uuid
from urllib.parse import urlencode

OID_CALLBACK_PATH = "/oauth/callback"

# keyed by state, contains {'key': {...}, 'code_verifier': ...}
# will hold sessions partially established
# (e.g., one way sent, redirect didn't return)
state_storage = {}


def get_from_session_storage(key):
    assert key in state_storage, f"key '{key}' not in STATE_STORAGE?"
    return state_storage[key]


def set_session_storage(key, value):
    state_storage[key] = value


def webid_from_access_token(access_token):
    if access_token is None:
        return None
    decoded_access_token = jwcrypto.jwt.JWT(jwt=access_token)
    return json.loads(decoded_access_token.token.objects["payload"])["sub"]


def dpop_from_atoken_for_url(key, access_token, url, method="GET"):
    keypair = jwcrypto.jwk.JWK.from_json(key)

    # We need to convert the access_token to DPoP to attach to our requsts.
    # This is per URI and method!
    headers = {
        "Authorization": ("DPoP " + access_token),
        "DPoP": _make_token_for(keypair, url, method),
    }
    return headers


def prepare_auth_data(redirect_url, client_id, callback_url):
    # create the data relevant to this session
    # that shall be used when we come back from auth round trip
    code_verifier, code_challenge = _make_verifier_challenge()
    key = _make_random_string()
    value = {"code_verifier": code_verifier, "redirect_url": redirect_url}

    # now make the browser go to auth page and direct it to come back here (to cb route)
    query = urlencode(
        {
            "code_challenge": code_challenge,
            "state": key,
            "response_type": "code",
            "redirect_uri": callback_url,
            "code_challenge_method": "S256",
            "client_id": client_id,
            # offline_access: also asks for refresh token
            "scope": "openid offline_access",
        }
    )
    return key, value, query


def handle_callback(value, provider_info, client_id, auth_code, callback_url):
    # Generate a key-pair.
    keypair = jwcrypto.jwk.JWK.generate(kty="EC", crv="P-256")
    code_verifier = value.pop("code_verifier")

    # Exchange auth code for access token
    resp = requests.post(
        url=provider_info["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": callback_url,
            "code": auth_code,
            "code_verifier": code_verifier,
        },
        headers={
            "DPoP": _make_token_for(keypair, provider_info["token_endpoint"], "POST")
        },
        allow_redirects=False,
    )
    return resp.json(), keypair


def init_oidc(issuer, callback_url):
    # https://pyoidc.readthedocs.io/en/latest/examples/rp.html#provider-info-discovery
    provider_info = requests.get(issuer + ".well-known/openid-configuration").json()
    client_id = _register_client(provider_info, callback_url)
    print("oic client-id:", client_id)
    return provider_info, client_id


def _make_random_string():
    return str(uuid.uuid4())


def _make_verifier_challenge():
    code_verifier = _make_random_string()
    code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode("utf-8")
    code_challenge = code_challenge.replace("=", "")
    return code_verifier, code_challenge


def _register_client(provider_info, redirect):
    # https://pyoidc.readthedocs.io/en/latest/examples/rp.html#client-registration
    registration_response = OicClient(client_authn_method=CLIENT_AUTHN_METHOD).register(
        provider_info["registration_endpoint"], redirect_uris=[redirect]
    )
    return registration_response["client_id"]


def _make_token_for(keypair, uri, method):
    jwt = jwcrypto.jwt.JWT(
        header={
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": keypair.export(private_key=False, as_dict=True),
        },
        claims={
            "jti": _make_random_string(),
            "htm": method,
            "htu": uri,
            "iat": int(datetime.datetime.now().timestamp()),
        },
    )
    jwt.make_signed_token(keypair)
    return jwt.serialize()


def webid_to_resource(webid: str) -> str:
    return webid.replace("profile/card#me", "private/rssdata.json")
