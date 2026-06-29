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
          if (reviewStatus != DetectionReviewStatus.unreviewed) return false;
          break;
        case _ReviewFilter.validated:
          if (reviewStatus != DetectionReviewStatus.validated) return false;
          break;
        case _ReviewFilter.corrected:
          if (reviewStatus != DetectionReviewStatus.corrected) return false;
          break;
        case _ReviewFilter.noise:
          if (reviewStatus != DetectionReviewStatus.noise) return false;
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

  Widget _buildDateChip(String label, _DateFilter value) {
    return ChoiceChip(
      label: Text(label),
      selected: _dateFilter == value,
      onSelected: (_) {
        setState(() {
          _dateFilter = value;
        });
      },
    );
  }

  Widget _buildReviewChip(String label, _ReviewFilter value) {
    return ChoiceChip(
      label: Text(label),
      selected: _reviewFilter == value,
      onSelected: (_) {
        setState(() {
          _reviewFilter = value;
        });
      },
    );
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

  Widget _buildDetectionRow(
    Detection detection,
    DetectionReviewStatus reviewStatus,
  ) {
    final confidenceText = formatConfidence(detection.confidence);
    final confidenceState = confidenceLabel(detection.confidence);

    return InkWell(
      onTap: () => _openDetail(detection),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: appPanelMuted,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: appPanelBorder),
              ),
              child: const Padding(
                padding: EdgeInsets.all(10),
                child: Icon(Icons.pets, size: 20),
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
                  if (detection.reviewStatus == DetectionReviewStatus.corrected)
                    Text(
                      'Original BirdNET: ${detection.species}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  const SizedBox(height: 4),
                  Text(
                    formatTimestamp(detection.timestamp),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  Text(
                    '$confidenceState - ${formatFilename(detection.filename)}',
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
                AppStatusPill(text: confidenceText, icon: Icons.verified),
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
    );
  }

  Widget _buildDetectionsPanel(List<Detection> detections) {
    if (detections.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay detecciones para los filtros actuales.'),
      );
    }

    return AppDataPanel(
      child: Column(
        children: [
          for (var i = 0; i < detections.length; i++) ...[
            if (i > 0) const Divider(height: 1),
            _buildDetectionRow(detections[i], detections[i].reviewStatus),
          ],
        ],
      ),
    );
  }

  Widget _buildContent(List<Detection> detections) {
    final filtered = _filteredDetections(detections);
    final latest = detections.isNotEmpty ? detections.first : null;
    final speciesOptions = _speciesOptions(detections);
    final pendingCount = detections
        .where(
          (detection) =>
              detection.reviewStatus == DetectionReviewStatus.unreviewed,
        )
        .length;

    if (!speciesOptions.contains(_speciesFilter)) {
      _speciesFilter = 'Todas';
    }

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.list_alt,
          title: 'Historial de detecciones',
          subtitle: 'Registros filtrables y revisables con evidencia acustica.',
          trailing: AppStatusPill(
            text: filtered.length.toString(),
            icon: Icons.pets,
          ),
        ),
        AppMetricGrid(
          children: [
            AppMetricCard(
              icon: Icons.timeline,
              label: 'Detecciones registradas',
              value: detections.length.toString(),
              detail: 'Limite actual de la API',
            ),
            AppMetricCard(
              icon: Icons.eco,
              label: 'Ultima deteccion',
              value: latest?.displaySpecies ?? 'Sin datos',
              detail: latest == null
                  ? 'Sin actividad'
                  : formatTimestamp(latest.timestamp),
            ),
            AppMetricCard(
              icon: Icons.rate_review_outlined,
              label: 'Sin revisar',
              value: pendingCount.toString(),
              detail: 'Trabajo pendiente',
            ),
          ],
        ),
        const AppSectionTitle(title: 'Filtros'),
        AppDataPanel(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _buildDateChip('Hoy', _DateFilter.today),
                  _buildDateChip('7 dias', _DateFilter.sevenDays),
                  _buildDateChip('Todas', _DateFilter.all),
                  FilterChip(
                    label: const Text('Confianza > 70%'),
                    selected: _highConfidenceOnly,
                    onSelected: (selected) {
                      setState(() {
                        _highConfidenceOnly = selected;
                      });
                    },
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _buildReviewChip('Todo', _ReviewFilter.all),
                  _buildReviewChip('Sin revisar', _ReviewFilter.pending),
                  _buildReviewChip('Validadas', _ReviewFilter.validated),
                  _buildReviewChip('Corregidas', _ReviewFilter.corrected),
                  _buildReviewChip('Ruido', _ReviewFilter.noise),
                  _buildReviewChip('Dudosas', _ReviewFilter.doubtful),
                  _buildReviewChip('Descartadas', _ReviewFilter.discarded),
                ],
              ),
              const SizedBox(height: 12),
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
        ),
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
