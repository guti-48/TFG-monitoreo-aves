import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/detection.dart';
import '../models/devices.dart';

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
        throw Exception('Error ${response.statusCode} al cambiar el estado del stream');
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
}