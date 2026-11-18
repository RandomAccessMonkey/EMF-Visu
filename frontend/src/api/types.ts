// Aliases over the types generated from the backend's OpenAPI schema (`pnpm gen:api`).
// Nothing here is hand-maintained: if the backend contract changes, regeneration breaks the build.
import type { components } from './schema'

type S = components['schemas']

export type Scene = S['Scene']
export type SceneObject = S['SceneObject']
export type Transform = S['Transform']
export type Domain = S['Domain']
export type Role = S['Role']
export type Primitive = SceneObject['primitive']
export type PrimitiveType = Primitive['type']
// `passive` (Phase 4C) has a default on the server; optional here.
export type SolveRequest = Omit<S['SolveRequest'], 'passive'> & { passive?: S['PassiveFilament'][] }
export type Sampling = SolveRequest['samplings'][number]
export type PlaneGridSampling = S['PlaneGridSampling']
export type LatticeSampling = S['LatticeSampling']
export type ResultHeader = S['ResultHeader']
export type ArrayEntry = S['ArrayEntry']
export type FieldLineInfo = S['FieldLineInfo']
export type FieldLineSet = S['FieldLineSet']
export type MethodInfo = S['MethodInfo']
export type ProbeContribution = S['ProbeContribution']
export type ProbeValue = S['ProbeValue']
export type PointSourceInfo = S['PointSourceInfo']
export type LocalizedText = S['LocalizedText']
export type EquationView = S['EquationView']
export type EquationsResponse = S['EquationsResponse']
export type EquationStatus = EquationView['status']
export type Preset = S['Preset']
export type SolverStatus = S['SolverStatus']
export type Health = S['Health']
export type ProbeResponse = S['ProbeResponse']
export type JobStatus = S['JobStatus']
export type JobCreated = S['JobCreated']
export type ProjectSummary = S['ProjectSummary']
export type ProjectOut = S['ProjectOut']
export type ErrorBody = S['ErrorBody']
export type Vec3 = [number, number, number]
export type GaussSurface = S['GaussSurface']
export type SurfaceShape = GaussSurface['shape']
export type SurfaceDisplay = S['SurfaceDisplay']
export type GaussSituation = S['GaussSituation']
export type FluxHeader = S['FluxHeader']
export type SurfaceFlux = S['SurfaceFlux']
export type ChargeFlux = S['ChargeFlux']
export type SubdivisionResult = S['SubdivisionResult']
export type CellResult = S['CellResult']
export type MeshInfo = S['MeshInfo']
export type CurrentSourceInfo = S['CurrentSourceInfo']
export type ProbeMagnetic = S['ProbeMagnetic']
export type MagneticContribution = S['MagneticContribution']
export type PresetVariant = S['PresetVariant']
export type Source = NonNullable<SceneObject['source']>
export type FieldKind = 'electric' | 'magnetic'
// Phase 3B
export type AmperePath = S['AmperePath']
export type PathShape = AmperePath['shape']
export type PathDisplay = S['PathDisplay']
export type AmpereHeader = S['AmpereHeader']
export type PathResult = S['PathResult']
export type AmpereCrossing = S['Crossing']
export type OneSidedValue = S['OneSidedValue']
export type ProbeComparison = S['ProbeComparison']
export type ViewHint = S['ViewHint']
// Phase 4A
export type CurrentProfile = NonNullable<Extract<Source, { type: 'circular_loop' }>['profile']>
export type InductionHeader = S['InductionHeader']
export type SurfaceResult = S['SurfaceResult']
export type SourceFlux = S['SourceFlux']
export type MutualInfo = S['Mutual']
export type TimeSourceInfo = S['TimeSourceInfo']
export type TimeHint = S['TimeHint']
export type ProfileSamples = S['ProfileSamples']
// Phase 4B
export type FluxSurface = S['FluxSurface']
export type FluxShape = FluxSurface['shape']
export type SlidingRodShape = S['SlidingRodShape']
export type MotionProfile = S['MotionProfile']
export type Translation = NonNullable<MotionProfile['translation']>
export type Rotation = NonNullable<MotionProfile['rotation']>
export type MotionState = S['MotionState']
export type MotionalSample = S['MotionalSample']
export type VelocityConvention = 'undefined' | 'left' | 'right'
/** Server responses always carry every field (defaults are serialized). */
export type TrajectorySettings = Required<S['TrajectorySettings']>
export type TestCharge = Required<Omit<S['TestCharge'], 'trajectory'>> & { trajectory: TrajectorySettings }
export type LorentzRequest = S['LorentzRequest']
export type LorentzResult = S['LorentzResult']
export type ParticleRequest = S['ParticleRequest']
export type TrajectoryResult = S['TrajectoryResult']
export type TrajectorySample = S['TrajectorySample']
// Phase 4C
export type PassiveCircuit = S['PassiveCircuit']
export type Electrical = S['Electrical']
export type Mechanics = S['Mechanics']
export type EddyDisk = S['EddyDisk']
export type CircuitResult = S['CircuitResult']
export type CircuitSeries = S['CircuitSeries']
export type ElementInfo = S['ElementInfo']
export type MatrixInfo = S['MatrixInfo']
export type PassiveFilament = S['PassiveFilament']
export type PassiveProbe = S['PassiveProbe']
