import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../models/review_status.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';
import 'detection_detail_screen.dart';

enum _DateFilter { today, sevenDays, all }

enum _ReviewFilter {
  all,
  pending,
  validated,
  corrected,
  noise,
  doubtful,
  discarded,
}

class DetectionsScreen extends StatefulWidget {
  final String baseUrl;

  const DetectionsScreen({super.key, required this.baseUrl});

  @override
  State<DetectionsScreen> createState() => _DetectionsScreenState();
}

class _DetectionsScreenState extends State<DetectionsScreen> {
  late final ApiService api;
  late Future<List<Detection>> _detectionsFuture;
  _DateFilter _dateFilter = _DateFilter.all;
  _ReviewFilter _reviewFilter = _ReviewFilter.all;
  String _speciesFilter = 'Todas';
  bool _highConfidenceOnly = false;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _detectionsFuture = api.getDetections();
  }

  Future<void> _refresh() async {
    setState(() {
      _detectionsFuture = api.getDetections();
    });

    await _detectionsFuture;
  }

  List<Detection> _filteredDetections(List<Detection> detections) {
    final now = DateTime.now();
    final todayStart = DateTime(now.year, now.month, now.day);
    final sevenDaysStart = todayStart.subtract(const Duration(days: 6));

    return detections.where((detection) {
      final parsed = DateTime.tryParse(detection.timestamp);

      if (_dateFilter == _DateFilter.today) {
        if (parsed == null || parsed.isBefore(todayStart)) return false;
      }

      if (_dateFilter == _DateFilter.sevenDays) {
        if (parsed == null || parsed.isBefore(sevenDaysStart)) return false;
      }

      if (_speciesFilter != 'Todas' &&
          detection.displaySpecies != _speciesFilter) {
        return false;
      }

      if (_highConfidenceOnly && confidencePercent(detection.confidence) < 70) {
        return false;
      }

      final reviewStatus = detection.reviewStatus;

      switch (_reviewFilter) {
        case _ReviewFilter.pending:
          if (!detection.needsBirdReview) return false;
          break;
        case _ReviewFilter.validated:
          if (reviewStatus != DetectionReviewStatus.validated) return false;
          break;
        case _ReviewFilter.corrected:
          if (reviewStatus != DetectionReviewStatus.corrected) return false;
          break;
        case _ReviewFilter.noise:
          if (!detection.isAmbientNoise) return false;
          break;
        case _ReviewFilter.doubtful:
          if (reviewStatus != DetectionReviewStatus.doubtful) return false;
          break;
        case _ReviewFilter.discarded:
          if (reviewStatus != DetectionReviewStatus.discarded) return false;
          break;
        case _ReviewFilter.all:
          break;
      }

      return true;
    }).toList();
  }

  List<String> _speciesOptions(List<Detection> detections) {
    final species =
        detections.map((detection) => detection.displaySpecies).toSet()
          ..removeWhere((value) => value.trim().isEmpty);

    return ['Todas', ...species.toList()..sort()];
  }

  Detection? _latestBirdDetection(List<Detection> detections) {
    for (final detection in detections) {
      if (!detection.isAmbientNoise) return detection;
    }

    return null;
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
      _detectionsFuture = api.getDetections();
    });
  }

  String _dateFilterLabel(_DateFilter value) {
    switch (value) {
      case _DateFilter.today:
        return 'Hoy';
      case _DateFilter.sevenDays:
        return '7 dias';
      case _DateFilter.all:
        return 'Todas';
    }
  }

  String _reviewFilterLabel(_ReviewFilter value) {
    switch (value) {
      case _ReviewFilter.all:
        return 'Todo';
      case _ReviewFilter.pending:
        return 'Pendiente';
      case _ReviewFilter.validated:
        return 'Validada';
      case _ReviewFilter.corrected:
        return 'Corregida';
      case _ReviewFilter.noise:
        return 'Ruido';
      case _ReviewFilter.doubtful:
        return 'Dudosa';
      case _ReviewFilter.discarded:
        return 'Descartada';
    }
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

  String _shortTime(String raw) {
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return formatTimestamp(raw);

    final hour = parsed.hour.toString().padLeft(2, '0');
    final minute = parsed.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  String _evidenceText(Detection detection) {
    final hasFile = detection.filename?.trim().isNotEmpty == true;
    final device = detection.deviceId == null
        ? 'Estacion sin asignar'
        : 'Estacion #${detection.deviceId}';

    if (!hasFile) return 'Evidencia pendiente - $device';
    return 'WAV + espectrograma - $device';
  }

  Widget _buildDetectionCard(
    Detection detection,
    DetectionReviewStatus reviewStatus,
  ) {
    final confidenceText = formatConfidence(detection.confidence);
    final confidenceState = confidenceLabel(detection.confidence);
    final isNoise = detection.isAmbientNoise;
    final leadingIcon = isNoise ? Icons.volume_off_outlined : Icons.pets;

    return AppDataPanel(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openDetail(detection),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: isNoise ? appWarmSoft : appGreenSoft,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: appPanelBorder),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(10),
                      child: Icon(
                        leadingIcon,
                        color: _reviewColor(context, reviewStatus),
                        size: 21,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          detection.displaySpecies,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${_shortTime(detection.timestamp)} - $confidenceText - ${reviewStatus.label}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  AppStatusPill(
                    text: confidenceState,
                    icon: Icons.verified_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                _evidenceText(detection),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (detection.reviewStatus == DetectionReviewStatus.corrected)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Original BirdNET: ${detection.species}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              if (isNoise)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Falso positivo - ${formatTimestamp(detection.timestamp)}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              if (detection.hasLearningSuggestion)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      AppStatusPill(
                        text:
                            'Sugerencia: ${detection.learnedSuggestion!.displaySpecies}',
                        icon: Icons.psychology_alt_outlined,
                        color: Theme.of(context).colorScheme.secondary,
                      ),
                      Text(
                        '${detection.learnedSuggestion!.supportCount} revisiones previas',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: AppSoundBars(
                      active: reviewStatus != DetectionReviewStatus.discarded,
                      height: 28,
                      color: _reviewColor(context, reviewStatus),
                    ),
                  ),
                  const SizedBox(width: 10),
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

  Widget _buildDetectionsPanel(List<Detection> detections) {
    if (detections.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay detecciones para los filtros actuales.'),
      );
    }

    return Column(
      children: [
        for (final detection in detections)
          _buildDetectionCard(detection, detection.reviewStatus),
      ],
    );
  }

  Widget _buildActivityPanel(
    List<Detection> detections,
    Detection? latestBird,
    int pendingBirdCount,
  ) {
    final title = pendingBirdCount == 0
        ? 'Sin aves pendientes'
        : pendingBirdCount == 1
        ? '1 ave por validar'
        : '$pendingBirdCount aves por validar';
    final pendingText = pendingBirdCount == 1
        ? '1 ave pendiente'
        : '$pendingBirdCount aves pendientes';

    return AppFieldHero(
      icon: Icons.eco_outlined,
      eyebrow: 'Aves escuchadas',
      title: title,
      subtitle: latestBird == null
          ? 'Aun no hay aves escuchadas para revisar'
          : 'Ultima ave: ${latestBird.displaySpecies} - ${formatTimestamp(latestBird.timestamp)}',
      status: AppStatusPill(
        text: pendingText,
        icon: Icons.rate_review_outlined,
        color: pendingBirdCount == 0
            ? Theme.of(context).colorScheme.primary
            : Theme.of(context).colorScheme.secondary,
      ),
      child: AppSoundBars(
        active: detections.any((detection) => !detection.isAmbientNoise),
        height: 38,
      ),
    );
  }

  Widget _buildFilters(List<String> speciesOptions) {
    return AppDataPanel(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<_DateFilter>(
            initialValue: _dateFilter,
            decoration: const InputDecoration(
              labelText: 'Fecha',
              prefixIcon: Icon(Icons.calendar_today_outlined),
            ),
            items: [
              for (final value in _DateFilter.values)
                DropdownMenuItem(
                  value: value,
                  child: Text(_dateFilterLabel(value)),
                ),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _dateFilter = value;
              });
            },
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<_ReviewFilter>(
            initialValue: _reviewFilter,
            decoration: const InputDecoration(
              labelText: 'Estado',
              prefixIcon: Icon(Icons.rate_review_outlined),
            ),
            items: [
              for (final value in _ReviewFilter.values)
                DropdownMenuItem(
                  value: value,
                  child: Text(_reviewFilterLabel(value)),
                ),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _reviewFilter = value;
              });
            },
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<bool>(
            initialValue: _highConfidenceOnly,
            decoration: const InputDecoration(
              labelText: 'Confianza',
              prefixIcon: Icon(Icons.verified_outlined),
            ),
            items: const [
              DropdownMenuItem(
                value: false,
                child: Text('Todas las confianzas'),
              ),
              DropdownMenuItem(
                value: true,
                child: Text('Solo confianza > 70%'),
              ),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _highConfidenceOnly = value;
              });
            },
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _speciesFilter,
            decoration: const InputDecoration(
              labelText: 'Especie',
              prefixIcon: Icon(Icons.eco),
            ),
            items: [
              for (final species in speciesOptions)
                DropdownMenuItem(value: species, child: Text(species)),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _speciesFilter = value;
              });
            },
          ),
        ],
      ),
    );
  }

  Widget _buildContent(List<Detection> detections) {
    final filtered = _filteredDetections(detections);
    final latestBird = _latestBirdDetection(detections);
    final speciesOptions = _speciesOptions(detections);
    final pendingBirdCount = detections
        .where((detection) => detection.needsBirdReview)
        .length;

    if (!speciesOptions.contains(_speciesFilter)) {
      _speciesFilter = 'Todas';
    }

    return AppPage(
      children: [
        _buildActivityPanel(detections, latestBird, pendingBirdCount),
        const AppSectionTitle(
          title: 'Filtros',
          subtitle: 'Afina la revision por fecha, confianza o estado.',
        ),
        _buildFilters(speciesOptions),
        const AppSectionTitle(title: 'Registros'),
        _buildDetectionsPanel(filtered),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<Detection>>(
        future: _detectionsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const AppPage(
              children: [
                SizedBox(height: 220),
                Center(child: CircularProgressIndicator()),
              ],
            );
          }

          if (snapshot.hasError) {
            return const AppPage(
              children: [
                AppDataPanel(
                  padding: EdgeInsets.all(16),
                  child: Text('Error cargando detecciones'),
                ),
              ],
            );
          }

          return _buildContent(snapshot.data ?? []);
        },
      ),
    );
  }
}