from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Union

try:
    from .lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3
except ImportError:  # Allows parser tests to import this module directly.
    from lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3


Pathish = Union[str, PathLike[str]]


@dataclass
class V56WorldInfo:
    properties: str
    unknown: list[int]


@dataclass
class V56Plane:
    normal: Vec3
    distance: float


@dataclass
class V56Surface:
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    color: Vec3
    texture_index: int
    flags: int
    texture_flags: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V56DiskVertex:
    vertex_index: int
    color: tuple[int, int, int]


@dataclass
class V56InlineLightmap:
    world_model_index: int
    poly_index: int
    width: int
    height: int
    data: list[int]

    @property
    def ref(self) -> str:
        return f"inline:{self.world_model_index}:{self.poly_index}"


@dataclass
class V56Polygon:
    lightmap_width: int
    lightmap_height: int
    surface_index: int
    disk_vertices: list[V56DiskVertex]
    lightmap: V56InlineLightmap | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V56Node:
    poly_index: int
    leaf_index: int
    child_indices: tuple[int, int]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V56WorldModel:
    world_name: str
    world_info_flags: int
    texture_names: list[str]
    points: list[Vec3]
    planes: list[V56Plane]
    surfaces: list[V56Surface]
    polygons: list[V56Polygon]
    nodes: list[V56Node]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LithtechDatV56:
    version: int
    object_data_pos: int
    render_data_pos: int
    world_info: V56WorldInfo
    world_model_count: int
    world_models: list[V56WorldModel]
    world_object_count: int


class LithtechDatV56Parser:
    version = 56

    def parse_file(self, filepath: Pathish) -> LithtechDatV56:
        with open(filepath, "rb") as file:
            return self.parse_bytes(file.read())

    def parse_bytes(self, data: bytes) -> LithtechDatV56:
        reader = BinaryReader(data)
        version = reader.u32()
        if version != self.version:
            raise ValueError(f"Expected DAT v56, got DAT v{version}")

        object_data_pos = reader.u32()
        render_data_pos = reader.u32()
        world_info = self._read_world_info(reader)

        reader.seek(object_data_pos)
        world_object_count = self._read_world_object_data(reader)
        world_models = [self._read_world_model_record(reader, 0)]
        additional_world_model_count = reader.u32()
        for world_model_index in range(1, additional_world_model_count + 1):
            world_models.append(self._read_world_model_record(reader, world_model_index))

        return LithtechDatV56(
            version=version,
            object_data_pos=object_data_pos,
            render_data_pos=render_data_pos,
            world_info=world_info,
            world_model_count=len(world_models),
            world_models=world_models,
            world_object_count=world_object_count,
        )

    def _read_world_info(self, reader: BinaryReader) -> V56WorldInfo:
        return V56WorldInfo(reader.str32(), [reader.u32() for _ in range(8)])

    def _read_world_object_data(self, reader: BinaryReader) -> int:
        world_object_count = reader.u32()
        for _ in range(world_object_count):
            self._read_world_object(reader)
        return world_object_count

    def _read_world_object(self, reader: BinaryReader) -> None:
        _data_length = reader.u16()
        _object_type = reader.str16()
        property_count = reader.u32()
        for _ in range(property_count):
            self._read_world_object_property(reader)

    def _read_world_object_property(self, reader: BinaryReader) -> None:
        _name = reader.str16()
        code = reader.u8()
        _flags = reader.u32()
        data_length = reader.u16()
        value_start = reader.tell()

        if code == 0:
            reader.str16()
        elif code in (1, 2):
            reader.read(12)
        elif code == 3:
            reader.read(4)
        elif code == 5:
            reader.read(1)
        elif code in (4, 6, 9):
            reader.read(4)
        elif code == 7:
            reader.read(16)

        consumed = reader.tell() - value_start
        if consumed < data_length:
            reader.read(data_length - consumed)

    def _read_world_model_record(self, reader: BinaryReader, world_model_index: int) -> V56WorldModel:
        next_world_model_pos = reader.u32()
        dummy_prefix = reader.read(32)
        world_model = self._read_world_model(reader, world_model_index)
        world_model.extras["next_world_model_pos"] = next_world_model_pos
        world_model.extras["dummy_prefix"] = dummy_prefix
        return world_model

    def _read_world_model(self, reader: BinaryReader, world_model_index: int) -> V56WorldModel:
        world_info_flags = reader.u32()
        world_name = reader.str16()
        next_position = reader.u32()

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
        min_box = reader.vec3()
        max_box = reader.vec3()
        world_translation = reader.vec3()
        texture_names_size = reader.u32()
        texture_count = reader.u32()
        texture_names = [reader.cstring() for _ in range(texture_count)]
        polygon_vertex_counts = [reader.u8() + reader.u8() for _ in range(poly_count)]

        leaves = [self._read_leaf(reader) for _ in range(leaf_count)]
        planes = [V56Plane(reader.vec3(), reader.f32()) for _ in range(plane_count)]
        surfaces = [self._read_surface(reader) for _ in range(surface_count)]
        polygons = [self._read_polygon(reader, polygon_vertex_counts[i]) for i in range(poly_count)]
        nodes = [self._read_node(reader) for _ in range(node_count)]
        user_portals = [self._read_user_portal(reader) for _ in range(user_portal_count)]
        points = [reader.vec3() for _ in range(point_count)]
        pblock_table = self._read_pblock_table(reader)
        root_node_index = reader.u32()
        unknown_count = reader.u32()
        polygon_list = [reader.vec3() for _ in range(poly_count)]
        inline_lightmap_count = reader.u32()
        if inline_lightmap_count > 0:
            self._attach_inline_lightmaps(reader, world_model_index, surfaces, polygons)

        return V56WorldModel(
            world_name=world_name,
            world_info_flags=world_info_flags,
            texture_names=texture_names,
            points=points,
            planes=planes,
            surfaces=surfaces,
            polygons=polygons,
            nodes=nodes,
            extras={
                "next_position": next_position,
                "unknown_value_2": unknown_value_2,
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
                "unknown_count": unknown_count,
                "polygon_list": polygon_list,
                "inline_lightmap_count": inline_lightmap_count,
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
        polygon_count = reader.u16()
        data["polygon_data"] = reader.read(polygon_count * 4)
        data["unknown"] = reader.f32()
        return data

    def _read_surface(self, reader: BinaryReader) -> V56Surface:
        uv_origin = reader.vec3()
        uv_u = reader.vec3()
        uv_v = reader.vec3()
        uv4 = reader.vec3()
        uv5 = reader.vec3()
        color = reader.vec3()
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
        return V56Surface(
            uv_origin=uv_origin,
            uv_u=uv_u,
            uv_v=uv_v,
            color=color,
            texture_index=texture_index,
            flags=flags,
            texture_flags=texture_flags,
            extras={
                "uv4": uv4,
                "uv5": uv5,
                "unknown": unknown,
                "unknown2": unknown2,
                "use_effects": use_effects,
                "effect_name": effect_name,
                "effect_param": effect_param,
            },
        )

    def _read_polygon(self, reader: BinaryReader, vertex_count: int) -> V56Polygon:
        lightmap_width = reader.u16()
        lightmap_height = reader.u16()
        unknown_1 = reader.u32()
        unknown_2 = reader.u32()
        surface_index = reader.u32()
        disk_vertices = [self._read_disk_vertex(reader) for _ in range(vertex_count)]
        return V56Polygon(
            lightmap_width=lightmap_width,
            lightmap_height=lightmap_height,
            surface_index=surface_index,
            disk_vertices=disk_vertices,
            extras={"unknown_1": unknown_1, "unknown_2": unknown_2},
        )

    def _read_disk_vertex(self, reader: BinaryReader) -> V56DiskVertex:
        return V56DiskVertex(reader.u16(), tuple(reader.read(3)))

    def _read_node(self, reader: BinaryReader) -> V56Node:
        unknown_intro = reader.u32()
        poly_index = reader.u32()
        leaf_index = reader.u16()
        child_indices = (reader.u32(), reader.u32())
        quat = (reader.f32(), reader.f32(), reader.f32(), reader.f32())
        return V56Node(poly_index, leaf_index, child_indices, {"unknown_intro": unknown_intro, "quat": quat})

    def _read_user_portal(self, reader: BinaryReader) -> dict[str, Any]:
        return {
            "name": reader.str16(),
            "unknown_1": reader.u32(),
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

    def _attach_inline_lightmaps(
        self,
        reader: BinaryReader,
        world_model_index: int,
        surfaces: list[V56Surface],
        polygons: list[V56Polygon],
    ) -> None:
        for poly_index, polygon in enumerate(polygons):
            surface = surfaces[polygon.surface_index]
            if not surface.flags & (1 << 7):
                continue
            width = reader.u8()
            height = reader.u8()
            data: list[int] = []
            for _ in range(width * height):
                data.extend(decode_v56_packed_lightmap_color(reader.u16()))
            polygon.lightmap = V56InlineLightmap(world_model_index, poly_index, width, height, data)


def parse_dat_v56_file(filepath: Pathish) -> LithtechDatV56:
    return LithtechDatV56Parser().parse_file(filepath)


def decode_v56_packed_lightmap_color(packed_color: int) -> list[int]:
    return [
        (packed_color & 0xF800) >> 8,
        (packed_color & 0x07E0) >> 3,
        (packed_color & 0x001F) << 3,
    ]


def extract_v56_mesh_batches(dat: LithtechDatV56, texture_size: tuple[float, float] = (256.0, 256.0)) -> list[MeshBatch]:
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

            for disk_vertex in polygon.disk_vertices:
                vertex = world_model.points[disk_vertex.vertex_index]
                batch.vertices.append(vertex)
                batch.normals.append(surface.color)
                batch.uv0.append(_opq_to_uv(vertex, surface.uv_origin, surface.uv_u, surface.uv_v, tex_width, tex_height))
                batch.vertex_colors.append(disk_vertex.color)

            for i in range(1, len(polygon.disk_vertices) - 1):
                batch.triangles.append((start_index, start_index + i, start_index + i + 1))
                batch.lightmap_refs.append(polygon.lightmap.ref if polygon.lightmap else None)

    return list(batches.values())


def create_v56_blender_meshes(blender_data, parent_collection, dat: LithtechDatV56, scale: float = 0.01) -> int:
    created = 0
    for batch in extract_v56_mesh_batches(dat):
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
