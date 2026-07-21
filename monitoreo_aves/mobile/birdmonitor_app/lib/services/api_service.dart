import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/detection.dart';
import '../models/devices.dart';
import '../models/audio_metrics.dart';
import '../models/review_status.dart';

class ApiService {
  static const defaultStreamNodeName = 'birdmonitor';

  final String baseUrl;
  final String streamNodeName;

  ApiService(String url, {this.streamNodeName = defaultStreamNodeName})
    : baseUrl = _normalizeBaseUrl(url);

  static String _normalizeBaseUrl(String url) {
    var cleanUrl = url.trim();

    if (cleanUrl.endsWith('/')) {
      cleanUrl = cleanUrl.substring(0, cleanUrl.length - 1);
    }

    return cleanUrl;
  }

  String _resolveStreamNodeName(String? nodeName) {
    final cleanNodeName = nodeName?.trim();
    return cleanNodeName == null || cleanNodeName.isEmpty
        ? streamNodeName
        : cleanNodeName;
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

  Future<DetectionReview> updateDetectionReview({
    required int detectionId,
    required DetectionReviewStatus status,
    String? correctedSpecies,
    String? note,
    String reviewer = 'mobile',
  }) async {
    final cleanCorrectedSpecies = correctedSpecies?.trim();

    final response = await http
        .patch(
          Uri.parse('$baseUrl/detections/$detectionId/review'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'status': status.storageValue,
            'corrected_species':
                cleanCorrectedSpecies == null || cleanCorrectedSpecies.isEmpty
                ? null
                : cleanCorrectedSpecies,
            'note': note?.trim(),
            'reviewer': reviewer,
          }),
        )
        .timeout(const Duration(seconds: 5));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Error ${response.statusCode} al guardar revision');
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map<String, dynamic>) {
      throw Exception(
        'La respuesta de /detections/$detectionId/review no es un objeto JSON',
      );
    }

    return DetectionReview.fromJson(decoded);
  }

  Future<List<String>> getSpeciesOptions() async {
    final response = await http
        .get(Uri.parse('$baseUrl/species/options'))
        .timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) {
      throw Exception('Error ${response.statusCode} al cargar especies');
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! List) {
      throw Exception('La respuesta de /species/options no es una lista');
    }

    return decoded
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toSet()
        .toList()
      ..sort();
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

  Future<Map<String, dynamic>> getStreamStatus({String? nodeName}) async {
    final effectiveNodeName = _resolveStreamNodeName(nodeName);
    final response = await http
        .get(
          Uri.parse(
            '$baseUrl/stream/control',
          ).replace(queryParameters: {'node_name': effectiveNodeName}),
        )
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

  Future<Map<String, dynamic>> setStreamEnabled(
    bool enabled, {
    String? nodeName,
    String? streamPath,
  }) async {
    final effectiveNodeName = _resolveStreamNodeName(nodeName);
    final body = <String, dynamic>{
      'node_name': effectiveNodeName,
      'stream_enabled': enabled,
    };

    if (streamPath != null && streamPath.trim().isNotEmpty) {
      body['stream_path'] = streamPath.trim();
    }

    final response = await http
        .post(
          Uri.parse('$baseUrl/stream/control'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
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

  String getHlsUrl({String streamPath = 'birdmonitor-audio'}) {
    final uri = Uri.parse(baseUrl);
    final cleanPath = streamPath.trim().replaceAll(RegExp(r'^/+|/+$'), '');

    return Uri(
      scheme: uri.scheme,
      host: uri.host,
      port: 8888,
      path:
          '/${cleanPath.isEmpty ? 'birdmonitor-audio' : cleanPath}/index.m3u8',
    ).toString();
  }

  Future<String> getConfiguredHlsUrl() async {
    try {
      final status = await getStreamStatus();
      final backendHlsUrl = status['hls_url']?.toString().trim();

      if (backendHlsUrl != null && backendHlsUrl.isNotEmpty) {
        return backendHlsUrl;
      }
    } catch (_) {
      // Keep the app usable offline or while the stream endpoint is starting.
    }

    return getHlsUrl();
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