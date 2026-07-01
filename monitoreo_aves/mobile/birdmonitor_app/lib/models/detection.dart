import 'review_status.dart';

class Detection {
  final int id;
  final String timestamp;
  final String species;
  final double confidence;
  final String? filename;
  final double? amplitude;
  final int? deviceId;
  final DetectionReview? review;
  final LearningSuggestion? learnedSuggestion;

  Detection({
    required this.id,
    required this.timestamp,
    required this.species,
    required this.confidence,
    this.filename,
    this.amplitude,
    this.deviceId,
    this.review,
    this.learnedSuggestion,
  });

  DetectionReviewStatus get reviewStatus =>
      review?.status ?? DetectionReviewStatus.unreviewed;

  bool get isAmbientNoise {
    final correctedSpecies = review?.correctedSpecies?.trim();
    if (reviewStatus == DetectionReviewStatus.corrected &&
        correctedSpecies != null &&
        correctedSpecies.isNotEmpty) {
      return false;
    }

    if (reviewStatus == DetectionReviewStatus.noise) return true;

    final normalized = species.trim().toLowerCase();
    return normalized == 'noise' ||
        normalized == 'ruido ambiente' ||
        normalized == 'noise_ruido ambiente' ||
        normalized.startsWith('noise_');
  }

  bool get needsBirdReview =>
      reviewStatus == DetectionReviewStatus.unreviewed && !isAmbientNoise;

  String get displaySpecies {
    final correctedSpecies = review?.correctedSpecies?.trim();
    if (reviewStatus == DetectionReviewStatus.corrected &&
        correctedSpecies != null &&
        correctedSpecies.isNotEmpty) {
      return correctedSpecies;
    }

    if (isAmbientNoise) return 'Ruido ambiente';

    return species;
  }

  bool get hasLearningSuggestion =>
      reviewStatus == DetectionReviewStatus.unreviewed &&
      learnedSuggestion != null;

  factory Detection.fromJson(Map<String, dynamic> json) {
    return Detection(
      id: _toInt(json['id']),
      timestamp: json['timestamp']?.toString() ?? '',
      species: json['species']?.toString() ?? 'Desconocida',
      confidence: _toDouble(json['confidence']),
      filename: json['filename']?.toString(),
      amplitude: json['amplitude'] == null
          ? null
          : _toDouble(json['amplitude']),
      deviceId: json['device_id'] == null ? null : _toInt(json['device_id']),
      review: json['review'] is Map<String, dynamic>
          ? DetectionReview.fromJson(json['review'] as Map<String, dynamic>)
          : null,
      learnedSuggestion: json['learned_suggestion'] is Map<String, dynamic>
          ? LearningSuggestion.fromJson(
              json['learned_suggestion'] as Map<String, dynamic>,
            )
          : null,
    );
  }

  static int _toInt(dynamic value) {
    if (value is int) return value;
    if (value is double) return value.toInt();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }

  static double _toDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is String) return double.tryParse(value) ?? 0.0;
    return 0.0;
  }
}

class LearningSuggestion {
  final int ruleId;
  final DetectionReviewStatus status;
  final String? correctedSpecies;
  final String? effectiveSpecies;
  final double learningConfidence;
  final int supportCount;
  final bool autoApply;
  final String reason;

  LearningSuggestion({
    required this.ruleId,
    required this.status,
    this.correctedSpecies,
    this.effectiveSpecies,
    required this.learningConfidence,
    required this.supportCount,
    required this.autoApply,
    required this.reason,
  });

  String get displaySpecies {
    final cleaned = effectiveSpecies?.trim();
    if (cleaned != null && cleaned.isNotEmpty) {
      if (status == DetectionReviewStatus.noise) return 'Ruido ambiente';
      return cleaned;
    }

    if (status == DetectionReviewStatus.noise) return 'Ruido ambiente';
    if (status == DetectionReviewStatus.discarded) return 'Descartar registro';
    return status.label;
  }

  String get confidenceText =>
      '${(learningConfidence * 100).toStringAsFixed(0)}%';

  factory LearningSuggestion.fromJson(Map<String, dynamic> json) {
    return LearningSuggestion(
      ruleId: Detection._toInt(json['rule_id']),
      status: DetectionReviewStatusLabel.fromStorage(
        json['status']?.toString(),
      ),
      correctedSpecies: json['corrected_species']?.toString(),
      effectiveSpecies: json['effective_species']?.toString(),
      learningConfidence: Detection._toDouble(json['learning_confidence']),
      supportCount: Detection._toInt(json['support_count']),
      autoApply: json['auto_apply'] == true,
      reason: json['reason']?.toString() ?? '',
    );
  }
}

class DetectionReview {
  final int id;
  final int detectionId;
  final DetectionReviewStatus status;
  final String? correctedSpecies;
  final String? note;
  final String? reviewer;
  final String? reviewedAt;
  final String? updatedAt;

  DetectionReview({
    required this.id,
    required this.detectionId,
    required this.status,
    this.correctedSpecies,
    this.note,
    this.reviewer,
    this.reviewedAt,
    this.updatedAt,
  });

  factory DetectionReview.fromJson(Map<String, dynamic> json) {
    return DetectionReview(
      id: Detection._toInt(json['id']),
      detectionId: Detection._toInt(json['detection_id']),
      status: DetectionReviewStatusLabel.fromStorage(
        json['status']?.toString(),
      ),
      correctedSpecies: json['corrected_species']?.toString(),
      note: json['note']?.toString(),
      reviewer: json['reviewer']?.toString(),
      reviewedAt: json['reviewed_at']?.toString(),
      updatedAt: json['updated_at']?.toString(),
    );
  }
}