from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Union

try:
    from .lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3
except ImportError:  # Allows parser tests to import this module directly.
    from lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3


Pathish = Union[str, PathLike[str]]


@dataclass
class LtbPs2WorldInfo:
    properties: str
    light_map_grid_size: float
    extents_min: Vec3
    extents_max: Vec3


@dataclass
class LtbPs2WorldTree:
    root_box_min: Vec3
    root_box_max: Vec3
    child_node_count: int
    terrain_depth: int
    layout: bytes


@dataclass
class LtbPs2ObjectProperty:
    name: str
    code: int
    value: Any


@dataclass
class LtbPs2WorldObject:
    name: str
    properties: list[LtbPs2ObjectProperty]


@dataclass
class LtbPs2WorldObjectData:
    string_list: list[str]
    world_objects: list[LtbPs2WorldObject]


@dataclass
class LtbPs2Plane:
    normal: Vec3
    distance: float


@dataclass
class LtbPs2Surface:
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    flags: int
    texture_index: int
    texture_flags: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LtbPs2DiskVertex:
    vertex_index: int
    packed: bool
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LtbPs2Polygon:
    surface_index: int
    plane_index: int
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    disk_vertices: list[LtbPs2DiskVertex]
    texture_index: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LtbPs2Node:
    poly_index: int
    leaf_index: int
    child_indices: tuple[int, int]


@dataclass
class LtbPs2WorldModel:
    world_name: str
    texture_names: list[str]
    points: list[Vec3]
    planes: list[LtbPs2Plane]
    surfaces: list[LtbPs2Surface]
    polygons: list[LtbPs2Polygon]
    nodes: list[LtbPs2Node]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LithtechLtbPs2:
    version: int
    object_data_pos: int
    render_data_pos: int
    world_info: LtbPs2WorldInfo
    world_tree: LtbPs2WorldTree
    texture_list: list[str]
    world_model_count: int
    world_models: list[LtbPs2WorldModel]
    world_object_data: LtbPs2WorldObjectData
    extras: dict[str, Any] = field(default_factory=dict)


class LtbPs2Parser:
    version = 66

    def parse_file(self, filepath: Pathish) -> LithtechLtbPs2:
        with open(filepath, "rb") as file:
            return self.parse_bytes(file.read())

    def parse_bytes(self, data: bytes) -> LithtechLtbPs2:
        reader = BinaryReader(data)
        version = reader.u32()
        if version != self.version:
            raise ValueError(f"Expected PS2 LTB v66, got v{version}")

        object_data_pos = reader.u32()
        render_data_pos = reader.u32()
        future = [reader.u32() for _ in range(8)]
        world_info = self._read_world_info(reader)
        world_tree = self._read_world_tree(reader)
        world_model_pos = reader.tell()

        reader.seek(object_data_pos)
        world_object_data = self._read_world_object_data(reader)

        reader.seek(world_model_pos)
        texture_list = self._read_texture_list(reader)
        world_model_count = reader.u32()
        world_models = [self._read_world_model_record(reader, texture_list) for _ in range(world_model_count)]

        return LithtechLtbPs2(
            version=version,
            object_data_pos=object_data_pos,
            render_data_pos=render_data_pos,
            world_info=world_info,
            world_tree=world_tree,
            texture_list=texture_list,
            world_model_count=world_model_count,
            world_models=world_models,
            world_object_data=world_object_data,
            extras={"future": future},
        )

    def _read_world_info(self, reader: BinaryReader) -> LtbPs2WorldInfo:
        return LtbPs2WorldInfo(reader.str32(), reader.f32(), reader.vec3(), reader.vec3())

    def _read_world_tree(self, reader: BinaryReader) -> LtbPs2WorldTree:
        root_box_min = reader.vec3()
        root_box_max = reader.vec3()
        child_node_count = reader.u32()
        terrain_depth = reader.u32()
        layout = reader.read(max(1, int(child_node_count * 0.125 + 1)))
        return LtbPs2WorldTree(root_box_min, root_box_max, child_node_count, terrain_depth, layout)

    def _read_world_object_data(self, reader: BinaryReader) -> LtbPs2WorldObjectData:
        object_count = reader.u32()
        string_count = reader.u32()
        header_unknown = (reader.u32(), reader.u32(), reader.u32(), reader.u16(), reader.u16())
        string_list = [reader.str16() for _ in range(string_count)]
        world_objects = [self._read_world_object(reader, string_list) for _ in range(object_count)]
        return LtbPs2WorldObjectData(string_list, world_objects)

    def _read_world_object(self, reader: BinaryReader, string_list: list[str]) -> LtbPs2WorldObject:
        _data_length = reader.u16()
        name = string_list[reader.u32()]
        property_count = reader.u32()
        properties = [self._read_object_property(reader, string_list) for _ in range(property_count)]
        return LtbPs2WorldObject(name, properties)

    def _read_object_property(self, reader: BinaryReader, string_list: list[str]) -> LtbPs2ObjectProperty:
        name = string_list[reader.u32()]
        code = reader.u8()
        _data_length = reader.u16()
        if code == 0:
            value = string_list[reader.u32()]
        elif code in (1, 2):
            value = reader.vec3()
        elif code == 3:
            value = reader.f32()
        elif code == 5:
            value = reader.u8()
        elif code in (4, 6):
            value = reader.u32()
        elif code == 7:
            value = (reader.f32(), reader.f32(), reader.f32(), reader.f32())
        else:
            value = None
        return LtbPs2ObjectProperty(name, code, value)

    def _read_texture_list(self, reader: BinaryReader) -> list[str]:
        texture_count = reader.u32()
        _texture_size = reader.u32()
        return [reader.str16() for _ in range(texture_count)]

    def _read_world_model_record(self, reader: BinaryReader, global_texture_list: list[str]) -> LtbPs2WorldModel:
        next_world_model_pos = reader.u32()
        world_model = self._read_world_model(reader, global_texture_list)
        world_model.extras["next_world_model_pos"] = next_world_model_pos
        reader.seek(next_world_model_pos)
        return world_model

    def _read_world_model(self, reader: BinaryReader, global_texture_list: list[str]) -> LtbPs2WorldModel:
        world_name = reader.str16()
        world_info_flags = reader.u32()
        unknown_value = reader.u32()
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
        name_length = reader.u8()
        texture_count = reader.u8()
        unknown_4 = reader.u16()
        polygon_vertex_counts = [self._read_polygon_vertex_count(reader) for _ in range(poly_count)]

        leaves = [self._read_leaf(reader) for _ in range(leaf_count)]
        planes = [LtbPs2Plane(reader.vec3(), reader.f32()) for _ in range(plane_count)]
        surfaces = [self._read_surface(reader) for _ in range(surface_count)]
        texture_names: list[str] = []
        polygons: list[LtbPs2Polygon] = []
        for i in range(poly_count):
            polygon = self._read_polygon(reader, polygon_vertex_counts[i], surfaces)
            surface = surfaces[polygon.surface_index]
            texture_name = global_texture_list[surface.texture_index]
            if texture_name not in texture_names:
                texture_names.append(texture_name)
            polygon.texture_index = texture_names.index(texture_name)
            polygons.append(polygon)

        nodes = [self._read_node(reader) for _ in range(node_count)]
        user_portals = [self._read_user_portal(reader) for _ in range(user_portal_count)]
        points = []
        point_trailing = []
        for _ in range(point_count):
            points.append(reader.vec3())
            point_trailing.append(reader.f32())

        return LtbPs2WorldModel(
            world_name=world_name,
            texture_names=texture_names,
            points=points,
            planes=planes,
            surfaces=surfaces,
            polygons=polygons,
            nodes=nodes,
            extras={
                "world_info_flags": world_info_flags,
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
                "name_length": name_length,
                "texture_count": texture_count,
                "unknown_4": unknown_4,
                "polygon_vertex_counts": polygon_vertex_counts,
                "leaves": leaves,
                "user_portals": user_portals,
                "point_trailing": point_trailing,
            },
        )

    def _read_polygon_vertex_count(self, reader: BinaryReader) -> int:
        count = reader.u8()
        _extra = reader.u8()
        return count

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

    def _read_surface(self, reader: BinaryReader) -> LtbPs2Surface:
        uv_origin = reader.vec3()
        uv_u = reader.vec3()
        uv_v = reader.vec3()
        start_index = reader.u32()
        flags = reader.u32()
        texture_index = reader.u32()
        texture_flags = reader.u16()
        use_effects = reader.u16()
        effect_name = ""
        effect_param = ""
        if use_effects == 1:
            effect_name = reader.str16()
            effect_param = reader.str16()
        return LtbPs2Surface(
            uv_origin=uv_origin,
            uv_u=uv_u,
            uv_v=uv_v,
            flags=flags,
            texture_index=texture_index,
            texture_flags=texture_flags,
            extras={
                "start_index": start_index,
                "use_effects": use_effects,
                "effect_name": effect_name,
                "effect_param": effect_param,
            },
        )

    def _read_polygon(
        self,
        reader: BinaryReader,
        vertex_count: int,
        surfaces: list[LtbPs2Surface],
    ) -> LtbPs2Polygon:
        unknown_1 = reader.u32()
        lightmap_width = reader.u8()
        lightmap_height = reader.u8()
        unknown_2 = reader.u8()
        unknown_3 = reader.u8()
        surface_index = reader.u32()
        plane_index = reader.u32()
        uv_offset_1 = reader.f32()
        center = reader.vec3()
        uv_offset_2 = reader.f32()
        surface = surfaces[surface_index]
        is_packed = (surface.flags & (1 << 2)) != 0
        disk_vertices = [self._read_disk_vertex(reader, is_packed) for _ in range(vertex_count)]
        return LtbPs2Polygon(
            surface_index=surface_index,
            plane_index=plane_index,
            uv_origin=surface.uv_origin,
            uv_u=surface.uv_u,
            uv_v=surface.uv_v,
            disk_vertices=disk_vertices,
            extras={
                "unknown_1": unknown_1,
                "lightmap_width": lightmap_width,
                "lightmap_height": lightmap_height,
                "unknown_2": unknown_2,
                "unknown_3": unknown_3,
                "uv_offset_1": uv_offset_1,
                "uv_offset_2": uv_offset_2,
                "center": center,
            },
        )

    def _read_disk_vertex(self, reader: BinaryReader, is_packed: bool) -> LtbPs2DiskVertex:
        if is_packed:
            return LtbPs2DiskVertex(reader.u32(), True)

        vertex_index = reader.u16()
        dummy = reader.read(2)
        unknown_floats = (reader.f32(), reader.f32(), reader.f32())
        peek = reader.u32()
        if peek < 60000 or peek == 0xFFFFFFFF:
            reader.seek(reader.tell() - 4)
            peek = None
        return LtbPs2DiskVertex(
            vertex_index,
            False,
            {"dummy": dummy, "unknown_floats": unknown_floats, "optional_hack": peek},
        )

    def _read_node(self, reader: BinaryReader) -> LtbPs2Node:
        return LtbPs2Node(reader.u32(), reader.u32(), (reader.u32(), reader.u32()))

    def _read_user_portal(self, reader: BinaryReader) -> dict[str, Any]:
        return {
            "name": reader.str16(),
            "unknown_1": reader.u32(),
            "unknown_2": reader.u32(),
            "unknown_short": reader.u16(),
            "center": reader.vec3(),
            "dims": reader.vec3(),
        }


def detect_ltb_ps2_version(filepath: Pathish) -> int:
    with open(filepath, "rb") as file:
        data = file.read(4)
    if len(data) != 4:
        raise ValueError("LTB file is too small to contain a version field.")
    return int.from_bytes(data, "little", signed=False)


def parse_ltb_ps2_file(filepath: Pathish) -> LithtechLtbPs2:
    return LtbPs2Parser().parse_file(filepath)


def extract_ltb_ps2_mesh_batches(dat: LithtechLtbPs2, texture_size: tuple[float, float] = (256.0, 256.0)) -> list[MeshBatch]:
    batches: dict[str, MeshBatch] = {}
    tex_width, tex_height = texture_size
    for world_model in dat.world_models:
        for polygon in world_model.polygons:
            texture_name = world_model.texture_names[polygon.texture_index]
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
                batch.uv0.append(_opq_to_uv(vertex, polygon.uv_origin, polygon.uv_u, polygon.uv_v, tex_width, tex_height))
            for i in range(1, len(polygon.disk_vertices) - 1):
                batch.triangles.append((start_index, start_index + i, start_index + i + 1))
                batch.lightmap_refs.append(None)
    return list(batches.values())


def create_ltb_ps2_blender_meshes(blender_data, parent_collection, dat: LithtechLtbPs2, scale: float = 0.01) -> int:
    created = 0
    for batch in extract_ltb_ps2_mesh_batches(dat):
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
