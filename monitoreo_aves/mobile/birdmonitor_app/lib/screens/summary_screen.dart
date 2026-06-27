import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';

class SummaryScreen extends StatefulWidget {
  final String baseUrl;

  const SummaryScreen({super.key, required this.baseUrl});

  @override
  State<SummaryScreen> createState() => _SummaryScreenState();
}

class _SummaryScreenState extends State<SummaryScreen> {
  late final ApiService api;

  late Future<List<Detection>> _detectionsFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  void _loadData() {
    _detectionsFuture = api.getDetections();
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await _detectionsFuture;
  }

  String _formatConfidence(double confidence) {
    final value = confidence <= 1 ? confidence * 100 : confidence;
    return '${value.toStringAsFixed(1)}%';
  }

  Widget _buildLatestDetectionPanel(Detection? latest) {
    if (latest == null) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('Todavia no hay detecciones registradas.'),
      );
    }

    return AppDataPanel(
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
                if (latest.filename != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    formatFilename(latest.filename),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 12),
          AppStatusPill(
            text: _formatConfidence(latest.confidence),
            icon: Icons.verified,
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryContent(List<Detection> detections) {
    final latest = detections.isNotEmpty ? detections.first : null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.dashboard,
          title: 'Centro de control',
          subtitle: 'Vista rapida del estado actual de BirdMonitor.',
        ),
        AppDataPanel(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              const Icon(Icons.dns_outlined),
              const SizedBox(width: 10),
              Expanded(
                child: SelectableText(
                  widget.baseUrl,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        const AppSectionTitle(
          title: 'Indicadores',
          subtitle: 'Lectura rapida de la actividad detectada.',
        ),
        AppMetricGrid(
          children: [
            AppMetricCard(
              icon: Icons.pets,
              label: 'Detecciones',
              value: detections.length.toString(),
              detail: 'Registros cargados',
            ),
            AppMetricCard(
              icon: Icons.eco,
              label: 'Ultima especie',
              value: latest?.species ?? 'Sin datos',
              detail: latest == null
                  ? 'Sin actividad reciente'
                  : 'Actividad reciente',
            ),
            AppMetricCard(
              icon: Icons.verified,
              label: 'Confianza',
              value: latest == null
                  ? 'Sin datos'
                  : _formatConfidence(latest.confidence),
              detail: 'Ultima deteccion',
            ),
          ],
        ),
        const AppSectionTitle(title: 'Ultima deteccion'),
        _buildLatestDetectionPanel(latest),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<dynamic>>(
        future: Future.wait([_detectionsFuture]),
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
            return AppPage(
              children: [
                AppDataPanel(
                  padding: const EdgeInsets.all(16),
                  child: Text('Error cargando resumen: ${snapshot.error}'),
                ),
              ],
            );
          }

          final detections = snapshot.data![0] as List<Detection>;

          return _buildSummaryContent(detections);
        },
      ),
    );
  }
}