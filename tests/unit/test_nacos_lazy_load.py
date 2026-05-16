from unittest.mock import patch


def test_get_settings_calls_nacos_exactly_once():
    """get_settings() must call _load_nacos_sync exactly once across multiple calls."""
    import src.common.config as cfg

    # Reset module state
    cfg._settings_instance = None
    cfg._nacos_loaded = False  # This will fail until we add the flag

    with patch.object(cfg, "_load_nacos_sync") as mock_load:
        cfg.get_settings()
        cfg.get_settings()
        cfg.get_settings()

    assert mock_load.call_count == 1, (
        f"Expected _load_nacos_sync called once, got {mock_load.call_count}"
    )
    # Cleanup
    cfg._settings_instance = None
    cfg._nacos_loaded = False


def test_accessing_module_does_not_call_nacos():
    """Simply reading module attributes must not trigger any network call."""
    import src.common.config as cfg

    cfg._settings_instance = None
    cfg._nacos_loaded = False

    with patch.object(cfg, "_load_nacos_sync") as mock_load:
        # Access a module attribute without calling get_settings()
        _ = cfg._settings_instance
        assert mock_load.call_count == 0

    cfg._settings_instance = None
    cfg._nacos_loaded = False
