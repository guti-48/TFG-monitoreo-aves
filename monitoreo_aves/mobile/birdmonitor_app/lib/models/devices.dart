class Device {
  final int id;
  final String name;
  final String? location;
  final double? lat;
  final double? lon;

  Device({
    required this.id,
    required this.name,
    this.location,
    this.lat,
    this.lon,
  });

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: _toInt(json['id']),
      name: json['name']?.toString() ?? 'Nodo desconocido',
      location: json['location']?.toString(),
      lat: json['lat'] == null ? null : _toDouble(json['lat']),
      lon: json['lon'] == null ? null : _toDouble(json['lon']),
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