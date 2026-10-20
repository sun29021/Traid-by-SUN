// Friendly names for the generated API schema types (schema.d.ts is generated; never edit it).
import type { components } from './schema';

type Schemas = components['schemas'];

export type Health = Schemas['Health'];
export type Welcome = Schemas['Welcome'];
export type SystemStatus = Schemas['SystemStatus'];
export type Task = Schemas['TaskOut'];
export type TaskStatus = Task['status'];
export type AuditEvent = Schemas['AuditEventOut'];
