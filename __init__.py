import bpy
import mathutils
import math

class VIEW3D_PT_BoneToMeshPanel(bpy.types.Panel):
    bl_label = "Bone To Mesh Gen 2.0"
    bl_description = "Create a mesh from the selected bone"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Manuel's Bone Gen 2.0"

    def draw(self, context):
        layout = self.layout
        bone_to_mesh_enabled = (context.active_object is not None
                                and context.active_object.type == 'ARMATURE'
                                and context.active_object.mode == 'OBJECT')

        row = layout.row()
        row.enabled = bone_to_mesh_enabled
        row.operator("object.bone_to_mesh", text="Create Mesh", icon='MESH_CUBE')

        if not bone_to_mesh_enabled:
            info_row = layout.row()
            info_row.alert = True
            info_row.label(text="Select an armature first", icon='ERROR')

        layout.prop(context.scene, "bone_mesh_segments")
        layout.prop(context.scene, "bone_mesh_rings")

def meshFromArmature(arm):
    name = arm.name + "_mesh"
    meshData = bpy.data.meshes.new(name + "Data")
    meshObj = bpy.data.objects.new(name, meshData)
    meshObj.matrix_world = arm.matrix_world.copy()
    return meshObj

def boneGeometry(l1, l2, x, z, base, roll):
    bone_length = (l2 - l1).length
    radius = bone_length * 0.15
    x1 = x * radius
    z1 = z * radius

    verts = [l1, l2, l1 + x1, l1 - x1, l1 + z1, l1 - z1]
    translation_vector = (l2 - l1) * 0.1
    for i in range(2, len(verts)):
        verts[i] += translation_vector

    rotation_matrix = mathutils.Matrix.Rotation(roll, 4, (l2 - l1).normalized())
    additional_rotation = mathutils.Matrix.Rotation(math.radians(45), 4, (l2 - l1).normalized())
    rotation_matrix @= additional_rotation

    for i in range(2, len(verts)):
        verts[i] = (rotation_matrix @ (verts[i] - l1)) + l1

    faces = [
        (base, base + 2, base + 4),
        (base, base + 4, base + 3),
        (base, base + 3, base + 5),
        (base, base + 5, base + 2),
        (base + 1, base + 2, base + 4),
        (base + 1, base + 4, base + 3),
        (base + 1, base + 3, base + 5),
        (base + 1, base + 5, base + 2),
    ]
    return verts, faces

def create_uv_sphere(center, radius, segments=8, rings=4):
    verts = []
    faces = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segments):
            theta = 2 * math.pi * j / segments
            x = center.x + radius * math.sin(phi) * math.cos(theta)
            y = center.y + radius * math.sin(phi) * math.sin(theta)
            z = center.z + radius * math.cos(phi)
            verts.append(mathutils.Vector((x, y, z)))

    for i in range(rings):
        for j in range(segments):
            a = i * segments + j
            b = a + segments
            c = b + 1 if (j + 1) < segments else b + 1 - segments
            d = a + 1 if (j + 1) < segments else a + 1 - segments
            faces.append((a, b, c, d))
    return verts, faces

def processArmature(self, context, arm, segments, rings, genVertexGroups=True):
    self.report({'INFO'}, f"Processing armature: {arm.name}")
    meshObj = meshFromArmature(arm)
    context.collection.objects.link(meshObj)

    verts = []
    edges = []
    faces = []
    vertexGroups = {}
    seen_points = set()

    prev_mode = arm.mode
    bpy.ops.object.mode_set(mode='EDIT')

    try:
        for editBone in [b for b in arm.data.edit_bones if b.use_deform]:
            boneName = editBone.name

            editBoneHead = editBone.head
            editBoneTail = editBone.tail
            editBoneX = editBone.x_axis
            editBoneZ = editBone.z_axis

            bone_length = (editBoneTail - editBoneHead).length
            sphere_radius = bone_length * 0.1

            baseIndex = len(verts)
            newVerts, newFaces = boneGeometry(editBoneHead, editBoneTail, editBoneX, editBoneZ, baseIndex, editBone.roll)
            verts.extend(newVerts)
            faces.extend(newFaces)

            # Add head sphere if not already seen
            head_key = tuple(round(c, 5) for c in editBoneHead)
            if head_key not in seen_points:
                headVerts, headFaces = create_uv_sphere(editBoneHead, sphere_radius, segments, rings)
                headBase = len(verts)
                verts.extend(headVerts)
                faces.extend([(headBase + v0, headBase + v1, headBase + v2, headBase + v3) for (v0, v1, v2, v3) in headFaces])
                seen_points.add(head_key)

            # Add tail sphere if not already seen
            tail_key = tuple(round(c, 5) for c in editBoneTail)
            if tail_key not in seen_points:
                tailVerts, tailFaces = create_uv_sphere(editBoneTail, sphere_radius, segments, rings)
                tailBase = len(verts)
                verts.extend(tailVerts)
                faces.extend([(tailBase + v0, tailBase + v1, tailBase + v2, tailBase + v3) for (v0, v1, v2, v3) in tailFaces])
                seen_points.add(tail_key)

            vertexGroups[boneName] = [(x, 1.0) for x in range(baseIndex, len(verts))]

        meshObj.data.from_pydata(verts, edges, faces)

    except Exception as e:
        self.report({'ERROR'}, f"Error processing armature: {str(e)}")
    finally:
        bpy.ops.object.mode_set(mode=prev_mode)

    if genVertexGroups:
        for name, vertexGroup in vertexGroups.items():
            groupObject = meshObj.vertex_groups.new(name=name)
            for (index, weight) in vertexGroup:
                groupObject.add([index], weight, 'REPLACE')

    modifier = meshObj.modifiers.new('ArmatureMod', 'ARMATURE')
    modifier.object = arm
    modifier.use_bone_envelopes = False
    modifier.use_vertex_groups = True

    meshObj.data.update()
    return meshObj

def createMesh(self, context):
    obj = context.active_object
    segments = context.scene.bone_mesh_segments
    rings = context.scene.bone_mesh_rings

    if obj is None:
        self.report({'ERROR'}, "No selection")
        return False
    elif obj.type != 'ARMATURE':
        self.report({'WARNING'}, "Armature expected")
        return False
    else:
        processArmature(self, context, obj, segments, rings)
        return True

class BoneToMeshOperator(bpy.types.Operator):
    bl_idname = "object.bone_to_mesh"
    bl_label = "Create Mesh from Bones"
    bl_description = "Create a mesh from the selected bone"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if createMesh(self, context):
            return {'FINISHED'}
        return {'CANCELLED'}

def register():
    bpy.utils.register_class(VIEW3D_PT_BoneToMeshPanel)
    bpy.utils.register_class(BoneToMeshOperator)
    bpy.types.Scene.bone_mesh_segments = bpy.props.IntProperty(name="Sphere Segments", default=8, min=3, max=64)
    bpy.types.Scene.bone_mesh_rings = bpy.props.IntProperty(name="Sphere Rings", default=4, min=2, max=64)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_BoneToMeshPanel)
    bpy.utils.unregister_class(BoneToMeshOperator)
    del bpy.types.Scene.bone_mesh_segments
    del bpy.types.Scene.bone_mesh_rings

if __name__ == "__main__":
    register()
