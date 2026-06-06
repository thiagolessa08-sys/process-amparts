from app.modules.base import ProcessModule

_registry: dict[str, "ProcessModule"] = {}


def register(module: "ProcessModule") -> None:
    _registry[module.key] = module


def get(key: str) -> "ProcessModule | None":
    return _registry.get(key)


def all_keys() -> list[str]:
    return list(_registry.keys())


# auto-registro dos módulos disponíveis
from app.modules.p2p_module import P2PModule  # noqa: E402
from app.modules.o2c_module import O2CModule  # noqa: E402
register(P2PModule())
register(O2CModule())
