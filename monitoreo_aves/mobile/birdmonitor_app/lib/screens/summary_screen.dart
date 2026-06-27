import 'package:flutter/material.dart';

import '../models/audio_metrics.dart';
import '../models/detection.dart';
import '../models/devices.dart';
import '../models/review_status.dart';
import '../services/api_service.dart';
import '../services/review_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';
import 'detection_detail_screen.dart';
import 'live_stream_screen.dart';

class SummaryScreen extends StatefulWidget {
  final String baseUrl;

  const SummaryScreen({super.key, required this.baseUrl});

  @override
  State<SummaryScreen> createState() => _SummaryScreenState();
}

class _SummaryScreenState extends State<SummaryScreen> {
  late final ApiService api;
  late final ReviewService reviewService;

  late Future<List<Detection>> _detectionsFuture;
  late Future<List<Device>> _devicesFuture;
  late Future<List<AudioMetric>> _metricsFuture;
  late Future<Map<String, dynamic>> _streamFuture;
  late Future<Map<int, DetectionReviewStatus>> _reviewFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    reviewService = ReviewService();
    _loadData();
  }

  void _loadData() {
    _detectionsFuture = _safeDetections();
    _devicesFuture = _safeDevices();
    _metricsFuture = _safeMetrics();
    _streamFuture = _safeStream();
    _reviewFuture = reviewService.getStatuses();
  }

  Future<List<Detection>> _safeDetections() async {
    try {
      return await api.getDetections();
    } catch (_) {
      return [];
    }
  }

  Future<List<Device>> _safeDevices() async {
    try {
      return await api.getDevices();
    } catch (_) {
      return [];
    }
  }

  Future<List<AudioMetric>> _safeMetrics() async {
    try {
      return await api.getAudioMetrics();
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>> _safeStream() async {
    try {
      return await api.getStreamStatus();
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await Future.wait([
      _detectionsFuture,
      _devicesFuture,
      _metricsFuture,
      _streamFuture,
      _reviewFuture,
    ]);
  }

  bool _isToday(Detection detection) {
    final parsed = DateTime.tryParse(detection.timestamp);
    if (parsed == null) return false;

    final now = DateTime.now();
    return parsed.year == now.year &&
        parsed.month == now.month &&
        parsed.day == now.day;
  }

  bool? _readBool(Map<String, dynamic> data, List<String> keys) {
    for (final key in keys) {
      final value = data[key];
      if (value is bool) return value;
      if (value is String) {
        final normalized = value.toLowerCase();
        if (normalized == 'true') return true;
        if (normalized == 'false') return false;
      }
    }

    return null;
  }

  String _statusLabel(bool? value) {
    if (value == true) return 'Activo';
    if (value == false) return 'Detenido';
    return 'Desconocido';
  }

  Color _statusColor(BuildContext context, bool? value) {
    if (value == true) return Theme.of(context).colorScheme.primary;
    if (value == false) return Theme.of(context).colorScheme.error;
    return Theme.of(context).colorScheme.secondary;
  }

  IconData _reviewIcon(DetectionReviewStatus status) {
    switch (status) {
      case DetectionReviewStatus.validated:
        return Icons.check_circle_outline;
      case DetectionReviewStatus.doubtful:
        return Icons.help_outline;
      case DetectionReviewStatus.discarded:
        return Icons.cancel_outlined;
      case DetectionReviewStatus.unreviewed:
        return Icons.rate_review_outlined;
    }
  }

  Color _reviewColor(BuildContext context, DetectionReviewStatus status) {
    switch (status) {
      case DetectionReviewStatus.validated:
        return Theme.of(context).colorScheme.primary;
      case DetectionReviewStatus.doubtful:
        return const Color(0xFF9A6A1E);
      case DetectionReviewStatus.discarded:
        return Theme.of(context).colorScheme.error;
      case DetectionReviewStatus.unreviewed:
        return Theme.of(context).colorScheme.secondary;
    }
  }

  Future<void> _openDetail(Detection detection) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DetectionDetailScreen(
          detection: detection,
          baseUrl: widget.baseUrl,
        ),
      ),
    );

    if (!mounted) return;
    setState(() {
      _reviewFuture = reviewService.getStatuses();
    });
  }

  void _openStream() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => LiveStreamScreen(baseUrl: widget.baseUrl),
      ),
    );
  }

  Widget _buildStationPanel(List<Device> devices, Map<String, dynamic> stream) {
    final station = devices.isNotEmpty ? devices.first : null;
    final desired = _readBool(stream, [
      'stream_enabled',
      'desired_enabled',
      'desired_stream_enabled',
    ]);
    final running = _readBool(stream, [
      'actual_running',
      'stream_running',
      'real_running',
      'is_running',
    ]);
    final hasStreamError = stream['error'] != null;

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: appGreenSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Icon(
                    Icons.sensors,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      station?.name ?? 'Estacion BirdMonitor',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      station?.location ?? widget.baseUrl,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              AppStatusPill(
                text: 'Peticion: ${_statusLabel(desired)}',
                icon: Icons.power_settings_new,
                color: _statusColor(context, desired),
              ),
              AppStatusPill(
                text: 'Nodo: ${_statusLabel(running)}',
                icon: Icons.graphic_eq,
                color: _statusColor(context, running),
              ),
              if (hasStreamError)
                AppStatusPill(
                  text: 'Stream sin confirmar',
                  icon: Icons.warning_amber_outlined,
                  color: Theme.of(context).colorScheme.error,
                ),
            ],
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _openStream,
            icon: const Icon(Icons.headphones),
            label: const Text('Abrir escucha'),
          ),
        ],
      ),
    );
  }

  Widget _buildLatestDetectionPanel(
    Detection? latest,
    Map<int, DetectionReviewStatus> reviews,
  ) {
    if (latest == null) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('Todavia no hay detecciones registradas.'),
      );
    }

    final reviewStatus = reviews[latest.id] ?? DetectionReviewStatus.unreviewed;

    return AppDataPanel(
      padding: EdgeInsets.zero,
      child: InkWell(
        onTap: () => _openDetail(latest),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: appGreenSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Icon(
                    Icons.pets,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      latest.species,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      formatTimestamp(latest.timestamp),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${confidenceLabel(latest.confidence)} - ${formatFilename(latest.filename)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  AppStatusPill(
                    text: formatConfidence(latest.confidence),
                    icon: Icons.verified,
                  ),
                  const SizedBox(height: 6),
                  AppStatusPill(
                    text: reviewStatus.label,
                    icon: _reviewIcon(reviewStatus),
                    color: _reviewColor(context, reviewStatus),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryContent(
    List<Detection> detections,
    List<Device> devices,
    List<AudioMetric> metrics,
    Map<String, dynamic> stream,
    Map<int, DetectionReviewStatus> reviews,
  ) {
    final latest = detections.isNotEmpty ? detections.first : null;
    final todayDetections = detections.where(_isToday).toList();
    final todaySpecies = todayDetections
        .map((detection) => detection.species)
        .where((species) => species.trim().isNotEmpty)
        .toSet();
    final pendingReviews = detections
        .where(
          (detection) =>
              (reviews[detection.id] ?? DetectionReviewStatus.unreviewed) ==
              DetectionReviewStatus.unreviewed,
        )
        .length;
    final latestMetric = metrics.isNotEmpty ? metrics.first : null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.dashboard,
          title: 'BirdMonitor',
          subtitle:
              'Estacion, evidencia reciente y trabajo pendiente de campo.',
          trailing: IconButton(
            tooltip: 'Actualizar',
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
          ),
        ),
        _buildStationPanel(devices, stream),
        const AppSectionTitle(
          title: 'Resumen de campo',
          subtitle: 'Lectura rapida de actividad, evidencia y revision.',
        ),
        AppMetricGrid(
          children: [
            AppMetricCard(
              icon: Icons.today_outlined,
              label: 'Detecciones hoy',
              value: todayDetections.length.toString(),
              detail: 'Registros de la fecha local',
            ),
            AppMetricCard(
              icon: Icons.eco,
              label: 'Especies hoy',
              value: todaySpecies.length.toString(),
              detail: todaySpecies.isEmpty
                  ? 'Sin especies nuevas'
                  : todaySpecies.take(2).join(', '),
            ),
            AppMetricCard(
              icon: Icons.rate_review_outlined,
              label: 'Pendientes',
              value: pendingReviews.toString(),
              detail: 'Detecciones sin revisar',
            ),
            AppMetricCard(
              icon: Icons.graphic_eq,
              label: 'NDSI reciente',
              value: latestMetric?.ndsi == null
                  ? 'Sin datos'
                  : latestMetric!.ndsi!.toStringAsFixed(3),
              detail: 'Paisaje sonoro',
            ),
          ],
        ),
        const AppSectionTitle(
          title: 'Ultima evidencia',
          subtitle: 'Toca el registro para revisar audio y espectrograma.',
        ),
        _buildLatestDetectionPanel(latest, reviews),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<dynamic>>(
        future: Future.wait([
          _detectionsFuture,
          _devicesFuture,
          _metricsFuture,
          _streamFuture,
          _reviewFuture,
        ]),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const AppPage(
              children: [
                SizedBox(height: 220),
                Center(child: CircularProgressIndicator()),
              ],
            );
          }

          final data = snapshot.data;
          if (snapshot.hasError || data == null) {
            return AppPage(
              children: [
                AppDataPanel(
                  padding: const EdgeInsets.all(16),
                  child: Text('Error cargando resumen: ${snapshot.error}'),
                ),
              ],
            );
          }

          return _buildSummaryContent(
            data[0] as List<Detection>,
            data[1] as List<Device>,
            data[2] as List<AudioMetric>,
            data[3] as Map<String, dynamic>,
            data[4] as Map<int, DetectionReviewStatus>,
          );
        },
      ),
    );
  }
}