export type VirtualTryOnStatus = "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";
export type BodyPresentation = "FEMININE" | "MASCULINE" | "NEUTRAL";
export type BodyShape = "BALANCED" | "TRIANGLE" | "INVERTED_TRIANGLE" | "RECTANGLE" | "OVAL";
export type SkinTone = "LIGHT" | "MEDIUM" | "TAN" | "DEEP";
export type FitPreference = "CLOSE" | "REGULAR" | "RELAXED";

export interface SyntheticBodyProfile {
  height_cm: number;
  weight_kg: number;
  chest_cm: number;
  waist_cm: number;
  hip_cm: number;
  shoulder_cm?: number;
  inseam_cm?: number;
  presentation: BodyPresentation;
  body_shape: BodyShape;
  skin_tone: SkinTone;
  fit_preference: FitPreference;
}

export interface TryOnFeedback {
  rating: number;
  issues: Array<"BODY_PROPORTION" | "GARMENT_DETAIL" | "MATERIAL" | "COLOR" | "OCCLUSION" | "OTHER">;
}

export interface VirtualTryOnJob {
  id: string;
  product_id: string;
  category: string;
  status: VirtualTryOnStatus;
  created_at: string;
  updated_at: string;
  expires_at: string;
  retry_after_seconds: number | null;
  attempt_count: number;
  model: {
    kind: "SYNTHETIC_ADULT";
    body_profile: SyntheticBodyProfile;
    uses_person_photo: false;
  };
  result: { url: string } | null;
  failure: { code: string } | null;
  saved: boolean;
  feedback: TryOnFeedback | null;
}
