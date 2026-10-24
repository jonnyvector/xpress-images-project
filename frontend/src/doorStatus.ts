// Where a door is in its life: upload → learn → approve replica → variants.
import type { Project } from './types';

type DoorStage = 'empty' | 'not_learned' | 'replica_pending' | 'ready' | 'variants';

export function doorStage(p: Project): DoorStage {
  if (p.results.length > 0 && p.has_signature) return 'variants';
  if (p.has_signature) return p.replica_approved ? 'ready' : 'replica_pending';
  if (p.results.length > 0) return 'variants'; // imported images, no learned style
  return p.upload_filename ? 'not_learned' : 'empty';
}

export function stageLabel(p: Project): string {
  switch (doorStage(p)) {
    case 'empty':
      return 'No image yet';
    case 'not_learned':
      return 'Not learned';
    case 'replica_pending':
      return 'Replica to approve';
    case 'ready':
      return 'Ready to generate';
    case 'variants':
      return `${p.results.length} variant${p.results.length === 1 ? '' : 's'}`;
  }
}

export function needsAttention(p: Project): boolean {
  const stage = doorStage(p);
  return stage === 'not_learned' || stage === 'replica_pending';
}

/** Best picture of the door: the learned replica, else a variant, else the upload. */
export function doorThumb(p: Project): string | null {
  if (p.has_base_image) return `/api/projects/${p.id}/base-image`;
  if (p.results.length > 0) return `/api/projects/${p.id}/results/0/image?watermark=false`;
  if (p.upload_filename) return `/api/projects/${p.id}/upload`;
  return null;
}

export function materialLabel(p: Project): string {
  return p.material_type === 'rtf' ? 'Thermofoil' : 'Wood';
}

export function productLabel(p: Project): string {
  return p.product_type === 'Drawer Front' ? 'Drawer front' : 'Cabinet door';
}
