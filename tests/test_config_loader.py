"""Stage 15 - ConfigLoader unit tests (6).

Uses an in-memory fake IFileSystem (no real vault needed).
"""
import warnings

from infrastructure import ConfigLoader


class FakeFS:
    def __init__(self, files):
        self._files = files  # name -> content

    def exists(self, name):
        return name in self._files

    def read_content(self, name):
        if name not in self._files:
            raise FileNotFoundError(name)
        return self._files[name]


YAML = "vault: .\nautosave_interval: 15\nfeatures:\n  extract_tags: true\n"
JSON = '{"vault": ".", "autosave_interval": 15}'
BROKEN = "vault: [unterminated\nautosave_interval: not a number"


def test_load_yaml():
    cfg = ConfigLoader().load("vault", FakeFS({"kroft_os.yaml": YAML}))
    assert cfg == {
        "vault": ".",
        "autosave_interval": 15,
        "features": {"extract_tags": True},
    }


def test_load_json_fallback():
    # No YAML present -> JSON is parsed.
    cfg = ConfigLoader().load("vault", FakeFS({"kroft_os.json": JSON}))
    assert cfg["autosave_interval"] == 15
    assert cfg["vault"] == "."


def test_load_missing():
    assert ConfigLoader().load("vault", FakeFS({})) == {}


def test_merge_cli_overrides_config():
    class Args:
        vault = None
        autosave = 30.0
    m = ConfigLoader().merge_with_cli(Args(), {"autosave_interval": 60})
    assert m["autosave_interval"] == 30.0


def test_merge_config_defaults():
    class Args:
        vault = None
        autosave = None
    m = ConfigLoader().merge_with_cli(Args(), {"autosave_interval": 15})
    assert m["autosave_interval"] == 15.0


def test_load_invalid_yaml():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cfg = ConfigLoader().load("vault", FakeFS({"kroft_os.yaml": BROKEN}))
    assert cfg == {}
