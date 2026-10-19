import stat

from izchu.storage import JsonStore


def test_json_store_round_trip_is_private_and_atomic(tmp_path):
    path = tmp_path / "secrets" / "token.json"
    store = JsonStore(path)

    store.write({"access_token": "secret", "athlete": {"id": 42}})

    assert store.read() == {"access_token": "secret", "athlete": {"id": 42}}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    store.delete()
    assert store.read() is None

