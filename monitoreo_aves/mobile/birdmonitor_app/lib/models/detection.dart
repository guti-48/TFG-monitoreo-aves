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

  Detection({
    required this.id,
    required this.timestamp,
    required this.species,
    required this.confidence,
    this.filename,
    this.amplitude,
    this.deviceId,
    this.review,
  });

  DetectionReviewStatus get reviewStatus =>
      review?.status ?? DetectionReviewStatus.unreviewed;

  String get displaySpecies {
    if (reviewStatus == DetectionReviewStatus.noise) {
      return 'Ruido ambiente';
    }

    final correctedSpecies = review?.correctedSpecies?.trim();
    if (reviewStatus == DetectionReviewStatus.corrected &&
        correctedSpecies != null &&
        correctedSpecies.isNotEmpty) {
      return correctedSpecies;
    }

    return species;
  }

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
