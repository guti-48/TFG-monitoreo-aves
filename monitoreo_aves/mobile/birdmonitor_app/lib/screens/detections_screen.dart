import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';

class DetectionsScreen extends StatefulWidget {
  final String baseUrl;

  const DetectionsScreen({super.key, required this.baseUrl});

  @override
  State<DetectionsScreen> createState() => _DetectionsScreenState();
}

class _DetectionsScreenState extends State<DetectionsScreen> {
  late final ApiService api;
  late Future<List<Detection>> _detectionsFuture;

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

  String _formatConfidence(double confidence) {
    final value = confidence <= 1 ? confidence * 100 : confidence;
    return '${value.toStringAsFixed(1)}%';
  }

  Widget _buildDetectionRow(Detection detection) {
    return Padding(
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
                  detection.species,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  formatTimestamp(detection.timestamp),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Text(
                  formatFilename(detection.filename),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          AppStatusPill(
            text: _formatConfidence(detection.confidence),
            icon: Icons.verified,
          ),
        ],
      ),
    );
  }

  Widget _buildDetectionsPanel(List<Detection> detections) {
    if (detections.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('Todavia no hay detecciones registradas.'),
      );
    }

    return AppDataPanel(
      child: Column(
        children: [
          for (var i = 0; i < detections.length; i++) ...[
            if (i > 0) const Divider(height: 1),
            _buildDetectionRow(detections[i]),
          ],
        ],
      ),
    );
  }

  Widget _buildContent(List<Detection> detections) {
    final latest = detections.isNotEmpty ? detections.first : null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.list_alt,
          title: 'Historial de detecciones',
          subtitle: 'Ultimas identificaciones recibidas desde el nodo.',
          trailing: AppStatusPill(
            text: detections.length.toString(),
            icon: Icons.pets,
          ),
        ),
        AppMetricGrid(
          children: [
            AppMetricCard(
              icon: Icons.timeline,
              label: 'Total cargado',
              value: detections.length.toString(),
              detail: 'Limite actual de la API',
            ),
            AppMetricCard(
              icon: Icons.eco,
              label: 'Ultima especie',
              value: latest?.species ?? 'Sin datos',
              detail: latest == null
                  ? 'Sin actividad'
                  : formatTimestamp(latest.timestamp),
            ),
          ],
        ),
        const AppSectionTitle(title: 'Registros'),
        _buildDetectionsPanel(detections),
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
