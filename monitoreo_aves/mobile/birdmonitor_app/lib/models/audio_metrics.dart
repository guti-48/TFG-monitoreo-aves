class AudioMetric {
  final int id;
  final String timestamp;
  final String? filename;
  final int? sampleRate;
  final double? duration;
  final double? rms;
  final double? peak;
  final double? clippingRatio;
  final double? dcOffset;
  final double? noiseFloorRms;
  final String? qualityStatus;
  final String? qualityDetail;
  final String? micDevice;
  final String? birdnetModel;
  final String? birdnetModelVersion;
  final String? birdnetlibVersion;
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
    this.peak,
    this.clippingRatio,
    this.dcOffset,
    this.noiseFloorRms,
    this.qualityStatus,
    this.qualityDetail,
    this.micDevice,
    this.birdnetModel,
    this.birdnetModelVersion,
    this.birdnetlibVersion,
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
      sampleRate: json['sample_rate'] == null
          ? null
          : _toInt(json['sample_rate']),
      duration: json['duration'] == null ? null : _toDouble(json['duration']),
      rms: json['rms'] == null ? null : _toDouble(json['rms']),
      peak: json['peak'] == null ? null : _toDouble(json['peak']),
      clippingRatio: json['clipping_ratio'] == null
          ? null
          : _toDouble(json['clipping_ratio']),
      dcOffset: json['dc_offset'] == null ? null : _toDouble(json['dc_offset']),
      noiseFloorRms: json['noise_floor_rms'] == null
          ? null
          : _toDouble(json['noise_floor_rms']),
      qualityStatus: json['quality_status']?.toString(),
      qualityDetail: json['quality_detail']?.toString(),
      micDevice: json['mic_device']?.toString(),
      birdnetModel: json['birdnet_model']?.toString(),
      birdnetModelVersion: json['birdnet_model_version']?.toString(),
      birdnetlibVersion: json['birdnetlib_version']?.toString(),
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