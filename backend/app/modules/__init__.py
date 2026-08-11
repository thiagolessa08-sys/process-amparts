from app.modules.base import ProcessModule

_registry: dict[str, "ProcessModule"] = {}


def register(module: "ProcessModule") -> None:
    _registry[module.key] = module


def get(key: str) -> "ProcessModule | None":
    return _registry.get(key)


def all_keys() -> list[str]:
    return list(_registry.keys())


# auto-registro dos módulos disponíveis
from app.modules.amparts_module import AmPartsModule  # noqa: E402
register(AmPartsModule())
