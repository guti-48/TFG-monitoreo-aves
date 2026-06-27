class AudioMetric {
  final int id;
  final String timestamp;
  final String? filename;
  final int? sampleRate;
  final double? duration;
  final double? rms;
  final double? aci;
  final double? adi;
  final double? aei;
  final double? bio;
  final double? ndsi;
  final double? ht;
  final double? hf;
  final double? h;
  final int? deviceId;

  AudioMetric({
    required this.id,
    required this.timestamp,
    this.filename,
    this.sampleRate,
    this.duration,
    this.rms,
    this.aci,
    this.adi,
    this.aei,
    this.bio,
    this.ndsi,
    this.ht,
    this.hf,
    this.h,
    this.deviceId,
  });

  factory AudioMetric.fromJson(Map<String, dynamic> json) {
    return AudioMetric(
      id: _toInt(json['id']),
      timestamp: json['timestamp']?.toString() ?? '',
      filename: json['filename']?.toString(),
      sampleRate: json['sample_rate'] == null ? null : _toInt(json['sample_rate']),
      duration: json['duration'] == null ? null : _toDouble(json['duration']),
      rms: json['rms'] == null ? null : _toDouble(json['rms']),
      aci: json['aci'] == null ? null : _toDouble(json['aci']),
      adi: json['adi'] == null ? null : _toDouble(json['adi']),
      aei: json['aei'] == null ? null : _toDouble(json['aei']),
      bio: json['bio'] == null ? null : _toDouble(json['bio']),
      ndsi: json['ndsi'] == null ? null : _toDouble(json['ndsi']),
      ht: json['ht'] == null ? null : _toDouble(json['ht']),
      hf: json['hf'] == null ? null : _toDouble(json['hf']),
      h: json['h'] == null ? null : _toDouble(json['h']),
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