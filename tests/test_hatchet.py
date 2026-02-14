import importlib
import sys


def test_hatchet_import(monkeypatch):
    created = {}

    class Dummy:
        def __init__(self):
            created['ok'] = True

    monkeypatch.setattr('hatchet_sdk.Hatchet', Dummy)
    sys.modules.pop('scythe.hatchet', None)
    module = importlib.import_module('scythe.hatchet')
    assert isinstance(module.hatchet, Dummy)
    assert created.get('ok') is True
