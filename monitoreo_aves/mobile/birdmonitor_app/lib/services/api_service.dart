import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/detection.dart';
import '../models/devices.dart';
import '../models/audio_metrics.dart';

class ApiService {
  final String baseUrl;

  ApiService(String url) : baseUrl = _normalizeBaseUrl(url);

  static String _normalizeBaseUrl(String url) {
    var cleanUrl = url.trim();

    if (cleanUrl.endsWith('/')) {
      cleanUrl = cleanUrl.substring(0, cleanUrl.length - 1);
    }

    return cleanUrl;
  }

  Future<bool> testConnection() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/devices/'))
          .timeout(const Duration(seconds: 5));

      return response.statusCode >= 200 && response.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  Future<List<Detection>> getDetections() async {
    final response = await http
        .get(Uri.parse('$baseUrl/detections/'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception('Error ${response.statusCode} al cargar detecciones');
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! List) {
      throw Exception('La respuesta de /detections/ no es una lista');
    }

    return decoded
        .map((item) => Detection.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  String getAudioUrl(String filename) {
    final cleanName = filename.trim();
    if (cleanName.isEmpty) return '';

    return '$baseUrl/records/${Uri.encodeComponent(cleanName)}';
  }

  String getSpectrogramUrl(String filename) {
    final cleanName = filename.trim();
    if (cleanName.isEmpty) return '';

    final baseName = cleanName.toLowerCase().endsWith('.wav')
        ? cleanName.substring(0, cleanName.length - 4)
        : cleanName;

    return '$baseUrl/spectrograms/${Uri.encodeComponent('$baseName.png')}';
  }

  Future<Map<String, dynamic>> getStreamStatus() async {
    final response = await http
        .get(Uri.parse('$baseUrl/stream/control?node_name=birdmonitor'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception('Error ${response.statusCode} al consultar el stream');
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map<String, dynamic>) {
      throw Exception('La respuesta de /stream/control no es un objeto JSON');
    }

    return decoded;
  }

  Future<Map<String, dynamic>> setStreamEnabled(bool enabled) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/stream/control'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'node_name': 'birdmonitor',
            'stream_enabled': enabled,
          }),
        )
        .timeout(const Duration(seconds: 5));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
        'Error ${response.statusCode} al cambiar el estado del stream',
      );
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map<String, dynamic>) {
      throw Exception('La respuesta de /stream/control no es un objeto JSON');
    }

    return decoded;
  }

  String getHlsUrl() {
    final uri = Uri.parse(baseUrl);

    return Uri(
      scheme: uri.scheme,
      host: uri.host,
      port: 8888,
      path: '/birdmonitor-audio/index.m3u8',
    ).toString();
  }

  Future<List<Device>> getDevices() async {
    final response = await http
        .get(Uri.parse('$baseUrl/devices/'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception('Error ${response.statusCode} al cargar nodos');
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! List) {
      throw Exception('La respuesta de /devices/ no es una lista');
    }

    return decoded
        .map((item) => Device.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<AudioMetric>> getAudioMetrics() async {
    final response = await http
        .get(Uri.parse('$baseUrl/audio-metrics/'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception(
        'Error ${response.statusCode} al cargar métricas acústicas',
      );
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! List) {
      throw Exception('La respuesta de /audio-metrics/ no es una lista');
    }

    return decoded
        .map((item) => AudioMetric.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<Map<String, dynamic>> getBiodiversityAnalytics() async {
    final response = await http
        .get(Uri.parse('$baseUrl/analytics/biodiversity'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception(
        'Error ${response.statusCode} al cargar análisis ecológico',
      );
    }

    final decoded = jsonDecode(response.body);

    if (decoded is Map<String, dynamic>) {
      return decoded;
    }

    if (decoded is List) {
      if (decoded.isEmpty) {
        return {};
      }

      final firstItem = decoded.first;

      if (firstItem is Map<String, dynamic>) {
        return firstItem;
      }

      return {'registros': decoded.length, 'datos': decoded.toString()};
    }

    return {'respuesta': decoded.toString()};
  }

  Future<dynamic> getDailyActivity(String date) async {
    final response = await http
        .get(Uri.parse('$baseUrl/analytics/daily-activity?date=$date'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception('Error ${response.statusCode} al cargar informe diario');
    }

    return jsonDecode(response.body);
  }
}