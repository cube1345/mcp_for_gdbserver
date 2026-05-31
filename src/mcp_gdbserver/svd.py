"""Small CMSIS-SVD parser used by register inspection tools."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree


def _tag_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in list(element) if _tag_name(child) == name]


def _child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in list(element):
        if _tag_name(child) == name:
            return child
    return None


def _child_text(element: ElementTree.Element, name: str) -> str | None:
    child = _child(element, name)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _parse_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    text = value.strip()
    if not text:
        return default
    return int(text.replace("_", ""), 0)


def _parse_bit_range(field: ElementTree.Element) -> tuple[int, int]:
    bit_offset = _child_text(field, "bitOffset")
    bit_width = _child_text(field, "bitWidth")
    if bit_offset is not None and bit_width is not None:
        return _parse_int(bit_offset), _parse_int(bit_width)

    lsb = _child_text(field, "lsb")
    msb = _child_text(field, "msb")
    if lsb is not None and msb is not None:
        low = _parse_int(lsb)
        high = _parse_int(msb)
        return low, high - low + 1

    bit_range = _child_text(field, "bitRange")
    if bit_range:
        high_text, low_text = bit_range.strip("[]").split(":", 1)
        high = _parse_int(high_text)
        low = _parse_int(low_text)
        return low, high - low + 1

    return 0, 1


def _dim_indices(dim_index: str | None, dim: int) -> list[str]:
    if not dim_index:
        return [str(index) for index in range(dim)]

    text = dim_index.strip()
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]

    if "-" in text:
        start, end = text.split("-", 1)
        if start.strip().isdigit() and end.strip().isdigit():
            return [str(index) for index in range(int(start), int(end) + 1)]

    return [text]


def _expand_name(template: str, index: str) -> str:
    if "%s" in template:
        return template.replace("%s", index)
    return f"{template}{index}"


@dataclass(frozen=True)
class SVDField:
    name: str
    bit_offset: int
    bit_width: int
    description: str | None = None

    def decode(self, register_value: int) -> int:
        mask = (1 << self.bit_width) - 1
        return (register_value >> self.bit_offset) & mask

    def to_dict(self, register_value: int | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "name": self.name,
            "bit_offset": self.bit_offset,
            "bit_width": self.bit_width,
            "description": self.description,
        }
        if register_value is not None:
            value = self.decode(register_value)
            data["value"] = value
            data["hex"] = hex(value)
        return data


@dataclass(frozen=True)
class SVDRegister:
    name: str
    address_offset: int
    size: int = 32
    access: str | None = None
    reset_value: int | None = None
    description: str | None = None
    fields: tuple[SVDField, ...] = ()

    def absolute_address(self, peripheral: "SVDPeripheral") -> int:
        return peripheral.base_address + self.address_offset

    @property
    def byte_size(self) -> int:
        return max(1, (self.size + 7) // 8)

    def to_dict(self, peripheral: "SVDPeripheral" | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "name": self.name,
            "address_offset": hex(self.address_offset),
            "size": self.size,
            "access": self.access,
            "reset_value": hex(self.reset_value) if self.reset_value is not None else None,
            "description": self.description,
            "fields": [field.to_dict() for field in self.fields],
        }
        if peripheral is not None:
            data["address"] = hex(self.absolute_address(peripheral))
        return data


@dataclass(frozen=True)
class SVDPeripheral:
    name: str
    base_address: int
    description: str | None = None
    registers: tuple[SVDRegister, ...] = ()

    def register_by_name(self, name: str) -> SVDRegister | None:
        normalized = name.upper()
        for register in self.registers:
            if register.name.upper() == normalized:
                return register
        return None

    def to_dict(self, include_registers: bool = False) -> dict[str, object]:
        data: dict[str, object] = {
            "name": self.name,
            "base_address": hex(self.base_address),
            "description": self.description,
        }
        if include_registers:
            data["registers"] = [register.to_dict(self) for register in self.registers]
        return data


@dataclass(frozen=True)
class SVDDevice:
    name: str
    source_path: str
    peripherals: tuple[SVDPeripheral, ...]

    @classmethod
    def from_file(cls, path: str | Path) -> "SVDDevice":
        source_path = str(Path(path))
        root = ElementTree.parse(source_path).getroot()
        name = _child_text(root, "name") or Path(source_path).stem

        peripherals_node = _child(root, "peripherals")
        if peripherals_node is None:
            return cls(name=name, source_path=source_path, peripherals=())

        parsed: dict[str, SVDPeripheral] = {}
        peripherals: list[SVDPeripheral] = []
        for peripheral_node in _children(peripherals_node, "peripheral"):
            peripheral = _parse_peripheral(peripheral_node, parsed)
            parsed[peripheral.name] = peripheral
            peripherals.append(peripheral)

        return cls(name=name, source_path=source_path, peripherals=tuple(peripherals))

    def peripheral_by_name(self, name: str) -> SVDPeripheral | None:
        normalized = name.upper()
        for peripheral in self.peripherals:
            if peripheral.name.upper() == normalized:
                return peripheral
        return None

    def list_peripherals(self, filter_text: str | None = None) -> list[SVDPeripheral]:
        if not filter_text:
            return list(self.peripherals)
        needle = filter_text.upper()
        return [peripheral for peripheral in self.peripherals if needle in peripheral.name.upper()]


def _parse_peripheral(
    node: ElementTree.Element,
    parsed: dict[str, SVDPeripheral],
) -> SVDPeripheral:
    derived_from = node.attrib.get("derivedFrom")
    base = parsed.get(derived_from, None) if derived_from else None

    name = _child_text(node, "name") or (base.name if base else "")
    description = _child_text(node, "description") or (base.description if base else None)
    base_address = _parse_int(
        _child_text(node, "baseAddress"),
        base.base_address if base else 0,
    )

    registers_node = _child(node, "registers")
    if registers_node is None and base is not None:
        registers = base.registers
    else:
        registers = tuple(_parse_registers(registers_node) if registers_node is not None else [])

    return SVDPeripheral(
        name=name,
        description=description,
        base_address=base_address,
        registers=registers,
    )


def _parse_registers(registers_node: ElementTree.Element) -> list[SVDRegister]:
    registers: list[SVDRegister] = []
    parsed: dict[str, SVDRegister] = {}

    for register_node in _children(registers_node, "register"):
        expanded = _parse_register_node(register_node, parsed)
        registers.extend(expanded)
        for register in expanded:
            parsed[register.name] = register

    return registers


def _parse_register_node(
    node: ElementTree.Element,
    parsed: dict[str, SVDRegister],
) -> list[SVDRegister]:
    derived_from = node.attrib.get("derivedFrom")
    base = parsed.get(derived_from, None) if derived_from else None

    name = _child_text(node, "name") or (base.name if base else "")
    address_offset = _parse_int(
        _child_text(node, "addressOffset"),
        base.address_offset if base else 0,
    )
    size = _parse_int(_child_text(node, "size"), base.size if base else 32)
    access = _child_text(node, "access") or (base.access if base else None)
    reset_text = _child_text(node, "resetValue")
    reset_value = _parse_int(reset_text) if reset_text is not None else (base.reset_value if base else None)
    description = _child_text(node, "description") or (base.description if base else None)

    fields_node = _child(node, "fields")
    if fields_node is None and base is not None:
        fields = base.fields
    else:
        fields = tuple(_parse_fields(fields_node) if fields_node is not None else [])

    register = SVDRegister(
        name=name,
        address_offset=address_offset,
        size=size,
        access=access,
        reset_value=reset_value,
        description=description,
        fields=fields,
    )

    dim = _parse_int(_child_text(node, "dim"), 0)
    if dim <= 0:
        return [register]

    increment = _parse_int(_child_text(node, "dimIncrement"), 0)
    indexes = _dim_indices(_child_text(node, "dimIndex"), dim)
    expanded = []
    for offset, index in enumerate(indexes[:dim]):
        expanded.append(
            replace(
                register,
                name=_expand_name(register.name, index),
                address_offset=register.address_offset + offset * increment,
            )
        )
    return expanded


def _parse_fields(fields_node: ElementTree.Element) -> list[SVDField]:
    fields: list[SVDField] = []
    for field_node in _children(fields_node, "field"):
        name = _child_text(field_node, "name") or ""
        bit_offset, bit_width = _parse_bit_range(field_node)
        fields.append(
            SVDField(
                name=name,
                bit_offset=bit_offset,
                bit_width=bit_width,
                description=_child_text(field_node, "description"),
            )
        )
    return fields
