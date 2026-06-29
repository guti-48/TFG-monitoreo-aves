import 'package:flutter/material.dart';

import '../models/audio_metrics.dart';
import '../models/detection.dart';
import '../models/devices.dart';
import '../models/review_status.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';
import 'daily_report_screen.dart';
import 'detection_detail_screen.dart';
import 'detections_screen.dart';
import 'live_stream_screen.dart';
import 'nodes_screen.dart';

class SummaryScreen extends StatefulWidget {
  final String baseUrl;

  const SummaryScreen({super.key, required this.baseUrl});

  @override
  State<SummaryScreen> createState() => _SummaryScreenState();
}

class _SummaryScreenState extends State<SummaryScreen> {
  late final ApiService api;

  late Future<List<Detection>> _detectionsFuture;
  late Future<List<Device>> _devicesFuture;
  late Future<List<AudioMetric>> _metricsFuture;
  late Future<Map<String, dynamic>> _streamFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  void _loadData() {
    _detectionsFuture = _safeDetections();
    _devicesFuture = _safeDevices();
    _metricsFuture = _safeMetrics();
    _streamFuture = _safeStream();
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
      case DetectionReviewStatus.corrected:
        return Icons.edit_outlined;
      case DetectionReviewStatus.noise:
        return Icons.volume_off_outlined;
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
      case DetectionReviewStatus.corrected:
        return Theme.of(context).colorScheme.secondary;
      case DetectionReviewStatus.noise:
        return const Color(0xFF8A6A2A);
      case DetectionReviewStatus.doubtful:
        return const Color(0xFF9A6A1E);
      case DetectionReviewStatus.discarded:
        return Theme.of(context).colorScheme.error;
      case DetectionReviewStatus.unreviewed:
        return Theme.of(context).colorScheme.secondary;
    }
  }

  String _relativeTime(String? raw) {
    final parsed = DateTime.tryParse(raw ?? '');
    if (parsed == null) return 'Sin actividad reciente';

    final diff = DateTime.now().difference(parsed);
    if (diff.inMinutes < 1) return 'Ahora mismo';
    if (diff.inMinutes < 60) return 'Hace ${diff.inMinutes} min';
    if (diff.inHours < 24) return 'Hace ${diff.inHours} h';
    return 'Hace ${diff.inDays} dias';
  }

  String _stationState(bool? desired, bool? running, bool hasError) {
    if (hasError) return 'Esperando nodo';
    if (running == true) return 'Estacion escuchando';
    if (desired == true) return 'Activacion solicitada';
    if (desired == false || running == false) return 'Stream detenido';
    return 'Estado sin confirmar';
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
    setState(_loadData);
  }

  void _openStream() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => LiveStreamScreen(baseUrl: widget.baseUrl),
      ),
    );
  }

  void _openDetections() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DetectionsScreen(baseUrl: widget.baseUrl),
      ),
    );
  }

  void _openDailyReport() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DailyReportScreen(baseUrl: widget.baseUrl),
      ),
    );
  }

  void _openStations() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => NodesScreen(baseUrl: widget.baseUrl)),
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

    return AppFieldHero(
      icon: Icons.sensors,
      eyebrow: 'Estacion activa',
      title: station?.name ?? 'Estacion BirdMonitor',
      subtitle: station?.location ?? widget.baseUrl,
      status: AppStatusPill(
        text: _stationState(desired, running, hasStreamError),
        icon: running == true ? Icons.graphic_eq : Icons.sensors_off_outlined,
        color: hasStreamError
            ? Theme.of(context).colorScheme.error
            : _statusColor(context, running ?? desired),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppSoundBars(active: running == true, height: 46),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              AppStatusPill(
                text: 'Escucha: ${_statusLabel(desired)}',
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
                  text: 'Sin confirmar',
                  icon: Icons.warning_amber_outlined,
                  color: Theme.of(context).colorScheme.error,
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLatestDetectionPanel(Detection? latest) {
    if (latest == null) {
      return const AppDataPanel(
        padding: EdgeInsets.all(18),
        child: Row(
          children: [
            Icon(Icons.eco_outlined),
            SizedBox(width: 12),
            Expanded(child: Text('Aun no hay actividad registrada.')),
          ],
        ),
      );
    }

    final reviewStatus = latest.reviewStatus;
    final filename = latest.filename?.trim() ?? '';

    return AppDataPanel(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openDetail(latest),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: filename.isEmpty
                    ? Container(
                        height: 96,
                        color: appPanelMuted,
                        padding: const EdgeInsets.all(18),
                        child: const AppSoundBars(active: true, height: 54),
                      )
                    : Image.network(
                        api.getSpectrogramUrl(filename),
                        height: 120,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) {
                          return Container(
                            height: 96,
                            color: appPanelMuted,
                            padding: const EdgeInsets.all(18),
                            child: const AppSoundBars(active: true, height: 54),
                          );
                        },
                      ),
              ),
              const SizedBox(height: 14),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          latest.displaySpecies,
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        if (latest.reviewStatus ==
                            DetectionReviewStatus.corrected)
                          Text(
                            'Original BirdNET: ${latest.species}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        const SizedBox(height: 5),
                        Text(
                          '${_relativeTime(latest.timestamp)} - ${formatTimestamp(latest.timestamp)}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 5),
                        Text(
                          '${confidenceLabel(latest.confidence)} - WAV + espectrograma',
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
              detection.reviewStatus == DetectionReviewStatus.unreviewed,
        )
        .length;
    final latestMetric = metrics.isNotEmpty ? metrics.first : null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.eco,
          leading: const BirdMonitorLogo(size: 40),
          title: 'BirdMonitor',
          subtitle: latest == null
              ? 'Sin actividad reciente. La estacion esta lista para registrar.'
              : 'Ultima escucha ${_relativeTime(latest.timestamp).toLowerCase()}.',
          trailing: IconButton(
            tooltip: 'Actualizar',
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
          ),
        ),
        _buildStationPanel(devices, stream),
        const AppSectionTitle(
          title: 'Ultima evidencia',
          subtitle: 'La pieza mas reciente para escuchar y revisar.',
        ),
        _buildLatestDetectionPanel(latest),
        const AppSectionTitle(
          title: 'Hoy',
          subtitle: 'Actividad detectada por la estacion en la fecha local.',
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
                  ? 'Sin actividad reciente'
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
          title: 'Accesos rapidos',
          subtitle: 'Herramientas de campo para moverte sin rodeos.',
        ),
        AppMetricGrid(
          children: [
            AppQuickAction(
              icon: Icons.headphones,
              title: 'Escucha',
              subtitle: 'Activar o detener el stream',
              onTap: _openStream,
            ),
            AppQuickAction(
              icon: Icons.list_alt,
              title: 'Detecciones',
              subtitle: 'Revisar actividad registrada',
              onTap: _openDetections,
            ),
            AppQuickAction(
              icon: Icons.today_outlined,
              title: 'Informe diario',
              subtitle: 'Ver el resumen por fecha',
              onTap: _openDailyReport,
            ),
            AppQuickAction(
              icon: Icons.place_outlined,
              title: 'Estaciones',
              subtitle: 'Ubicacion y nodos propios',
              onTap: _openStations,
            ),
          ],
        ),
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
          );
        },
      ),
    );
  }
}
