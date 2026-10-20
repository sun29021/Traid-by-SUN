// Friendly names for the generated API schema types (schema.d.ts is generated; never edit it).
import type { components } from './schema';

type Schemas = components['schemas'];

export type Health = Schemas['Health'];
export type Welcome = Schemas['Welcome'];
export type SystemStatus = Schemas['SystemStatus'];
export type Task = Schemas['TaskOut'];
export type TaskStatus = Task['status'];
export type AuditEvent = Schemas['AuditEventOut'];

export type Profile = Schemas['ProfileOut'];
export type ProfileStatus = Profile['status'];
export type SurfaceType = Profile['surface_type'];
export type ProfileCreate = Schemas['ProfileCreate'];
export type ProfileUpdate = Schemas['ProfileUpdate'];
export type CoverageItem = Schemas['CoverageItem'];
export type FileRef = Schemas['FileRef'];
export type Reference = Schemas['ReferenceOut'];
export type ReferenceStatus = Reference['status'];
export type ReferenceUpload = Schemas['ReferenceUpload'];
export type ReferenceChange = Schemas['ReferenceChange'];
export type UploadIssue = Schemas['UploadIssue'];
export type Glyph = Schemas['GlyphOut'];
export type GlyphStatus = Glyph['status'];
export type GlyphBulk = Schemas['GlyphBulk'];
export type BulkResult = Schemas['BulkResult'];
