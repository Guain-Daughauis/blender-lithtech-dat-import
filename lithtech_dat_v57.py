from dataclasses import dataclass
from os import PathLike
from typing import Union

try:
    from .lithtech_dat_v56 import (
        LithtechDatV56Parser,
        V56WorldModel,
        create_v56_blender_meshes,
        extract_v56_mesh_batches,
    )
    from .lithtech_dat_v66 import BinaryReader, MeshBatch
except ImportError:  # Allows parser tests to import this module directly.
    from lithtech_dat_v56 import (
        LithtechDatV56Parser,
        V56WorldModel,
        create_v56_blender_meshes,
        extract_v56_mesh_batches,
    )
    from lithtech_dat_v66 import BinaryReader, MeshBatch


Pathish = Union[str, PathLike[str]]


@dataclass
class V57WorldInfo:
    properties: str
    light_map_grid_size: float
    unknown: list[int]


@dataclass
class LithtechDatV57:
    version: int
    object_data_pos: int
    render_data_pos: int
    world_info: V57WorldInfo
    world_model_count: int
    world_models: list[V56WorldModel]
    world_object_count: int


class LithtechDatV57Parser(LithtechDatV56Parser):
    version = 57

    def parse_file(self, filepath: Pathish) -> LithtechDatV57:
        with open(filepath, "rb") as file:
            return self.parse_bytes(file.read())

    def parse_bytes(self, data: bytes) -> LithtechDatV57:
        reader = BinaryReader(data)
        version = reader.u32()
        if version != self.version:
            raise ValueError(f"Expected DAT v57, got DAT v{version}")

        object_data_pos = reader.u32()
        render_data_pos = reader.u32()
        world_info = self._read_world_info(reader)

        reader.seek(object_data_pos)
        world_object_count = self._read_world_object_data(reader)
        world_models = [self._read_world_model_record(reader, 0)]
        additional_world_model_count = reader.u32()
        for world_model_index in range(1, additional_world_model_count + 1):
            world_models.append(self._read_world_model_record(reader, world_model_index))

        return LithtechDatV57(
            version=version,
            object_data_pos=object_data_pos,
            render_data_pos=render_data_pos,
            world_info=world_info,
            world_model_count=len(world_models),
            world_models=world_models,
            world_object_count=world_object_count,
        )

    def _read_world_info(self, reader: BinaryReader) -> V57WorldInfo:
        return V57WorldInfo(reader.str32(), reader.f32(), [reader.u32() for _ in range(8)])


def parse_dat_v57_file(filepath: Pathish) -> LithtechDatV57:
    return LithtechDatV57Parser().parse_file(filepath)


def extract_v57_mesh_batches(dat: LithtechDatV57) -> list[MeshBatch]:
    return extract_v56_mesh_batches(dat)


def create_v57_blender_meshes(blender_data, parent_collection, dat: LithtechDatV57, scale: float = 0.01) -> int:
    return create_v56_blender_meshes(blender_data, parent_collection, dat, scale=scale)
