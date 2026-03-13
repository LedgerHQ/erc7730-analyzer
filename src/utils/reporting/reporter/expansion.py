"""ERC-7730 format expansion utilities."""

from typing import Any


def _extract_reference_name(value: str, prefix: str) -> str | None:
    if not value.startswith(prefix):
        return None
    return value[len(prefix) :] or None


def _extract_embedded_reference_names(value: str, prefix: str) -> set[str]:
    names: set[str] = set()
    start = 0
    while True:
        idx = value.find(prefix, start)
        if idx == -1:
            break
        remainder = value[idx + len(prefix) :]
        name_chars = []
        for char in remainder:
            if char.isalnum() or char in {"_", "-"}:
                name_chars.append(char)
            else:
                break
        if name_chars:
            names.add("".join(name_chars))
        start = idx + len(prefix)
    return names


def _scan_string_references(
    value: str,
    *,
    referenced_constants: set[str],
    referenced_enums: set[str],
    referenced_maps: set[str],
) -> None:
    referenced_constants.update(_extract_embedded_reference_names(value, "$.metadata.constants."))
    referenced_enums.update(_extract_embedded_reference_names(value, "$.metadata.enums."))
    referenced_maps.update(_extract_embedded_reference_names(value, "$.metadata.maps."))


def expand_erc7730_format_with_refs(
    selector_format: dict[str, Any],
    full_erc7730: dict[str, Any],
    format_key: str = None,
) -> dict[str, Any]:
    """
    Expand an ERC-7730 selector format with the metadata it references.

    This keeps prompt payloads compact while still preserving the definitions,
    constants, enums, maps, and lightweight metadata context needed to audit v2
    descriptors accurately.

    Args:
        selector_format: The format dict for this selector.
        full_erc7730: The complete ERC-7730 descriptor.
        format_key: The original key used in display.formats (function sig or selector).
    """
    result: dict[str, Any] = {}

    referenced_defs: set[str] = set()
    referenced_constants: set[str] = set()
    referenced_enums: set[str] = set()
    referenced_maps: set[str] = set()

    def scan(obj: Any) -> None:
        if isinstance(obj, str):
            _scan_string_references(
                obj,
                referenced_constants=referenced_constants,
                referenced_enums=referenced_enums,
                referenced_maps=referenced_maps,
            )
        elif isinstance(obj, dict):
            for key, value in obj.items():
                if key == "$ref" and isinstance(value, str):
                    def_name = _extract_reference_name(value, "$.display.definitions.")
                    if def_name:
                        referenced_defs.add(def_name)
                    enum_name = _extract_reference_name(value, "$.metadata.enums.")
                    if enum_name:
                        referenced_enums.add(enum_name)
                elif key == "map" and isinstance(value, str):
                    map_name = _extract_reference_name(value, "$.metadata.maps.")
                    if map_name:
                        referenced_maps.add(map_name)

                if isinstance(value, str):
                    _scan_string_references(
                        value,
                        referenced_constants=referenced_constants,
                        referenced_enums=referenced_enums,
                        referenced_maps=referenced_maps,
                    )
                elif isinstance(value, (dict, list)):
                    scan(value)
        elif isinstance(obj, list):
            for item in obj:
                scan(item)

    scan(selector_format)

    metadata = full_erc7730.get("metadata", {})
    display = full_erc7730.get("display", {})
    definitions = display.get("definitions", {})

    # Definitions can themselves reference other definitions, constants, enums,
    # or maps. Resolve the full transitive closure so prompt/report packets keep
    # all support data needed for nested $ref chains.
    scanned_defs: set[str] = set()
    pending_defs = list(referenced_defs)
    while pending_defs:
        def_name = pending_defs.pop()
        if def_name in scanned_defs:
            continue
        scanned_defs.add(def_name)

        definition = definitions.get(def_name)
        if not definition:
            continue

        before_defs = set(referenced_defs)
        scan(definition)
        for new_def in referenced_defs - before_defs:
            if new_def not in scanned_defs:
                pending_defs.append(new_def)

    informative_metadata = {key: metadata[key] for key in ("owner", "contractName", "info", "token") if key in metadata}
    if informative_metadata or referenced_constants or referenced_enums or referenced_maps:
        result["metadata"] = {}
        result["metadata"].update(informative_metadata)

        if referenced_constants and metadata.get("constants"):
            result["metadata"]["constants"] = {
                name: metadata["constants"][name] for name in referenced_constants if name in metadata["constants"]
            }

        if referenced_enums and metadata.get("enums"):
            result["metadata"]["enums"] = {
                name: metadata["enums"][name] for name in referenced_enums if name in metadata["enums"]
            }

        if referenced_maps and metadata.get("maps"):
            result["metadata"]["maps"] = {
                name: metadata["maps"][name] for name in referenced_maps if name in metadata["maps"]
            }

    if referenced_defs or selector_format:
        result.setdefault("display", {})

        if referenced_defs and definitions:
            result["display"]["definitions"] = {
                name: definitions[name] for name in referenced_defs if name in definitions
            }

        if selector_format:
            result["display"]["formats"] = {}
            key = format_key or selector_format.get("$id", "unknown")
            result["display"]["formats"][key] = selector_format

    return result
