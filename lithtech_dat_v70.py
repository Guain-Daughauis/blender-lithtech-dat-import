from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Union

try:
    from .lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3
except ImportError:  # Allows parser tests to import this module directly.
    from lithtech_dat_v66 import BinaryReader, MeshBatch, Vec2, Vec3


Pathish = Union[str, PathLike[str]]


@dataclass
class V70WorldInfo:
    properties: str
    light_map_grid_size: float
    extents_min: Vec3
    extents_max: Vec3


@dataclass
class V70WorldTree:
    root_box_min: Vec3
    root_box_max: Vec3
    child_node_count: int
    terrain_depth: int
    layout: bytes


@dataclass
class V70Plane:
    normal: Vec3
    distance: float


@dataclass
class V70Surface:
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    texture_index: int
    flags: int
    texture_flags: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V70DiskVertex:
    vertex_index: int
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V70Polygon:
    center: Vec3
    lightmap_width: int
    lightmap_height: int
    surface_index: int
    plane_index: int
    uv_origin: Vec3
    uv_u: Vec3
    uv_v: Vec3
    disk_vertices: list[V70DiskVertex]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class V70Node:
    poly_index: int
    leaf_index: int
    child_indices: tuple[int, int]


@dataclass
class V70WorldModel:
    world_name: str
    world_info_flags: int
    texture_names: list[str]
    points: list[Vec3]
    planes: list[V70Plane]
    surfaces: list[V70Surface]
    polygons: list[V70Polygon]
    nodes: list[V70Node]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class LithtechDatV70:
    version: int
    object_data_pos: int
    render_data_pos: int
    world_info: V70WorldInfo
    world_tree: V70WorldTree
    world_model_count: int
    world_models: list[V70WorldModel]
    world_object_count: int
    extras: dict[str, Any] = field(default_factory=dict)


class LithtechDatV70Parser:
    version = 70

    def parse_file(self, filepath: Pathish) -> LithtechDatV70:
        with open(filepath, "rb") as file:
            return self.parse_bytes(file.read())

    def parse_bytes(self, data: bytes) -> LithtechDatV70:
        reader = BinaryReader(data)
        version = reader.u32()
        if version != self.version:
            raise ValueError(f"Expected DAT v70, got DAT v{version}")

        object_data_pos = reader.u32()
        render_data_pos = reader.u32()
        future = [reader.u32() for _ in range(8)]
        world_info = self._read_world_info(reader)
        world_tree = self._read_world_tree(reader)
        world_model_pos = reader.tell()

        reader.seek(object_data_pos)
        world_object_count = reader.u32()

        reader.seek(world_model_pos)
        world_model_count = reader.u32()
        world_models = [self._read_world_model_record(reader) for _ in range(world_model_count)]

        return LithtechDatV70(
            version=version,
            object_data_pos=object_data_pos,
            render_data_pos=render_data_pos,
            world_info=world_info,
            world_tree=world_tree,
            world_model_count=world_model_count,
            world_models=world_models,
            world_object_count=world_object_count,
            extras={"future": future, "external_lightmap_offset_present": render_data_pos != reader.length()},
        )

    def _read_world_info(self, reader: BinaryReader) -> V70WorldInfo:
        return V70WorldInfo(
            properties=reader.str32(),
            light_map_grid_size=reader.f32(),
            extents_min=reader.vec3(),
            extents_max=reader.vec3(),
        )

    def _read_world_tree(self, reader: BinaryReader) -> V70WorldTree:
        root_box_min = reader.vec3()
        root_box_max = reader.vec3()
        child_node_count = reader.u32()
        terrain_depth = reader.u32()
        layout = reader.read(max(1, int(child_node_count * 0.125 + 1)))
        return V70WorldTree(root_box_min, root_box_max, child_node_count, terrain_depth, layout)

    def _read_world_model_record(self, reader: BinaryReader) -> V70WorldModel:
        next_world_model_pos = reader.u32()
        dummy_prefix = reader.read(32)
        world_model = self._read_world_model(reader)
        world_model.extras["next_world_model_pos"] = next_world_model_pos
        world_model.extras["dummy_prefix"] = dummy_prefix
        if world_model.extras.get("section_count", 0) > 0:
            reader.seek(next_world_model_pos)
        return world_model

    def _read_world_model(self, reader: BinaryReader) -> V70WorldModel:
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
        planes = [V70Plane(reader.vec3(), reader.f32()) for _ in range(plane_count)]
        surfaces = [self._read_surface(reader) for _ in range(surface_count)]
        points = [reader.vec3() for _ in range(point_count)]
        polygons = [self._read_polygon(reader, polygon_vertex_counts[i]) for i in range(poly_count)]
        nodes = [self._read_node(reader) for _ in range(node_count)]
        user_portals = [self._read_user_portal(reader) for _ in range(user_portal_count)]

        pblock_table = self._read_pblock_table(reader)
        root_node_index = reader.u32()
        section_count = reader.u32()

        return V70WorldModel(
            world_name=world_name,
            world_info_flags=world_info_flags,
            texture_names=texture_names,
            points=points,
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

    def _read_surface(self, reader: BinaryReader) -> V70Surface:
        uv_origin = reader.vec3()
        uv_u = reader.vec3()
        uv_v = reader.vec3()
        texture_index = reader.u16()
        flags = reader.u32()
        unknown2 = reader.u32()
        use_effects = reader.u8()
        effect_name = ""
        effect_param = ""
        if use_effects == 1:
            effect_name = reader.str16()
            effect_param = reader.str16()
        texture_flags = reader.u16()
        return V70Surface(
            uv_origin=uv_origin,
            uv_u=uv_u,
            uv_v=uv_v,
            texture_index=texture_index,
            flags=flags,
            texture_flags=texture_flags,
            extras={
                "unknown2": unknown2,
                "use_effects": use_effects,
                "effect_name": effect_name,
                "effect_param": effect_param,
            },
        )

    def _read_polygon(self, reader: BinaryReader, vertex_count: int) -> V70Polygon:
        center = reader.vec3()
        lightmap_width = reader.u16()
        lightmap_height = reader.u16()
        unknown_flag = reader.u16()
        unknown_list = [reader.u16() for _ in range(unknown_flag * 2)]
        surface_index = reader.u32()
        plane_index = reader.u32()
        uv_origin = reader.vec3()
        uv_u = reader.vec3()
        uv_v = reader.vec3()
        disk_vertices = [self._read_disk_vertex(reader) for _ in range(vertex_count)]
        return V70Polygon(
            center=center,
            lightmap_width=lightmap_width,
            lightmap_height=lightmap_height,
            surface_index=surface_index,
            plane_index=plane_index,
            uv_origin=uv_origin,
            uv_u=uv_u,
            uv_v=uv_v,
            disk_vertices=disk_vertices,
            extras={"unknown_flag": unknown_flag, "unknown_list": unknown_list},
        )

    def _read_disk_vertex(self, reader: BinaryReader) -> V70DiskVertex:
        return V70DiskVertex(reader.u16(), {"dummy": reader.read(3)})

    def _read_node(self, reader: BinaryReader) -> V70Node:
        return V70Node(reader.u32(), reader.u16(), (reader.u32(), reader.u32()))

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


def parse_dat_v70_file(filepath: Pathish) -> LithtechDatV70:
    return LithtechDatV70Parser().parse_file(filepath)


def extract_v70_mesh_batches(dat: LithtechDatV70, texture_size: tuple[float, float] = (256.0, 256.0)) -> list[MeshBatch]:
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
                batch.uv0.append(_opq_to_uv(vertex, polygon.uv_origin, polygon.uv_u, polygon.uv_v, tex_width, tex_height))

            for i in range(1, len(polygon.disk_vertices) - 1):
                batch.triangles.append((start_index, start_index + i, start_index + i + 1))
                batch.lightmap_refs.append(None)

    return list(batches.values())


def create_v70_blender_meshes(blender_data, parent_collection, dat: LithtechDatV70, scale: float = 0.01) -> int:
    created = 0
    for batch in extract_v70_mesh_batches(dat):
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

