__all__ = ["app", "create_app", "create_runtime_app", "main"]


def create_app(*args, **kwargs):
    from callio.core.server import create_app as _create_app

    return _create_app(*args, **kwargs)


def create_runtime_app(*args, **kwargs):
    from callio.app import create_runtime_app as _create_runtime_app

    return _create_runtime_app(*args, **kwargs)


def main(*args, **kwargs):
    from callio.app import main as _main

    return _main(*args, **kwargs)


def __getattr__(name):
    if name == "app":
        from callio.app import app as _app

        return _app
    raise AttributeError(name)
