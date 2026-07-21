import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
  static const _stationNamePrefix = 'station_display_name.';
  static const _stationLocationPrefix = 'station_display_location.';

  late final ApiService api;

  final Map<String, String> _stationNameOverrides = {};
  final Map<String, String> _stationLocationOverrides = {};

  late Future<List<Detection>> _detectionsFuture;
  late Future<List<Device>> _devicesFuture;
  late Future<List<AudioMetric>> _metricsFuture;
  late Future<Map<String, dynamic>> _streamFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
    _loadStationDisplayPreferences();
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

  Future<void> _loadStationDisplayPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    final names = <String, String>{};
    final locations = <String, String>{};

    for (final key in prefs.getKeys()) {
      if (key.startsWith(_stationNamePrefix)) {
        final stationKey = key.substring(_stationNamePrefix.length);
        final value = prefs.getString(key)?.trim();
        if (value != null && value.isNotEmpty) names[stationKey] = value;
      }

      if (key.startsWith(_stationLocationPrefix)) {
        final stationKey = key.substring(_stationLocationPrefix.length);
        final value = prefs.getString(key)?.trim();
        if (value != null && value.isNotEmpty) locations[stationKey] = value;
      }
    }

    if (!mounted) return;
    setState(() {
      _stationNameOverrides
        ..clear()
        ..addAll(names);
      _stationLocationOverrides
        ..clear()
        ..addAll(locations);
    });
  }

  String _stationStorageKey(Device? station) {
    if (station == null) return 'default';
    if (station.id != 0) return station.id.toString();
    final cleanName = station.name.trim();
    return cleanName.isEmpty ? 'default' : cleanName;
  }

  String _stationDisplayName(Device? station) {
    final key = _stationStorageKey(station);
    final localName = _stationNameOverrides[key]?.trim();
    if (localName != null && localName.isNotEmpty) return localName;

    final backendName = station?.name.trim();
    if (backendName != null && backendName.isNotEmpty) return backendName;

    return 'Estacion BirdMonitor';
  }

  String _stationDisplayLocation(Device? station) {
    final key = _stationStorageKey(station);
    final localLocation = _stationLocationOverrides[key]?.trim();
    if (localLocation != null && localLocation.isNotEmpty) {
      return localLocation;
    }

    final backendLocation = station?.location?.trim();
    if (backendLocation != null && backendLocation.isNotEmpty) {
      return backendLocation;
    }

    return 'Ubicacion sin definir';
  }

  Future<void> _editStationDisplay(Device? station) async {
    final key = _stationStorageKey(station);
    final originalName = station?.name.trim() ?? '';
    final originalLocation = station?.location?.trim() ?? '';
    final nameController = TextEditingController(
      text: _stationDisplayName(station),
    );
    final locationController = TextEditingController(
      text: _stationDisplayLocation(station) == 'Ubicacion sin definir'
          ? ''
          : _stationDisplayLocation(station),
    );

    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Editar estacion'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameController,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Nombre visible',
                  prefixIcon: Icon(Icons.sensors),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: locationController,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  labelText: 'Ubicacion',
                  prefixIcon: Icon(Icons.place_outlined),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(context, {
                  'name': nameController.text.trim(),
                  'location': locationController.text.trim(),
                });
              },
              child: const Text('Guardar'),
            ),
          ],
        );
      },
    );

    nameController.dispose();
    locationController.dispose();

    if (result == null) return;

    final newName = result['name']?.trim() ?? '';
    final newLocation = result['location']?.trim() ?? '';
    final prefs = await SharedPreferences.getInstance();

    if (newName.isEmpty || newName == originalName) {
      await prefs.remove('$_stationNamePrefix$key');
      _stationNameOverrides.remove(key);
    } else {
      await prefs.setString('$_stationNamePrefix$key', newName);
      _stationNameOverrides[key] = newName;
    }

    if (newLocation.isEmpty || newLocation == originalLocation) {
      await prefs.remove('$_stationLocationPrefix$key');
      _stationLocationOverrides.remove(key);
    } else {
      await prefs.setString('$_stationLocationPrefix$key', newLocation);
      _stationLocationOverrides[key] = newLocation;
    }

    if (!mounted) return;
    setState(() {});
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

  double? _boundedProgress(double? value) {
    if (value == null) return null;
    final absolute = value.abs();
    if (absolute == 0) return 0;
    return (absolute / (absolute + 1)).clamp(0, 1).toDouble();
  }

  double? _ndsiProgress(double? ndsi) {
    if (ndsi == null) return null;
    return ((ndsi + 1) / 2).clamp(0, 1).toDouble();
  }

  String _bioacousticLevel(AudioMetric? metric) {
    final ndsi = metric?.ndsi;
    if (metric == null || ndsi == null) return 'Sin nivel bioacustico';
    if (ndsi >= 0.35) return 'Biofonia dominante';
    if (ndsi >= 0.08) return 'Biofonia presente';
    if (ndsi > -0.20) return 'Paisaje sonoro mixto';
    return 'Ruido dominante';
  }

  String _bioacousticDetail(AudioMetric? metric) {
    if (metric == null) {
      return 'Aun no hay muestras acusticas para interpretar el paisaje sonoro.';
    }

    final ndsi = metric.ndsi;
    final when = _relativeTime(metric.timestamp).toLowerCase();
    if (ndsi == null) return 'Ultima muestra $when, sin NDSI calculado.';
    if (ndsi >= 0.35) {
      return 'Ultima muestra $when: predominan sonidos biologicos frente al ruido.';
    }
    if (ndsi >= 0.08) {
      return 'Ultima muestra $when: hay actividad biologica reconocible en el audio.';
    }
    if (ndsi > -0.20) {
      return 'Ultima muestra $when: mezcla entre biofonia, ambiente y posible ruido.';
    }
    return 'Ultima muestra $when: el ruido pesa mas que la biofonia registrada.';
  }

  Color _bioacousticColor(BuildContext context, AudioMetric? metric) {
    final ndsi = metric?.ndsi;
    if (ndsi == null) return Theme.of(context).colorScheme.secondary;
    if (ndsi >= 0.08) return Theme.of(context).colorScheme.primary;
    if (ndsi > -0.20) return const Color(0xFF9A6A1E);
    return Theme.of(context).colorScheme.error;
  }

  Widget _buildBioMetricLine({
    required String label,
    required String value,
    required String detail,
    double? progress,
    String? leftLabel,
    String? rightLabel,
  }) {
    final color = Theme.of(context).colorScheme.primary;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              Text(value, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 4),
          if (progress != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 6,
                backgroundColor: appGreenSoft,
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            ),
            if (leftLabel != null || rightLabel != null) ...[
              const SizedBox(height: 3),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      leftLabel ?? '',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  Text(
                    rightLabel ?? '',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ],
            const SizedBox(height: 2),
          ],
          Text(
            detail,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildBioacousticSummary(AudioMetric? metric) {
    return AppFieldHero(
      icon: Icons.graphic_eq,
      eyebrow: 'Nivel bioacustico',
      title: _bioacousticLevel(metric),
      subtitle: _bioacousticDetail(metric),
      status: AppStatusPill(
        text: metric?.ndsi == null
            ? 'Sin NDSI'
            : 'NDSI ${formatValue(metric!.ndsi)}',
        icon: Icons.eco_outlined,
        color: _bioacousticColor(context, metric),
      ),
      child: metric == null
          ? null
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildBioMetricLine(
                  label: 'Balance biofonia / ruido',
                  value: formatValue(metric.ndsi),
                  detail:
                      'El NDSI resume si pesan mas los sonidos biologicos o el ruido de fondo.',
                  progress: _ndsiProgress(metric.ndsi),
                  leftLabel: 'Ruido',
                  rightLabel: 'Biofonia',
                ),
                _buildBioMetricLine(
                  label: 'Actividad biologica',
                  value: formatValue(metric.bio),
                  detail:
                      'BIO estima la energia acustica asociada a actividad biologica.',
                  progress: _boundedProgress(metric.bio),
                ),
                _buildBioMetricLine(
                  label: 'Complejidad acustica',
                  value: formatValue(metric.aci),
                  detail:
                      'ACI aumenta cuando el audio tiene variaciones y eventos sonoros.',
                  progress: _boundedProgress(metric.aci),
                ),
              ],
            ),
    );
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

  void _openSecondaryScreen(String title, Widget screen) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AppSecondaryScaffold(title: title, child: screen),
      ),
    );
  }

  void _openStream() {
    _openSecondaryScreen('Escucha', LiveStreamScreen(baseUrl: widget.baseUrl));
  }

  void _openDetections() {
    _openSecondaryScreen(
      'Detecciones',
      DetectionsScreen(baseUrl: widget.baseUrl),
    );
  }

  void _openDailyReport() {
    _openSecondaryScreen(
      'Informe diario',
      DailyReportScreen(baseUrl: widget.baseUrl),
    );
  }

  void _openStations() {
    _openSecondaryScreen('Estaciones', NodesScreen(baseUrl: widget.baseUrl));
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

    final displayName = _stationDisplayName(station);
    final displayLocation = _stationDisplayLocation(station);

    return AppFieldHero(
      icon: Icons.sensors,
      eyebrow: 'Estacion activa',
      title: displayName,
      subtitle: displayLocation,
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
          AppSoundBars(active: running == true, height: 28),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
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
              OutlinedButton.icon(
                onPressed: () => _editStationDisplay(station),
                icon: const Icon(Icons.edit_location_alt_outlined, size: 18),
                label: const Text('Editar'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(0, 34),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  visualDensity: VisualDensity.compact,
                ),
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
        .where((detection) => !detection.isAmbientNoise)
        .map((detection) => detection.displaySpecies)
        .where((species) => species.trim().isNotEmpty)
        .toSet();
    final pendingReviews = detections
        .where((detection) => detection.needsBirdReview)
        .length;
    final latestMetric = metrics.isNotEmpty ? metrics.first : null;

    return AppPage(
      children: [
        _buildStationPanel(devices, stream),
        _buildBioacousticSummary(latestMetric),
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
              label: 'Aves pendientes',
              value: pendingReviews.toString(),
              detail: 'Aves escuchadas sin validar',
            ),
            AppMetricCard(
              icon: Icons.graphic_eq,
              label: 'Muestras acusticas',
              value: metrics.length.toString(),
              detail: latestMetric == null
                  ? 'Sin muestras registradas'
                  : 'Ultima ${_relativeTime(latestMetric.timestamp).toLowerCase()}',
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
