"""Application mobile : serveur local (accès par clé, données, lecture seule)."""
import json
import socket
import urllib.error
import urllib.request

import pytest

from pirate_tracker.companion.server import CompanionServer, build_summary, new_token
from pirate_tracker.config import Config
from pirate_tracker.database import Database
from pirate_tracker.tracker import Tracker
from tests.test_storage_and_tracker import fake_result


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def tracker(tmp_path):
    db = Database(tmp_path / "c.db")
    tr = Tracker(db, Config(tmp_path / "s.json"))
    r = fake_result("a.replay", chests=4, items=["WID_Assault_CoreAR_Athena_SR"])
    r["chests"][3]["id"] = r["chests"][2]["id"]
    r["chests"][3]["reopen"] = True
    tr.record_match(r)
    tr.set_initial_chests(2500)
    yield tr
    db.close()


@pytest.fixture
def server(tracker):
    srv = CompanionServer(tracker, new_token(), free_port())
    assert srv.start()
    yield srv
    srv.stop()


def get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_summary_content(tracker):
    d = build_summary(tracker)
    assert (d["total"], d["counted"], d["initial"], d["unique"], d["reopens"]) == (2504, 4, 2500, 3, 1)
    assert d["matches"][0]["chests"] == 4 and d["matches"][0]["unique"] == 3
    assert len(d["days"]) == 30
    assert d["loot"][0]["rarity"] == "Légendaire"
    json.dumps(d)  # sérialisable


def test_access_requires_the_key(server):
    base = f"http://127.0.0.1:{server.port}"
    assert get(base + "/")[0] == 403
    assert get(base + "/api/summary")[0] == 403
    assert get(base + "/api/summary?t=mauvaise-cle")[0] == 403


def test_page_and_data_with_the_key(server):
    base = f"http://127.0.0.1:{server.port}"
    code, body, headers = get(f"{base}/?t={server.token}")
    assert code == 200 and b"<h1>Coffres</h1>" in body
    assert f"pt={server.token}" in headers.get("Set-Cookie", "")
    code, body, _ = get(f"{base}/api/summary?t={server.token}")
    assert code == 200 and json.loads(body)["total"] == 2504
    # Page ajoutée à l'écran d'accueil : la clé vient du cookie
    code, _, _ = get(f"{base}/api/summary", {"Cookie": f"pt={server.token}"})
    assert code == 200
    # Icônes et manifeste publics (nécessaires à l'écran d'accueil), aucune donnée dedans
    assert get(base + "/manifest.webmanifest")[0] == 200
    assert get(base + "/icon-180.png")[0] == 200


def test_read_only(server):
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/summary?t={server.token}", data=b"{}",
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 501  # aucune méthode d'écriture


def test_port_already_used(tracker):
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.listen()
    try:
        srv = CompanionServer(tracker, new_token(), port)
        assert not srv.start() and "indisponible" in srv.error
    finally:
        s.close()
