package com.atelier.gateway.tryon;

import java.util.List;
import java.util.Set;

public record TryOnRequest(
    String product_id,
    BodyProfile body_profile
) {
    public record BodyProfile(
        double height_cm, double weight_kg, double chest_cm, double waist_cm, double hip_cm,
        Double shoulder_cm, Double inseam_cm, String presentation, String body_shape,
        String skin_tone, String fit_preference
    ) {
        private static final Set<String> PRESENTATIONS = Set.of("FEMININE", "MASCULINE", "NEUTRAL");
        private static final Set<String> SHAPES = Set.of("BALANCED", "TRIANGLE", "INVERTED_TRIANGLE", "RECTANGLE", "OVAL");
        private static final Set<String> TONES = Set.of("LIGHT", "MEDIUM", "TAN", "DEEP");
        private static final Set<String> FITS = Set.of("CLOSE", "REGULAR", "RELAXED");

        public BodyProfile normalized() {
            return new BodyProfile(
                height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, inseam_cm,
                presentation == null ? "NEUTRAL" : presentation,
                body_shape == null ? "BALANCED" : body_shape,
                skin_tone == null ? "MEDIUM" : skin_tone,
                fit_preference == null ? "REGULAR" : fit_preference
            );
        }

        public void validate() {
            double bmi = weight_kg / Math.pow(height_cm / 100, 2);
            if (height_cm < 135 || height_cm > 220 || weight_kg < 30 || weight_kg > 220
                || chest_cm < 60 || chest_cm > 170 || waist_cm < 45 || waist_cm > 180 || hip_cm < 60 || hip_cm > 180
                || (shoulder_cm != null && (shoulder_cm < 28 || shoulder_cm > 70))
                || (inseam_cm != null && (inseam_cm < 45 || inseam_cm > 120)) || bmi < 10 || bmi > 70 || !PRESENTATIONS.contains(presentation)
                || !SHAPES.contains(body_shape) || !TONES.contains(skin_tone) || !FITS.contains(fit_preference)) {
                throw new IllegalArgumentException("Body profile is invalid");
            }
        }
    }

    public record SaveRequest(boolean saved) { }

    public record FeedbackRequest(
        int rating,
        List<String> issues
    ) {
        private static final Set<String> ISSUES = Set.of(
            "BODY_PROPORTION", "GARMENT_DETAIL", "MATERIAL", "COLOR", "OCCLUSION", "OTHER"
        );

        public FeedbackRequest normalized() {
            return new FeedbackRequest(rating, issues == null ? List.of() : List.copyOf(issues));
        }

        public void validate() {
            if (issues == null || issues.size() > 5) {
                throw new IllegalArgumentException("Try-on feedback is invalid");
            }
            if (rating < 1 || rating > 5 || issues == null || issues.stream().anyMatch(issue -> !ISSUES.contains(issue))) {
                throw new IllegalArgumentException("Try-on feedback is invalid");
            }
        }
    }
}
