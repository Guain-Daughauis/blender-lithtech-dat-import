from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Union


Pathish = Union[str, PathLike[str]]
Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


@dataclass
class V66WorldInfo:
    properties: str
    light_map_grid_size: float
    extents_min: Vec3
    extents_max: Vec3


@dataclass
class V66WorldTree:
    root_box_min: Vec3
    root_box_max: Vec3
    child_node_count: int
    terrain_depth: int
    layout: bytes


@dataclass
class V66Plane:
    normal: Vec3
    distance: float


@dataclass
class V66Surface:
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    texture_index: int
    flags: int
    texture_flags: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V66DiskVertex:
    vertex_index: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V66Polygon:
    center: Vec3
    lightmap_width: int
    lightmap_height: int
    surface_index: int
    plane_index: int
    disk_vertices: list[V66DiskVertex]
    lightmap: "V66LightmapFrameData | None" = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V66Node:
    poly_index: int
    leaf_index: int
    child_indices: tuple[int, int]


@dataclass
class V66WorldModel:
    world_name: str
    world_info_flags: int
    texture_names: list[str]
    points: list[Vec3]
    point_normals: list[Vec3]
    planes: list[V66Plane]
    surfaces: list[V66Surface]
    polygons: list[V66Polygon]
    nodes: list[V66Node]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LithtechDatV66:
    version: int
    object_data_pos: int
    render_data_pos: int
    world_info: V66WorldInfo
    world_tree: V66WorldTree
    world_model_count: int
    world_models: list[V66WorldModel]
    world_object_count: int
    lightmaps: "V66WorldLightMaps | None" = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeshBatch:
    name: str
    texture_name: str
    vertices: list[Vec3]
    triangles: list[tuple[int, int, int]]
    normals: list[Vec3]
    uv0: list[Vec2]
    vertex_colors: list[tuple[int, int, int]] = field(default_factory=list)
    lightmap_refs: list[str | None] = field(default_factory=list)


@dataclass
class V66LightmapFrame:
    world_model_index: int
    poly_index: int


@dataclass
class V66LightmapFrameData:
    name: str
    world_model_index: int
    poly_index: int
    data: list[int]
    width: int = 0
    height: int = 0

    @property
    def ref(self) -> str:
        return f"{self.name}:{self.world_model_index}:{self.poly_index}"


@dataclass
class V66WorldLightMaps:
    total_frames_1: int
    total_animations: int
    total_memory: int
    total_frames_2: int
    animations: list[str]
    by_polygon: dict[tuple[int, int], V66LightmapFrameData]


class BinaryReader:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def tell(self) -> int:
        return self._pos

    def seek(self, pos: int) -> None:
        if pos < 0 or pos > len(self._data):
            raise ValueError(f"Seek outside DAT data: {pos}")
        self._pos = pos

    def length(self) -> int:
        return len(self._data)

    def read(self, size: int) -> bytes:
        end = self._pos + size
        if end > len(self._data):
            raise EOFError("Unexpected end of DAT data")
        data = self._data[self._pos:end]
        self._pos = end
        return data

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return int.from_bytes(self.read(2), "little", signed=False)

    def u32(self) -> int:
        return int.from_bytes(self.read(4), "little", signed=False)

    def f32(self) -> float:
        import struct

        return struct.unpack("<f", self.read(4))[0]

    def vec3(self) -> Vec3:
        return (self.f32(), self.f32(), self.f32())

    def str16(self) -> str:
        return self.read(self.u16()).decode("ascii")

    def str32(self) -> str:
        return self.read(self.u32()).decode("ascii")

    def cstring(self) -> str:
        start = self._pos
        while self._pos < len(self._data) and self._data[self._pos] != 0:
            self._pos += 1
        if self._pos >= len(self._data):
            raise EOFError("Unterminated DAT string")
        value = self._data[start:self._pos].decode("ascii")
        self._pos += 1
        return value


class LithtechDatV66Parser:
    version = 66

    def parse_file(self, filepath: Pathish) -> LithtechDatV66:
        with open(filepath, "rb") as file:
            return self.parse_bytes(file.read())

    def parse_bytes(self, data: bytes) -> LithtechDatV66:
        reader = BinaryReader(data)
        version = reader.u32()
        if version != self.version:
            raise ValueError(f"Expected DAT v66, got DAT v{version}")

        object_data_pos = reader.u32()
        render_data_pos = reader.u32()
        future = [reader.u32() for _ in range(8)]
        world_info = self._read_world_info(reader)
        world_tree = self._read_world_tree(reader)
        world_model_pos = reader.tell()

        lightmaps = None
        if render_data_pos != reader.length():
            reader.seek(render_data_pos)
            lightmaps = V66WorldLightMapsParser().parse(reader)

        reader.seek(object_data_pos)
        world_object_count = reader.u32()

        reader.seek(world_model_pos)
        world_model_count = reader.u32()
        world_models = [self._read_world_model_record(reader) for _ in range(world_model_count)]
        if lightmaps is not None:
            self._attach_lightmaps(world_models, lightmaps)

        return LithtechDatV66(
            version=version,
            object_data_pos=object_data_pos,
            render_data_pos=render_data_pos,
            world_info=world_info,
            world_tree=world_tree,
            world_model_count=world_model_count,
            world_models=world_models,
            world_object_count=world_object_count,
            lightmaps=lightmaps,
            extras={"future": future},
        )

    def _attach_lightmaps(self, world_models: list[V66WorldModel], lightmaps: V66WorldLightMaps) -> None:
        for (world_model_index, poly_index), lightmap in lightmaps.by_polygon.items():
            if world_model_index >= len(world_models):
                continue
            world_model = world_models[world_model_index]
            if poly_index >= len(world_model.polygons):
                continue
            polygon = world_model.polygons[poly_index]
            lightmap.width = polygon.lightmap_width
            lightmap.height = polygon.lightmap_height
            polygon.lightmap = lightmap

    def _read_world_info(self, reader: BinaryReader) -> V66WorldInfo:
        return V66WorldInfo(
            properties=reader.str32(),
            light_map_grid_size=reader.f32(),
            extents_min=reader.vec3(),
            extents_max=reader.vec3(),
        )

    def _read_world_tree(self, reader: BinaryReader) -> V66WorldTree:
        root_box_min = reader.vec3()
        root_box_max = reader.vec3()
        child_node_count = reader.u32()
        terrain_depth = reader.u32()
        layout = self._read_world_tree_layout(reader, child_node_count)
        return V66WorldTree(root_box_min, root_box_max, child_node_count, terrain_depth, layout)

    def _read_world_tree_layout(self, reader: BinaryReader, child_node_count: int) -> bytes:
        byte_count = max(1, int(child_node_count * 0.125 + 1))
        return reader.read(byte_count)

    def _read_world_model_record(self, reader: BinaryReader) -> V66WorldModel:
        next_world_model_pos = reader.u32()
        dummy_prefix = reader.read(32)
        world_model = self._read_world_model(reader)
        world_model.extras["next_world_model_pos"] = next_world_model_pos
        world_model.extras["dummy_prefix"] = dummy_prefix
        if world_model.extras.get("section_count", 0) > 0:
            reader.seek(next_world_model_pos)
        return world_model

    def _read_world_model(self, reader: BinaryReader) -> V66WorldModel:
        world_info_flags = reader.u32()
        unknown_value = reader.u32()
        world_name = reader.str16()

        point_count = reader.u32()
        plane_count = reader.u32()
        surface_count = reader.u32()
        user_portal_count = reader.u32()
        poly_count = reader.u32()
        leaf_count = reader.u32()
        vert_count = reader.u32()
        total_vis_list_size = reader.u32()
        leaf_list_count = reader.u32()
        node_count = reader.u32()
        unknown_value_2 = reader.u32()
        unknown_value_3 = reader.u32()
        min_box = reader.vec3()
        max_box = reader.vec3()
        world_translation = reader.vec3()
        texture_names_size = reader.u32()
        texture_count = reader.u32()
        texture_names = [reader.cstring() for _ in range(texture_count)]
        polygon_vertex_counts = [reader.u8() + reader.u8() for _ in range(poly_count)]

        leaves = [self._read_leaf(reader) for _ in range(leaf_count)]
        planes = [V66Plane(reader.vec3(), reader.f32()) for _ in range(plane_count)]
        surfaces = [self._read_surface(reader) for _ in range(surface_count)]
        polygons = [self._read_polygon(reader, polygon_vertex_counts[i]) for i in range(poly_count)]
        nodes = [self._read_node(reader) for _ in range(node_count)]
        user_portals = [self._read_user_portal(reader) for _ in range(user_portal_count)]

        points: list[Vec3] = []
        point_normals: list[Vec3] = []
        for _ in range(point_count):
            points.append(reader.vec3())
            point_normals.append(reader.vec3())

        pblock_table = self._read_pblock_table(reader)
        root_node_index = reader.u32()
        section_count = reader.u32()

        return V66WorldModel(
            world_name=world_name,
            world_info_flags=world_info_flags,
            texture_names=texture_names,
            points=points,
            point_normals=point_normals,
            planes=planes,
            surfaces=surfaces,
            polygons=polygons,
            nodes=nodes,
            extras={
                "unknown_value": unknown_value,
                "unknown_value_2": unknown_value_2,
                "unknown_value_3": unknown_value_3,
                "user_portal_count": user_portal_count,
                "leaf_count": leaf_count,
                "vert_count": vert_count,
                "total_vis_list_size": total_vis_list_size,
                "leaf_list_count": leaf_list_count,
                "min_box": min_box,
                "max_box": max_box,
                "world_translation": world_translation,
                "texture_names_size": texture_names_size,
                "polygon_vertex_counts": polygon_vertex_counts,
                "leaves": leaves,
                "user_portals": user_portals,
                "pblock_table": pblock_table,
                "root_node_index": root_node_index,
                "section_count": section_count,
            },
        )

    def _read_leaf(self, reader: BinaryReader) -> dict[str, Any]:
        count = reader.u16()
        data: dict[str, Any] = {"count": count}
        if count == 65535:
            data["index"] = reader.u16()
        else:
            data["records"] = []
            for _ in range(count):
                portal_id = reader.u16()
                size = reader.u16()
                data["records"].append({"portal_id": portal_id, "contents": reader.read(size)})
        polygon_count = reader.u32()
        data["polygon_data"] = reader.read(polygon_count * 4)
        data["unknown"] = reader.u32()
        return data

    def _read_surface(self, reader: BinaryReader) -> V66Surface:
        uv_origin = reader.vec3()
        uv_u = reader.vec3()
        uv_v = reader.vec3()
        texture_index = reader.u16()
        unknown = reader.u32()
        flags = reader.u32()
        unknown2 = reader.u32()
        use_effects = reader.u8()
        effect_name = ""
        effect_param = ""
        if use_effects == 1:
            effect_name = reader.str16()
            effect_param = reader.str16()
        texture_flags = reader.u16()
        return V66Surface(
            uv_origin=uv_origin,
            uv_u=uv_u,
            uv_v=uv_v,
            texture_index=texture_index,
            flags=flags,
            texture_flags=texture_flags,
            extras={
                "unknown": unknown,
                "unknown2": unknown2,
                "use_effects": use_effects,
                "effect_name": effect_name,
                "effect_param": effect_param,
            },
        )

    def _read_polygon(self, reader: BinaryReader, vertex_count: int) -> V66Polygon:
        center = reader.vec3()
        lightmap_width = reader.u16()
        lightmap_height = reader.u16()
        unknown_flag = reader.u16()
        unknown_list = [reader.u16() for _ in range(unknown_flag * 2)]
        surface_index = reader.u16()
        plane_index = reader.u16()
        disk_vertices = [self._read_disk_vertex(reader) for _ in range(vertex_count)]
        return V66Polygon(
            center=center,
            lightmap_width=lightmap_width,
            lightmap_height=lightmap_height,
            surface_index=surface_index,
            plane_index=plane_index,
            disk_vertices=disk_vertices,
            extras={"unknown_flag": unknown_flag, "unknown_list": unknown_list},
        )

    def _read_disk_vertex(self, reader: BinaryReader) -> V66DiskVertex:
        return V66DiskVertex(reader.u16(), {"dummy": reader.read(3)})

    def _read_node(self, reader: BinaryReader) -> V66Node:
        return V66Node(reader.u32(), reader.u16(), (reader.u32(), reader.u32()))

    def _read_user_portal(self, reader: BinaryReader) -> dict[str, Any]:
        return {
            "name": reader.str16(),
            "unknown_1": reader.u32(),
            "unknown_2": reader.u32(),
            "unknown_short": reader.u16(),
            "center": reader.vec3(),
            "dims": reader.vec3(),
        }

    def _read_pblock_table(self, reader: BinaryReader) -> dict[str, Any]:
        counts = (reader.u32(), reader.u32(), reader.u32())
        size = counts[0] * counts[1] * counts[2]
        data = {
            "counts": counts,
            "unknown_vector_1": reader.vec3(),
            "unknown_vector_2": reader.vec3(),
            "records": [],
        }
        for _ in range(size):
            record_size = reader.u16()
            unknown = reader.u16()
            data["records"].append({"size": record_size, "unknown": unknown, "contents": reader.read(6 * record_size)})
        return data


class V66WorldLightMapsParser:
    def parse(self, reader: BinaryReader) -> V66WorldLightMaps:
        total_frames_1 = reader.u32()
        total_animations = reader.u32()
        total_memory = reader.u32()
        total_frames_2 = reader.u32()
        count = reader.u32()
        animations = []
        by_polygon: dict[tuple[int, int], V66LightmapFrameData] = {}

        for _ in range(count):
            name, mapped_data = self._read_lightmap_data(reader)
            animations.append(name)
            by_polygon.update(mapped_data)

        return V66WorldLightMaps(
            total_frames_1=total_frames_1,
            total_animations=total_animations,
            total_memory=total_memory,
            total_frames_2=total_frames_2,
            animations=animations,
            by_polygon=by_polygon,
        )

    def _read_lightmap_data(self, reader: BinaryReader) -> tuple[str, dict[tuple[int, int], V66LightmapFrameData]]:
        name = reader.str16()
        lightmap_type = reader.u32()
        _batch_count = reader.u32()
        frame_count = reader.u32()
        frames = [V66LightmapFrame(reader.u16(), reader.u16()) for _ in range(frame_count)]
        mapped_data: dict[tuple[int, int], V66LightmapFrameData] = {}

        for frame in frames:
            size = reader.u32()
            raw = reader.read(size)
            data = list(raw) if lightmap_type > 0 else decode_v66_lightmap_batch(raw)
            mapped_data[(frame.world_model_index, frame.poly_index)] = V66LightmapFrameData(
                name=name,
                world_model_index=frame.world_model_index,
                poly_index=frame.poly_index,
                data=data,
            )

        return name, mapped_data


def parse_dat_v66_file(filepath: Pathish) -> LithtechDatV66:
    return LithtechDatV66Parser().parse_file(filepath)


def decode_v66_lightmap_batch(data: bytes) -> list[int]:
    reader = BinaryReader(data)
    color_data: list[int] = []
    while reader.tell() < reader.length():
        tag = reader.u16()
        copy_count = 1
        if tag & 0x8000:
            copy_count = reader.u8()
            tag = tag & 0x7FFF

        r = (tag >> 10) & 31
        g = (tag >> 5) & 31
        b = tag & 31
        for _ in range(copy_count):
            color_data.extend([r, g, b])
    return color_data


def extract_v66_mesh_batches(dat: LithtechDatV66, texture_size: tuple[float, float] = (256.0, 256.0)) -> list[MeshBatch]:
    batches: dict[str, MeshBatch] = {}
    tex_width, tex_height = texture_size

    for world_model in dat.world_models:
        for polygon in world_model.polygons:
            surface = world_model.surfaces[polygon.surface_index]
            texture_name = world_model.texture_names[surface.texture_index]
            batch = batches.setdefault(
                texture_name,
                MeshBatch(
                    name=f"{world_model.world_name}_{len(batches):03}",
                    texture_name=texture_name,
                    vertices=[],
                    triangles=[],
                    normals=[],
                    uv0=[],
                ),
            )
            start_index = len(batch.vertices)
            plane = world_model.planes[polygon.plane_index]

            for disk_vertex in polygon.disk_vertices:
                vertex = world_model.points[disk_vertex.vertex_index]
                batch.vertices.append(vertex)
                batch.normals.append(plane.normal)
                batch.uv0.append(_opq_to_uv(vertex, surface.uv_origin, surface.uv_u, surface.uv_v, tex_width, tex_height))

            for i in range(1, len(polygon.disk_vertices) - 1):
                batch.triangles.append((start_index, start_index + i, start_index + i + 1))
                batch.lightmap_refs.append(polygon.lightmap.ref if polygon.lightmap else None)

    return list(batches.values())


def create_v66_blender_meshes(blender_data, parent_collection, dat: LithtechDatV66, scale: float = 0.01) -> int:
    created = 0
    for batch in extract_v66_mesh_batches(dat):
        mesh = blender_data.meshes.new(f"{batch.name}_Mesh")
        mesh.from_pydata([_to_blender_coords(vertex, scale) for vertex in batch.vertices], [], batch.triangles)
        if hasattr(mesh, "update"):
            mesh.update()

        material = blender_data.materials.new(batch.texture_name)
        if hasattr(mesh, "materials"):
            mesh.materials.append(material)

        obj = blender_data.objects.new(batch.name, mesh)
        parent_collection.objects.link(obj)
        created += 1
    return created


def _opq_to_uv(vertex: Vec3, origin: Vec3, u_axis: Vec3, v_axis: Vec3, tex_width: float, tex_height: float) -> Vec2:
    point = _sub_vec3(vertex, origin)
    return (_dot_vec3(point, u_axis) / tex_width, _dot_vec3(point, v_axis) / tex_height)


def _to_blender_coords(vertex: Vec3, scale: float) -> Vec3:
    return (vertex[0] * scale, vertex[2] * scale, vertex[1] * scale)


def _sub_vec3(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot_vec3(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
