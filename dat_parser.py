from dataclasses import dataclass
from os import PathLike
from typing import Callable, Union

try:
    from .kaitai_lithtech_dat_struct import LithtechDat
    from .lithtech_dat_v56 import parse_dat_v56_file
    from .lithtech_dat_v57 import parse_dat_v57_file
    from .lithtech_dat_v66 import parse_dat_v66_file
    from .lithtech_dat_v70 import parse_dat_v70_file
    from .lithtech_dat_v127 import parse_dat_v127_file
except ImportError:  # Allows parser tests to import this module directly.
    from kaitai_lithtech_dat_struct import LithtechDat
    from lithtech_dat_v56 import parse_dat_v56_file
    from lithtech_dat_v57 import parse_dat_v57_file
    from lithtech_dat_v66 import parse_dat_v66_file
    from lithtech_dat_v70 import parse_dat_v70_file
    from lithtech_dat_v127 import parse_dat_v127_file


Pathish = Union[str, PathLike[str]]


class DatFormatError(ValueError):
    """Raised when a file is too small or malformed before parser dispatch."""


class UnsupportedDatVersionError(ValueError):
    """Raised when a DAT version is known or detected but not implemented."""

    def __init__(self, version: int):
        known_label = KNOWN_DAT_VERSIONS.get(version, f"DAT v{version}")
        supported = ", ".join(f"v{v}" for v in sorted(SUPPORTED_DAT_PARSERS))
        super().__init__(
            f"{known_label} is not implemented by this importer yet. "
            f"Implemented DAT versions: {supported}."
        )
        self.version = version


@dataclass(frozen=True)
class DatParserProfile:
    version: int
    label: str
    parse_file: Callable[[Pathish], object]


KNOWN_DAT_VERSIONS = {
    56: "DAT v56 (LithTech 1)",
    57: "DAT v57 (LithTech 1.5)",
    66: "DAT v66 (LithTech 2 / NOLF)",
    70: "DAT v70 (Talon / AVP2)",
    85: "DAT v85 (Jupiter)",
    127: "DAT v127 (Psycho / LT1.5 variant)",
}


SUPPORTED_DAT_PARSERS = {
    56: DatParserProfile(
        version=56,
        label=KNOWN_DAT_VERSIONS[56],
        parse_file=parse_dat_v56_file,
    ),
    57: DatParserProfile(
        version=57,
        label=KNOWN_DAT_VERSIONS[57],
        parse_file=parse_dat_v57_file,
    ),
    66: DatParserProfile(
        version=66,
        label=KNOWN_DAT_VERSIONS[66],
        parse_file=parse_dat_v66_file,
    ),
    70: DatParserProfile(
        version=70,
        label=KNOWN_DAT_VERSIONS[70],
        parse_file=parse_dat_v70_file,
    ),
    85: DatParserProfile(
        version=85,
        label=KNOWN_DAT_VERSIONS[85],
        parse_file=LithtechDat.from_file,
    ),
    127: DatParserProfile(
        version=127,
        label=KNOWN_DAT_VERSIONS[127],
        parse_file=parse_dat_v127_file,
    ),
}


def detect_dat_version(filepath: Pathish) -> int:
    with open(filepath, "rb") as file:
        data = file.read(4)

    if len(data) != 4:
        raise DatFormatError("DAT file is too small to contain a version field.")

    return int.from_bytes(data, byteorder="little", signed=False)


def parser_profile_for_version(version: int) -> DatParserProfile:
    try:
        return SUPPORTED_DAT_PARSERS[version]
    except KeyError as exc:
        raise UnsupportedDatVersionError(version) from exc


def parse_dat_file(filepath: Pathish):
    version = detect_dat_version(filepath)
    profile = parser_profile_for_version(version)
    return profile.parse_file(filepath)
