class Detection {
  final int id;
  final String timestamp;
  final String species;
  final double confidence;
  final String? filename;
  final double? amplitude;
  final int? deviceId;

  Detection({
    required this.id,
    required this.timestamp,
    required this.species,
    required this.confidence,
    this.filename,
    this.amplitude,
    this.deviceId,
  });

  factory Detection.fromJson(Map<String, dynamic> json) {
    return Detection(
      id: _toInt(json['id']),
      timestamp: json['timestamp']?.toString() ?? '',
      species: json['species']?.toString() ?? 'Desconocida',
      confidence: _toDouble(json['confidence']),
      filename: json['filename']?.toString(),
      amplitude: json['amplitude'] == null ? null : _toDouble(json['amplitude']),
      deviceId: json['device_id'] == null ? null : _toInt(json['device_id']),
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