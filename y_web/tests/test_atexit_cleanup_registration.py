from y_web import _should_register_atexit_cleanup


def test_atexit_cleanup_disabled_by_default():
    assert _should_register_atexit_cleanup({}) is False


def test_atexit_cleanup_enabled_with_opt_in_flag():
    assert _should_register_atexit_cleanup({"YSOCIAL_ENABLE_ATEXIT_CLEANUP": "1"})
    assert _should_register_atexit_cleanup({"YSOCIAL_ENABLE_ATEXIT_CLEANUP": "true"})


def test_atexit_cleanup_disabled_for_client_subprocess():
    assert (
        _should_register_atexit_cleanup(
            {"YSOCIAL_ENABLE_ATEXIT_CLEANUP": "1", "Y_CLIENT_SUBPROCESS": "1"}
        )
        is False
    )
