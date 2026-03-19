import tvc_config


def test_tvc_config_paths_have_expected_basics():
    paths = tvc_config.PATHS

    required_keys = ("root", "assets", "intelligence", "evidence")
    for key in required_keys:
        assert key in paths
        assert isinstance(paths[key], str)
        assert paths[key].strip()
